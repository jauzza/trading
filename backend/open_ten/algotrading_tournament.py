from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .analytics import adjusted_p_values, reality_check, stationary_bootstrap_mean
from .engine import ExecutionConfig, INSTRUMENTS, fees_for, round_to_tick
from .phase5 import ProtectedMarketDataGuard
from .research import MNQ_FP, NQ_FP, _condition_dates

NY = ZoneInfo("America/New_York")
PERIODS = {
    "discovery": set(range(2018, 2022)),
    "validation": {2022, 2023},
    "historical_evaluation": {2024, 2025},
}
DAILY_IDS = [
    "ALG01_REVERSAL", "ALG01_DOWN_REVERSAL", "ALG01_MOMENTUM",
    "ALG02_IBS_RANGE", "ALG04_RSI2_LONG", "ALG04_RSI2_LONG_SHORT",
    "ALG04_RSI2_ONE_DAY", "ALG05_BB_BASIC_MID", "ALG05_BB_TREND_MID",
    "ALG05_BB_TREND_UPPER", "ALG09_BUY_DIP_20",
]
HOURLY_IDS = ["ALG03_ADX_DI_INITIAL", "ALG03_ADX_TUNED", "ALG03_ADX_TUNED_EMA200"]
ALL_IDS = DAILY_IDS + HOURLY_IDS
NO_STOP_IDS = set(DAILY_IDS)


@dataclass
class Position:
    candidate_id: str
    side: str
    signal_ts: pd.Timestamp
    entry_ts: pd.Timestamp
    entry_ref: float
    entry_instrument_id: int
    mae_points: float = 0.0
    mfe_points: float = 0.0


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verify_lock(project_root: Path) -> dict[str, Any]:
    lock = json.loads((project_root / "research/algotrading_tournament.lock.json").read_text())
    specification = project_root / lock["specification_file"]
    if _sha256(specification) != lock["specification_sha256"]:
        raise RuntimeError("algotrading tournament specification hash mismatch")
    return json.loads(specification.read_text())


def _dataset(manifest: dict, symbol: str) -> dict:
    fingerprint = NQ_FP if symbol == "NQ" else MNQ_FP
    dataset = manifest["datasets"].get(fingerprint)
    if not dataset or dataset["request"]["symbol"] != f"{symbol}.v.0":
        raise RuntimeError(f"preserved {symbol} dataset not found")
    return dataset


def _load_market(root: Path, symbol: str) -> tuple[pd.DataFrame, list[str]]:
    guard = ProtectedMarketDataGuard(root)
    manifest = guard.manifest()
    parts = []
    opened = []
    for partition in _dataset(manifest, symbol)["partitions"]:
        year = int(partition["year"])
        if year >= 2026:
            raise RuntimeError("protected partition rejected before market read")
        if year < 2018 or (symbol == "MNQ" and year < 2019):
            continue
        path = guard.assert_allowed_path(partition["path"])
        frame = pd.read_parquet(
            path,
            columns=["instrument_id", "open", "high", "low", "close", "volume", "ts_event"],
        ).reset_index()
        frame["ts_ny"] = pd.to_datetime(frame["ts_event"], utc=True).dt.tz_convert("America/New_York")
        parts.append(frame.drop(columns=["ts_event"]))
        opened.append(str(path))
    if not parts:
        raise RuntimeError(f"no allowed {symbol} partitions")
    frame = pd.concat(parts, ignore_index=True).sort_values("ts_ny").drop_duplicates("ts_ny", keep="last")
    if frame.ts_ny.max().date().year >= 2026:
        raise RuntimeError("protected market observation loaded")
    return frame.reset_index(drop=True), opened


def _rth(frame: pd.DataFrame, degraded: set) -> pd.DataFrame:
    local_time = frame.ts_ny.dt.time
    result = frame[(local_time >= time(9, 30)) & (local_time <= time(15, 59))].copy()
    result["session_date"] = result.ts_ny.dt.date
    result = result[~result.session_date.isin(degraded)]
    result = result[result.ts_ny.dt.weekday < 5]
    return result.reset_index(drop=True)


def _daily(rth: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for session_date, group in rth.groupby("session_date", sort=True):
        group = group.sort_values("ts_ny")
        times = set(group.ts_ny.dt.time)
        if time(9, 30) not in times or len(group) < 180:
            continue
        if group.ts_ny.duplicated().any() or group.instrument_id.nunique() != 1:
            continue
        if ((group.high < group[["open", "close"]].max(axis=1)) | (group.low > group[["open", "close"]].min(axis=1))).any():
            continue
        rows.append({
            "session_date": session_date,
            "open_ts": group.iloc[0].ts_ny,
            "close_ts": group.iloc[-1].ts_ny,
            "open": float(group.iloc[0].open),
            "high": float(group.high.max()),
            "low": float(group.low.min()),
            "close": float(group.iloc[-1].close),
            "volume": int(group.volume.sum()),
            "instrument_id": int(group.iloc[0].instrument_id),
            "minutes": int(len(group)),
        })
    daily = pd.DataFrame(rows)
    if daily.empty:
        return daily
    daily["roll_after"] = daily.instrument_id.ne(daily.instrument_id.shift(-1)) & daily.instrument_id.shift(-1).notna()
    close = daily.close
    daily["sma5"] = close.rolling(5, min_periods=5).mean()
    daily["sma200"] = close.rolling(200, min_periods=200).mean()
    daily["ibs"] = (close - daily.low) / (daily.high - daily.low).replace(0, np.nan)
    daily["highest10"] = daily.high.rolling(10, min_periods=10).max()
    daily["avg_range25"] = daily.high.rolling(25, min_periods=25).mean() - daily.low.rolling(25, min_periods=25).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=.5, adjust=False, min_periods=2).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=.5, adjust=False, min_periods=2).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_fallback = pd.Series(np.where(gain > 0, 100.0, 0.0), index=daily.index)
    daily["rsi2"] = (100 - 100 / (1 + rs)).fillna(rsi_fallback)
    daily["bb_mid"] = close.rolling(20, min_periods=20).mean()
    sd = close.rolling(20, min_periods=20).std(ddof=0)
    daily["bb_lower"] = daily.bb_mid - 2 * sd
    daily["bb_upper"] = daily.bb_mid + 2 * sd
    return daily.reset_index(drop=True)


