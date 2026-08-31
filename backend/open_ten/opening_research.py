from __future__ import annotations

import json
import math
from bisect import bisect_left
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from arch.bootstrap import SPA

from .analytics import max_drawdown
from .engine import ExecutionConfig, INSTRUMENTS, execute_signal, round_to_tick, round_trip_cost_per_contract
from .models import Bar, Signal

NY = ZoneInfo("America/New_York")
NQ_FP = "e0ae8898e1f56f76"
TARGETS = (1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5)
PERIODS = {"discovery": (2018, 2021), "validation": (2022, 2023), "historical_evaluation": (2024, 2025)}
CONTROL_VARIANTS = {
    "first_candle_only": "NQ:B_CANDLE_4R_fixed1",
    "full_overnight_ema": "NQ:B_EMA_FULL_4R_fixed1",
    "candle_and_ema_agreement": "NQ:B_EMA_BODY_4R_fixed1",
    "same_day_ema": "NQ:B_EMA_SAME_DAY_4R_fixed1",
    "overnight_direction": "NQ:B_OVERNIGHT_4R_fixed1",
    "seeded_random": "NQ:B_RANDOM_4R_fixed1",
    "always_long": "NQ:B_ALWAYS_LONG_4R_fixed1",
    "always_short": "NQ:B_ALWAYS_SHORT_4R_fixed1",
}


def _dates(frame: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(frame.entry_ts, utc=True).dt.date


def _metrics(frame: pd.DataFrame, starting: float = 100_000, pnl_column: str = "net_pnl") -> dict:
    if frame.empty:
        return {"net_profit": 0, "average_trade": 0, "trades": 0, "win_rate": 0, "profit_factor": None, "max_drawdown": 0, "sharpe_session": 0, "expectancy_r": 0, "total_costs": 0, "positive_years": 0, "years": 0, "by_year": {}, "long": {}, "short": {}, "max_consecutive_losses": 0}
    frame = frame.sort_values("entry_ts").copy()
    pnl = frame[pnl_column].to_numpy(float)
    equity = np.r_[starting, starting + np.cumsum(pnl)]
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    dd, duration = max_drawdown(equity.tolist())
    realized = frame.realized_r.to_numpy(float) if "realized_r" in frame else pnl / starting
    std = float(np.std(realized, ddof=1)) if len(realized) > 1 else 0
    years = pd.to_datetime(frame.entry_ts, utc=True).dt.year
    by_year = frame.assign(_year=years).groupby("_year")[pnl_column].sum().to_dict()
    streak = best = 0
    for value in pnl:
        streak = streak + 1 if value < 0 else 0
        best = max(best, streak)
    side_metrics = {}
    if "side" in frame:
        for side in ("long", "short"):
            selected = frame[frame.side == side]
            side_metrics[side] = {"trades": int(len(selected)), "net_profit": round(float(selected[pnl_column].sum()), 2), "average_trade": round(float(selected[pnl_column].mean()), 2) if len(selected) else 0, "win_rate": round(float((selected[pnl_column] > 0).mean()), 4) if len(selected) else 0}
    return {
        "net_profit": round(float(pnl.sum()), 2), "total_return": round(float(pnl.sum() / starting), 6),
        "average_trade": round(float(pnl.mean()), 2), "trades": int(len(frame)),
        "win_rate": round(float((pnl > 0).mean()), 4),
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 3) if len(losses) else None,
        "max_drawdown": round(float(dd), 6), "drawdown_duration_trades": duration,
        "sharpe_session": round(float(np.mean(realized) / std * math.sqrt(252)), 3) if std else 0,
        "expectancy_r": round(float(np.mean(realized)), 4),
        "total_costs": round(float(frame.total_costs.sum()), 2) if "total_costs" in frame else 0,
        "positive_years": int(sum(value > 0 for value in by_year.values())), "years": len(by_year),
        "by_year": {str(int(year)): round(float(value), 2) for year, value in sorted(by_year.items())},
        "long": side_metrics.get("long", {}), "short": side_metrics.get("short", {}),
        "max_consecutive_losses": best,
    }


def _period_metrics(frame: pd.DataFrame) -> dict:
    years = pd.to_datetime(frame.entry_ts, utc=True).dt.year
    return {name: _metrics(frame[(years >= bounds[0]) & (years <= bounds[1])]) for name, bounds in PERIODS.items()}


def _load_trades(root: Path) -> pd.DataFrame:
    frame = pd.read_parquet(root / "research/trades.parquet")
    frame["entry_date"] = pd.to_datetime(frame.entry_ts, utc=True).dt.date
    return frame


