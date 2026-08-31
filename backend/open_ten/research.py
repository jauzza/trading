from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

from .analytics import adjusted_p_values, metrics, paired_matrix_bootstrap, reality_check, stationary_bootstrap_mean
from .engine import ExecutionConfig, execute_signal
from .models import Bar, Signal
from .strategies import StrategyAConfig, StrategyBConfig, strategy_a, strategy_a_mechanical, strategy_b

NQ_FP = "e0ae8898e1f56f76"
MNQ_FP = "a136a761bbf3d8a0"
NY = ZoneInfo("America/New_York")
PERIODS = {
    "discovery": set(range(2018, 2022)),
    "validation": {2022, 2023},
    "historical_evaluation": {2024, 2025},
}


def _bar(row) -> Bar:
    return Bar(row.ts_ny.to_pydatetime(), float(row.open), float(row.high), float(row.low), float(row.close), int(row.volume), int(row.instrument_id))


def _clone(signal: Signal, variant: str) -> Signal:
    return Signal(signal.ts, signal.strategy, variant, signal.side, signal.entry, signal.stop, signal.target_r, signal.reason, signal.available_at, dict(signal.metadata))


def _quality(day: date, rth: pd.DataFrame, expected: int, degraded: set[date], roll_dates: set[date]) -> tuple[bool, dict]:
    times = set(rth.ts_ny.dt.time) if len(rth) else set()
    duplicates = int(rth.ts_ny.duplicated().sum()) if len(rth) else 0
    ranges = rth.high - rth.low if len(rth) else pd.Series(dtype=float)
    median_range = float(ranges.median()) if len(ranges) else 0
    suspicious = int((ranges > max(50.0, median_range * 20)).sum()) if len(ranges) else 0
    missing = max(0, expected - int(rth.ts_ny.nunique()))
    checks = {
        "date": day.isoformat(), "bars": int(len(rth)), "expected": expected,
        "missing_minutes": missing, "duplicates": duplicates,
        "has_0930": time(9, 30) in times, "has_0935": time(9, 35) in times,
        "has_1000": time(10, 0) in times, "suspicious_bars": suspicious,
        "degraded_condition": day in degraded, "roll_session": day in roll_dates,
        "legacy_feed": day < date(2017, 5, 21),
    }
    accepted = missing == duplicates == suspicious == 0 and all(checks[key] for key in ("has_0930", "has_0935", "has_1000")) and day not in degraded and day not in roll_dates
    checks["accepted"] = accepted
    if not accepted:
        checks["reasons"] = [key for key in ("missing_minutes", "duplicates", "suspicious_bars") if checks[key]]
        checks["reasons"] += [key for key in ("has_0930", "has_0935", "has_1000") if not checks[key]]
        checks["reasons"] += (["degraded_condition"] if day in degraded else []) + (["roll_session"] if day in roll_dates else [])
    return accepted, checks


def _roll_dates(mapping_files: list[Path]) -> set[date]:
    dates: set[date] = set()
    for path in mapping_files:
        payload = json.loads(path.read_text())
        for mapping in payload.get("mappings", []):
            for interval in mapping.get("intervals", [])[1:]:
                dates.add(date.fromisoformat(interval["start_date"]))
    return dates


def _condition_dates(root: Path) -> tuple[set[date], list[dict]]:
    path = root / "conditions-2016-2025.json"
    if not path.exists():
        raise RuntimeError("cached dataset conditions are missing; research will not contact Databento")
    rows = json.loads(path.read_text())
    return {date.fromisoformat(row["date"]) for row in rows if row.get("condition") != "available"}, rows


def _load_partition(path: str) -> pd.DataFrame:
    frame = pd.read_parquet(path).sort_index().reset_index()
    if "ts_event" not in frame.columns:
        frame = frame.rename(columns={frame.columns[0]: "ts_event"})
    frame["ts_ny"] = pd.to_datetime(frame.ts_event, utc=True).dt.tz_convert("America/New_York")
    return frame