def _round_trip_components(symbol: str, config: ExecutionConfig, contracts: int = 1) -> dict[str, float]:
    spec = INSTRUMENTS[symbol]
    schedule = fees_for(symbol, config)
    multiplier = 2 * contracts * config.fee_multiplier
    fees = schedule.per_side * multiplier
    spread = config.spread_ticks_round_trip * spec.tick_size * spec.point_value * contracts
    slippage = 2 * config.slippage_ticks_per_side * spec.tick_size * spec.point_value * contracts
    return {"fees": fees, "spread": spread, "slippage": slippage, "total": fees + spread + slippage}


def _trade_record(
    candidate_id: str,
    symbol: str,
    side: str,
    signal_ts: pd.Timestamp,
    entry_ts: pd.Timestamp,
    exit_ts: pd.Timestamp,
    entry_ref: float,
    exit_ref: float,
    outcome: str,
    instrument_id: int,
    mae_points: float = 0.0,
    mfe_points: float = 0.0,
    config: ExecutionConfig | None = None,
    valid_causal: bool = True,
) -> dict[str, Any]:
    config = config or ExecutionConfig(fixed_contracts=1, max_contracts=1)
    spec = INSTRUMENTS[symbol]
    direction = 1 if side == "long" else -1
    entry_ref = round_to_tick(entry_ref, spec.tick_size)
    exit_ref = round_to_tick(exit_ref, spec.tick_size)
    entry = round_to_tick(entry_ref + direction * config.slippage_ticks_per_side * spec.tick_size, spec.tick_size)
    exit_price = round_to_tick(exit_ref - direction * config.slippage_ticks_per_side * spec.tick_size, spec.tick_size)
    gross = direction * (exit_ref - entry_ref) * spec.point_value
    cost = _round_trip_components(symbol, config)
    net = gross - cost["total"]
    return {
        "candidate_id": candidate_id,
        "symbol": symbol,
        "side": side,
        "signal_ts": signal_ts.isoformat(),
        "entry_ts": entry_ts.isoformat(),
        "exit_ts": exit_ts.isoformat(),
        "entry_reference": entry_ref,
        "entry_fill": entry,
        "exit_reference": exit_ref,
        "exit_fill": exit_price,
        "instrument_id": instrument_id,
        "contracts": 1,
        "gross_pnl": round(gross, 2),
        "fees": round(cost["fees"], 2),
        "spread_cost": round(cost["spread"], 2),
        "slippage_cost": round(cost["slippage"], 2),
        "total_costs": round(cost["total"], 2),
        "net_pnl": round(net, 2),
        "outcome": outcome,
        "mae_points": round(max(0.0, mae_points), 2),
        "mfe_points": round(max(0.0, mfe_points), 2),
        "duration_hours": round(max(0.0, (exit_ts - entry_ts).total_seconds() / 3600), 2),
        "valid_causal": valid_causal,
    }


def _entry_signal(candidate_id: str, row: Any, previous: Any | None) -> str | None:
    if candidate_id == "ALG02_IBS_RANGE":
        threshold = row.highest10 - 2.5 * row.avg_range25
        return "long" if pd.notna(threshold) and row.close < threshold and row.ibs < .3 else None
    if candidate_id in {"ALG04_RSI2_LONG", "ALG04_RSI2_ONE_DAY"}:
        return "long" if pd.notna(row.sma200) and row.close > row.sma200 and row.rsi2 < 5 else None
    if candidate_id == "ALG04_RSI2_LONG_SHORT":
        if pd.isna(row.sma200):
            return None
        if row.close > row.sma200 and row.rsi2 < 5:
            return "long"
        if row.close < row.sma200 and row.rsi2 > 95:
            return "short"
        return None
    if candidate_id.startswith("ALG05_"):
        if pd.isna(row.bb_lower) or row.close >= row.bb_lower:
            return None
        if candidate_id != "ALG05_BB_BASIC_MID" and (pd.isna(row.sma200) or row.close <= row.sma200):
            return None
        return "long"
    if candidate_id == "ALG09_BUY_DIP_20":
        return "long" if pd.notna(row.ibs) and row.ibs < .2 else None
    return None


def _exit_signal(candidate_id: str, side: str, row: Any, previous: Any | None) -> bool:
    if previous is None:
        return False
    if candidate_id == "ALG02_IBS_RANGE":
        return row.close > previous.high
    if candidate_id in {"ALG04_RSI2_LONG", "ALG04_RSI2_LONG_SHORT"}:
        return pd.notna(row.sma5) and (row.close > row.sma5 if side == "long" else row.close < row.sma5)
    if candidate_id in {"ALG05_BB_BASIC_MID", "ALG05_BB_TREND_MID"}:
        return pd.notna(row.bb_mid) and row.close > row.bb_mid
    if candidate_id == "ALG05_BB_TREND_UPPER":
        return pd.notna(row.bb_upper) and row.close > row.bb_upper
    return False


