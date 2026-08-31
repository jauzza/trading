from __future__ import annotations

import json
import math
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from arch.bootstrap import SPA

from .engine import ExecutionConfig, execute_signal
from .models import Bar, Signal
from .opening_research import NQ_FP, _bar, _metrics

NY = ZoneInfo("America/New_York")
EXIT_SPECS: dict[str, float | None] = {"fixed_4r": 4.0, "fixed_5r": 5.0, "stop_and_1555": None}
REPS = 50_000
BLOCK = 10


def _duration_stats(values: pd.Series) -> dict:
    clean = values.dropna().astype(float)
    if clean.empty:
        return {"sessions": 0, "mean_minutes": 0, "median_minutes": 0, "p25_minutes": 0, "p75_minutes": 0, "p90_minutes": 0}
    return {
        "sessions": int(len(clean)),
        "mean_minutes": round(float(clean.mean()), 2),
        "median_minutes": round(float(clean.median()), 2),
        "p25_minutes": round(float(clean.quantile(.25)), 2),
        "p75_minutes": round(float(clean.quantile(.75)), 2),
        "p90_minutes": round(float(clean.quantile(.90)), 2),
    }


def _audit_metrics(frame: pd.DataFrame) -> dict:
    base = _metrics(frame)
    pnl = frame.net_pnl.astype(float)
    winners, losers = frame[pnl > 0], frame[pnl < 0]
    stops = frame[frame.outcome.astype(str).str.contains("stop")]
    target_or_time = frame[~frame.index.isin(stops.index)]
    targets = frame[frame.outcome.astype(str).str.contains("target")]
    time_exits = frame[frame.outcome == "session_exit"]
    total_available = float(frame.available_minutes.sum()) if "available_minutes" in frame else 0
    total_duration = float(frame.duration_minutes.sum())
    return base | {
        "median_trade": round(float(pnl.median()), 2),
        "average_winner": round(float(winners.net_pnl.mean()), 2) if len(winners) else 0,
        "average_loser": round(float(losers.net_pnl.mean()), 2) if len(losers) else 0,
        "time_in_market": {
            "total_hours": round(total_duration / 60, 2),
            "fraction_of_available_rth": round(total_duration / total_available, 6) if total_available else 0,
        },
        "holding_time": {
            "all": _duration_stats(frame.duration_minutes),
            "winners": _duration_stats(winners.duration_minutes),
            "losers": _duration_stats(losers.duration_minutes),
            "stop_exits": _duration_stats(stops.duration_minutes),
            "target_or_time_exits": _duration_stats(target_or_time.duration_minutes),
            "target_exits": _duration_stats(targets.duration_minutes),
            "time_exits": _duration_stats(time_exits.duration_minutes),
        },
    }


def _concentration(frame: pd.DataFrame) -> dict:
    frame = frame.sort_values("entry_ts").copy()
    total_net = float(frame.net_pnl.sum())
    gross_winning_profit = float(frame.loc[frame.net_pnl > 0, "net_pnl"].sum())
    ordered = frame.sort_values("net_pnl", ascending=False)

    def removal(label: str, removed: pd.DataFrame) -> dict:
        removed_profit = float(removed.net_pnl.sum())
        remaining = frame.drop(removed.index)
        return {
            "label": label,
            "removed_sessions": int(len(removed)),
            "removed_profit": round(removed_profit, 2),
            "share_of_gross_winning_profit": round(removed_profit / gross_winning_profit, 8) if gross_winning_profit else 0,
            "share_of_final_net_profit": round(removed_profit / total_net, 8) if total_net else None,
            "remaining": _audit_metrics(remaining),
        }

    tests = {f"best_{count}_trades": removal(f"Best {count} trade{'s' if count != 1 else ''}", ordered.head(count)) for count in (1, 5, 10, 20)}
    tests["best_1pct_sessions"] = removal("Best 1% of sessions", ordered.head(math.ceil(len(frame) * .01)))
    timestamps = pd.to_datetime(frame.entry_ts, utc=True).dt.tz_convert(None)
    for name, keys in {
        "best_month": timestamps.dt.to_period("M"),
        "best_quarter": timestamps.dt.to_period("Q"),
        "best_year": timestamps.dt.year,
    }.items():
        totals = frame.assign(_period=keys).groupby("_period").net_pnl.sum()
        best = totals.idxmax()
        item = removal(name.replace("_", " ").title(), frame[keys == best])
        item["period"] = str(best)
        tests[name] = item
    return {
        "gross_winning_profit_definition": "sum of positive after-cost trade P&L before subtracting losing trades",
        "gross_winning_profit": round(gross_winning_profit, 2),
        "final_net_profit": round(total_net, 2),
        "tests": tests,
    }