def _contexts(frame: pd.DataFrame, day: date, market_open: pd.Timestamp, rth_history: list[Bar]) -> dict[str, list[Bar]]:
    prior_evening = pd.Timestamp(datetime.combine(day - timedelta(days=1), time(18), NY))
    midnight = pd.Timestamp(datetime.combine(day, time(0), NY))
    full = frame[(frame.ts_ny >= prior_evening) & (frame.ts_ny < market_open)]
    same_day = frame[(frame.ts_ny >= midnight) & (frame.ts_ny < market_open)]
    return {
        "full_overnight": [_bar(row) for row in full.itertuples(index=False)],
        "same_day": [_bar(row) for row in same_day.itertuples(index=False)],
        "regular_session": rth_history[-3_000:],
    }


def _new_state(starting: float) -> dict:
    return {"equity": starting, "trades": [], "sizing_skips": 0, "skipped_overlap": 0, "daily_loss_stops": 0}


def _execute_day(key: str, signals: list[Signal], bars: list[Bar], symbol: str, state: dict, config: ExecutionConfig, day: date) -> None:
    daily_pnl, last_exit = 0.0, None
    by_ts = {bar.ts: bar for bar in bars}
    for signal in sorted(signals, key=lambda item: item.ts):
        if last_exit and signal.ts <= last_exit:
            state["skipped_overlap"] += 1
            continue
        if daily_pnl <= -state["equity"] * config.daily_loss_fraction:
            state["daily_loss_stops"] += 1
            break
        future = [bar for bar in bars if bar.ts >= signal.ts and bar.ts.time() <= time(15, 55)]
        if not future:
            continue
        trade = execute_signal(signal, future, state["equity"], symbol, config, f"{symbol}-{key}-{day.isoformat()}-{len(state['trades']) + 1}")
        if trade is None:
            state["sizing_skips"] += 1
            continue
        entry_bar = by_ts.get(signal.ts)
        if entry_bar and entry_bar.instrument_id is not None:
            trade.underlying = str(entry_bar.instrument_id)
        trade.synthetic = False
        state["trades"].append(trade)
        state["equity"] += trade.net_pnl
        daily_pnl += trade.net_pnl
        last_exit = trade.exit_ts


def _run_specs() -> dict[str, tuple[ExecutionConfig, float]]:
    b_controls = [
        "B_EMA_FULL_4R_fixed1", "B_CANDLE_4R_fixed1", "B_ALWAYS_LONG_4R_fixed1", "B_ALWAYS_SHORT_4R_fixed1",
        "B_RANDOM_4R_fixed1", "B_OVERNIGHT_4R_fixed1", "B_EMA_SAME_DAY_4R_fixed1", "B_EMA_RTH_4R_fixed1",
        "B_EMA_SLOPE_4R_fixed1", "B_EMA_BODY_4R_fixed1", "B_EMA_SLOPE_BODY_4R_fixed1",
        "B_SHIFT_0935_4R_fixed1", "B_SHIFT_0940_4R_fixed1", "B_SHIFT_0945_4R_fixed1",
    ]
    specs: dict[str, tuple[ExecutionConfig, float]] = {}
    for symbol in ("NQ", "MNQ"):
        assumed_margin = 22_000 if symbol == "NQ" else 2_200
        fixed = ExecutionConfig(fixed_contracts=1, max_contracts=1, margin_per_contract=assumed_margin)
        dynamic = ExecutionConfig(risk_fraction=.01, margin_per_contract=assumed_margin)
        cost2 = ExecutionConfig(risk_fraction=.01, fee_multiplier=2, slippage_ticks_per_side=2, spread_ticks_round_trip=2, margin_per_contract=assumed_margin)
        cost4 = ExecutionConfig(risk_fraction=.01, fee_multiplier=4, slippage_ticks_per_side=4, spread_ticks_round_trip=4, margin_per_contract=assumed_margin)
        for name in b_controls:
            specs[f"{symbol}:{name}"] = (fixed, 100_000)
        specs[f"{symbol}:B_EMA_FULL_4R_risk1"] = (dynamic, 100_000)
        specs[f"{symbol}:B_EMA_FULL_4R_cost2x"] = (cost2, 100_000)
        specs[f"{symbol}:B_EMA_FULL_4R_cost4x"] = (cost4, 100_000)
        for name in ("A1_CONFIRMED_2R", "A1_CONFIRMED_4R", "A1_SWEEP_2R", "A1_SWEEP_4R", "A2_MECHANICAL_2R"):
            specs[f"{symbol}:{name}_risk1"] = (dynamic, 100_000)
    return specs


