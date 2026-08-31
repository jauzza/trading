from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import NormalDist, mean
from typing import Iterable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

from .analytics import adjusted_p_values, max_drawdown, reality_check, stationary_bootstrap_mean
from .engine import ExecutionConfig, INSTRUMENTS, execute_signal
from .models import Bar, Signal, Trade
from .research import MNQ_FP, NQ_FP, PERIODS, _bar, _condition_dates, _contexts, _load_partition, _quality, _roll_dates
from .strategies import StrategyBConfig, aggregate_five_minute, confirmed_pivots, ema, strategy_b

NY = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "research/candidate_resolution_manifest.json"
LOCK = ROOT / "research/preregistration.lock.json"
PREREG = ROOT / "docs/strategy_tournament_preregistration.md"
PERIOD_BOUNDS = {"development": (2018, 2021), "validation": (2022, 2023), "historical_evaluation": (2024, 2025)}
FAMILIES = {
    "C01": "opening_momentum_range", "C02": "opening_momentum_range", "C03": "trend_pullback_channel",
    "C04": "trend_pullback_channel", "C05": "trend_pullback_channel", "C08": "objective_levels",
    "C09": "objective_levels", "C10": "objective_levels", "C11": "vwap", "C14": "gap",
    "C15": "objective_levels", "C16": "opening_momentum_range", "C17": "opening_momentum_range",
    "BASE_CANDLE": "opening_momentum_range", "BASE_EMA": "opening_momentum_range",
    "BASE_LONG": "baselines", "BASE_SHORT": "baselines", "BASE_RANDOM": "baselines",
}


def sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verify_preregistration() -> dict:
    lock = json.loads(LOCK.read_text())
    for relative, expected in lock["files"].items():
        actual = sha256_file(ROOT / relative)
        if actual != expected:
            raise RuntimeError(f"preregistration integrity failure: {relative}")
    payload = json.loads(MANIFEST.read_text())
    for item in payload["candidates"]:
        canonical = json.dumps(item["specification"], sort_keys=True, separators=(",", ":")).encode()
        if hashlib.sha256(canonical).hexdigest() != item["specification_hash"]:
            raise RuntimeError(f"candidate specification hash mismatch: {item['candidate_id']}")
    return payload