def _cost_break_even(frame: pd.DataFrame) -> dict:
    baseline = float(frame.total_costs.median())
    multiplier = float(frame.gross_pnl.sum() / frame.total_costs.sum())
    return {
        "baseline_all_in_round_trip_cost": round(baseline, 2),
        "break_even_multiplier": round(multiplier, 6),
        "break_even_all_in_round_trip_cost": round(baseline * multiplier, 2),
        "same_sessions": int(len(frame)),
    }


def _reconciliation(current: pd.DataFrame, reference: pd.DataFrame, keys: list[str]) -> dict:
    left = current.copy()
    right = reference.copy()
    left["date"] = left.date.astype(str)
    right["date"] = right.date.astype(str)
    merged = left.merge(right, on="date", suffixes=("_new", "_reference"), how="outer", indicator=True)
    diffs = {}
    for key in keys:
        new, old = f"{key}_new", f"{key}_reference"
        if new in merged and old in merged:
            diffs[key] = round(float((pd.to_numeric(merged[new], errors="coerce") - pd.to_numeric(merged[old], errors="coerce")).abs().max()), 10)
    return {
        "current_trades": int(len(current)),
        "reference_trades": int(len(reference)),
        "matched_trades": int((merged._merge == "both").sum()),
        "left_only": int((merged._merge == "left_only").sum()),
        "right_only": int((merged._merge == "right_only").sum()),
        "maximum_absolute_differences": diffs,
        "gross_to_net_maximum_error": round(float((current.gross_pnl - current.total_costs - current.net_pnl).abs().max()), 10),
        "exact": bool((merged._merge == "both").all() and all(value == 0 for value in diffs.values()) and float((current.gross_pnl - current.total_costs - current.net_pnl).abs().max()) < 1e-9),
    }


def _finite_p(value: float) -> dict:
    conservative = 1 / (REPS + 1)
    return {
        "raw": round(float(value), 8),
        "display": f"≤ approximately {conservative:.5f}" if value == 0 else f"{value:.5f}",
    }


def _spa(benchmark: np.ndarray, models: np.ndarray, names: list[str], benchmark_label: str, seed: int) -> dict:
    spa = SPA(-benchmark, -models, block_size=BLOCK, reps=REPS, bootstrap="stationary", studentize=True, nested=False, seed=seed)
    spa.compute()
    pvalues = {name: _finite_p(float(value)) for name, value in spa.pvalues.items()}
    return {
        "benchmark": benchmark_label,
        "models": names,
        "observations": int(len(benchmark)),
        "resamples": REPS,
        "expected_block_length": BLOCK,
        "seed": seed,
        "library": "arch.bootstrap.SPA 8.0.0",
        "pvalues": pvalues,
        "monte_carlo_resolution": {
            "nominal": 1 / REPS,
            "conservative_zero_exceedance": 1 / (REPS + 1),
            "display": "approximately 0.00002",
        },
    }


def _walk_forward(frames: dict[str, pd.DataFrame]) -> dict:
    selections, selected_rows = [], []
    for test_year in range(2022, 2026):
        training_scores = {}
        for name, frame in frames.items():
            years = pd.to_datetime(frame.entry_ts, utc=True).dt.year
            training_scores[name] = round(float(frame.loc[years < test_year, "net_pnl"].sum()), 2)
        selected = max(training_scores, key=training_scores.get)
        test = frames[selected][pd.to_datetime(frames[selected].entry_ts, utc=True).dt.year == test_year].copy()
        selected_rows.append(test)
        selections.append({
            "test_year": test_year,
            "training_through": test_year - 1,
            "selection_rule": "highest cumulative after-cost NQ net profit on prior years; identical fixed-contract sessions",
            "selected_exit": selected,
            "prior_year_scores": training_scores,
            "forward": _audit_metrics(test),
        })
    selected_frame = pd.concat(selected_rows, ignore_index=True)
    fixed = {}
    for name, frame in frames.items():
        years = pd.to_datetime(frame.entry_ts, utc=True).dt.year
        fixed[name] = _audit_metrics(frame[years >= 2022])
    return {"selections": selections, "combined_selected": _audit_metrics(selected_frame), "fixed_2022_2025": fixed}