def _day_signals(rth: list[Bar], contexts: dict[str, list[Bar]]) -> dict[str, list[Signal]]:
    controls = {
        "B_EMA_FULL_4R_fixed1": StrategyBConfig(variant="B_EMA_FULL", target_r=4),
        "B_CANDLE_4R_fixed1": StrategyBConfig(variant="B_CANDLE", target_r=4, direction_mode="candle_body", min_warmup_periods=1, ema_session="none"),
        "B_ALWAYS_LONG_4R_fixed1": StrategyBConfig(variant="B_ALWAYS_LONG", target_r=4, direction_mode="always_long"),
        "B_ALWAYS_SHORT_4R_fixed1": StrategyBConfig(variant="B_ALWAYS_SHORT", target_r=4, direction_mode="always_short"),
        "B_RANDOM_4R_fixed1": StrategyBConfig(variant="B_RANDOM", target_r=4, direction_mode="random", random_seed=1701),
        "B_OVERNIGHT_4R_fixed1": StrategyBConfig(variant="B_OVERNIGHT", target_r=4, direction_mode="overnight_direction"),
        "B_EMA_SAME_DAY_4R_fixed1": StrategyBConfig(variant="B_EMA_SAME_DAY", target_r=4, ema_session="same_day"),
        "B_EMA_RTH_4R_fixed1": StrategyBConfig(variant="B_EMA_RTH", target_r=4, ema_session="regular_session"),
        "B_EMA_SLOPE_4R_fixed1": StrategyBConfig(variant="B_EMA_SLOPE", target_r=4, direction_mode="ema_slope_only"),
        "B_EMA_BODY_4R_fixed1": StrategyBConfig(variant="B_EMA_BODY", target_r=4, require_body_agreement=True),
        "B_EMA_SLOPE_BODY_4R_fixed1": StrategyBConfig(variant="B_EMA_SLOPE_BODY", target_r=4, require_body_agreement=True, require_slope=True),
        "B_SHIFT_0935_4R_fixed1": StrategyBConfig(variant="B_SHIFT_0935", target_r=4, opening_time=time(9, 35)),
        "B_SHIFT_0940_4R_fixed1": StrategyBConfig(variant="B_SHIFT_0940", target_r=4, opening_time=time(9, 40)),
        "B_SHIFT_0945_4R_fixed1": StrategyBConfig(variant="B_SHIFT_0945", target_r=4, opening_time=time(9, 45)),
    }
    signals: dict[str, list[Signal]] = {}
    for name, config in controls.items():
        warmup = contexts.get(config.ema_session, contexts["full_overnight"])
        signals[name] = strategy_b(rth, warmup, config)
    base = signals["B_EMA_FULL_4R_fixed1"]
    for name in ("B_EMA_FULL_4R_risk1", "B_EMA_FULL_4R_cost2x", "B_EMA_FULL_4R_cost4x"):
        signals[name] = [_clone(signal, name) for signal in base]
    signals["A1_CONFIRMED_2R_risk1"] = strategy_a(rth, StrategyAConfig(variant="A1_CONFIRMED_2R", target_r=2, stop_mode="confirmed_pivot"))
    signals["A1_CONFIRMED_4R_risk1"] = strategy_a(rth, StrategyAConfig(variant="A1_CONFIRMED_4R", target_r=4, stop_mode="confirmed_pivot"))
    signals["A1_SWEEP_2R_risk1"] = strategy_a(rth, StrategyAConfig(variant="A1_SWEEP_2R", target_r=2, stop_mode="sweep_extreme"))
    signals["A1_SWEEP_4R_risk1"] = strategy_a(rth, StrategyAConfig(variant="A1_SWEEP_4R", target_r=4, stop_mode="sweep_extreme"))
    signals["A2_MECHANICAL_2R_risk1"] = strategy_a_mechanical(rth, StrategyAConfig(variant="A2_MECHANICAL_2R", target_r=2, max_attempts=1))
    return signals


