from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pandas_market_calendars as mcal

from .phase5 import ProtectedMarketDataGuard, _execute, _tail_tests, _trade_metrics, c01_signals
from .research import NQ_FP, _bar, _condition_dates, _quality, _roll_dates
from .strategies import aggregate_five_minute


EMA_PERIODS = (150, 200, 250)
VOLUME_RATIOS = (.8, 1.0, 1.2)


def run_c01_robustness(root: Path = Path("data")) -> dict:
    guard = ProtectedMarketDataGuard(root); manifest = guard.manifest(); before = guard.checksums(manifest)
    dataset = manifest["datasets"][NQ_FP]
    degraded, _ = _condition_dates(root)
    roll_dates = _roll_dates([Path(partition["mapping_path"]) for partition in dataset["partitions"]])
    schedule = mcal.get_calendar("NYSE").schedule("2018-01-01", "2025-12-31")
    parameters = [(ema_period, volume_ratio) for ema_period in EMA_PERIODS for volume_ratio in VOLUME_RATIOS]
    trades = defaultdict(list); equity = defaultdict(lambda: 100_000.0); accepted = []
    include_roll_trades = []; include_roll_equity = 100_000.0; include_roll_accepted = []
    prior_tail = pd.DataFrame(); history_fives = []; include_roll_history = []

    for partition in sorted(dataset["partitions"], key=lambda row: int(row["year"])):
        year = int(partition["year"])
        if year >= 2026:
            raise RuntimeError("protected partition rejected before market read")
        if year < 2018:
            continue
        current = guard.read_parquet(partition["path"])
        frame = pd.concat([prior_tail, current], ignore_index=True).sort_values("ts_ny") if len(prior_tail) else current
        for session_day, calendar_row in schedule[schedule.index.year == year].iterrows():
            day = session_day.date(); market_open = calendar_row.market_open.tz_convert("America/New_York"); market_close = calendar_row.market_close.tz_convert("America/New_York")
            rth_frame = frame[(frame.ts_ny >= market_open) & (frame.ts_ny < market_close)].copy()
            expected = int((market_close - market_open).total_seconds() / 60)
            baseline_ok, _ = _quality(day, rth_frame, expected, degraded, roll_dates)
            include_ok, _ = _quality(day, rth_frame, expected, degraded, set())
            if not baseline_ok and not include_ok:
                continue
            rth = [_bar(row) for row in rth_frame.itertuples(index=False)]
            if include_ok:
                include_roll_accepted.append(day)
                signal = c01_signals(rth, include_roll_history)
                if signal:
                    trade = _execute(signal[0], rth, "NQ", include_roll_equity, "matched_4R", "fixed1", f"C01:include-roll:{day}")
                    if trade:
                        include_roll_trades.append(trade); include_roll_equity += trade.net_pnl
                include_roll_history.extend(aggregate_five_minute(rth)); include_roll_history = include_roll_history[-1000:]
            if baseline_ok:
                accepted.append(day)
                for ema_period, volume_ratio in parameters:
                    key = f"ema_{ema_period}:volume_{volume_ratio:.1f}"
                    signal = c01_signals(rth, history_fives, ema_period, volume_ratio)
                    if not signal:
                        continue
                    trade = _execute(signal[0], rth, "NQ", equity[key], "matched_4R", "fixed1", f"C01:{key}:{day}")
                    if trade:
                        trades[key].append(trade); equity[key] += trade.net_pnl
                history_fives.extend(aggregate_five_minute(rth)); history_fives = history_fives[-1000:]
        cutoff = current.ts_ny.max() - pd.Timedelta(days=4); prior_tail = current[current.ts_ny >= cutoff].copy()

    surface = {}
    for ema_period, volume_ratio in parameters:
        key = f"ema_{ema_period}:volume_{volume_ratio:.1f}"
        metrics = _trade_metrics(trades[key], accepted); metrics.pop("session_r", None); metrics.pop("equity", None)
        metrics["tail"] = _tail_tests(trades[key]); surface[key] = metrics
    roll_metrics = _trade_metrics(include_roll_trades, include_roll_accepted); roll_metrics.pop("session_r", None); roll_metrics.pop("equity", None)
    after = guard.checksums(manifest)
    if before != after:
        raise RuntimeError("raw cache immutability failure")
    result = {
        "schema_version": 1, "candidate": "C01", "selection_eligible": False,
        "purpose": "bounded post-selection plateau and roll-exclusion robustness audit",
        "frozen_center": {"ema_period": 200, "volume_ratio": 1.0},
        "parameter_surface": surface,
        "roll_sensitivity": {"baseline_excluded_roll_sessions": surface["ema_200:volume_1.0"], "include_roll_sessions": roll_metrics,
                             "note": "Include-roll is an audit sensitivity only; the authoritative tournament excludes contract-roll sessions."},
        "raw_cache_immutable": True,
    }
    destination = root / "research/phase5-c01-robustness.json"
    destination.write_text(json.dumps(result, indent=2, default=str))
    return result