def _build_trades(root: Path, accepted: dict[date, int]) -> tuple[dict[str, pd.DataFrame], dict[str, dict]]:
    manifest = json.loads((root / "manifest.json").read_text())
    dataset = manifest["datasets"][NQ_FP]
    if dataset["request"]["end"] > "2026-01-01" or any(int(part["year"]) >= 2026 for part in dataset["partitions"]):
        raise RuntimeError("2026 is reserved")
    rows: dict[str, list[dict]] = {name: [] for name in EXIT_SPECS}
    delayed: dict[str, list[dict]] = {"delay_1m": [], "delay_2m": []}
    delay_rejections = {"delay_1m": {"stop_touched_before_entry": 0, "entry_at_or_through_stop": 0, "missing_bar": 0}, "delay_2m": {"stop_touched_before_entry": 0, "entry_at_or_through_stop": 0, "missing_bar": 0}}
    prior_tail = pd.DataFrame()
    config = ExecutionConfig(fixed_contracts=1, max_contracts=1, margin_per_contract=22_000)

    def add_trade(bucket: list[dict], trade, day: date, available: float) -> None:
        bucket.append({"date": day.isoformat(), "available_minutes": available, **trade.to_dict()})

    for part in sorted(dataset["partitions"], key=lambda item: item["year"]):
        year = int(part["year"])
        if year < 2017:
            continue
        if year >= 2026:
            raise RuntimeError("refusing to inspect 2026")
        print(f"Phase 4 bounded audit: NQ {year}", flush=True)
        current = pd.read_parquet(part["path"]).sort_index().reset_index()
        if "ts_event" not in current:
            current = current.rename(columns={current.columns[0]: "ts_event"})
        current["ts_ny"] = pd.to_datetime(current.ts_event, utc=True).dt.tz_convert("America/New_York")
        combined = pd.concat([prior_tail, current], ignore_index=True).sort_values("ts_ny") if len(prior_tail) else current
        for day in sorted(day for day in accepted if day.year == year):
            start = pd.Timestamp(datetime.combine(day - timedelta(days=1), time(18), NY))
            end = pd.Timestamp(datetime.combine(day, time(16), NY))
            session = combined[(combined.ts_ny >= start) & (combined.ts_ny < end)]
            market_close = pd.Timestamp(datetime.combine(day, time(9, 30), NY)) + pd.Timedelta(minutes=accepted[day])
            rth = session[(session.ts_ny >= pd.Timestamp(datetime.combine(day, time(9, 30), NY))) & (session.ts_ny < market_close)]
            opening = rth[(rth.ts_ny.dt.time >= time(9, 30)) & (rth.ts_ny.dt.time <= time(9, 34))]
            if len(opening) != 5:
                continue
            open_price, close_price = float(opening.iloc[0].open), float(opening.iloc[-1].close)
            if close_price == open_price:
                continue
            side = "long" if close_price > open_price else "short"
            stop = float(opening.low.min()) if side == "long" else float(opening.high.max())
            bars = [_bar(row) for row in rth.itertuples(index=False)]
            entry_bar = next((bar for bar in bars if bar.ts.time() == time(9, 35)), None)
            if entry_bar is None or (side == "long" and entry_bar.open <= stop) or (side == "short" and entry_bar.open >= stop):
                continue
            future = [bar for bar in bars if bar.ts >= entry_bar.ts and bar.ts.time() <= time(15, 55)]
            if not future:
                continue
            available = max(0, (future[-1].ts - entry_bar.ts).total_seconds() / 60)
            for name, target_r in EXIT_SPECS.items():
                signal = Signal(entry_bar.ts, "First candle", name, side, entry_bar.open, stop, target_r, "completed opening-candle body direction", entry_bar.ts, {})
                trade = execute_signal(signal, future, 100_000, "NQ", config, f"phase4-{name}-{day}")
                if trade:
                    add_trade(rows[name], trade, day, available)
            for minutes, delayed_bar in ((1, next((bar for bar in bars if bar.ts.time() == time(9, 36)), None)), (2, next((bar for bar in bars if bar.ts.time() == time(9, 37)), None))):
                key = f"delay_{minutes}m"
                if delayed_bar is None:
                    delay_rejections[key]["missing_bar"] += 1
                    continue
                pre_entry = [bar for bar in future if entry_bar.ts <= bar.ts < delayed_bar.ts]
                stop_touched = any(bar.low <= stop for bar in pre_entry) if side == "long" else any(bar.high >= stop for bar in pre_entry)
                if stop_touched:
                    delay_rejections[key]["stop_touched_before_entry"] += 1
                    continue
                if (side == "long" and delayed_bar.open <= stop) or (side == "short" and delayed_bar.open >= stop):
                    delay_rejections[key]["entry_at_or_through_stop"] += 1
                    continue
                delayed_future = [bar for bar in future if bar.ts >= delayed_bar.ts]
                delayed_available = max(0, (future[-1].ts - delayed_bar.ts).total_seconds() / 60)
                signal = Signal(delayed_bar.ts, "First candle delayed", key, side, delayed_bar.open, stop, 4.0, "causal delayed reference entry", delayed_bar.ts, {})
                trade = execute_signal(signal, delayed_future, 100_000, "NQ", config, f"phase4-{key}-{day}")
                if trade:
                    add_trade(delayed[key], trade, day, delayed_available)
        cutoff = current.ts_ny.max() - pd.Timedelta(days=4)
        prior_tail = current[current.ts_ny >= cutoff].copy()
    frames = {name: pd.DataFrame(data) for name, data in rows.items()}
    delay_frames = {name: pd.DataFrame(data) for name, data in delayed.items()}
    return frames, {"frames": delay_frames, "rejections": delay_rejections}