def _summary(key: str, full_state: dict, period_states: dict[str, dict], starting: float) -> dict:
    full_metrics = metrics(full_state["trades"], starting)
    periods = {name: metrics(state["trades"], starting) for name, state in period_states.items()}
    anchored_periods = {name: metrics([trade for trade in full_state["trades"] if trade.entry_ts.year in years], starting) for name, years in PERIODS.items()}
    strongest_removed = sorted(full_state["trades"], key=lambda trade: trade.net_pnl, reverse=True)[5:]
    return {
        "id": key, "metrics": full_metrics, "periods": periods, "splits": periods,
        "anchored_periods": anchored_periods,
        "after_best_5_removed": metrics(strongest_removed, starting),
        "sizing_skips": full_state["sizing_skips"], "overlap_skips": full_state["skipped_overlap"],
        "daily_loss_stops": full_state["daily_loss_stops"], "evidence": "inconclusive",
    }


def _daily_r(trades: list, days: list[date]) -> np.ndarray:
    values: dict[date, float] = defaultdict(float)
    for trade in trades:
        values[trade.entry_ts.date()] += trade.realized_r
    return np.asarray([values[day] for day in days], dtype=float)


def run_research(root: Path = Path("data")) -> dict:
    manifest = json.loads((root / "manifest.json").read_text())
    for dataset in manifest["datasets"].values():
        if dataset["request"]["end"] > "2026-01-01" or any(int(part["year"]) >= 2026 for part in dataset["partitions"]):
            raise RuntimeError("2026 data is reserved and must remain untouched")
    degraded, condition_rows = _condition_dates(root)
    schedule = mcal.get_calendar("NYSE").schedule("2016-01-01", "2025-12-31")
    specs = _run_specs()
    full_states = {key: _new_state(starting) for key, (_, starting) in specs.items()}
    period_states = {key: {name: _new_state(starting) for name in PERIODS} for key, (_, starting) in specs.items()}
    quality_reports: dict[str, list[dict]] = {}
    accepted_counts: dict[str, int] = defaultdict(int)
    session_days: dict[str, list[date]] = defaultdict(list)

    for symbol, fingerprint in (("NQ", NQ_FP), ("MNQ", MNQ_FP)):
        entry = manifest["datasets"][fingerprint]
        roll_dates = _roll_dates([Path(part["mapping_path"]) for part in entry["partitions"]])
        symbol_quality: list[dict] = []
        prior_tail = pd.DataFrame()
        rth_history: list[Bar] = []
        for part in sorted(entry["partitions"], key=lambda item: item["year"]):
            year = int(part["year"])
            if year >= 2026:
                raise RuntimeError("refusing to inspect reserved 2026 partition")
            print(f"Phase 2 audit and backtest: {symbol} {year}", flush=True)
            current = _load_partition(part["path"])
            frame = pd.concat([prior_tail, current], ignore_index=True).sort_values("ts_ny") if len(prior_tail) else current
            year_schedule = schedule[schedule.index.year == year]
            for session_day, row in year_schedule.iterrows():
                day = session_day.date() if hasattr(session_day, "date") else session_day
                if symbol == "MNQ" and day < date(2019, 5, 6):
                    continue
                market_open = row.market_open.tz_convert("America/New_York")
                market_close = row.market_close.tz_convert("America/New_York")
                rth = frame[(frame.ts_ny >= market_open) & (frame.ts_ny < market_close)].copy()
                accepted, report = _quality(day, rth, int((market_close - market_open).total_seconds() / 60), degraded, roll_dates)
                symbol_quality.append(report)
                if not accepted or (symbol == "NQ" and day < date(2018, 1, 1)):
                    continue
                accepted_counts[symbol] += 1
                session_days[symbol].append(day)
                rth_bars = [_bar(item) for item in rth.itertuples(index=False)]
                contexts = _contexts(frame, day, market_open, rth_history)
                day_signals = _day_signals(rth_bars, contexts)
                period = next((name for name, years in PERIODS.items() if year in years), None)
                for name, signals in day_signals.items():
                    key = f"{symbol}:{name}"
                    if key not in specs:
                        continue
                    config, _ = specs[key]
                    _execute_day(key, signals, rth_bars, symbol, full_states[key], config, day)
                    if period:
                        _execute_day(key, signals, rth_bars, symbol, period_states[key][period], config, day)
                rth_history.extend(rth_bars)
                rth_history = rth_history[-3_000:]
            cutoff = current.ts_ny.max() - pd.Timedelta(days=4)
            prior_tail = current[current.ts_ny >= cutoff].copy()
        quality_reports[symbol] = symbol_quality

    summaries = {key: _summary(key, full_states[key], period_states[key], specs[key][1]) for key in specs}
    control_names = [name for name in (
        "B_CANDLE_4R_fixed1", "B_ALWAYS_LONG_4R_fixed1", "B_ALWAYS_SHORT_4R_fixed1", "B_RANDOM_4R_fixed1",
        "B_OVERNIGHT_4R_fixed1", "B_EMA_SAME_DAY_4R_fixed1", "B_EMA_RTH_4R_fixed1", "B_EMA_SLOPE_4R_fixed1",
        "B_EMA_BODY_4R_fixed1", "B_EMA_SLOPE_BODY_4R_fixed1", "B_SHIFT_0935_4R_fixed1",
        "B_SHIFT_0940_4R_fixed1", "B_SHIFT_0945_4R_fixed1",
    )]
    inference_days = [day for day in session_days["NQ"] if day.year <= 2023]
    evaluation_days = [day for day in session_days["NQ"] if day.year >= 2024]
    candidate_key = "NQ:B_EMA_FULL_4R_fixed1"
    candidate = _daily_r(full_states[candidate_key]["trades"], inference_days)
    controls = np.column_stack([_daily_r(full_states[f"NQ:{name}"]["trades"], inference_days) for name in control_names])
    paired = paired_matrix_bootstrap(candidate, controls, samples=50_000, mean_block=10, seed=1701)
    raw_p = [item["p_value"] for item in paired]
    bh = adjusted_p_values(raw_p, "bh")
    by = adjusted_p_values(raw_p, "by")
    comparisons = {}
    for name, item, bh_p, by_p in zip(control_names, paired, bh, by):
        comparisons[name] = item | {"bh_adjusted_p": round(bh_p, 8), "by_adjusted_p": round(by_p, 8)}
    rc = reality_check(np.column_stack([candidate, controls]), controls[:, 0], samples=50_000, mean_block=10, seed=1702)
    candidate_eval = _daily_r(full_states[candidate_key]["trades"], evaluation_days)
    candle_eval = _daily_r(full_states["NQ:B_CANDLE_4R_fixed1"]["trades"], evaluation_days)
    evaluation_comparison = stationary_bootstrap_mean(candidate_eval - candle_eval, samples=50_000, mean_block=10, seed=1703)
    evaluation_comparison["observed_mean_difference"] = round(float(np.mean(candidate_eval - candle_eval)), 6)
    candle_comparison = comparisons["B_CANDLE_4R_fixed1"]
    ema_adds_value = candle_comparison["low"] > 0 and candle_comparison["by_adjusted_p"] < .05 and evaluation_comparison["observed_mean_difference"] > 0

    for key, item in summaries.items():
        validation = item["periods"]["validation"]
        evaluation = item["periods"]["historical_evaluation"]
        if validation["trades"] and validation["expectancy_r"] <= 0 and evaluation["expectancy_r"] <= 0:
            item["evidence"] = "rejected"
        elif validation["expectancy_r"] > 0 and evaluation["expectancy_r"] > 0:
            item["evidence"] = "promising_exploratory"
        else:
            item["evidence"] = "inconclusive"
    frozen = (
        ema_adds_value and rc["spa_p_value"] < .05
        and summaries[candidate_key]["periods"]["validation"]["net_profit"] > 0
        and summaries[candidate_key]["periods"]["historical_evaluation"]["net_profit"] > 0
    )
    if frozen:
        summaries[candidate_key]["evidence"] = "frozen_for_untouched_holdout"

    result = {
        "schema_version": 2, "generated_at": datetime.now().astimezone().isoformat(), "data_mode": "real_licensed_cached_only",
        "research_window": {
            "core": "2018-2025", "discovery": "2018-2021", "validation": "2022-2023",
            "historical_evaluation": "2024-2025 (previously inspected; not a blind holdout)",
            "reserved_holdout": "2026 — not downloaded, opened, inspected, or backtested",
        },
        "execution_assumptions": {
            "NQ": {"point_value": 20, "round_trip_fees": 5.10, "slippage_ticks_per_side": 1, "spread_ticks_round_trip": 1},
            "MNQ": {"point_value": 2, "round_trip_fees": 2.40, "slippage_ticks_per_side": 1, "spread_ticks_round_trip": 1},
            "same_bar_policy": "adverse_first", "session_exit": "15:55 America/New_York",
        },
        "session_definition": {
            "full_overnight_ema": "previous calendar day 18:00 through 09:29 America/New_York, including Sunday evening for Monday sessions",
            "same_day_ema": "00:00 through 09:29 America/New_York", "regular_session_ema": "prior accepted RTH bars",
            "dst": "timezone-aware America/New_York timestamps", "rolls": "mapping change sessions excluded",
        },
        "manifest_fingerprints": [NQ_FP, MNQ_FP], "accepted_sessions": dict(accepted_counts),
        "quality": {symbol: {
            "total": len(rows), "accepted": sum(row["accepted"] for row in rows), "excluded": sum(not row["accepted"] for row in rows),
            "legacy": sum(row["legacy_feed"] for row in rows), "degraded": sum(row["degraded_condition"] for row in rows),
            "roll": sum(row["roll_session"] for row in rows), "sessions": rows,
        } for symbol, rows in quality_reports.items()},
        "dataset_conditions": {"records": len(condition_rows), "degraded_dates": sorted(day.isoformat() for day in degraded)},
        "statistics": {
            "unit": "accepted session; no-trade sessions are zero", "confirmatory_window": "2018-2023",
            "bootstrap": "Politis-Romano stationary bootstrap", "paired_ema_vs_controls": comparisons,
            "white_reality_check_and_spa": rc, "historical_evaluation_ema_vs_candle": evaluation_comparison,
            "ema_adds_value": ema_adds_value,
            "interpretation": "Exploratory controls share a correction family; 2024-2025 is historical evaluation, not genuine holdout evidence.",
        },
        "strategies": summaries, "credible_candidates": [candidate_key] if frozen else [],
        "frozen_candidate": candidate_key if frozen else None,
        "conclusion": "FROZEN FOR UNTOUCHED 2026 HOLDOUT" if frozen else "NO STRATEGY QUALIFIES FOR THE UNTOUCHED 2026 HOLDOUT",
    }
    derived = root / "research"
    derived.mkdir(parents=True, exist_ok=True)
    (derived / "results.json").write_text(json.dumps(result, indent=2, default=str))
    trade_rows = [{"run_variant": key, **trade.to_dict()} for key, state in full_states.items() for trade in state["trades"]]
    pd.DataFrame(trade_rows).to_parquet(derived / "trades.parquet", index=False, compression="zstd")
    pd.DataFrame([row for rows in quality_reports.values() for row in rows]).to_parquet(derived / "quality.parquet", index=False, compression="zstd")
    if frozen:
        frozen_payload = {
            "frozen_at": result["generated_at"], "candidate": candidate_key,
            "strategy": asdict(StrategyBConfig(variant="B_EMA_FULL", target_r=4)),
            "execution": result["execution_assumptions"], "training_data_end_exclusive": "2026-01-01",
        }
        (derived / "frozen-strategy-b.json").write_text(json.dumps(frozen_payload, indent=2, default=str))
    return result