def _close_position(position: Position, row: Any, exit_price: float, exit_ts: pd.Timestamp, outcome: str, symbol: str) -> dict:
    return _trade_record(
        position.candidate_id, symbol, position.side, position.signal_ts, position.entry_ts,
        exit_ts, position.entry_ref, exit_price, outcome, position.entry_instrument_id,
        position.mae_points, position.mfe_points,
    )


def simulate_daily(daily: pd.DataFrame, candidate_id: str, symbol: str) -> tuple[list[dict], dict]:
    records: list[dict] = []
    diagnostics = {"signals": 0, "roll_skips": 0, "roll_exits": 0, "overlap_signals": 0}
    if daily.empty:
        return records, diagnostics
    rows = list(daily.itertuples(index=False))

    if candidate_id.startswith("ALG01_"):
        for index in range(1, len(rows) - 1):
            previous, signal, entry_day = rows[index - 1], rows[index], rows[index + 1]
            reversal = signal.high < previous.high and signal.low < previous.low
            if candidate_id == "ALG01_DOWN_REVERSAL":
                reversal = reversal and signal.close < signal.open
            momentum = signal.high > previous.high and signal.low > previous.low
            setup = momentum if candidate_id == "ALG01_MOMENTUM" else reversal
            if not setup:
                continue
            diagnostics["signals"] += 1
            if signal.instrument_id != entry_day.instrument_id:
                diagnostics["roll_skips"] += 1
                continue
            trigger = signal.high
            if entry_day.high < trigger:
                continue
            entry_ref = max(entry_day.open, trigger)
            mae = max(0.0, entry_ref - entry_day.low)
            mfe = max(0.0, entry_day.high - entry_ref)
            records.append(_trade_record(
                candidate_id, symbol, "long", signal.close_ts, entry_day.open_ts, entry_day.close_ts,
                entry_ref, entry_day.close, "session_close", entry_day.instrument_id, mae, mfe,
            ))
        return records, diagnostics

    position: Position | None = None
    pending_entry: dict | None = None
    pending_exit = False
    for index, row in enumerate(rows):
        previous = rows[index - 1] if index else None
        if position and pending_exit:
            records.append(_close_position(position, row, row.open, row.open_ts, "signal_exit", symbol))
            position = None
            pending_exit = False

        if position is None and pending_entry is not None:
            if pending_entry["instrument_id"] != row.instrument_id:
                diagnostics["roll_skips"] += 1
            else:
                position = Position(
                    candidate_id, pending_entry["side"], pending_entry["signal_ts"], row.open_ts,
                    float(row.open), int(row.instrument_id),
                )
            pending_entry = None

        if position is not None:
            if position.side == "long":
                position.mae_points = max(position.mae_points, position.entry_ref - row.low)
                position.mfe_points = max(position.mfe_points, row.high - position.entry_ref)
            else:
                position.mae_points = max(position.mae_points, row.high - position.entry_ref)
                position.mfe_points = max(position.mfe_points, position.entry_ref - row.low)

            if candidate_id in {"ALG04_RSI2_ONE_DAY", "ALG09_BUY_DIP_20"}:
                records.append(_close_position(position, row, row.close, row.close_ts, "scheduled_close", symbol))
                position = None
            elif row.roll_after:
                records.append(_close_position(position, row, row.close, row.close_ts, "roll_exit", symbol))
                diagnostics["roll_exits"] += 1
                position = None
                pending_exit = False
            elif _exit_signal(candidate_id, position.side, row, previous):
                pending_exit = True

        side = _entry_signal(candidate_id, row, previous)
        if side:
            diagnostics["signals"] += 1
            if position is None and not pending_exit and pending_entry is None:
                pending_entry = {"side": side, "signal_ts": row.close_ts, "instrument_id": row.instrument_id}
            else:
                diagnostics["overlap_signals"] += 1

    if position is not None:
        row = rows[-1]
        records.append(_close_position(position, row, row.close, row.close_ts, "end_of_data", symbol))
    return records, diagnostics


def noncausal_buy_dip_diagnostic(daily: pd.DataFrame, symbol: str) -> list[dict]:
    records = []
    rows = list(daily.itertuples(index=False))
    for index, signal in enumerate(rows[:-1]):
        if pd.isna(signal.ibs) or signal.ibs >= .2:
            continue
        exit_day = rows[index + 1]
        if signal.instrument_id != exit_day.instrument_id:
            continue
        records.append(_trade_record(
            "ALG09_BUY_DIP_20_LITERAL_NONCAUSAL", symbol, "long", signal.close_ts, signal.close_ts,
            exit_day.close_ts, signal.close, exit_day.close, "next_close", signal.instrument_id,
            valid_causal=False,
        ))
    return records