def _comparisons(trades: pd.DataFrame) -> tuple[dict, list[date]]:
    frames = {name: trades[trades.run_variant == variant].copy() for name, variant in CONTROL_VARIANTS.items()}
    shared = sorted(set.intersection(*(set(frame.entry_date) for frame in frames.values())))
    first_dates = set(frames["first_candle_only"].entry_date)
    first_frame = frames["first_candle_only"]
    output = {}
    for name, frame in frames.items():
        matched = frame[frame.entry_date.isin(shared)]
        pair_dates = first_dates & set(frame.entry_date)
        pair_matched = frame[frame.entry_date.isin(pair_dates)]
        first_pair = first_frame[first_frame.entry_date.isin(pair_dates)]
        output[name] = {
            "natural": _metrics(frame), "natural_periods": _period_metrics(frame),
            "shared": _metrics(matched), "shared_periods": _period_metrics(matched),
            "shared_with_first_candle": _metrics(pair_matched),
            "shared_with_first_candle_periods": _period_metrics(pair_matched),
            "first_candle_on_same_pair_sessions": _metrics(first_pair),
            "first_candle_on_same_pair_periods": _period_metrics(first_pair),
            "shared_with_first_candle_sessions": len(pair_dates),
        }
    return output, shared


def _cost_stress(frame: pd.DataFrame, matched_dates: set[date]) -> dict:
    selected = frame[frame.entry_date.isin(matched_dates)].sort_values("entry_ts").copy()
    baseline_cost = float(selected.total_costs.median())
    rows = []
    for multiplier in np.arange(1, 4.01, .5):
        stressed = selected.copy()
        stressed["net_stress"] = stressed.gross_pnl - stressed.total_costs * multiplier
        stressed["realized_r"] = stressed.net_stress / ((stressed.reference_entry - stressed.stop).abs() * 20)
        stressed["total_costs"] = stressed.total_costs * multiplier
        result = _metrics(stressed, pnl_column="net_stress")
        rows.append({"multiplier": float(multiplier), "all_in_round_trip_cost": round(baseline_cost * multiplier, 2), **result})
    break_even_multiplier = float(selected.gross_pnl.sum() / selected.total_costs.sum())
    return {"same_trades_at_every_level": int(len(selected)), "baseline_all_in_round_trip_cost": round(baseline_cost, 2), "break_even_multiplier": round(break_even_multiplier, 3), "break_even_all_in_round_trip_cost": round(baseline_cost * break_even_multiplier, 2), "levels": rows}


def _account_replay(frame: pd.DataFrame, symbol: str, starting: float, cost_multiplier: float) -> dict:
    spec = INSTRUMENTS[symbol]
    margin = 22_000 if symbol == "NQ" else 2_200
    equity = float(starting)
    curve = [equity]
    sizes, realized_risk = [], []
    skipped_risk = skipped_margin = 0
    for row in frame.sort_values("entry_ts").itertuples(index=False):
        stop_points = abs(float(row.reference_entry) - float(row.stop))
        cost = float(row.total_costs) * cost_multiplier
        risk_per_contract = stop_points * spec.point_value + cost
        risk_size = math.floor(equity * .01 / risk_per_contract) if equity > 0 else 0
        margin_size = math.floor(equity / margin) if equity > 0 else 0
        contracts = min(risk_size, margin_size, 20)
        if contracts < 1:
            if margin_size < 1:
                skipped_margin += 1
            else:
                skipped_risk += 1
            continue
        sizes.append(contracts)
        realized_risk.append(contracts * risk_per_contract / equity)
        equity += contracts * (float(row.gross_pnl) - cost)
        curve.append(equity)
        if equity <= 0:
            break
    drawdown, _ = max_drawdown(curve)
    return {
        "starting_balance": starting, "cost_multiplier": cost_multiplier, "eligible_trades": int(len(frame)),
        "executed_trades": len(sizes), "skipped_trades": skipped_risk + skipped_margin,
        "skipped_risk": skipped_risk, "skipped_margin": skipped_margin,
        "average_contracts": round(float(np.mean(sizes)), 3) if sizes else 0,
        "median_contracts": round(float(np.median(sizes)), 3) if sizes else 0,
        "maximum_contracts": max(sizes, default=0),
        "average_realized_risk_fraction": round(float(np.mean(realized_risk)), 6) if realized_risk else 0,
        "ending_equity": round(equity, 2), "net_profit": round(equity - starting, 2),
        "total_return": round(equity / starting - 1, 6), "max_drawdown": round(drawdown, 6),
        "survived": equity > 0, "minimum_equity": round(min(curve), 2),
    }


def _account_feasibility(trades: pd.DataFrame) -> dict:
    output = {}
    for strategy, suffix in (("first_candle_only", "B_CANDLE_4R_fixed1"), ("full_overnight_ema", "B_EMA_FULL_4R_fixed1")):
        output[strategy] = {}
        for symbol in ("NQ", "MNQ"):
            frame = trades[trades.run_variant == f"{symbol}:{suffix}"].copy()
            output[strategy][symbol] = [_account_replay(frame, symbol, balance, multiplier) for balance in (10_000, 25_000, 50_000, 100_000) for multiplier in (1, 2, 4)]
    return output