class ProtectedMarketDataGuard:
    """Reject protected partitions from manifest/path metadata before any market file is opened."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def manifest(self) -> dict:
        payload = json.loads((self.root / "manifest.json").read_text())
        for dataset in payload.get("datasets", {}).values():
            if dataset.get("request", {}).get("end", "9999") > "2026-01-01":
                raise RuntimeError("request crosses protected market boundary")
            for partition in dataset.get("partitions", []):
                if int(partition["year"]) >= 2026:
                    raise RuntimeError("protected partition rejected before market read")
        return payload

    @staticmethod
    def assert_allowed_path(path: str | Path) -> Path:
        candidate = Path(path)
        for part in candidate.parts:
            if part.startswith("year="):
                try:
                    year = int(part.split("=", 1)[1])
                except ValueError as exc:
                    raise RuntimeError("invalid market partition") from exc
                if year >= 2026:
                    raise RuntimeError("protected partition rejected before path inspection")
        return candidate

    def read_parquet(self, path: str | Path) -> pd.DataFrame:
        return _load_partition(str(self.assert_allowed_path(path)))

    def allowed_raw_files(self, manifest: dict) -> list[Path]:
        files = [self.root / "manifest.json"]
        for dataset in manifest["datasets"].values():
            for partition in dataset["partitions"]:
                if int(partition["year"]) >= 2026:
                    raise RuntimeError("protected partition rejected before hashing")
                files.extend((Path(partition["path"]), Path(partition["mapping_path"])))
        files.extend(sorted((self.root / "fred").glob("*.json")))
        return files

    def checksums(self, manifest: dict) -> dict[str, str]:
        return {str(path): sha256_file(path) for path in self.allowed_raw_files(manifest)}


@dataclass(frozen=True)
class FeatureValue:
    name: str
    value: float | str | bool | None
    known_at: datetime
    source_timestamp: datetime | None
    calculation_window: str
    available_for_this_entry: bool

    def to_dict(self) -> dict:
        data = asdict(self)
        data["known_at"] = self.known_at.isoformat()
        data["source_timestamp"] = self.source_timestamp.isoformat() if self.source_timestamp else None
        return data


def _aggregate(bars: list[Bar], minutes: int) -> list[Bar]:
    groups: dict[datetime, list[Bar]] = defaultdict(list)
    for bar in bars:
        anchor = bar.ts.replace(minute=bar.ts.minute - bar.ts.minute % minutes, second=0, microsecond=0)
        groups[anchor].append(bar)
    output = []
    for anchor, group in sorted(groups.items()):
        group.sort(key=lambda value: value.ts)
        if len(group) != minutes or any(group[i].ts - group[i - 1].ts != timedelta(minutes=1) for i in range(1, len(group))):
            continue
        output.append(Bar(anchor, group[0].open, max(x.high for x in group), min(x.low for x in group), group[-1].close, sum(x.volume for x in group)))
    return output


def _fives_to_fifteens(bars: list[Bar]) -> list[Bar]:
    groups: dict[datetime, list[Bar]] = defaultdict(list)
    for bar in bars:
        anchor = bar.ts.replace(minute=bar.ts.minute - bar.ts.minute % 15, second=0, microsecond=0)
        groups[anchor].append(bar)
    output = []
    for anchor, group in sorted(groups.items()):
        group.sort(key=lambda value: value.ts)
        if len(group) != 3 or any(group[i].ts - group[i - 1].ts != timedelta(minutes=5) for i in range(1, 3)):
            continue
        output.append(Bar(anchor, group[0].open, max(x.high for x in group), min(x.low for x in group), group[-1].close, sum(x.volume for x in group)))
    return output


def _ema_series(values: list[float], period: int) -> np.ndarray:
    return np.asarray(ema(values, period), dtype=float)


def _atr(bars: list[Bar], period: int = 14) -> np.ndarray:
    if not bars:
        return np.array([])
    tr = [bars[0].high - bars[0].low]
    for previous, current in zip(bars, bars[1:]):
        tr.append(max(current.high - current.low, abs(current.high - previous.close), abs(current.low - previous.close)))
    return pd.Series(tr).ewm(alpha=1 / period, adjust=False).mean().to_numpy()


def _next_minute(rth: list[Bar], completed: Bar) -> Bar | None:
    decision = completed.ts + timedelta(minutes=(5 if completed.ts.minute % 5 == 0 else 1))
    return next((bar for bar in rth if bar.ts >= decision), None)


def _signal(candidate: str, side: str, entry: Bar, stop: float, reason: str, metadata: dict | None = None) -> Signal | None:
    if (side == "long" and stop >= entry.open) or (side == "short" and stop <= entry.open) or abs(entry.open - stop) < .25:
        return None
    return Signal(entry.ts, candidate, candidate, side, entry.open, stop, None, reason, entry.ts, metadata or {})


def _first_signal(items: Iterable[Signal | None]) -> list[Signal]:
    return [item for item in items if item is not None][:1]


def c01_signals(rth: list[Bar], history_fives: list[Bar], ema_period: int = 200, volume_ratio: float = 1.0) -> list[Signal]:
    """Frozen C01 signal with bounded local perturbations for plateau audits."""
    fives = aggregate_five_minute(rth)
    fifteens = _aggregate(rth, 15)
    signals = []
    if len(fifteens) >= 3:
        opening = fifteens[0]
        hist15 = _fives_to_fifteens(history_fives[-max(800, ema_period * 4):] + fives)
        for bar in fifteens[1:]:
            index = hist15.index(bar) if bar in hist15 else -1
            if index < ema_period:
                continue
            value = _ema_series([item.close for item in hist15[:index + 1]], ema_period)[-1]
            previous = hist15[index - 1]
            side = "long" if bar.close > opening.high and bar.close > value else "short" if bar.close < opening.low and bar.close < value else None
            if side and bar.volume > previous.volume * volume_ratio:
                entry = _next_minute(rth, Bar(bar.ts, bar.open, bar.high, bar.low, bar.close, bar.volume))
                if entry:
                    signals.append(_signal("C01", side, entry, bar.low if side == "long" else bar.high,
                                           f"15-minute ORB close + volume {volume_ratio:.2f}x + EMA{ema_period}"))
                break
    return _first_signal(signals)


def candidate_signals(
    rth: list[Bar], overnight: list[Bar], history_fives: list[Bar], prior: dict | None,
) -> dict[str, list[Signal]]:
    fives = aggregate_five_minute(rth)
    context = [*history_fives, *fives]
    output: dict[str, list[Signal]] = {}

    # C01 — 15-minute ORB close, volume and lagged 200 EMA.
    output["C01"] = c01_signals(rth, history_fives)

    # C02 — opening-range break and confirmed retest.
    c02 = []
    if fives:
        opening = fives[0]
        state = None
        for bar in fives[1:]:
            if state is None:
                state = "long" if bar.close > opening.high else "short" if bar.close < opening.low else None
                continue
            touched = bar.low <= opening.high if state == "long" else bar.high >= opening.low
            held = bar.close >= opening.high if state == "long" else bar.close <= opening.low
            if touched and held:
                entry = _next_minute(rth, bar)
                if entry:
                    c02.append(_signal("C02", state, entry, bar.low if state == "long" else bar.high, "completed opening-range retest"))
                break
    output["C02"] = _first_signal(c02)

    # C03 — Keltner/stochastic/momentum, matched management only.
    c03 = []
    if len(context) >= 100:
        closes = np.asarray([bar.close for bar in context])
        highs = pd.Series([bar.high for bar in context])
        lows = pd.Series([bar.low for bar in context])
        mid = _ema_series(closes.tolist(), 20)
        atr = _atr(context, 14)
        raw_k = 100 * (pd.Series(closes) - lows.rolling(10).min()) / (highs.rolling(10).max() - lows.rolling(10).min())
        slow_k = raw_k.rolling(3).mean().rolling(3).mean().to_numpy()
        start = len(history_fives)
        last_touch = None
        for i in range(max(80, start), len(context) - 1):
            if context[i].high >= mid[i] + 2.15 * atr[i]: last_touch = "upper"
            if context[i].low <= mid[i] - 2.15 * atr[i]: last_touch = "lower"
            momentum = closes[i] - closes[i - 80]
            side = "long" if momentum > 0 and last_touch == "upper" and slow_k[i] < 20 else "short" if momentum < 0 and last_touch == "lower" and slow_k[i] > 80 else None
            if not side or context[i].ts.date() != rth[0].ts.date():
                continue
            entry = _next_minute(rth, context[i])
            if entry:
                stop = mid[i] - 1.75 * atr[i] if side == "long" else mid[i] + 1.75 * atr[i]
                c03.append(_signal("C03", side, entry, stop, "Keltner stochastic momentum pullback"))
            break
    output["C03"] = _first_signal(c03)

    # C04 — five-minute Bollinger width expansion and EMA200 slope.
    c04 = []
    if len(context) >= 201:
        closes = pd.Series([bar.close for bar in context], dtype=float)
        mid = closes.rolling(20).mean(); sd = closes.rolling(20).std(ddof=0)
        width = 4 * sd; trend = pd.Series(_ema_series(closes.tolist(), 200))
        for i in range(max(len(history_fives), 200), len(context)):
            side = "long" if closes[i] > mid[i] + 2 * sd[i] and trend[i] > trend[i - 1] else "short" if closes[i] < mid[i] - 2 * sd[i] and trend[i] < trend[i - 1] else None
            if side and width[i] > width[i - 1]:
                entry = _next_minute(rth, context[i])
                if entry:
                    stop = min(context[i].low, context[i - 1].low) if side == "long" else max(context[i].high, context[i - 1].high)
                    c04.append(_signal("C04", side, entry, stop, "Bollinger width trend breakout"))
                break
    output["C04"] = _first_signal(c04)

    # C05 — lag-safe confirmed pivot in a dual-EMA trend.
    c05 = []
    if len(context) >= 25:
        closes = [bar.close for bar in context]
        fast, slow = _ema_series(closes, 9), _ema_series(closes, 20)
        pivots = confirmed_pivots(context)
        for i in range(max(len(history_fives), 22), len(context)):
            current = context[i]
            trend = "long" if fast[i] > fast[i-1] and slow[i] > slow[i-1] else "short" if fast[i] < fast[i-1] and slow[i] < slow[i-1] else None
            if not trend:
                continue
            kind = "low" if trend == "long" else "high"
            legal = [p for p in pivots if p["kind"] == kind and p["available_at"] <= current.ts]
            confirms = current.high > context[i-1].high if trend == "long" else current.low < context[i-1].low
            if legal and confirms:
                entry = _next_minute(rth, current)
                if entry:
                    c05.append(_signal("C05", trend, entry, float(legal[-1]["price"]), "confirmed trend-pivot pullback"))
                break
    output["C05"] = _first_signal(c05)

    pdh = prior.get("high") if prior else None; pdl = prior.get("low") if prior else None
    onh = max((bar.high for bar in overnight), default=None); onl = min((bar.low for bar in overnight), default=None)

    # C08 — prior-level sweep/re-entry then 50% retracement.
    c08 = []
    if pdh is not None:
        state = None
        for bar in fives:
            if state is None:
                if bar.high > pdh and bar.close < pdh: state = ("short", bar, (bar.high + bar.low) / 2)
                elif bar.low < pdl and bar.close > pdl: state = ("long", bar, (bar.high + bar.low) / 2)
                continue
            side, sweep, midpoint = state
            reached = bar.high >= midpoint if side == "short" else bar.low <= midpoint
            if reached:
                entry = _next_minute(rth, bar)
                if entry: c08.append(_signal("C08", side, entry, sweep.high if side == "short" else sweep.low, "prior-level sweep and 50% retrace"))
                break
    output["C08"] = _first_signal(c08)

    # C09 — PDH/PDL breakout and one-tick retest.
    c09 = []
    if pdh is not None:
        state = None
        for bar in fives:
            if state is None:
                state = "long" if bar.close > pdh else "short" if bar.close < pdl else None
                continue
            level = pdh if state == "long" else pdl
            touched = bar.low <= level + .25 if state == "long" else bar.high >= level - .25
            held = bar.close >= level if state == "long" else bar.close <= level
            if touched and held:
                entry = _next_minute(rth, bar)
                if entry: c09.append(_signal("C09", state, entry, bar.low if state == "long" else bar.high, "previous-day level break and retest"))
                break
    output["C09"] = _first_signal(c09)

    # C10 — overnight close breakout.
    c10 = []
    if onh is not None:
        for bar in fives:
            side = "long" if bar.close > onh else "short" if bar.close < onl else None
            if side:
                entry = _next_minute(rth, bar)
                if entry: c10.append(_signal("C10", side, entry, bar.low if side == "long" else bar.high, "overnight-range close breakout"))
                break
    output["C10"] = _first_signal(c10)

    # C11 — RTH VWAP reclaim and retest.
    c11 = []
    if fives:
        cumulative_pv = cumulative_v = 0.0; state = None
        for bar in fives:
            cumulative_pv += ((bar.high + bar.low + bar.close) / 3) * bar.volume; cumulative_v += bar.volume
            vwap = cumulative_pv / cumulative_v if cumulative_v else bar.close
            if state is None:
                state = "long" if bar.open < vwap < bar.close else "short" if bar.open > vwap > bar.close else None
                continue
            touched = bar.low <= vwap if state == "long" else bar.high >= vwap
            held = bar.close > vwap if state == "long" else bar.close < vwap
            if touched and held:
                entry = _next_minute(rth, bar)
                if entry: c11.append(_signal("C11", state, entry, bar.low if state == "long" else bar.high, "RTH VWAP reclaim and retest"))
                break
    output["C11"] = _first_signal(c11)

    # C14 — gap fill with five-point minimum and first-candle confirmation.
    c14 = []
    if prior and fives:
        gap = fives[0].open - prior["close"]
        side = "short" if gap >= 5 and fives[0].close < fives[0].open else "long" if gap <= -5 and fives[0].close > fives[0].open else None
        entry = _next_minute(rth, fives[0]) if side else None
        if entry: c14.append(_signal("C14", side, entry, fives[0].high if side == "short" else fives[0].low, "regular-session gap fill confirmation"))
    output["C14"] = _first_signal(c14)
    # C15 — failed prior-day break.
    c15 = []
    if pdh is not None:
        for bar in fives:
            side = "short" if bar.high > pdh and bar.close < pdh else "long" if bar.low < pdl and bar.close > pdl else None
            if side:
                entry = _next_minute(rth, bar)
                if entry: c15.append(_signal("C15", side, entry, bar.high if side == "short" else bar.low, "failed prior-day range breakout"))
                break
    output["C15"] = _first_signal(c15)

    # C16 — first-hour initial-balance breakout.
    c16 = []
    initial = [bar for bar in rth if time(9, 30) <= bar.ts.time() <= time(10, 29)]
    if len(initial) == 60:
        ibh, ibl = max(bar.high for bar in initial), min(bar.low for bar in initial)
        for bar in fives:
            if bar.ts.time() < time(10, 30): continue
            side = "long" if bar.close > ibh else "short" if bar.close < ibl else None
            if side:
                entry = _next_minute(rth, bar)
                if entry: c16.append(_signal("C16", side, entry, bar.low if side == "long" else bar.high, "initial-balance breakout and hold"))
                break
    output["C16"] = _first_signal(c16)

    # C17 — objective fragment only, explicitly a negative control.
    c17 = []
    if len(context) >= 201 and len(rth) > 6:
        opening = fives[0]; trend = _ema_series([bar.close for bar in context[:len(history_fives)+1]], 200)
        side = "long" if opening.close > trend[-1] and trend[-1] > trend[-2] else "short" if opening.close < trend[-1] and trend[-1] < trend[-2] else None
        confirm = rth[5]
        if side and ((confirm.close > trend[-1]) if side == "long" else (confirm.close < trend[-1])):
            entry = rth[6]; stop = entry.open - 20.25 if side == "long" else entry.open + 20.25
            c17.append(_signal("C17", side, entry, stop, "opening EMA continuation negative control"))
    output["C17"] = _first_signal(c17)

    return output


def baseline_signals(rth: list[Bar], overnight: list[Bar]) -> dict[str, list[Signal]]:
    definitions = {
        "BASE_CANDLE": StrategyBConfig(variant="BASE_CANDLE", target_r=4, direction_mode="candle_body", min_warmup_periods=1, ema_session="none"),
        "BASE_EMA": StrategyBConfig(variant="BASE_EMA", target_r=4),
        "BASE_LONG": StrategyBConfig(variant="BASE_LONG", target_r=4, direction_mode="always_long"),
        "BASE_SHORT": StrategyBConfig(variant="BASE_SHORT", target_r=4, direction_mode="always_short"),
        "BASE_RANDOM": StrategyBConfig(variant="BASE_RANDOM", target_r=4, direction_mode="random", random_seed=5517),
    }
    output = {}
    for name, config in definitions.items():
        signals = strategy_b(rth, overnight, config)
        output[name] = [Signal(s.ts, name, name, s.side, s.entry, s.stop, None, s.reason, s.available_at, s.metadata) for s in signals]
    return output


def _period(year: int) -> str | None:
    return next((name for name, bounds in PERIOD_BOUNDS.items() if bounds[0] <= year <= bounds[1]), None)


def _cost_config(symbol: str, sizing: str, multiplier: int = 1) -> ExecutionConfig:
    margin = INSTRUMENTS[symbol].assumed_margin
    common = dict(max_contracts=20, margin_per_contract=margin, fee_multiplier=multiplier,
                  slippage_ticks_per_side=multiplier, spread_ticks_round_trip=multiplier)
    return ExecutionConfig(fixed_contracts=1, **common) if sizing == "fixed1" else ExecutionConfig(risk_fraction=.01, **common)


def _execute(signal: Signal, bars: list[Bar], symbol: str, equity: float, overlay: str, sizing: str, trade_id: str) -> Trade | None:
    cloned = Signal(signal.ts, signal.strategy, signal.variant, signal.side, signal.entry, signal.stop,
                    4 if overlay == "matched_4R" else None, signal.reason, signal.available_at, dict(signal.metadata))
    future = [bar for bar in bars if cloned.ts <= bar.ts and bar.ts.time() <= time(15, 55)]
    return execute_signal(cloned, future, equity, symbol, _cost_config(symbol, sizing), trade_id) if future else None


def _delay_signal(signal: Signal, bars: list[Bar], minutes: int) -> Signal | None:
    delayed_at = signal.ts + timedelta(minutes=minutes)
    entry = next((bar for bar in bars if bar.ts >= delayed_at), None)
    if entry is None:
        return None
    intervening = [bar for bar in bars if signal.ts <= bar.ts < entry.ts]
    stop_touched = any(bar.low <= signal.stop for bar in intervening) if signal.side == "long" else any(bar.high >= signal.stop for bar in intervening)
    if stop_touched:
        return None
    return Signal(entry.ts, signal.strategy, signal.variant, signal.side, entry.open, signal.stop, signal.target_r,
                  f"{signal.reason}; causal {minutes}-minute delay", entry.ts, {**signal.metadata, "delay_minutes": minutes})


def _trade_metrics(trades: list[Trade], accepted_days: list[date], starting: float = 100_000) -> dict:
    pnl = np.asarray([trade.net_pnl for trade in trades], dtype=float)
    r = np.asarray([trade.realized_r for trade in trades], dtype=float)
    equity = np.r_[starting, starting + np.cumsum(pnl)]
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    dd, duration = max_drawdown(equity.tolist())
    by_year = {str(year): round(sum(t.net_pnl for t in trades if t.entry_ts.year == year), 2) for year in sorted({d.year for d in accepted_days})}
    daily = defaultdict(float)
    for trade in trades: daily[trade.entry_ts.date()] += trade.realized_r
    sessions = np.asarray([daily[day] for day in accepted_days], dtype=float)
    gross_profit = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(losses.sum()) if len(losses) else 0.0
    return {
        "accepted_sessions": len(accepted_days), "trades": len(trades), "net_profit": round(float(pnl.sum()), 2),
        "return": round(float(pnl.sum() / starting), 6), "expectancy_trade_r": round(float(r.mean()), 6) if len(r) else 0,
        "expectancy_session_r": round(float(sessions.mean()), 6) if len(sessions) else 0,
        "win_rate": round(float((pnl > 0).mean()), 6) if len(pnl) else 0,
        "profit_factor": round(gross_profit / abs(gross_loss), 4) if gross_loss else None,
        "max_drawdown": round(dd, 6), "drawdown_duration_trades": duration,
        "total_costs": round(sum(t.total_costs for t in trades), 2), "turnover_contracts": sum(t.contracts for t in trades),
        "average_holding_minutes": round(mean([t.duration_minutes for t in trades]), 2) if trades else 0,
        "average_mae_points": round(mean([t.mae_points for t in trades]), 3) if trades else 0,
        "average_mfe_points": round(mean([t.mfe_points for t in trades]), 3) if trades else 0,
        "by_year": by_year, "positive_years": sum(value > 0 for value in by_year.values()),
        "equity": [round(value, 2) for value in equity], "session_r": sessions.tolist(),
    }


def _tail_tests(trades: list[Trade]) -> dict:
    values = np.asarray([trade.net_pnl for trade in trades], dtype=float)
    if not len(values):
        return {"low_tail_dependence": False, "reason": "no trades"}
    ordered = np.sort(values)[::-1]; net = float(values.sum()); gross = float(values[values > 0].sum())
    remove_count = max(1, math.ceil(len(values) * .01))
    by_year = defaultdict(float)
    for trade in trades: by_year[trade.entry_ts.year] += trade.net_pnl
    positive_year_total = sum(max(0, value) for value in by_year.values())
    best_year_share = max((max(0, value) for value in by_year.values()), default=0) / positive_year_total if positive_year_total else None
    best_trade_share = ordered[0] / net if net > 0 else None
    after_best_1pct = net - ordered[:remove_count].sum()
    annual_best_removed = net - sum(max((t.net_pnl for t in trades if t.entry_ts.year == year), default=0) for year in by_year)
    lower, upper = np.quantile(values, [.01, .99]); winsorized = float(np.clip(values, lower, upper).sum())
    flag = after_best_1pct > 0 and best_trade_share is not None and best_trade_share <= .10 and best_year_share is not None and best_year_share <= .40
    return {
        "largest_trade_share_net": round(best_trade_share, 6) if best_trade_share is not None else None,
        "largest_trade_share_gross_profit": round(ordered[0] / gross, 6) if gross else None,
        "top5_share_net": round(float(ordered[:5].sum() / net), 6) if net else None,
        "top10_share_net": round(float(ordered[:10].sum() / net), 6) if net else None,
        "best_1pct_removed_trades": remove_count, "net_after_best_1pct": round(float(after_best_1pct), 2),
        "net_after_best5": round(float(net - ordered[:5].sum()), 2),
        "net_after_best_trade_each_year": round(float(annual_best_removed), 2),
        "winsorized_1pct_net": round(winsorized, 2), "largest_positive_year_share": round(best_year_share, 6) if best_year_share is not None else None,
        "skew": round(float(pd.Series(values).skew()), 4), "kurtosis": round(float(pd.Series(values).kurt()), 4),
        "expected_shortfall_5pct": round(float(values[values <= np.quantile(values, .05)].mean()), 2),
        "downside_deviation": round(float(np.sqrt(np.mean(np.minimum(values, 0) ** 2))), 4),
        "low_tail_dependence_components_without_period_signs": flag,
    }


def _two_sided_p(bootstrap: dict) -> float:
    one = float(bootstrap["p_value"])
    median = float(bootstrap.get("median", 0.0))
    low = float(bootstrap.get("low", median)); high = float(bootstrap.get("high", median))
    if abs(low) < 1e-15 and abs(median) < 1e-15 and abs(high) < 1e-15:
        return 1.0
    tail = one if median > 0 else 1 - one + float(bootstrap["minimum_p_value"])
    return min(1.0, 2 * tail)


def _deflated_sharpe(session_r: np.ndarray, trials: int) -> dict:
    if len(session_r) < 3 or np.std(session_r, ddof=1) == 0:
        return {"dsr_probability": 0.0, "trials": trials}
    sr = float(np.mean(session_r) / np.std(session_r, ddof=1) * math.sqrt(252))
    expected_max = NormalDist().inv_cdf(max(.500001, 1 - 1 / max(2, trials)))
    se = math.sqrt(max(1e-12, (1 + .5 * sr * sr) / (len(session_r) - 1)))
    return {"annualized_sharpe": round(sr, 5), "expected_max_null_sharpe": round(expected_max, 5),
            "dsr_probability": round(NormalDist().cdf((sr - expected_max) / se), 8), "trials": trials}


def _pbo(matrix: np.ndarray, blocks: int = 8) -> dict:
    if matrix.ndim != 2 or matrix.shape[1] < 4 or matrix.shape[0] < blocks * 4:
        return {"status": "not_meaningful", "reason": "insufficient sessions/configurations"}
    chunks = np.array_split(np.arange(matrix.shape[0]), blocks); logits = []
    for selected in itertools.combinations(range(blocks), blocks // 2):
        train_idx = np.concatenate([chunks[i] for i in selected]); test_idx = np.concatenate([chunks[i] for i in range(blocks) if i not in selected])
        train_score = matrix[train_idx].mean(axis=0); winner = int(np.argmax(train_score)); test_score = matrix[test_idx].mean(axis=0)
        rank = (np.argsort(np.argsort(test_score))[winner] + 1) / (len(test_score) + 1)
        logits.append(math.log(rank / (1 - rank)))
    return {"status": "computed", "blocks": blocks, "splits": len(logits), "pbo": round(float(np.mean(np.asarray(logits) <= 0)), 6), "median_logit": round(float(np.median(logits)), 6)}


def _feature_rows(day: date, signal: Signal, rth: list[Bar], overnight: list[Bar], prior: dict | None,
                  prior_vix: float | None, volume_history: dict[time, list[float]], day_events: list[dict], holiday_adjacent: bool,
                  vvg_history: list[dict]) -> list[dict]:
    cutoff = signal.ts
    completed = [bar for bar in rth if bar.ts < cutoff]
    opening = completed[:5]
    onh = max((b.high for b in overnight), default=None); onl = min((b.low for b in overnight), default=None)
    rth_open = rth[0].open; direction = 1 if signal.side == "long" else -1
    same_minute = completed[-1].ts.time() if completed else time(9, 30)
    past_volumes = volume_history.get(same_minute, [])[-20:]
    rel_volume = completed[-1].volume / np.median(past_volumes) if completed and past_volumes and np.median(past_volumes) else None
    pv = np.cumsum([((b.high+b.low+b.close)/3)*b.volume for b in completed]); vol = np.cumsum([b.volume for b in completed])
    vwaps = pv / np.where(vol == 0, np.nan, vol) if len(completed) else np.array([])
    vwap_slope = float(vwaps[-1] - vwaps[-6]) if len(vwaps) >= 6 else None
    future_events = [datetime.fromisoformat(row["actual_at"]) for row in day_events if datetime.fromisoformat(row["actual_at"]) >= cutoff]
    minutes_to_event = min(((event-cutoff).total_seconds()/60 for event in future_events), default=None)
    vvg = None
    if cutoff.time() >= time(10, 0) and prior and len(vvg_history) >= 20:
        gap = abs(rth[0].open-prior["close"]); first30 = abs(rth[29].close-rth[0].open) if len(rth) >= 30 else None
        first_volume = sum(bar.volume for bar in rth[:5]); history = vvg_history[-20:]
        vvg = bool(first30 is not None and gap >= np.median([row["gap"] for row in history]) and
                   first30 >= np.median([row["first30"] for row in history]) and
                   first_volume >= np.median([row["first_volume"] for row in history]))
    values = {
        "opening_range_size": max((b.high for b in opening), default=np.nan) - min((b.low for b in opening), default=np.nan),
        "overnight_opening_alignment": (direction == (1 if overnight and overnight[-1].close > overnight[0].open else -1)) if overnight else None,
        "distance_to_overnight_high": rth_open - onh if onh is not None else None,
        "distance_to_overnight_low": rth_open - onl if onl is not None else None,
        "distance_to_prior_day_high": rth_open - prior["high"] if prior else None,
        "distance_to_prior_day_low": rth_open - prior["low"] if prior else None,
        "prior_day_regime": prior.get("efficiency") if prior else None,
        "lagged_vix_regime": prior_vix,
        "scheduled_macro_event": bool(day_events), "time_to_scheduled_event_minutes": minutes_to_event,
        "ten_am_event": any(datetime.fromisoformat(row["actual_at"]).time() == time(10, 0) for row in day_events),
        "overnight_gap": rth_open - prior["close"] if prior else None,
        "same_time_relative_volume": rel_volume, "lag_safe_vwap_slope": vwap_slope,
        "holiday_adjacency": holiday_adjacent, "weekday": day.weekday(),
        "options_expiration": day.weekday() == 4 and 15 <= day.day <= 21,
        "month_quarter_end": (day + timedelta(days=1)).month != day.month,
        "lagged_large_prior_move": prior.get("range_z") if prior else None,
        "vvg_regime_score": vvg,
    }
    rows = []
    for name, value in values.items():
        available = value is not None and not (isinstance(value, float) and math.isnan(value))
        item = FeatureValue(name, value if available else None, cutoff, completed[-1].ts if completed else None,
                            "strictly before actual strategy entry", available)
        rows.append({"date": day.isoformat(), "strategy": signal.strategy, "entry_ts": cutoff.isoformat(), **item.to_dict()})
    return rows


def run_phase5(root: Path = Path("data"), smoke: bool = False, bootstrap_samples: int = 50_000) -> dict:
    specs = verify_preregistration()
    guard = ProtectedMarketDataGuard(root)
    manifest = guard.manifest()
    before = guard.checksums(manifest)
    degraded, _ = _condition_dates(root)
    schedule = mcal.get_calendar("NYSE").schedule("2018-01-01", "2025-12-31")
    if smoke: schedule = schedule[(schedule.index >= "2024-01-02") & (schedule.index <= "2024-01-12")]

    states: dict[str, dict] = {}
    delay_states: dict[str, dict[str, list[Trade]]] = defaultdict(lambda: {"one_minute": [], "one_signal_bar": []})
    accepted: dict[str, list[date]] = defaultdict(list)
    features: list[dict] = []
    ledger = [{"experiment_id": item["candidate_id"], "family": item["overlap_group"], "status": item["decision"], "reason": item["reason"]} for item in specs["candidates"]]
    vix_payload = json.loads((root / "fred/vixcls.json").read_text())
    vix = {row["date"]: float(row["value"]) for row in vix_payload["rows"]}
    macro_path = root / "macro/events-2018-2025.json"
    macro_payload = json.loads(macro_path.read_text()) if macro_path.exists() else {"events": []}
    macro_by_day: dict[str, list[dict]] = defaultdict(list)
    for event in macro_payload["events"]:
        if event.get("known_before_session"):
            macro_by_day[datetime.fromisoformat(event["actual_at"]).date().isoformat()].append(event)
    scheduled_dates = {index.date() for index in schedule.index}

    for symbol, fingerprint in (("NQ", NQ_FP), ("MNQ", MNQ_FP)):
        dataset = manifest["datasets"][fingerprint]
        roll_dates = _roll_dates([Path(part["mapping_path"]) for part in dataset["partitions"]])
        prior_tail = pd.DataFrame(); history_fives: list[Bar] = []; prior = None; prior_ranges: list[float] = []
        volume_history: dict[time, list[float]] = defaultdict(list)
        vvg_history: list[dict] = []
        for partition in sorted(dataset["partitions"], key=lambda row: int(row["year"])):
            year = int(partition["year"])
            if year >= 2026: raise RuntimeError("protected partition rejected before market read")
            if year < 2018 or (symbol == "MNQ" and year < 2019): continue
            if smoke and year != 2024: continue
            current = guard.read_parquet(partition["path"])
            frame = pd.concat([prior_tail, current], ignore_index=True).sort_values("ts_ny") if len(prior_tail) else current
            year_schedule = schedule[schedule.index.year == year]
            for session_day, calendar_row in year_schedule.iterrows():
                day = session_day.date(); market_open = calendar_row.market_open.tz_convert("America/New_York"); market_close = calendar_row.market_close.tz_convert("America/New_York")
                rth_frame = frame[(frame.ts_ny >= market_open) & (frame.ts_ny < market_close)].copy()
                ok, _ = _quality(day, rth_frame, int((market_close-market_open).total_seconds()/60), degraded, roll_dates)
                if not ok or (symbol == "MNQ" and day < date(2019, 5, 6)): continue
                accepted[symbol].append(day)
                rth = [_bar(row) for row in rth_frame.itertuples(index=False)]
                contexts = _contexts(frame, day, market_open, [])
                overnight = contexts["full_overnight"]
                signals = {**candidate_signals(rth, overnight, history_fives, prior), **baseline_signals(rth, overnight)}
                for candidate, candidate_items in signals.items():
                    if not candidate_items: continue
                    for overlay in ("matched_4R", "matched_EOD"):
                        for sizing in ("fixed1", "risk1"):
                            key = f"{symbol}:{candidate}:{overlay}:{sizing}"
                            state = states.setdefault(key, {"equity": 100_000.0, "trades": [], "period_equity": {name: 100_000.0 for name in PERIOD_BOUNDS}, "period_trades": {name: [] for name in PERIOD_BOUNDS}})
                            trade = _execute(candidate_items[0], rth, symbol, state["equity"], overlay, sizing, f"{key}:{day}")
                            if trade:
                                trade.synthetic = False; state["trades"].append(trade); state["equity"] += trade.net_pnl
                            period = _period(day.year)
                            if period:
                                p_trade = _execute(candidate_items[0], rth, symbol, state["period_equity"][period], overlay, sizing, f"{key}:{period}:{day}")
                                if p_trade:
                                    p_trade.synthetic = False; state["period_trades"][period].append(p_trade); state["period_equity"][period] += p_trade.net_pnl
                    robustness_key = f"{symbol}:{candidate}:matched_4R:fixed1"
                    robustness_equity = 100_000 + sum(t.net_pnl for t in delay_states[robustness_key]["one_minute"])
                    delayed = _delay_signal(candidate_items[0], rth, 1)
                    if delayed:
                        delayed_trade = _execute(delayed, rth, symbol, robustness_equity, "matched_4R", "fixed1", f"{robustness_key}:delay1:{day}")
                        if delayed_trade: delay_states[robustness_key]["one_minute"].append(delayed_trade)
                    bar_minutes = 15 if candidate == "C01" else 1 if candidate == "C17" else 5
                    bar_equity = 100_000 + sum(t.net_pnl for t in delay_states[robustness_key]["one_signal_bar"])
                    bar_delayed = _delay_signal(candidate_items[0], rth, bar_minutes)
                    if bar_delayed:
                        bar_trade = _execute(bar_delayed, rth, symbol, bar_equity, "matched_4R", "fixed1", f"{robustness_key}:delaybar:{day}")
                        if bar_trade: delay_states[robustness_key]["one_signal_bar"].append(bar_trade)
                    if symbol == "NQ":
                        prior_vix = next((vix.get((day-timedelta(days=i)).isoformat()) for i in range(1, 8) if vix.get((day-timedelta(days=i)).isoformat()) is not None), None)
                        holiday_adjacent = ((day-timedelta(days=1)).weekday() < 5 and day-timedelta(days=1) not in scheduled_dates) or ((day+timedelta(days=1)).weekday() < 5 and day+timedelta(days=1) not in scheduled_dates)
                        features.extend(_feature_rows(day, candidate_items[0], rth, overnight, prior, prior_vix, volume_history, macro_by_day.get(day.isoformat(), []), holiday_adjacent, vvg_history))
                day_range = max(b.high for b in rth) - min(b.low for b in rth)
                prior_ranges.append(day_range)
                if prior and len(rth) >= 30:
                    vvg_history.append({"gap": abs(rth[0].open-prior["close"]), "first30": abs(rth[29].close-rth[0].open), "first_volume": sum(bar.volume for bar in rth[:5])})
                prior = {"high": max(b.high for b in rth), "low": min(b.low for b in rth), "open": rth[0].open, "close": rth[-1].close,
                         "efficiency": abs(rth[-1].close-rth[0].open)/day_range if day_range else 0,
                         "range_z": (day_range-np.mean(prior_ranges[-20:]))/np.std(prior_ranges[-20:]) if len(prior_ranges) >= 20 and np.std(prior_ranges[-20:]) else 0}
                history_fives.extend(aggregate_five_minute(rth)); history_fives = history_fives[-1000:]
                for bar in rth: volume_history[bar.ts.time()].append(bar.volume)
            cutoff = current.ts_ny.max() - pd.Timedelta(days=4); prior_tail = current[current.ts_ny >= cutoff].copy()

    # The no-trade control is explicit: every eligible session is a zero return,
    # and it participates in the experiment ledger/inference like other baselines.
    for symbol in ("NQ", "MNQ"):
        if accepted[symbol]:
            for overlay in ("matched_4R", "matched_EOD"):
                for sizing in ("fixed1", "risk1"):
                    states[f"{symbol}:BASE_NONE:{overlay}:{sizing}"] = {
                        "equity": 100_000.0, "trades": [],
                        "period_equity": {name: 100_000.0 for name in PERIOD_BOUNDS},
                        "period_trades": {name: [] for name in PERIOD_BOUNDS},
                    }

    summaries = {}; session_arrays = {}; family_p = defaultdict(list)
    for key, state in states.items():
        symbol, candidate, overlay, sizing = key.split(":")
        natural_days = accepted[symbol]
        item = _trade_metrics(state["trades"], natural_days)
        item["periods"] = {name: _trade_metrics(state["period_trades"][name], [d for d in natural_days if bounds[0] <= d.year <= bounds[1]]) for name, bounds in PERIOD_BOUNDS.items()}
        item["tail"] = _tail_tests(state["trades"]); item["family"] = FAMILIES.get(candidate, "other")
        arrays = np.asarray(item.pop("session_r")); session_arrays[key] = arrays
        for period in item["periods"].values(): period.pop("session_r", None)
        stressed = {}
        for multiplier in (1, 2, 4):
            pnl = sum(t.gross_pnl - t.total_costs * multiplier for t in state["trades"])
            stressed[str(multiplier)] = round(pnl, 2)
        item["cost_stress_net"] = stressed
        if key in delay_states:
            item["delay_stress"] = {
                label: _trade_metrics(rows, natural_days) for label, rows in delay_states[key].items()
            }
            for delay_item in item["delay_stress"].values(): delay_item.pop("session_r", None)
        period_positive = item["periods"]["validation"]["net_profit"] > 0 and item["periods"]["historical_evaluation"]["net_profit"] > 0
        item["tail"]["low_tail_dependence"] = bool(item["tail"].get("low_tail_dependence_components_without_period_signs") and period_positive)
        summaries[key] = item

    # Paired candidate-vs-first-candle inference on identical accepted sessions.
    inference = {}; trial_count = len(states) + len(ledger)
    comparable_keys = [key for key in summaries if key.startswith("NQ:") and key.endswith(":matched_4R:fixed1")]
    benchmark_key = "NQ:BASE_CANDLE:matched_4R:fixed1"
    if benchmark_key in session_arrays and comparable_keys:
        benchmark = session_arrays[benchmark_key]
        matrix = np.column_stack([session_arrays[key] for key in comparable_keys])
        raw = []
        for index, key in enumerate(comparable_keys):
            boot = stationary_bootstrap_mean(matrix[:, index] - benchmark, bootstrap_samples, 10, 5500 + index)
            boot["two_sided_raw_p"] = _two_sided_p(boot); raw.append(boot["two_sided_raw_p"]); inference[key] = boot
        bh, by = adjusted_p_values(raw, "bh"), adjusted_p_values(raw, "by")
        for key, bhp, byp in zip(comparable_keys, bh, by):
            inference[key]["bh_adjusted_p"] = round(bhp, 8); inference[key]["by_adjusted_p"] = round(byp, 8)
            family_p[FAMILIES.get(key.split(":")[1], "other")].append(inference[key]["two_sided_raw_p"])
        for family in sorted({FAMILIES.get(key.split(":")[1], "other") for key in comparable_keys}):
            keys = [key for key in comparable_keys if FAMILIES.get(key.split(":")[1], "other") == family]
            family_raw = [inference[key]["two_sided_raw_p"] for key in keys]
            family_bh = adjusted_p_values(family_raw, "bh"); family_by = adjusted_p_values(family_raw, "by")
            for key, bhp, byp in zip(keys, family_bh, family_by):
                inference[key]["family"] = family
                inference[key]["family_bh_adjusted_p"] = round(bhp, 8)
                inference[key]["family_by_adjusted_p"] = round(byp, 8)
        rc = reality_check(matrix, benchmark, bootstrap_samples, 10, 5601)
        pbo = _pbo(matrix)
    else:
        rc = {"status": "unavailable"}; pbo = {"status": "unavailable"}

    dispositions = {}
    for item in specs["candidates"]:
        candidate = item["candidate_id"]; key = f"NQ:{candidate}:matched_4R:fixed1"
        if item["decision"].startswith("defer") or item["decision"] == "duplicate_excluded":
            dispositions[candidate] = {"evidence": "inconclusive", "failed_gates": [item["decision"]], "reason": item["reason"]}; continue
        if item["decision"] == "negative_control":
            dispositions[candidate] = {"evidence": "inconclusive", "failed_gates": ["negative_control_not_selection_eligible"], "reason": item["reason"]}; continue
        result = summaries.get(key)
        if not result:
            dispositions[candidate] = {"evidence": "rejected", "failed_gates": ["no_executable_signals"], "reason": "No valid signal survived data and execution checks."}; continue
        validation = result["periods"]["validation"]; evaluation = result["periods"]["historical_evaluation"]
        risk_result = summaries.get(f"NQ:{candidate}:matched_4R:risk1", {})
        days = accepted["NQ"]
        candidate_array = session_arrays.get(key, np.zeros(len(days)))
        benchmark_array = session_arrays.get(benchmark_key, np.zeros(len(days)))
        validation_mask = np.asarray([2022 <= day.year <= 2023 for day in days]); evaluation_mask = np.asarray([2024 <= day.year <= 2025 for day in days])
        paired_validation = float(np.mean(candidate_array[validation_mask] - benchmark_array[validation_mask])) if validation_mask.any() else 0
        paired_evaluation = float(np.mean(candidate_array[evaluation_mask] - benchmark_array[evaluation_mask])) if evaluation_mask.any() else 0
        delay = result.get("delay_stress", {})
        gates = {
            "positive_validation": validation["expectancy_session_r"] > 0,
            "positive_historical_evaluation": evaluation["expectancy_session_r"] > 0,
            "sample_size": result["trades"] >= 200 and validation["trades"] >= 40 and evaluation["trades"] >= 40,
            "six_positive_years": result["positive_years"] >= 6,
            "positive_2x_costs": result["cost_stress_net"]["2"] > 0,
            "low_tail_dependence": result["tail"]["low_tail_dependence"],
            "one_minute_delay_positive": delay.get("one_minute", {}).get("net_profit", 0) > 0,
            "one_signal_bar_delay_positive": delay.get("one_signal_bar", {}).get("net_profit", 0) > 0,
            "drawdown_under_30pct": bool(risk_result) and abs(risk_result["max_drawdown"]) <= .30,
            "positive_paired_effect_validation": paired_validation > 0,
            "positive_paired_effect_historical_evaluation": paired_evaluation > 0,
        }
        failed = [name for name, passed in gates.items() if not passed]
        evidence = "robust_historical_candidate" if not failed else "promising_exploratory" if result["net_profit"] > 0 and validation["net_profit"] > 0 else "rejected" if validation["net_profit"] <= 0 and evaluation["net_profit"] <= 0 else "inconclusive"
        dispositions[candidate] = {"evidence": evidence, "failed_gates": failed, "gates": gates,
                                   "paired_effect_session_r": {"validation": round(paired_validation, 6), "historical_evaluation": round(paired_evaluation, 6)},
                                   "reason": "Strict preregistered gates applied without relaxation."}

    for key in comparable_keys:
        summaries[key]["deflated_sharpe"] = _deflated_sharpe(session_arrays[key], trial_count)
    trade_lookup = {}
    for key, state in states.items():
        if key.startswith("NQ:") and key.endswith(":matched_4R:fixed1"):
            trade_lookup[key] = {trade.entry_ts.date().isoformat(): trade for trade in state["trades"]}
    for row in features:
        trade = trade_lookup.get(f"NQ:{row['strategy']}:matched_4R:fixed1", {}).get(row["date"])
        row.update({
            "net_r": trade.realized_r if trade else 0.0, "net_pnl": trade.net_pnl if trade else 0.0,
            "win": bool(trade and trade.net_pnl > 0), "stop_out": bool(trade and "stop" in trade.outcome),
            "mae_points": trade.mae_points if trade else None, "mfe_points": trade.mfe_points if trade else None,
            "tail_winner": False, "drawdown_contribution": min(0.0, trade.net_pnl) if trade else 0.0,
        })
    by_strategy_trades = defaultdict(list)
    for row in features:
        if row["name"] == "opening_range_size" and row["net_pnl"]:
            by_strategy_trades[row["strategy"]].append(row)
    for rows in by_strategy_trades.values():
        threshold = np.quantile([row["net_pnl"] for row in rows], .99)
        dates = {row["date"] for row in rows if row["net_pnl"] >= threshold}
        for row in features:
            if row["strategy"] == rows[0]["strategy"] and row["date"] in dates: row["tail_winner"] = True

    after = guard.checksums(manifest)
    immutable = before == after
    if not immutable: raise RuntimeError("raw cache immutability failure")
    result = {
        "schema_version": 1, "generated_at": datetime.now(NY).isoformat(), "smoke": smoke,
        "data_window": "2018-2025 preserved cache only", "holdout_guard": {"status": "UNTOUCHED", "protected_boundary": "2025-12-31", "rejected_before_read": True},
        "preregistration": json.loads(LOCK.read_text()), "candidate_dispositions": dispositions,
        "accepted_sessions": {key: len(value) for key, value in accepted.items()}, "summaries": summaries,
        "inference": {"unit": "eligible session with no-trade zero", "bootstrap_resamples": bootstrap_samples, "expected_block_sessions": 10,
                      "paired_vs_first_candle": inference, "white_reality_check_spa": rc, "pbo_cscv": pbo,
                      "honest_configuration_count": trial_count},
        "raw_cache": {"immutable": immutable, "before": before, "after": after}, "experiment_ledger": ledger,
        "limitations": ["One-minute OHLCV cannot reconstruct tick order, queue position, L2, footprint, true delta, or volume-at-price.",
                        "Macro coverage is limited to official/FRED-indexed BLS, BEA, and Federal Reserve releases with verified historical dates; Census retail sales and private ISM remain excluded.",
                        "All 2018-2025 observations have been inspected historically; 2024-2025 is evaluation, not a clean holdout."],
    }
    if not smoke:
        destination = root / "research"; destination.mkdir(parents=True, exist_ok=True)
        (destination / "phase5-results.json").write_text(json.dumps(result, indent=2, default=str))
        trade_rows = [{"run_key": key, **trade.to_dict()} for key, state in states.items() for trade in state["trades"]]
        pd.DataFrame(trade_rows).to_parquet(destination / "phase5-trades.parquet", index=False, compression="zstd")
        pd.DataFrame(features).to_parquet(destination / "phase5-features.parquet", index=False, compression="zstd")
        with (destination / "phase5-tournament.csv").open("w", newline="") as handle:
            writer = csv.writer(handle); writer.writerow(["run_key","family","trades","net_profit","expectancy_session_r","max_drawdown","positive_years","cost_2x_net","low_tail_dependence"])
            for key, item in summaries.items(): writer.writerow([key,item["family"],item["trades"],item["net_profit"],item["expectancy_session_r"],item["max_drawdown"],item["positive_years"],item["cost_stress_net"]["2"],item["tail"]["low_tail_dependence"]])
    return result