def _hourly(rth: pd.DataFrame) -> pd.DataFrame:
    work = rth.copy()
    minute = work.ts_ny.dt.hour * 60 + work.ts_ny.dt.minute - (9 * 60 + 30)
    work["bucket"] = (minute // 60).astype(int)
    work = work[(work.bucket >= 0) & (work.bucket <= 5)]
    rows = []
    for (session_date, bucket), group in work.groupby(["session_date", "bucket"], sort=True):
        group = group.sort_values("ts_ny")
        if len(group) != 60 or group.instrument_id.nunique() != 1:
            continue
        rows.append({
            "session_date": session_date, "bucket": int(bucket), "ts": group.iloc[0].ts_ny,
            "last_ts": group.iloc[-1].ts_ny, "open": float(group.iloc[0].open),
            "high": float(group.high.max()), "low": float(group.low.min()),
            "close": float(group.iloc[-1].close), "volume": int(group.volume.sum()),
            "instrument_id": int(group.iloc[0].instrument_id),
        })
    hourly = pd.DataFrame(rows)
    if hourly.empty:
        return hourly
    up = hourly.high.diff()
    down = -hourly.low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=hourly.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=hourly.index)
    previous_close = hourly.close.shift(1)
    true_range = pd.concat([
        hourly.high - hourly.low,
        (hourly.high - previous_close).abs(),
        (hourly.low - previous_close).abs(),
    ], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    hourly["atr14"] = atr
    hourly["plus_di"] = plus_di
    hourly["minus_di"] = minus_di
    hourly["adx14"] = dx.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    hourly["ema200"] = hourly.close.ewm(span=200, adjust=False, min_periods=200).mean()
    return hourly.reset_index(drop=True)


def _hourly_signals(hourly: pd.DataFrame, candidate_id: str) -> list[dict]:
    if hourly.empty:
        return []
    valid = hourly.adx14.notna() & hourly.atr14.notna()
    if candidate_id == "ALG03_ADX_DI_INITIAL":
        condition = valid & (hourly.adx14 > 25) & (hourly.plus_di > hourly.minus_di) & (hourly.plus_di.shift(1) <= hourly.minus_di.shift(1))
        stop_atr, target_r = 1.0, 2.0
    else:
        condition = valid & (hourly.adx14 > 25) & (hourly.adx14.shift(1) <= 25)
        if candidate_id == "ALG03_ADX_TUNED_EMA200":
            condition &= hourly.ema200.notna() & (hourly.close > hourly.ema200)
        stop_atr, target_r = 1.5, 3.5
    output = []
    for index in np.flatnonzero(condition.to_numpy()):
        row = hourly.iloc[index]
        output.append({
            "candidate_id": candidate_id, "signal_ts": row.last_ts, "stop_points": float(row.atr14 * stop_atr),
            "target_r": target_r, "instrument_id": int(row.instrument_id),
        })
    return output


def simulate_hourly(rth: pd.DataFrame, hourly: pd.DataFrame, candidate_id: str, symbol: str) -> tuple[list[dict], dict]:
    records = []
    diagnostics = {"signals": 0, "overlap_signals": 0, "roll_exits": 0, "end_of_data_exits": 0}
    signals = _hourly_signals(hourly, candidate_id)
    diagnostics["signals"] = len(signals)
    timestamps = rth.ts_ny.array.asi8
    opens = rth.open.to_numpy(dtype=float)
    highs = rth.high.to_numpy(dtype=float)
    lows = rth.low.to_numpy(dtype=float)
    closes = rth.close.to_numpy(dtype=float)
    instruments = rth.instrument_id.to_numpy(dtype=np.int64)
    last_exit: pd.Timestamp | None = None
    for signal in signals:
        signal_ts = pd.Timestamp(signal["signal_ts"])
        if last_exit is not None and signal_ts <= last_exit:
            diagnostics["overlap_signals"] += 1
            continue
        entry_index = int(np.searchsorted(timestamps, signal_ts.value, side="right"))
        if entry_index >= len(rth):
            continue
        if int(instruments[entry_index]) != signal["instrument_id"]:
            continue
        entry_ref = round_to_tick(float(opens[entry_index]))
        stop = round_to_tick(entry_ref - signal["stop_points"], mode="down")
        risk = entry_ref - stop
        if risk < .25:
            continue
        target = round_to_tick(entry_ref + risk * signal["target_r"])
        exit_ref = float(closes[-1])
        exit_ts = pd.Timestamp(timestamps[-1], tz="UTC").tz_convert(NY)
        outcome = "end_of_data"
        mae = mfe = 0.0
        instrument_id = int(instruments[entry_index])
        for offset in range(entry_index, len(rth)):
            if int(instruments[offset]) != instrument_id:
                exit_ref = float(closes[offset - 1])
                exit_ts = pd.Timestamp(timestamps[offset - 1], tz="UTC").tz_convert(NY)
                outcome = "roll_exit"
                diagnostics["roll_exits"] += 1
                break
            mae = max(mae, entry_ref - float(lows[offset]))
            mfe = max(mfe, float(highs[offset]) - entry_ref)
            stop_hit = float(lows[offset]) <= stop
            target_hit = float(highs[offset]) >= target
            if stop_hit:
                exit_ref = min(float(opens[offset]), stop)
                exit_ts = pd.Timestamp(timestamps[offset], tz="UTC").tz_convert(NY)
                outcome = "ambiguous_stop" if target_hit else "stop"
                break
            if target_hit:
                exit_ref = target
                exit_ts = pd.Timestamp(timestamps[offset], tz="UTC").tz_convert(NY)
                outcome = "target"
                break
        if outcome == "end_of_data":
            diagnostics["end_of_data_exits"] += 1
        records.append(_trade_record(
            candidate_id, symbol, "long", signal_ts, pd.Timestamp(timestamps[entry_index], tz="UTC").tz_convert(NY), exit_ts,
            entry_ref, exit_ref, outcome, instrument_id, mae, mfe,
        ))
        last_exit = exit_ts
    return records, diagnostics


def _max_drawdown(net: list[float], starting: float = 100_000) -> tuple[float, float]:
    equity = starting + np.cumsum(np.asarray(net, dtype=float))
    if not len(equity):
        return 0.0, 0.0
    peaks = np.maximum.accumulate(np.r_[starting, equity])[:-1]
    dollars = equity - peaks
    pct = np.divide(dollars, peaks, out=np.zeros_like(dollars), where=peaks != 0)
    return round(float(dollars.min()), 2), round(float(pct.min()), 6)


def _mark_to_market_drawdown(records: list[dict], daily: pd.DataFrame | None, symbol: str | None, starting: float) -> tuple[float, float]:
    if daily is None or symbol is None or daily.empty or not records:
        return _max_drawdown([float(row["net_pnl"]) for row in records], starting)
    prepared = []
    for row in records:
        prepared.append({
            **row,
            "entry_time": pd.Timestamp(row["entry_ts"]),
            "exit_time": pd.Timestamp(row["exit_ts"]),
        })
    equity = []
    for day in daily.itertuples(index=False):
        close_ts = pd.Timestamp(day.close_ts)
        realized = sum(float(row["net_pnl"]) for row in prepared if row["exit_time"] <= close_ts)
        unrealized = 0.0
        for row in prepared:
            if row["entry_time"] <= close_ts < row["exit_time"]:
                direction = 1 if row["side"] == "long" else -1
                unrealized += direction * (float(day.close) - float(row["entry_reference"])) * INSTRUMENTS[symbol].point_value
                unrealized -= float(row["total_costs"])
        equity.append(starting + realized + unrealized)
    if not equity:
        return 0.0, 0.0
    values = np.asarray(equity, dtype=float)
    peaks = np.maximum.accumulate(np.r_[starting, values])[:-1]
    dollars = values - peaks
    pct = np.divide(dollars, peaks, out=np.zeros_like(dollars), where=peaks != 0)
    daily_dollars, daily_pct = float(dollars.min()), float(pct.min())

    running = peak = starting
    mae_dollars = mae_pct = 0.0
    point_value = INSTRUMENTS[symbol].point_value
    for row in sorted(prepared, key=lambda value: value["entry_time"]):
        stressed = running - float(row["mae_points"]) * point_value - float(row["total_costs"])
        mae_dollars = min(mae_dollars, stressed - peak)
        mae_pct = min(mae_pct, stressed / peak - 1 if peak else 0.0)
        running += float(row["net_pnl"])
        peak = max(peak, running)
    return round(min(daily_dollars, mae_dollars), 2), round(min(daily_pct, mae_pct), 6)


def summarize(
    records: list[dict],
    starting: float = 100_000,
    daily: pd.DataFrame | None = None,
    symbol: str | None = None,
) -> dict[str, Any]:
    records = sorted(records, key=lambda row: (row["entry_ts"], row["exit_ts"]))
    net = [float(row["net_pnl"]) for row in records]
    wins = [value for value in net if value > 0]
    losses = [value for value in net if value < 0]
    gross_profit = sum(wins)
    closed_dd_dollars, closed_dd_pct = _max_drawdown(net, starting)
    dd_dollars, dd_pct = _mark_to_market_drawdown(records, daily, symbol, starting)
    by_year: dict[str, float] = {}
    for row in records:
        year = str(pd.Timestamp(row["entry_ts"]).year)
        by_year[year] = by_year.get(year, 0.0) + float(row["net_pnl"])
    sorted_wins = sorted(wins, reverse=True)
    remove_count = max(1, int(np.ceil(len(records) * .01))) if records else 0
    best_removed = sorted(records, key=lambda row: float(row["net_pnl"]), reverse=True)[remove_count:]
    total_costs = sum(float(row["total_costs"]) for row in records)
    gross = sum(float(row["gross_pnl"]) for row in records)
    return {
        "trades": len(records),
        "net_profit": round(sum(net), 2),
        "gross_profit_before_costs": round(gross, 2),
        "total_costs": round(total_costs, 2),
        "return_on_100k": round(sum(net) / starting, 6),
        "win_rate": round(len(wins) / len(records), 6) if records else 0.0,
        "profit_factor": round(gross_profit / abs(sum(losses)), 4) if losses else None,
        "expectancy": round(float(np.mean(net)), 2) if net else 0.0,
        "max_drawdown_dollars": dd_dollars,
        "max_drawdown": dd_pct,
        "closed_trade_max_drawdown_dollars": closed_dd_dollars,
        "closed_trade_max_drawdown": closed_dd_pct,
        "drawdown_method": "worst of daily mark-to-market and intratrade MAE proxy" if daily is not None and symbol else "closed trades only",
        "positive_years": sum(value > 0 for value in by_year.values()),
        "years_observed": len(by_year),
        "by_year": {key: round(value, 2) for key, value in sorted(by_year.items())},
        "top_5_trade_share_of_gross_profit": round(sum(sorted_wins[:5]) / gross_profit, 6) if gross_profit else 0.0,
        "net_after_best_1pct_removed": round(sum(float(row["net_pnl"]) for row in best_removed), 2),
        "cost_2x_net": round(gross - 2 * total_costs, 2),
        "cost_4x_net": round(gross - 4 * total_costs, 2),
        "average_duration_hours": round(float(np.mean([row["duration_hours"] for row in records])), 2) if records else 0.0,
        "roll_exits": sum(row["outcome"] == "roll_exit" for row in records),
        "worst_trade_mae_dollars": round(max((float(row["mae_points"]) * INSTRUMENTS[symbol].point_value + float(row["total_costs"]) for row in records), default=0.0), 2) if symbol else None,
    }


def _period_summaries(records: list[dict], daily: pd.DataFrame, symbol: str) -> dict[str, dict]:
    return {
        name: summarize(
            [row for row in records if pd.Timestamp(row["entry_ts"]).year in years],
            daily=daily[daily.session_date.map(lambda value: value.year in years)], symbol=symbol,
        )
        for name, years in PERIODS.items()
    }


def _session_array(records: list[dict], sessions: list) -> np.ndarray:
    by_day = {day: 0.0 for day in sessions}
    for row in records:
        day = pd.Timestamp(row["exit_ts"]).date()
        if day in by_day:
            by_day[day] += float(row["net_pnl"])
    return np.asarray([by_day[day] for day in sessions], dtype=float)


def _two_sided(one_sided: float) -> float:
    return round(min(1.0, 2 * min(one_sided, 1 - one_sided)), 8)


def _classify(summary: dict, periods: dict, inference: dict, has_stop: bool) -> dict:
    gates = {
        "full_net_positive": summary["net_profit"] > 0,
        "validation_positive": periods["validation"]["net_profit"] > 0,
        "historical_evaluation_positive": periods["historical_evaluation"]["net_profit"] > 0,
        "sample_size_50": summary["trades"] >= 50,
        "at_least_four_positive_years": summary["positive_years"] >= 4,
        "profit_factor_above_one": (summary["profit_factor"] or 0) > 1,
        "positive_after_2x_costs": summary["cost_2x_net"] > 0,
        "positive_after_best_1pct_removed": summary["net_after_best_1pct_removed"] > 0,
        "by_adjusted_p_below_005": inference.get("by_adjusted_p", 1) < .05,
        "drawdown_under_30pct": abs(summary["max_drawdown"]) <= .30,
        "explicit_protective_stop": has_stop,
    }
    failed = [name for name, passed in gates.items() if not passed]
    if not failed:
        label = "robust_historical_candidate_not_proven"
    elif summary["net_profit"] > 0 and periods["validation"]["net_profit"] > 0 and periods["historical_evaluation"]["net_profit"] > 0:
        label = "promising_exploratory"
    elif summary["net_profit"] <= 0 and periods["validation"]["net_profit"] <= 0:
        label = "rejected_historically"
    else:
        label = "inconclusive"
    return {"label": label, "failed_gates": failed, "gates": gates, "proven": False}


def _control_records(daily: pd.DataFrame, symbol: str) -> list[dict]:
    records = []
    for row in daily.itertuples(index=False):
        records.append(_trade_record(
            "CONTROL_ALWAYS_LONG_RTH", symbol, "long", row.open_ts, row.open_ts, row.close_ts,
            row.open, row.close, "session_close", row.instrument_id,
            max(0.0, row.open - row.low), max(0.0, row.high - row.open),
        ))
    return records


def _report_markdown(result: dict) -> str:
    ibs_nq = result["results"]["NQ:ALG02_IBS_RANGE"]
    ibs_mnq = result["results"]["MNQ:ALG02_IBS_RANGE"]
    dip_nq = result["results"]["NQ:ALG09_BUY_DIP_20"]
    dip_literal = result["noncausal_diagnostics"]["NQ:ALG09_BUY_DIP_20_LITERAL_NONCAUSAL"]["summary"]
    adx_nq = result["results"]["NQ:ALG03_ADX_TUNED_EMA200"]
    adx_mnq = result["results"]["MNQ:ALG03_ADX_TUNED_EMA200"]
    nq_rc = result["inference"]["reality_check_spa"]["NQ"]["10"]
    mnq_rc = result["inference"]["reality_check_spa"]["MNQ"]["10"]
    lines = [
        "# r/algotrading NQ/MNQ one-by-one historical test",
        "",
        "## Verdict",
        "",
        "These are corrected retrospective tests, not proof. Every causal, objectively recoverable Reddit rule was run separately on preserved 2018-2025 Databento data with instrument-specific NQ/MNQ costs. No 2026 market data was read. **No candidate is proven and none passed the full promotion gate.**",
        "",
        f"The strongest new family was `ALG02_IBS_RANGE`: NQ earned ${ibs_nq['summary']['net_profit']:,.2f} over {ibs_nq['summary']['trades']} trades (PF {ibs_nq['summary']['profit_factor']:.2f}, mark-to-market/MAE drawdown {ibs_nq['summary']['max_drawdown']:.2%}); MNQ earned ${ibs_mnq['summary']['net_profit']:,.2f} over {ibs_mnq['summary']['trades']} trades. Both validation and 2024-2025 evaluation were positive, and both remained positive after removing the best 1% of trades. It still failed family-adjusted significance (NQ raw two-sided p={ibs_nq['inference']['two_sided_p']:.4f}, BH={ibs_nq['inference']['bh_adjusted_p']:.4f}, BY={ibs_nq['inference']['by_adjusted_p']:.4f}) and has no protective stop.",
        "",
        f"`ALG09_BUY_DIP_20` was also historically positive: NQ ${dip_nq['summary']['net_profit']:,.2f}, {dip_nq['summary']['trades']} trades, PF {dip_nq['summary']['profit_factor']:.2f}, drawdown {dip_nq['summary']['max_drawdown']:.2%}. But the impossible same-close source diagnostic showed ${dip_literal['net_profit']:,.2f}; enforcing a causal next-open fill removed ${dip_literal['net_profit'] - dip_nq['summary']['net_profit']:,.2f}. Its raw two-sided p={dip_nq['inference']['two_sided_p']:.4f} and BY-adjusted p={dip_nq['inference']['by_adjusted_p']:.4f}.",
        "",
        f"The tuned ADX+EMA200 rule made ${adx_nq['summary']['net_profit']:,.2f} on NQ but lost ${abs(adx_nq['periods']['validation']['net_profit']):,.2f} in 2022-2023, so it is inconclusive. MNQ was positive in validation by only ${adx_mnq['periods']['validation']['net_profit']:,.2f}; that is not convincing independent evidence because NQ and MNQ share the same underlying signal.",
        "",
        f"The family-level White reality-check/SPA did not reject no edge: at the primary 10-session block NQ p={nq_rc['reality_check_p_value']:.4f}/SPA={nq_rc['spa_p_value']:.4f}, MNQ p={mnq_rc['reality_check_p_value']:.4f}/SPA={mnq_rc['spa_p_value']:.4f}. Block lengths 5 and 20 reached the same conclusion.",
        "",
        "## One-by-one results",
        "",
        "| Instrument | Candidate | Trades | Net | PF | Max DD | Validation | 2024-25 eval | Net ex best 1% | Evidence |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for symbol in ("NQ", "MNQ"):
        for candidate_id in ALL_IDS:
            item = result["results"].get(f"{symbol}:{candidate_id}")
            if not item:
                continue
            summary, periods = item["summary"], item["periods"]
            pf = "n/a" if summary["profit_factor"] is None else f"{summary['profit_factor']:.2f}"
            lines.append(
                f"| {symbol} | {candidate_id} | {summary['trades']} | ${summary['net_profit']:,.2f} | {pf} | {summary['max_drawdown']:.2%} | "
                f"${periods['validation']['net_profit']:,.2f} | ${periods['historical_evaluation']['net_profit']:,.2f} | "
                f"${summary['net_after_best_1pct_removed']:,.2f} | {item['classification']['label']} |"
            )
    lines += [
        "",
        "## What survived and what failed",
        "",
        "- **Best candidate for further prospective work:** `ALG02_IBS_RANGE`. It had the strongest combination of PF, period consistency, cost tolerance, and tail-removal survival. It remains exploratory because the search-adjusted tests failed and the source has no stop.",
        "- **Second candidate:** `ALG09_BUY_DIP_20`. It has enough trades and positive validation/evaluation, but its edge shrank materially when the impossible same-close fill was corrected, and it failed family-adjusted inference.",
        "- **Bollinger variants:** positive in both later periods, but only 15-33 trades, no stop, NQ drawdowns around 33-35%, and no adjusted significance. Too sparse for a trading conclusion.",
        "- **ADX variants:** headline full-sample profits came mainly outside the 2022-2023 validation period. The tuned NQ variants failed validation.",
        "- **RSI2:** long and long/short variants lost money in 2024-2025; the one-day version was weak and tail-dependent. Not promoted.",
        "- **Daily reversal/momentum:** reversal profits were unstable by year and tail-sensitive; momentum lost money overall and badly in 2024-2025. Not promoted.",
        "",
        "## Relation to the earlier r/Daytrading tournament",
        "",
        "The objective Daytrading slate was already executed in Phase 5 and corrected again in Phases 6-7. Corrected C01 earned $117,590.50 over 1,495 NQ trades with PF 1.1621 and -14.68% maximum drawdown, but failed the stronger conclusion because profits were right-tail dependent, the best 1% removal made it negative, and reality-check/SPA evidence did not establish superiority. The present r/algotrading run does not overturn that result. ALG02 and ALG09 diversify the entry horizon, but neither passes adjusted significance or operational-risk gates.",
        "",
        "So the combined answer is: **some rules made money historically; no Reddit rule is proven; no rule is authorized for live trading; the most defensible next test is frozen prospective MNQ paper execution of ALG02 and ALG09, not another retrospective parameter search.**",
        "",
        "## Interpretation rules",
        "",
        "- `robust_historical_candidate_not_proven` means every frozen historical gate passed; it still is not proof or a clean holdout result.",
        "- `promising_exploratory` means full, validation, and historical-evaluation P&L were positive but at least one robustness gate failed.",
        "- `inconclusive` means the periods or robustness checks disagree.",
        "- `rejected_historically` means full and validation evidence are non-positive under the frozen implementation.",
        "- Strategies without explicit stops fail the protective-stop gate even when historical P&L is positive.",
        "",
        "## Source fidelity and corrections",
        "",
        "Daily close-based signals are entered at the next RTH open so the completed close is actually known. The source-literal same-close ALG09 diagnostic is recorded separately and excluded from inference because it is not executable without look-ahead. ADX/DMI/ATR use standard Wilder period 14 because the Reddit post did not state a period. Bollinger bands use 20 SMA and two population standard deviations. Continuous-contract mapping changes force a flat exit so roll gaps cannot manufacture profit. Drawdown is the worse of daily mark-to-market and an intratrade MAE proxy, not merely the closed-trade equity curve.",
        "",
        "## Non-reproducible leads",
        "",
        "SL06 is a trend-feature tutorial rather than a trade rule; SL07 needs two calendar-spread legs; SL08 needs a point-in-time ETF universe; SL10 is methodology; SL11 omits its oscillator/filter/exit definitions. They were not approximated.",
        "",
        "## Statistical warning",
        "",
        "All 2018-2025 observations were previously inspected. Bootstrap and multiple-testing corrections measure historical uncertainty and search burden; they do not create a new holdout. Reddit publication dates are provenance, not ex-ante evidence.",
        "",
        "`2026 MARKET HOLDOUT: UNTOUCHED`",
    ]
    return "\n".join(lines) + "\n"


def run_algotrading_tournament(
    project_root: Path = Path("."),
    data_root: Path = Path("data"),
    bootstrap_samples: int = 50_000,
    write_outputs: bool = True,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    data_root = data_root.resolve()
    specification = verify_lock(project_root)
    degraded, _ = _condition_dates(data_root)
    all_records: list[dict] = []
    results: dict[str, dict] = {}
    diagnostics: dict[str, dict] = {}
    opened_partitions: dict[str, list[str]] = {}
    session_arrays: dict[str, np.ndarray] = {}
    sessions_by_symbol: dict[str, list] = {}
    noncausal: dict[str, dict] = {}

    for symbol in ("NQ", "MNQ"):
        market, opened = _load_market(data_root, symbol)
        opened_partitions[symbol] = opened
        rth = _rth(market, degraded)
        daily = _daily(rth)
        hourly = _hourly(rth)
        sessions = list(daily.session_date)
        sessions_by_symbol[symbol] = sessions
        for candidate_id in DAILY_IDS:
            records, diag = simulate_daily(daily, candidate_id, symbol)
            key = f"{symbol}:{candidate_id}"
            all_records.extend(records)
            diagnostics[key] = diag
            results[key] = {
                "summary": summarize(records, daily=daily, symbol=symbol),
                "periods": _period_summaries(records, daily, symbol),
                "diagnostics": diag,
                "has_explicit_stop": False,
            }
            session_arrays[key] = _session_array(records, sessions)
        for candidate_id in HOURLY_IDS:
            records, diag = simulate_hourly(rth, hourly, candidate_id, symbol)
            key = f"{symbol}:{candidate_id}"
            all_records.extend(records)
            diagnostics[key] = diag
            results[key] = {
                "summary": summarize(records, daily=daily, symbol=symbol),
                "periods": _period_summaries(records, daily, symbol),
                "diagnostics": diag,
                "has_explicit_stop": True,
            }
            session_arrays[key] = _session_array(records, sessions)
        control = _control_records(daily, symbol)
        results[f"{symbol}:CONTROL_ALWAYS_LONG_RTH"] = {
            "summary": summarize(control, daily=daily, symbol=symbol), "periods": _period_summaries(control, daily, symbol), "classification": {"label": "control", "proven": False},
        }
        literal = noncausal_buy_dip_diagnostic(daily, symbol)
        noncausal[f"{symbol}:ALG09_BUY_DIP_20_LITERAL_NONCAUSAL"] = {
            "summary": summarize(literal, daily=daily, symbol=symbol), "reason": "same completed close used as the fill; excluded from inference and promotion",
        }

    raw_p: list[float] = []
    keys: list[str] = []
    for symbol in ("NQ", "MNQ"):
        for candidate_id in ALL_IDS:
            key = f"{symbol}:{candidate_id}"
            boot = stationary_bootstrap_mean(session_arrays[key], bootstrap_samples, 10, 8100 + len(keys))
            boot["two_sided_p"] = _two_sided(boot["p_value"])
            results[key]["inference"] = boot
            raw_p.append(boot["two_sided_p"])
            keys.append(key)
    bh = adjusted_p_values(raw_p, "bh")
    by = adjusted_p_values(raw_p, "by")
    for key, bh_value, by_value in zip(keys, bh, by):
        results[key]["inference"]["bh_adjusted_p"] = round(bh_value, 8)
        results[key]["inference"]["by_adjusted_p"] = round(by_value, 8)
        results[key]["classification"] = _classify(
            results[key]["summary"], results[key]["periods"], results[key]["inference"], results[key]["has_explicit_stop"],
        )

    reality = {}
    for symbol in ("NQ", "MNQ"):
        matrix = np.column_stack([session_arrays[f"{symbol}:{candidate_id}"] for candidate_id in ALL_IDS])
        benchmark = np.zeros(len(sessions_by_symbol[symbol]))
        reality[symbol] = {
            str(block): reality_check(matrix, benchmark, bootstrap_samples, block, 9000 + block + (100 if symbol == "MNQ" else 0))
            for block in (5, 10, 20)
        }

    result = {
        "schema_version": 1,
        "generated_at": datetime.now(NY).isoformat(),
        "specification_sha256": _sha256(project_root / "research/algotrading_candidate_specifications_v1.json"),
        "data_window": "2018-2025 preserved cache only; MNQ begins 2019-05-06",
        "holdout_guard": {"status": "UNTOUCHED", "protected_boundary": "2026-01-01", "opened_2026_market_data": False},
        "source_archive": "local r/algotrading posts.jsonl; no external browsing",
        "results": results,
        "noncausal_diagnostics": noncausal,
        "inference": {
            "unit": "accepted RTH session with no-trade zero",
            "bootstrap": "Politis-Romano stationary",
            "bootstrap_samples": bootstrap_samples,
            "primary_expected_block_sessions": 10,
            "multiple_testing_family": keys,
            "corrections": ["BH", "BY", "White reality check", "SPA-style maximum"],
            "reality_check_spa": reality,
        },
        "opened_partitions": opened_partitions,
        "non_reproducible_leads": specification["non_reproducible_leads"],
        "limitations": [
            "Retrospective historical evaluation only; all 2018-2025 years were previously inspected.",
            "One-minute OHLCV cannot resolve within-minute stop/target order; adverse-first is used.",
            "Daily equity/index rules are adapted to NQ/MNQ RTH and next-open executable fills.",
            "No-stop source strategies have unbounded modeled gap risk and automatically fail the protective-stop promotion gate.",
            "NQ and MNQ are the same underlying signal and are not independent replications.",
        ],
        "proven_strategies": [],
    }
    if write_outputs:
        output = project_root / "phase8"
        output.mkdir(parents=True, exist_ok=True)
        (output / "algotrading_tournament_results.json").write_text(json.dumps(result, indent=2, default=str))
        pd.DataFrame(all_records).to_parquet(output / "algotrading_trades.parquet", index=False, compression="zstd")
        with (output / "algotrading_tournament.csv").open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["run_key", "trades", "net_profit", "profit_factor", "max_drawdown", "validation_net", "historical_evaluation_net", "net_after_best_1pct_removed", "by_adjusted_p", "classification"])
            for key in keys:
                item = results[key]
                writer.writerow([
                    key, item["summary"]["trades"], item["summary"]["net_profit"], item["summary"]["profit_factor"],
                    item["summary"]["max_drawdown"], item["periods"]["validation"]["net_profit"],
                    item["periods"]["historical_evaluation"]["net_profit"], item["summary"]["net_after_best_1pct_removed"],
                    item["inference"]["by_adjusted_p"], item["classification"]["label"],
                ])
        (output / "ALGOTRADING_STRATEGY_TEST_REPORT.md").write_text(_report_markdown(result))
    return result