def _concentration(frame: pd.DataFrame) -> dict:
    frame = frame.sort_values("entry_ts").copy()
    net = float(frame.net_pnl.sum())
    gross_profit = float(frame.loc[frame.net_pnl > 0, "net_pnl"].sum())
    ordered = frame.sort_values("net_pnl", ascending=False)

    def removal(label: str, removed: pd.DataFrame) -> dict:
        contribution = float(removed.net_pnl.sum())
        remaining = frame.drop(removed.index)
        return {"label": label, "removed_trades": int(len(removed)), "removed_pnl": round(contribution, 2), "share_of_gross_profit": round(contribution / gross_profit, 6) if gross_profit else 0, "share_of_net_profit": round(contribution / net, 6) if net else None, "remaining": _metrics(remaining)}

    results = {}
    for count in (1, 5, 10, 20):
        results[f"best_{count}_trades"] = removal(f"Best {count} trades", ordered.head(count))
    for fraction in (.01, .05):
        count = math.ceil(len(frame) * fraction)
        results[f"best_{int(fraction * 100)}pct_sessions"] = removal(f"Best {fraction:.0%} of sessions", ordered.head(count))
    timestamps = pd.to_datetime(frame.entry_ts, utc=True).dt.tz_convert(None)
    periods = {
        "best_month": timestamps.dt.to_period("M"),
        "best_quarter": timestamps.dt.to_period("Q"),
        "best_year": timestamps.dt.year,
    }
    for label, keys in periods.items():
        totals = frame.assign(_period=keys).groupby("_period").net_pnl.sum()
        best = totals.idxmax()
        selected = frame[keys == best]
        item = removal(label.replace("_", " ").title(), selected)
        item["period"] = str(best)
        results[label] = item
    return {"original": _metrics(frame), "gross_profit_definition": "sum of positive net trade outcomes", "tests": results}


def _random_miss(frame: pd.DataFrame, fraction: float, seed: int, reps: int = 5_000) -> dict:
    values = frame.net_pnl.to_numpy(float)
    rng = np.random.default_rng(seed)
    totals = []
    for offset in range(0, reps, 500):
        size = min(500, reps - offset)
        capture = rng.random((size, len(values))) >= fraction
        totals.append(capture @ values)
    draws = np.concatenate(totals)
    low, median, high = np.quantile(draws, [.025, .5, .975])
    return {"miss_fraction": fraction, "repetitions": reps, "low_net_profit": round(float(low), 2), "median_net_profit": round(float(median), 2), "high_net_profit": round(float(high), 2), "probability_profitable": round(float(np.mean(draws > 0)), 6), "expected_captured_trades": round(len(values) * (1 - fraction), 1), "seed": seed}


def _bar(row) -> Bar:
    return Bar(row.ts_ny.to_pydatetime(), float(row.open), float(row.high), float(row.low), float(row.close), int(row.volume), int(row.instrument_id))


def _managed_trade(signal: Signal, bars: list[Bar], mode: str) -> dict:
    entry = round_to_tick(signal.entry)
    direction = 1 if signal.side == "long" else -1
    stop = round_to_tick(signal.stop, mode="down" if signal.side == "long" else "up")
    risk = abs(entry - stop)
    target = round_to_tick(entry + direction * risk * 4)
    active_stop = stop
    reference_exit, exit_ts, outcome = entry, signal.ts, "session_exit"
    best = entry
    for bar in bars:
        stop_hit = bar.low <= active_stop if signal.side == "long" else bar.high >= active_stop
        target_hit = bar.high >= target if signal.side == "long" else bar.low <= target
        if stop_hit:
            reference_exit = min(bar.open, active_stop) if signal.side == "long" else max(bar.open, active_stop)
            exit_ts, outcome = bar.ts, "managed_stop"
            break
        if target_hit:
            reference_exit, exit_ts, outcome = target, bar.ts, "target"
            break
        reference_exit, exit_ts = bar.close, bar.ts
        best = max(best, bar.high) if signal.side == "long" else min(best, bar.low)
        favorable = direction * (best - entry)
        if mode == "break_even_1r" and favorable >= risk:
            active_stop = max(active_stop, entry) if signal.side == "long" else min(active_stop, entry)
        elif mode == "trail_1r_after_2r" and favorable >= 2 * risk:
            proposed = best - direction * risk
            active_stop = max(active_stop, proposed) if signal.side == "long" else min(active_stop, proposed)
        elif mode == "trail_1r_after_1r" and favorable >= risk:
            proposed = best - direction * risk
            active_stop = max(active_stop, proposed) if signal.side == "long" else min(active_stop, proposed)
    gross = direction * (reference_exit - entry) * 20
    cost = round_trip_cost_per_contract("NQ", ExecutionConfig(fixed_contracts=1))
    net = gross - cost
    return {"entry_ts": signal.ts.isoformat(), "side": signal.side, "net_pnl": round(net, 2), "gross_pnl": round(gross, 2), "total_costs": cost, "realized_r": round(net / (risk * 20), 6), "outcome": outcome, "exit_ts": exit_ts.isoformat()}