def run_phase4_audit(root: Path = Path("data")) -> dict:
    phase2 = json.loads((root / "research/results.json").read_text())
    accepted = {date.fromisoformat(row["date"]): int(row["expected"]) for row in phase2["quality"]["NQ"]["sessions"] if row["accepted"] and "2018-01-01" <= row["date"] <= "2025-12-31"}
    if any(day.year >= 2026 for day in accepted):
        raise RuntimeError("2026 is reserved")
    frames, delayed_payload = _build_trades(root, accepted)
    if any(len(frame) != 1959 for frame in frames.values()):
        raise RuntimeError(f"bounded exits did not preserve 1,959 sessions: { {name: len(frame) for name, frame in frames.items()} }")

    trade_cache = pd.read_parquet(root / "research/trades.parquet")
    ema_cached = trade_cache[trade_cache.run_variant == "NQ:B_EMA_FULL_4R_fixed1"].copy()
    cached = trade_cache[trade_cache.run_variant == "NQ:B_CANDLE_4R_fixed1"].copy()
    cached["date"] = pd.to_datetime(cached.entry_ts, utc=True).dt.date.astype(str)
    targets = pd.read_parquet(root / "research/opening-candle-targets.parquet")
    exits = pd.read_parquet(root / "research/opening-candle-exits.parquet")
    references = {
        "fixed_4r": cached,
        "fixed_5r": targets[targets.target_r == 5].copy(),
        "stop_and_1555": exits[exits.variant == "fixed_eod"].copy(),
    }
    reconciliations = {
        name: _reconciliation(frame, references[name], ["net_pnl", "gross_pnl", "total_costs"])
        for name, frame in frames.items()
    }
    variant_results = {}
    for name, frame in frames.items():
        variant_results[name] = {
            "metrics": _audit_metrics(frame),
            "cost_break_even": _cost_break_even(frame),
            "concentration": _concentration(frame),
            "reconciliation": reconciliations[name],
        }

    delayed_results = {}
    for key, delayed in delayed_payload["frames"].items():
        dates = set(delayed.date.astype(str))
        baseline = frames["fixed_4r"][frames["fixed_4r"].date.astype(str).isin(dates)].copy()
        delayed_results[key] = {
            "causal_rules": "enter at delayed bar open; reject if any completed post-09:35 pre-entry bar touched the original stop; retain original stop; recalculate 4R target from delayed reference entry; apply baseline spread, one tick slippage per side, and NQ fees",
            "rejections": delayed_payload["rejections"][key],
            "matched_sessions": int(len(delayed)),
            "delayed": _audit_metrics(delayed),
            "baseline_0935_same_sessions": _audit_metrics(baseline),
        }

    days = sorted(day for day in accepted if day.year <= 2023)
    def session_returns(frame: pd.DataFrame) -> np.ndarray:
        lookup = frame.assign(_date=pd.to_datetime(frame.entry_ts, utc=True).dt.date).groupby("_date").realized_r.sum().to_dict()
        return np.asarray([lookup.get(day, 0.0) for day in days])
    four, five, eod = (session_returns(frames[name]) for name in EXIT_SPECS)
    statistics = {
        "window": "2018-2023 accepted NQ sessions; no-trade accepted sessions assigned zero",
        "fixed_4r_vs_zero": _spa(np.zeros(len(days)), four[:, None], ["fixed_4r"], "zero after-cost session R", 4401),
        "exit_family_vs_fixed_4r": _spa(four, np.column_stack([five, eod]), ["fixed_5r", "stop_and_1555"], "fixed_4r after-cost session R on identical sessions", 4402),
        "random_direction_comparison": "omitted from Phase 4; one seeded random path is not treated as sufficient evidence",
    }

    holding_discrepancy = {
        "resolution": "The earlier approximately 87-minute figure was the 86.5-minute mean of the full-overnight EMA strategy and was incorrectly described as a median. Phase 3's 24-minute median and 89-minute mean refer to the simple fixed-4R strategy and are correct.",
        "simple_fixed_4r": variant_results["fixed_4r"]["metrics"]["holding_time"],
        "full_overnight_ema_cached": {
            **_duration_stats(ema_cached.duration_minutes),
            "source": f"NQ:B_EMA_FULL_4R_fixed1 cached {len(ema_cached):,}-trade run",
        },
    }

    result = {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(),
        "data_window": "preserved 2018-2025 only",
        "reserved_holdout": "2026 not accessed; rejected by guard",
        "scope": "bounded to fixed 4R, fixed 5R, and initial stop plus 15:55-bar-close exit with no profit target",
        "execution_specification": {
            "instrument": "one fixed NQ contract",
            "entry": "09:35 New York one-minute bar open after the 09:30-09:34 candle completes",
            "direction": "opening candle body direction",
            "initial_stop": "opposite extreme of the completed opening candle; active from the entry bar onward for every exit",
            "forced_exit": "for stop_and_1555, reference exit is the close of the bar timestamped 15:55 New York (or the final available early-close bar); actual simulated fill includes adverse one-tick exit slippage",
            "profit_targets": {"fixed_4r": "4 times initial reference risk", "fixed_5r": "5 times initial reference risk", "stop_and_1555": "none"},
            "costs": {"round_trip_spread_ticks": 1, "slippage_ticks_per_side": 1, "round_trip_fees": 5.10, "baseline_all_in_round_trip": 20.10},
            "same_bar": "if stop and target are both touched in one OHLC bar, adverse-first; EOD has no target, so only the stop can terminate it intrabar",
            "sessions": "the same 1,959 accepted NQ sessions dated 2018-2025",
            "stop_difference": "none; stop price, activation, gap-through handling, tick rounding, spread, slippage, and fees are identical across all three exits",
        },
        "variants": variant_results,
        "walk_forward": _walk_forward(frames),
        "delayed_entry": delayed_results,
        "statistical_reporting": statistics,
        "holding_time_discrepancy": holding_discrepancy,
        "final_decision": {
            "choice": "C",
            "candidate": "Simple opening candle with initial stop plus fixed 15:55-bar-close exit and no profit target",
            "authorization": "prospective paper trading only",
            "evidence_label": "Historical exploratory",
            "why": "Within the bounded three-exit comparison it had the highest net profit and profit factor, the lowest maximum drawdown, the highest cost break-even, and was selected using prior years for every 2022-2025 test year. It is more dependent on its largest individual trend days than 4R or 5R, so the purpose of prospective paper trading is specifically to audit that fragility and real execution. This is not validation and does not authorize live or automated trading.",
        },
        "inspection_status": "All 2018-2025 data has now been inspected; no result is a clean holdout.",
    }
    (root / "research/phase4-results.json").write_text(json.dumps(result, indent=2, default=str))
    pd.concat([frame.assign(audit_variant=name) for name, frame in frames.items()], ignore_index=True).to_parquet(root / "research/phase4-trades.parquet", index=False, compression="zstd")
    pd.concat([frame.assign(audit_variant=name) for name, frame in delayed_payload["frames"].items()], ignore_index=True).to_parquet(root / "research/phase4-delayed-trades.parquet", index=False, compression="zstd")
    return result