def _vix_lookup(root: Path):
    payload = json.loads((root / "fred/vixcls.json").read_text())
    rows = payload["rows"]
    dates = [row["date"] for row in rows]
    values = [float(row["value"]) for row in rows]

    def prior(day: date):
        index = bisect_left(dates, day.isoformat()) - 1
        return values[index] if index >= 0 else None

    return prior


def _raw_experiments(root: Path, accepted: dict[date, int]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    manifest = json.loads((root / "manifest.json").read_text())
    entry = manifest["datasets"][NQ_FP]
    if entry["request"]["end"] > "2026-01-01" or any(int(part["year"]) >= 2026 for part in entry["partitions"]):
        raise RuntimeError("2026 is reserved")
    prior_vix = _vix_lookup(root)
    features, target_rows, exit_rows = [], [], []
    fixed = ExecutionConfig(fixed_contracts=1, max_contracts=1, margin_per_contract=22_000)
    prior_tail = pd.DataFrame()
    previous_close = previous_range = None
    close_history: list[float] = []
    for part in sorted(entry["partitions"], key=lambda item: item["year"]):
        year = int(part["year"])
        if year < 2017:
            continue
        if year >= 2026:
            raise RuntimeError("refusing to inspect 2026")
        print(f"Opening-candle experiments: NQ {year}", flush=True)
        current = pd.read_parquet(part["path"]).sort_index().reset_index()
        if "ts_event" not in current:
            current = current.rename(columns={current.columns[0]: "ts_event"})
        current["ts_ny"] = pd.to_datetime(current.ts_event, utc=True).dt.tz_convert("America/New_York")
        combined = pd.concat([prior_tail, current], ignore_index=True).sort_values("ts_ny") if len(prior_tail) else current
        days = sorted(day for day in accepted if day.year == year)
        for day in days:
            start = pd.Timestamp(datetime.combine(day - timedelta(days=1), time(18), NY))
            end = pd.Timestamp(datetime.combine(day, time(16), NY))
            session = combined[(combined.ts_ny >= start) & (combined.ts_ny < end)]
            market_close = pd.Timestamp(datetime.combine(day, time(9, 30), NY)) + pd.Timedelta(minutes=accepted[day])
            rth = session[(session.ts_ny >= pd.Timestamp(datetime.combine(day, time(9, 30), NY))) & (session.ts_ny < market_close)]
            opening = rth[(rth.ts_ny.dt.time >= time(9, 30)) & (rth.ts_ny.dt.time <= time(9, 34))]
            if len(opening) != 5:
                continue
            bars = [_bar(row) for row in rth.itertuples(index=False)]
            first = bars[0]
            open_price, close_price = float(opening.iloc[0].open), float(opening.iloc[-1].close)
            high, low = float(opening.high.max()), float(opening.low.min())
            if close_price == open_price:
                previous_close, previous_range = float(rth.iloc[-1].close), float(rth.high.max() - rth.low.min())
                close_history.append(previous_close)
                continue
            side = "long" if close_price > open_price else "short"
            entry_bar = next((bar for bar in bars if bar.ts.time() == time(9, 35)), None)
            if entry_bar is None:
                continue
            stop = low if side == "long" else high
            if (side == "long" and entry_bar.open <= stop) or (side == "short" and entry_bar.open >= stop):
                continue
            signal = Signal(entry_bar.ts, "First candle", "CANDLE", side, entry_bar.open, stop, 4, "opening candle direction", entry_bar.ts, {})
            future = [bar for bar in bars if bar.ts >= entry_bar.ts and bar.ts.time() <= time(15, 55)]
            base = execute_signal(signal, future, 100_000, "NQ", fixed, f"raw-{day}")
            if base is None:
                continue
            overnight = session[session.ts_ny < pd.Timestamp(datetime.combine(day, time(9, 30), NY))]
            overnight_open = float(overnight.iloc[0].open) if len(overnight) else None
            overnight_close = float(overnight.iloc[-1].close) if len(overnight) else None
            overnight_return = overnight_close - overnight_open if overnight_open is not None else None
            overnight_range = float(overnight.high.max() - overnight.low.min()) if len(overnight) else None
            body = abs(close_price - open_price)
            total_range = high - low
            one_minute = next((bar for bar in bars if bar.ts.time() == time(9, 36)), None)
            two_minute = next((bar for bar in bars if bar.ts.time() == time(9, 37)), None)
            moved_away = bool(one_minute and ((side == "long" and one_minute.open >= entry_bar.open + .25) or (side == "short" and one_minute.open <= entry_bar.open - .25)))
            bull = bool(len(close_history) >= 50 and previous_close is not None and previous_close > mean(close_history[-50:]))
            row = {
                "date": day.isoformat(), "entry_ts": entry_bar.ts.isoformat(), "side": side,
                "opening_color": "green" if side == "long" else "red", "opening_open": open_price, "opening_close": close_price,
                "opening_range": total_range, "opening_body": body, "body_to_range": body / total_range if total_range else 0,
                "upper_wick": high - max(open_price, close_price), "lower_wick": min(open_price, close_price) - low,
                "overnight_return": overnight_return, "overnight_range": overnight_range,
                "overnight_direction": "up" if overnight_return and overnight_return > 0 else "down" if overnight_return and overnight_return < 0 else "flat",
                "previous_day_range": previous_range, "opening_gap": open_price - previous_close if previous_close is not None else None,
                "gap_direction": "up" if previous_close is not None and open_price > previous_close else "down" if previous_close is not None and open_price < previous_close else "flat",
                "prior_vix": prior_vix(day), "day_of_week": day.strftime("%A"), "month": day.month, "year": day.year,
                "market_regime": "bullish" if bull else "bearish", "entry_moved_away_1m": moved_away,
                "one_minute_open": one_minute.open if one_minute else None, "two_minute_open": two_minute.open if two_minute else None,
                "base_net_pnl": base.net_pnl, "base_realized_r": base.realized_r, "base_outcome": base.outcome,
            }
            features.append(row)
            for target in TARGETS:
                target_signal = Signal(signal.ts, signal.strategy, f"{target}R", side, signal.entry, signal.stop, target, signal.reason, signal.available_at, {})
                trade = execute_signal(target_signal, future, 100_000, "NQ", fixed, f"target-{target}-{day}")
                if trade:
                    target_rows.append({"date": day.isoformat(), "entry_ts": trade.entry_ts.isoformat(), "side": side, "target_r": target, "net_pnl": trade.net_pnl, "gross_pnl": trade.gross_pnl, "total_costs": trade.total_costs, "realized_r": trade.realized_r, "outcome": trade.outcome})
            for label, cutoff, target in (("fixed_eod", time(15, 55), 100), ("exit_1030", time(10, 30), 4), ("exit_1130", time(11, 30), 4), ("exit_1300", time(13, 0), 4), ("exit_1500", time(15, 0), 4)):
                truncated = [bar for bar in future if bar.ts.time() <= cutoff]
                exit_signal = Signal(signal.ts, signal.strategy, label, side, signal.entry, signal.stop, target, signal.reason, signal.available_at, {})
                trade = execute_signal(exit_signal, truncated, 100_000, "NQ", fixed, f"{label}-{day}")
                if trade:
                    exit_rows.append({"date": day.isoformat(), "variant": label, **{key: getattr(trade, key) for key in ("net_pnl", "gross_pnl", "total_costs", "realized_r", "outcome")}, "entry_ts": trade.entry_ts.isoformat(), "side": side})
            for mode in ("break_even_1r", "trail_1r_after_1r", "trail_1r_after_2r"):
                exit_rows.append({"date": day.isoformat(), "variant": mode, **_managed_trade(signal, future, mode)})
            for delay, delayed_bar in ((0, entry_bar), (1, one_minute), (2, two_minute)):
                if delayed_bar is None or (side == "long" and delayed_bar.open <= stop) or (side == "short" and delayed_bar.open >= stop):
                    continue
                delayed_signal = Signal(delayed_bar.ts, signal.strategy, f"delay_{delay}m", side, delayed_bar.open, stop, 4, signal.reason, delayed_bar.ts, {})
                delayed_future = [bar for bar in future if bar.ts >= delayed_bar.ts]
                trade = execute_signal(delayed_signal, delayed_future, 100_000, "NQ", fixed, f"delay-{delay}-{day}")
                if trade:
                    exit_rows.append({"date": day.isoformat(), "variant": f"delay_{delay}m", **{key: getattr(trade, key) for key in ("net_pnl", "gross_pnl", "total_costs", "realized_r", "outcome")}, "entry_ts": trade.entry_ts.isoformat(), "side": side})
            previous_close, previous_range = float(rth.iloc[-1].close), float(rth.high.max() - rth.low.min())
            close_history.append(previous_close)
        cutoff = current.ts_ny.max() - pd.Timedelta(days=4)
        prior_tail = current[current.ts_ny >= cutoff].copy()
    return pd.DataFrame(features), pd.DataFrame(target_rows), pd.DataFrame(exit_rows)


def _bucket(series: pd.Series, discovery: pd.Series) -> pd.Series:
    clean = discovery.dropna()
    if clean.nunique() < 4:
        return pd.Series("unavailable", index=series.index)
    edges = [-np.inf, *np.quantile(clean, [.25, .5, .75]).tolist(), np.inf]
    return pd.cut(series, bins=edges, labels=["small", "medium", "large", "very_large"], include_lowest=True).astype(str)


def _factor_analysis(features: pd.DataFrame) -> dict:
    frame = features.copy()
    discovery = frame.year <= 2021
    frame["opening_range_bucket"] = _bucket(frame.opening_range, frame.loc[discovery, "opening_range"])
    frame["body_ratio_bucket"] = _bucket(frame.body_to_range, frame.loc[discovery, "body_to_range"])
    frame["overnight_range_bucket"] = _bucket(frame.overnight_range, frame.loc[discovery, "overnight_range"])
    frame["previous_range_bucket"] = _bucket(frame.previous_day_range, frame.loc[discovery, "previous_day_range"])
    frame["vix_regime"] = pd.cut(frame.prior_vix, [-np.inf, 15, 25, np.inf], labels=["below_15", "15_to_25", "25_plus"]).astype(str)
    frame["overnight_agreement"] = np.where(((frame.side == "long") & (frame.overnight_direction == "up")) | ((frame.side == "short") & (frame.overnight_direction == "down")), "agrees", "disagrees")
    frame["gap_agreement"] = np.where(((frame.side == "long") & (frame.gap_direction == "up")) | ((frame.side == "short") & (frame.gap_direction == "down")), "agrees", "disagrees")
    factors = ["side", "opening_color", "opening_range_bucket", "body_ratio_bucket", "overnight_direction", "overnight_agreement", "overnight_range_bucket", "previous_range_bucket", "vix_regime", "gap_direction", "gap_agreement", "day_of_week", "month", "year", "market_regime"]
    output = {}
    for factor in factors:
        rows = []
        for value, selected in frame.groupby(factor, dropna=False):
            item = {"value": str(value), "overall": {"sessions": int(len(selected)), "net_profit": round(float(selected.base_net_pnl.sum()), 2), "average_trade": round(float(selected.base_net_pnl.mean()), 2), "expectancy_r": round(float(selected.base_realized_r.mean()), 4), "win_rate": round(float((selected.base_net_pnl > 0).mean()), 4)}}
            for name, bounds in PERIODS.items():
                period = selected[(selected.year >= bounds[0]) & (selected.year <= bounds[1])]
                item[name] = {"sessions": int(len(period)), "net_profit": round(float(period.base_net_pnl.sum()), 2), "average_trade": round(float(period.base_net_pnl.mean()), 2) if len(period) else 0, "expectancy_r": round(float(period.base_realized_r.mean()), 4) if len(period) else 0}
            rows.append(item)
        output[factor] = rows
    walk_forward = {}
    for factor in [name for name in factors if name not in {"year", "month", "opening_color"}]:
        tests, total = [], 0.0
        for year in range(2022, 2026):
            training = frame[frame.year < year]
            eligible = [(value, group) for value, group in training.groupby(factor) if len(group) >= 100]
            if not eligible:
                continue
            chosen, _ = max(eligible, key=lambda item: item[1].base_realized_r.mean())
            test = frame[(frame.year == year) & (frame[factor] == chosen)]
            pnl = float(test.base_net_pnl.sum())
            total += pnl
            tests.append({"year": year, "selected_value": str(chosen), "training_sessions": int(len(training[training[factor] == chosen])), "test_sessions": int(len(test)), "test_net_profit": round(pnl, 2), "test_expectancy_r": round(float(test.base_realized_r.mean()), 4) if len(test) else 0})
        baseline = frame[frame.year >= 2022]
        walk_forward[factor] = {"tests": tests, "combined_net_profit": round(total, 2), "unfiltered_same_years_net_profit": round(float(baseline.base_net_pnl.sum()), 2)}
    return {"grouped": output, "exploratory_expanding_walk_forward": walk_forward}


def _target_analysis(targets: pd.DataFrame, exits: pd.DataFrame) -> dict:
    results = {}
    for target, selected in targets.groupby("target_r"):
        results[f"{target:g}R"] = {"overall": _metrics(selected), "periods": _period_metrics(selected)}
    selections, walk_rows = [], []
    for year in range(2022, 2026):
        training = targets[pd.to_datetime(targets.entry_ts, utc=True).dt.year < year]
        chosen = float(training.groupby("target_r").realized_r.mean().idxmax())
        test = targets[(pd.to_datetime(targets.entry_ts, utc=True).dt.year == year) & (targets.target_r == chosen)]
        selections.append({"test_year": year, "selected_target": chosen, "training_through": year - 1, "test_net_profit": round(float(test.net_pnl.sum()), 2), "test_trades": int(len(test)), "test_expectancy_r": round(float(test.realized_r.mean()), 4)})
        walk_rows.append(test)
    walk = pd.concat(walk_rows, ignore_index=True)
    alternatives = {name: {"overall": _metrics(selected), "periods": _period_metrics(selected)} for name, selected in exits.groupby("variant")}
    fixed_four = targets[(targets.target_r == 4) & (pd.to_datetime(targets.entry_ts, utc=True).dt.year >= 2022)]
    return {"targets": results, "expanding_walk_forward": {"selections": selections, "combined": _metrics(walk), "fixed_4r_same_test_years": _metrics(fixed_four)}, "exit_management": alternatives, "classification": "exploratory; no target is treated as predeclared"}


def _spa_test(benchmark_returns: np.ndarray, model_returns: np.ndarray, names: list[str], seed: int) -> dict:
    spa = SPA(-benchmark_returns, -model_returns, block_size=10, reps=50_000, bootstrap="stationary", studentize=True, nested=False, seed=seed)
    spa.compute()
    pvalues = spa.pvalues
    return {"benchmark": "specified separately", "models": names, "repetitions": 50_000, "block_size": 10, "library": "arch.bootstrap.SPA 8.0.0", "pvalues": {key: round(float(value), 8) for key, value in pvalues.items()}, "better_models_consistent_5pct": [names[index] for index in spa.better_models(.05, "consistent")]}


def _statistical_benchmarks(trades: pd.DataFrame, accepted_days: list[date]) -> dict:
    days = sorted(day for day in accepted_days if day.year <= 2023)

    def returns(variant: str) -> np.ndarray:
        frame = trades[trades.run_variant == variant]
        lookup = frame.groupby("entry_date").realized_r.sum().to_dict()
        return np.asarray([lookup.get(day, 0.0) for day in days])

    candle = returns(CONTROL_VARIANTS["first_candle_only"])
    ema = returns(CONTROL_VARIANTS["full_overnight_ema"])
    random = returns(CONTROL_VARIANTS["seeded_random"])
    family_names = list(CONTROL_VARIANTS)
    family = np.column_stack([returns(CONTROL_VARIANTS[name]) for name in family_names])
    zero = np.zeros(len(days))
    return {
        "window": "2018-2023 accepted NQ sessions; no-trade sessions are zero",
        "simple_vs_zero": _spa_test(zero, candle[:, None], ["first_candle_only"], 3101) | {"question": "Does the first-candle rule outperform zero after costs?"},
        "ema_vs_simple": _spa_test(candle, ema[:, None], ["full_overnight_ema"], 3102) | {"question": "Does EMA outperform first-candle only?"},
        "simple_vs_random": _spa_test(random, candle[:, None], ["first_candle_only"], 3103) | {"question": "Does first-candle only outperform seeded random direction?"},
        "family_vs_simple": _spa_test(candle, family, family_names, 3104) | {"question": "Does any member of the tested family outperform first-candle only?"},
        "interpretation": "ARCH 'upper' corresponds to White's conservative reality check; 'consistent' is Hansen SPA recentering. These are established library results. The prior custom test was a studentized maximum-bootstrap approximation with first-candle only as benchmark, not a test against zero.",
    }


def run_opening_research(root: Path = Path("data")) -> dict:
    corrected = json.loads((root / "research/results.json").read_text())
    accepted_map = {date.fromisoformat(row["date"]): int(row["expected"]) for row in corrected["quality"]["NQ"]["sessions"] if row["accepted"] and row["date"] >= "2018-01-01"}
    accepted_days = sorted(accepted_map)
    if any(day.year >= 2026 for day in accepted_days):
        raise RuntimeError("2026 is reserved")
    trades = _load_trades(root)
    comparisons, shared = _comparisons(trades)
    candle = trades[trades.run_variant == CONTROL_VARIANTS["first_candle_only"]].copy()
    ema = trades[trades.run_variant == CONTROL_VARIANTS["full_overnight_ema"]].copy()
    shared_pair = set(candle.entry_date) & set(ema.entry_date)
    features, targets, exits = _raw_experiments(root, accepted_map)
    discovery_threshold = float(features.loc[features.year <= 2021, "opening_range"].quantile(.90))
    feature_dates = pd.to_datetime(features.date).dt.date
    fast_dates = set(feature_dates[features.opening_range > discovery_threshold])
    moved_dates = set(feature_dates[features.entry_moved_away_1m])

    def deterministic_miss(frame: pd.DataFrame, missed: set[date], label: str) -> dict:
        remaining = frame[~frame.entry_date.isin(missed)]
        missed_frame = frame[frame.entry_date.isin(missed)]
        return {"label": label, "missed_trades": int(len(missed_frame)), "missed_net_pnl": round(float(missed_frame.net_pnl.sum()), 2), "remaining": _metrics(remaining), "target_winners_missed": int(missed_frame.outcome.astype(str).str.contains("target").sum())}

    missed = {
        "random": [_random_miss(candle, fraction, 4100 + int(fraction * 100)) for fraction in (.05, .10, .20)],
        "unusually_fast_opening_moves": deterministic_miss(candle, fast_dates, f"Miss opening ranges above discovery 90th percentile ({discovery_threshold:.2f} points)"),
        "entry_moved_away_before_manual_order": deterministic_miss(candle, moved_dates, "One-minute proxy: 09:36 open at least one tick worse than intended 09:35 open"),
        "precision_note": "15-second and 30-second delays cannot be modeled from one-minute OHLC. The one-minute proxy is the nearest defensible observation, not second-level evidence.",
    }
    delay_results = {name: _metrics(selected) for name, selected in exits[exits.variant.str.startswith("delay_")].groupby("variant")}
    baseline_candle = _metrics(candle)
    extra_tick = candle.copy()
    extra_tick["net_extra"] = extra_tick.net_pnl - 10.0
    extra_tick["realized_r"] = extra_tick.net_extra / ((extra_tick.reference_entry - extra_tick.stop).abs() * 20)
    extra_tick["total_costs"] = extra_tick.total_costs + 10.0
    execution = {
        "entry_timing": {"intended": "09:35:00 New York at the first available one-minute bar open", "15_seconds": "not identifiable", "30_seconds": "not identifiable", "one_and_two_minute_proxies": delay_results},
        "one_additional_tick_slippage_per_side": _metrics(extra_tick, pnl_column="net_extra"),
        "baseline": baseline_candle,
        "median_stop_points": round(float((candle.reference_entry - candle.stop).abs().median()), 2),
        "median_duration_minutes": round(float(candle.duration_minutes.median()), 1),
        "average_duration_minutes": round(float(candle.duration_minutes.mean()), 1),
        "bracket_order_assessment": "Operationally helpful and likely necessary for consistent manual execution; it cannot remove signal-to-entry latency or fast-market slippage.",
    }
    instrument_summary = {}
    for symbol in ("NQ", "MNQ"):
        instrument_summary[symbol] = {
            "first_candle_only_fixed_one_contract": _metrics(trades[trades.run_variant == f"{symbol}:B_CANDLE_4R_fixed1"]),
            "full_overnight_ema_fixed_one_contract": _metrics(trades[trades.run_variant == f"{symbol}:B_EMA_FULL_4R_fixed1"]),
        }
    result = {
        "schema_version": 1, "generated_at": datetime.now().astimezone().isoformat(),
        "data_window": "cached 2018-2025 only", "reserved_holdout": "2026 untouched and rejected by guard",
        "primary_question": "What happens if I trade first-candle direction with a 4R target, and does EMA improve it?",
        "comparison": {"shared_all_controls_sessions": len(shared), "shared_ema_and_simple_sessions": len(shared_pair), "strategies": comparisons},
        "pure_execution_cost_stress": {
            "first_candle_only": _cost_stress(candle, shared_pair),
            "full_overnight_ema": _cost_stress(ema, shared_pair),
            "design": "Fixed one NQ contract and identical EMA/simple matched sessions at every cost level. Costs change P&L only; they never change eligibility or sizing.",
        },
        "account_feasibility": _account_feasibility(trades),
        "concentration": {"first_candle_only": _concentration(candle), "full_overnight_ema": _concentration(ema)},
        "missed_trade_scenarios": missed,
        "edge_diagnostics": _factor_analysis(features),
        "target_and_exit_research": _target_analysis(targets, exits),
        "execution_practicality": execution,
        "instrument_summary": instrument_summary,
        "statistical_benchmarks": _statistical_benchmarks(trades, accepted_days),
        "plain_language_conclusion": "Both first-candle-only and EMA versions were historically profitable. The EMA version performed better in this sample, but the improvement is not strong enough to conclude that the EMA is responsible.",
    }
    output = root / "research/opening-candle-results.json"
    output.write_text(json.dumps(result, indent=2, default=str))
    features.to_parquet(root / "research/opening-candle-features.parquet", index=False, compression="zstd")
    targets.to_parquet(root / "research/opening-candle-targets.parquet", index=False, compression="zstd")
    exits.to_parquet(root / "research/opening-candle-exits.parquet", index=False, compression="zstd")
    return result
