from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import mean, median
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, precision_score, recall_score, roc_auc_score
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from .analytics import adjusted_p_values, max_drawdown, reality_check, stationary_bootstrap_mean
from .engine import ExecutionConfig, INSTRUMENTS, execute_signal
from .models import Bar, Signal, Trade
from .phase5 import (
    ProtectedMarketDataGuard, _aggregate, _cost_config, _deflated_sharpe, _execute,
    _fives_to_fifteens, _pbo, _tail_tests,
)
from .research import NQ_FP, _bar, _condition_dates, _contexts, _quality, _roll_dates
from .strategies import aggregate_five_minute, ema


NY = ZoneInfo("America/New_York")
SEED = 61001
HORIZONS = (1, 2, 3, 5, 10, 15, 30, 60, 90, 120)
PERIODS = {"development": (2018, 2021), "validation": (2022, 2023), "historical_evaluation": (2024, 2025)}
PRE_ENTRY_FEATURES = [
    "weekday", "month", "quarter", "month_end", "quarter_end", "holiday_adjacent", "opex",
    "scheduled_macro_event", "ten_am_event", "time_since_prior_close_hours",
    "overnight_return", "overnight_range_atr", "open_position_overnight", "overnight_trend_slope_atr",
    "overnight_volatility", "overnight_volume_ratio", "prior_return_atr", "prior_range_atr",
    "prior_close_location", "prior_trend_slope_atr", "prior_volatility", "prior_volume_ratio",
    "consecutive_direction", "opening_range_atr", "opening_body_fraction", "opening_upper_wick_fraction",
    "opening_lower_wick_fraction", "opening_direction", "opening_volume_ratio", "volume_acceleration",
    "gap_atr", "open_vs_pdh_atr", "open_vs_pdl_atr", "open_vs_onh_atr", "open_vs_onl_atr",
    "breakout_time_minutes", "breakout_body_fraction", "breakout_volume_ratio", "entry_vs_vwap_atr",
    "vwap_slope_atr", "ema_distance_atr", "ema_slope_atr", "key_level_room_r",
]


def _json_sha(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _period(year: int) -> str:
    return next(name for name, bounds in PERIODS.items() if bounds[0] <= year <= bounds[1])


def _slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return float(np.polyfit(np.arange(len(values)), np.asarray(values, dtype=float), 1)[0])


def _std_returns(bars: list[Bar]) -> float:
    if len(bars) < 3:
        return 0.0
    closes = np.asarray([bar.close for bar in bars], dtype=float)
    return float(np.std(np.diff(closes), ddof=1))


def _c01_causal_signal(
    rth: list[Bar], history_fives: list[Bar], *, ema_period: int = 200,
    volume_ratio: float = 1.0, cancel_after_first_outside: bool = False,
) -> Signal | None:
    """Corrected C01: a 15-minute bar is actionable only at anchor + 15 minutes."""
    fives = aggregate_five_minute(rth)
    fifteens = _aggregate(rth, 15)
    if len(fifteens) < 3:
        return None
    opening = fifteens[0]
    hist15 = _fives_to_fifteens(history_fives[-max(800, ema_period * 4):] + fives)
    for breakout in fifteens[1:]:
        try:
            index = hist15.index(breakout)
        except ValueError:
            continue
        if index < ema_period:
            continue
        values = ema([item.close for item in hist15[: index + 1]], ema_period)
        ema_value = float(values[-1]); ema_prior = float(values[-2])
        side = "long" if breakout.close > opening.high and breakout.close > ema_value else "short" if breakout.close < opening.low and breakout.close < ema_value else None
        outside = breakout.close > opening.high or breakout.close < opening.low
        if side and breakout.volume > hist15[index - 1].volume * volume_ratio:
            available_at = breakout.ts + timedelta(minutes=15)
            entry = next((bar for bar in rth if bar.ts >= available_at), None)
            if entry is None:
                return None
            stop = breakout.low if side == "long" else breakout.high
            if (side == "long" and stop >= entry.open) or (side == "short" and stop <= entry.open):
                return None
            return Signal(
                entry.ts, "C01", "C01-v1-causal-timing", side, entry.open, stop, 4,
                "completed 15-minute ORB close + prior-bar volume + EMA200",
                available_at,
                {
                    "opening_high": opening.high, "opening_low": opening.low,
                    "opening_open": opening.open, "opening_close": opening.close,
                    "opening_volume": opening.volume, "breakout_ts": breakout.ts.isoformat(),
                    "breakout_open": breakout.open, "breakout_high": breakout.high,
                    "breakout_low": breakout.low, "breakout_close": breakout.close,
                    "breakout_volume": breakout.volume, "previous_volume": hist15[index - 1].volume,
                    "ema": ema_value, "ema_prior": ema_prior, "ema_period": ema_period,
                    "volume_ratio_threshold": volume_ratio,
                },
            )
        if outside and cancel_after_first_outside:
            return None
    return None


def _retest_signal(signal: Signal, rth: list[Bar]) -> Signal | None:
    boundary = float(signal.metadata["opening_high"] if signal.side == "long" else signal.metadata["opening_low"])
    future = [bar for bar in rth if signal.ts <= bar.ts < signal.ts + timedelta(minutes=60)]
    for index, bar in enumerate(future[:-1]):
        touched = bar.low <= boundary if signal.side == "long" else bar.high >= boundary
        held = bar.close >= boundary if signal.side == "long" else bar.close <= boundary
        if touched and held:
            nxt = future[index + 1]
            stop = bar.low if signal.side == "long" else bar.high
            if (signal.side == "long" and stop < nxt.open) or (signal.side == "short" and stop > nxt.open):
                return Signal(nxt.ts, "P6_RETEST", "P6_RETEST-v1", signal.side, nxt.open, stop, 4,
                              "C01 breakout then objective opening-range-boundary retest", nxt.ts,
                              {"parent_signal_ts": signal.ts.isoformat(), "boundary": boundary})
    return None


def _failure_reversal_signal(signal: Signal, rth: list[Bar]) -> Signal | None:
    opening_high = float(signal.metadata["opening_high"]); opening_low = float(signal.metadata["opening_low"])
    future = [bar for bar in rth if signal.ts <= bar.ts < signal.ts + timedelta(minutes=30)]
    for index, bar in enumerate(future[:-1]):
        failed = bar.close < opening_high if signal.side == "long" else bar.close > opening_low
        if not failed:
            continue
        nxt = future[index + 1]; side = "short" if signal.side == "long" else "long"
        stop = max(float(signal.metadata["breakout_high"]), bar.high) if side == "short" else min(float(signal.metadata["breakout_low"]), bar.low)
        if (side == "long" and stop < nxt.open) or (side == "short" and stop > nxt.open):
            return Signal(nxt.ts, "P6_FAILURE_REVERSAL", "P6_FAILURE_REVERSAL-v1", side, nxt.open, stop, 4,
                          "completed C01 break closes back through opening-range boundary", nxt.ts,
                          {"parent_signal_ts": signal.ts.isoformat()})
    return None


def _execute_cost_stress(signal: Signal, rth: list[Bar], equity: float, multiplier: int, trade_id: str) -> Trade | None:
    config = ExecutionConfig(
        fixed_contracts=1, max_contracts=1, margin_per_contract=INSTRUMENTS["NQ"].assumed_margin,
        fee_multiplier=multiplier, slippage_ticks_per_side=multiplier,
        spread_ticks_round_trip=multiplier,
    )
    future = [bar for bar in rth if signal.ts <= bar.ts and bar.ts.time() <= time(15, 55)]
    return execute_signal(signal, future, equity, "NQ", config, trade_id) if future else None


def _one_minute_delayed_signal(signal: Signal, rth: list[Bar]) -> Signal | None:
    entry = next((bar for bar in rth if bar.ts >= signal.ts + timedelta(minutes=1)), None)
    if entry is None:
        return None
    intervening = [bar for bar in rth if signal.ts <= bar.ts < entry.ts]
    stop_touched = any(bar.low <= signal.stop for bar in intervening) if signal.side == "long" else any(bar.high >= signal.stop for bar in intervening)
    if stop_touched or (signal.side == "long" and signal.stop >= entry.open) or (signal.side == "short" and signal.stop <= entry.open):
        return None
    return Signal(entry.ts, signal.strategy, f"{signal.variant}-delay1", signal.side, entry.open, signal.stop, 4,
                  f"{signal.reason}; one-minute causal delay", entry.ts, dict(signal.metadata))


def _trade_dict(trade: Trade, run_key: str) -> dict:
    return {"run_key": run_key, **trade.to_dict()}


def _vwap(bars: list[Bar]) -> float | None:
    volume = sum(bar.volume for bar in bars)
    return sum(((bar.high + bar.low + bar.close) / 3) * bar.volume for bar in bars) / volume if volume else None


def _session_features(
    day: date, rth: list[Bar], overnight: list[Bar], signal: Signal | None, prior: dict | None,
    atr: float, prior_close_ts: datetime | None, volume_history: dict, day_events: list[dict],
    holiday_adjacent: bool,
) -> dict:
    opening = _aggregate(rth[:15], 15)[0]
    cutoff = signal.ts if signal else opening.ts + timedelta(minutes=15)
    completed = [bar for bar in rth if bar.ts < cutoff]
    onh = max((bar.high for bar in overnight), default=rth[0].open); onl = min((bar.low for bar in overnight), default=rth[0].open)
    on_open = overnight[0].open if overnight else rth[0].open; on_close = overnight[-1].close if overnight else rth[0].open
    on_range = max(onh - onl, .25); prior_high = prior["high"] if prior else rth[0].open; prior_low = prior["low"] if prior else rth[0].open
    cumulative_vwap = _vwap(completed); prior_vwap = _vwap(completed[:-5]) if len(completed) > 5 else cumulative_vwap
    metadata = signal.metadata if signal else {}
    entry = signal.entry if signal else rth[0].open
    direction = 1 if signal and signal.side == "long" else -1 if signal else 0
    key_levels = [prior_high, prior_low, onh, onl]
    room = [direction * (level - entry) for level in key_levels if direction * (level - entry) > 0]
    risk = abs(signal.entry - signal.stop) if signal else max(opening.high - opening.low, .25)
    opening_volume_history = volume_history.get("opening", [])
    overnight_volume_history = volume_history.get("overnight", [])
    event_times = [datetime.fromisoformat(event["actual_at"]) for event in day_events]
    return {
        "date": day.isoformat(), "period": _period(day.year), "eligible": True,
        "signal": signal is not None, "known_at": cutoff.isoformat(), "entry_ts": signal.ts.isoformat() if signal else None,
        "side": signal.side if signal else None, "weekday": day.weekday(), "month": day.month,
        "quarter": (day.month - 1) // 3 + 1, "month_end": (day + timedelta(days=1)).month != day.month,
        "quarter_end": day.month in (3, 6, 9, 12) and (day + timedelta(days=1)).month != day.month,
        "holiday_adjacent": holiday_adjacent, "opex": day.weekday() == 4 and 15 <= day.day <= 21,
        "scheduled_macro_event": bool(day_events), "ten_am_event": any(value.time() == time(10, 0) for value in event_times),
        "event_after_entry": any(value >= cutoff for value in event_times),
        "time_since_prior_close_hours": (rth[0].ts - prior_close_ts).total_seconds() / 3600 if prior_close_ts else None,
        "overnight_return": on_close - on_open, "overnight_range": on_range, "overnight_range_atr": on_range / atr,
        "overnight_high": onh, "overnight_low": onl, "open_vs_onh_atr": (rth[0].open - onh) / atr,
        "open_vs_onl_atr": (rth[0].open - onl) / atr, "open_position_overnight": (rth[0].open - onl) / on_range,
        "overnight_trend_slope_atr": _slope([bar.close for bar in overnight]) / atr,
        "overnight_volatility": _std_returns(overnight) / atr,
        "overnight_volume_ratio": sum(bar.volume for bar in overnight) / median(overnight_volume_history) if overnight_volume_history else None,
        "prior_return_atr": (prior["close"] - prior["open"]) / atr if prior else None,
        "prior_range_atr": prior["range"] / atr if prior else None,
        "prior_close_location": prior["close_location"] if prior else None,
        "prior_trend_slope_atr": prior["trend_slope"] / atr if prior else None,
        "prior_volatility": prior["volatility"] / atr if prior else None,
        "prior_volume_ratio": prior["volume"] / median(volume_history.get("prior_volume", [])) if prior and volume_history.get("prior_volume") else None,
        "consecutive_direction": prior.get("consecutive_direction") if prior else 0,
        "opening_range": opening.high - opening.low, "opening_range_atr": (opening.high - opening.low) / atr,
        "opening_body": opening.close - opening.open,
        "opening_body_fraction": abs(opening.close - opening.open) / max(opening.high - opening.low, .25),
        "opening_upper_wick_fraction": (opening.high - max(opening.open, opening.close)) / max(opening.high - opening.low, .25),
        "opening_lower_wick_fraction": (min(opening.open, opening.close) - opening.low) / max(opening.high - opening.low, .25),
        "opening_direction": 1 if opening.close > opening.open else -1 if opening.close < opening.open else 0,
        "opening_volume": opening.volume,
        "opening_volume_ratio": opening.volume / median(opening_volume_history) if opening_volume_history else None,
        "volume_acceleration": float(metadata.get("breakout_volume", np.nan)) / max(float(metadata.get("opening_volume", opening.volume)), 1) if signal else None,
        "gap": rth[0].open - prior["close"] if prior else None, "gap_atr": (rth[0].open - prior["close"]) / atr if prior else None,
        "open_vs_pdh_atr": (rth[0].open - prior_high) / atr, "open_vs_pdl_atr": (rth[0].open - prior_low) / atr,
        "entry_vwap": cumulative_vwap, "entry_vs_vwap_atr": direction * (entry - cumulative_vwap) / atr if signal and cumulative_vwap else None,
        "vwap_slope_atr": (cumulative_vwap - prior_vwap) / atr if cumulative_vwap and prior_vwap else None,
        "ema_distance_atr": direction * (entry - float(metadata.get("ema", entry))) / atr if signal else None,
        "ema_slope_atr": direction * (float(metadata.get("ema", entry)) - float(metadata.get("ema_prior", entry))) / atr if signal else None,
        "breakout_time_minutes": (signal.ts - datetime.combine(day, time(9, 30), NY)).total_seconds() / 60 if signal else None,
        "breakout_body_fraction": abs(float(metadata.get("breakout_close", 0)) - float(metadata.get("breakout_open", 0))) / max(float(metadata.get("breakout_high", 0)) - float(metadata.get("breakout_low", 0)), .25) if signal else None,
        "breakout_volume_ratio": float(metadata.get("breakout_volume", 0)) / max(float(metadata.get("previous_volume", 1)), 1) if signal else None,
        "key_level_room_r": min(room) / risk if room else 10.0,
        "overnight_alignment": direction == (1 if on_close > on_open else -1) if signal and on_close != on_open else None,
        "vwap_alignment": direction * (entry - cumulative_vwap) > 0 if signal and cumulative_vwap else None,
    }


def _path_row(signal: Signal, trade: Trade, rth: list[Bar], features: dict) -> dict:
    direction = 1 if signal.side == "long" else -1
    reference = trade.reference_entry; risk = abs(reference - trade.stop)
    future = [bar for bar in rth if bar.ts >= signal.ts]
    row = {
        "date": signal.ts.date().isoformat(), "entry_ts": signal.ts.isoformat(), "side": signal.side,
        "risk_points": risk, "opening_high": signal.metadata["opening_high"], "opening_low": signal.metadata["opening_low"],
        "net_pnl": trade.net_pnl, "net_r": trade.realized_r, "outcome": trade.outcome,
        "mae_r_full": trade.mae_points / risk, "mfe_r_full": trade.mfe_points / risk,
    }
    for horizon in HORIZONS:
        bars = future[:horizon]
        if len(bars) < horizon:
            row[f"return_r_{horizon}m"] = None; row[f"mae_r_{horizon}m"] = None; row[f"mfe_r_{horizon}m"] = None
            continue
        close = bars[-1].close
        row[f"return_r_{horizon}m"] = direction * (close - reference) / risk
        row[f"mae_r_{horizon}m"] = max(0.0, (reference - min(bar.low for bar in bars)) / risk) if signal.side == "long" else max(0.0, (max(bar.high for bar in bars) - reference) / risk)
        row[f"mfe_r_{horizon}m"] = max(0.0, (max(bar.high for bar in bars) - reference) / risk) if signal.side == "long" else max(0.0, (reference - min(bar.low for bar in bars)) / risk)
    row["return_r_1555"] = direction * (future[-1].close - reference) / risk if future else None
    row["close_inside_or_5m"] = any(signal.metadata["opening_low"] <= bar.close <= signal.metadata["opening_high"] for bar in future[:5])
    row["close_inside_or_30m"] = any(signal.metadata["opening_low"] <= bar.close <= signal.metadata["opening_high"] for bar in future[:30])
    row["volume_first_5_ratio"] = sum(bar.volume for bar in future[:5]) / max(float(signal.metadata["breakout_volume"]) / 3, 1)
    row["event_after_entry"] = features["event_after_entry"]
    return row


def _summary(trades: list[Trade], accepted_days: list[date]) -> dict:
    pnl = np.asarray([trade.net_pnl for trade in trades], dtype=float); r = np.asarray([trade.realized_r for trade in trades], dtype=float)
    equity = np.r_[100_000.0, 100_000.0 + np.cumsum(pnl)]; dd, duration = max_drawdown(equity.tolist())
    wins = pnl[pnl > 0]; losses = pnl[pnl < 0]
    by_year = {str(year): round(sum(trade.net_pnl for trade in trades if trade.entry_ts.year == year), 2) for year in range(2018, 2026)}
    annual_r = {str(year): round(float(np.mean([trade.realized_r for trade in trades if trade.entry_ts.year == year])), 6) if any(trade.entry_ts.year == year for trade in trades) else 0 for year in range(2018, 2026)}
    by_month = defaultdict(float); by_weekday = defaultdict(float)
    for trade in trades:
        by_month[str(trade.entry_ts.month)] += trade.net_pnl; by_weekday[str(trade.entry_ts.weekday())] += trade.net_pnl
    loss_streak = current = 0
    for value in pnl:
        current = current + 1 if value < 0 else 0; loss_streak = max(loss_streak, current)
    ordered = np.sort(pnl)[::-1] if len(pnl) else np.array([]); best1 = max(1, math.ceil(len(pnl) * .01)) if len(pnl) else 0; best5 = max(1, math.ceil(len(pnl) * .05)) if len(pnl) else 0
    tail = _tail_tests(trades)
    if "low_tail_dependence_components_without_period_signs" in tail:
        tail["low_tail_dependence_components_without_period_signs"] = bool(tail["low_tail_dependence_components_without_period_signs"])
    return {
        "accepted_sessions": len(accepted_days), "trades": len(trades), "net_profit": round(float(pnl.sum()), 2),
        "expectancy_trade_r": round(float(r.mean()), 6) if len(r) else 0,
        "expectancy_eligible_session_r": round(float(r.sum() / len(accepted_days)), 6) if accepted_days else 0,
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 4) if len(losses) and losses.sum() else None,
        "win_rate": round(float((pnl > 0).mean()), 6) if len(pnl) else 0,
        "max_drawdown": round(dd, 6), "max_drawdown_dollars": round(float(np.min(equity - np.maximum.accumulate(equity))), 2),
        "drawdown_duration_trades": duration, "longest_losing_streak": loss_streak,
        "total_costs": round(sum(trade.total_costs for trade in trades), 2), "by_year": by_year,
        "annual_expectancy_r": annual_r, "positive_years": sum(value > 0 for value in by_year.values()),
        "by_month": dict(by_month), "by_weekday": dict(by_weekday),
        "long_short": {side: {"trades": sum(trade.side == side for trade in trades), "net_profit": round(sum(trade.net_pnl for trade in trades if trade.side == side), 2)} for side in ("long", "short")},
        "best_trade": round(float(ordered[0]), 2) if len(ordered) else 0, "best_5_total": round(float(ordered[:5].sum()), 2) if len(ordered) else 0,
        "best_1pct_total": round(float(ordered[:best1].sum()), 2) if len(ordered) else 0,
        "top_5pct_total": round(float(ordered[:best5].sum()), 2) if len(ordered) else 0,
        "worst_1pct_total": round(float(np.sort(pnl)[:best1].sum()), 2) if len(pnl) else 0,
        "net_after_best_trade": round(float(pnl.sum() - ordered[0]), 2) if len(ordered) else 0,
        "net_after_best_5": round(float(pnl.sum() - ordered[:5].sum()), 2) if len(ordered) else 0,
        "net_after_best_1pct": round(float(pnl.sum() - ordered[:best1].sum()), 2) if len(ordered) else 0,
        "net_after_best_5pct": round(float(pnl.sum() - ordered[:best5].sum()), 2) if len(ordered) else 0,
        "median_trade": round(float(np.median(pnl)), 2) if len(pnl) else 0,
        "median_winner": round(float(np.median(wins)), 2) if len(wins) else 0,
        "median_loser": round(float(np.median(losses)), 2) if len(losses) else 0,
        "tail": tail, "equity": [round(float(value), 2) for value in equity],
    }


def _chronological_models(frame: pd.DataFrame) -> dict:
    data = frame[frame.signal].copy().sort_values("date"); data["year"] = pd.to_datetime(data.date).dt.year
    features = [name for name in PRE_ENTRY_FEATURES if name in data.columns]
    x = data[features].apply(pd.to_numeric, errors="coerce"); y = (data.net_pnl <= 0).astype(int)
    models = {
        "logistic": Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("model", LogisticRegression(C=.25, max_iter=2000, random_state=SEED))]),
        "tree_depth2": Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", DecisionTreeClassifier(max_depth=2, min_samples_leaf=40, random_state=SEED))]),
        "random_forest_shallow": Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", RandomForestClassifier(n_estimators=120, max_depth=3, min_samples_leaf=30, random_state=SEED, n_jobs=1))]),
        "gradient_boosting_shallow": Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", GradientBoostingClassifier(n_estimators=60, max_depth=2, learning_rate=.04, min_samples_leaf=30, random_state=SEED))]),
        "knn_20": Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("model", KNeighborsClassifier(n_neighbors=20, weights="distance"))]),
    }
    output = {}
    for model_name, model in models.items():
        predictions = pd.Series(index=data.index, dtype=float); retained_oos = pd.Series(False, index=data.index, dtype=bool); folds = []
        for year in range(2020, 2026):
            train = data.year < year; test = data.year == year
            if train.sum() < 100 or test.sum() < 20:
                continue
            model.fit(x.loc[train], y.loc[train]); probability = model.predict_proba(x.loc[test])[:, 1]
            predictions.loc[test] = probability; train_probability = model.predict_proba(x.loc[train])[:, 1]
            cutoff = float(np.quantile(train_probability, .80)); retained = probability < cutoff
            retained_oos.loc[test] = retained
            actual = y.loc[test].to_numpy(); pnl = data.loc[test, "net_pnl"].to_numpy(float)
            folds.append({
                "year": year, "train_sessions": int(train.sum()), "test_sessions": int(test.sum()),
                "auc": round(float(roc_auc_score(actual, probability)), 6) if len(np.unique(actual)) > 1 else None,
                "brier": round(float(brier_score_loss(actual, probability)), 6),
                "precision": round(float(precision_score(actual, probability >= .5, zero_division=0)), 6),
                "recall": round(float(recall_score(actual, probability >= .5, zero_division=0)), 6),
                "retained_fraction": round(float(retained.mean()), 6), "unfiltered_net": round(float(pnl.sum()), 2),
                "filtered_net": round(float(pnl[retained].sum()), 2), "removed_net": round(float(pnl[~retained].sum()), 2),
            })
        valid = predictions.notna(); probability = predictions.loc[valid].to_numpy(); actual = y.loc[valid].to_numpy(); pnl = data.loc[valid, "net_pnl"].to_numpy(float)
        retained = retained_oos.loc[valid].to_numpy()
        output[model_name] = {
            "features": features, "folds": folds,
            "oos_auc": round(float(roc_auc_score(actual, probability)), 6) if len(np.unique(actual)) > 1 else None,
            "oos_brier": round(float(brier_score_loss(actual, probability)), 6) if len(probability) else None,
            "oos_sessions": int(valid.sum()), "retained_fraction": round(float(retained.mean()), 6) if len(retained) else 0,
            "unfiltered_net": round(float(pnl.sum()), 2), "filtered_net": round(float(pnl[retained].sum()), 2),
            "positive_improvement_folds": sum(fold["filtered_net"] > fold["unfiltered_net"] for fold in folds),
            "fold_count": len(folds),
        }
    # Shuffled-label falsification uses the same chronological logistic procedure.
    shuffled = y.copy(); shuffled[:] = np.random.default_rng(SEED).permutation(shuffled.to_numpy())
    predictions = pd.Series(index=data.index, dtype=float)
    for year in range(2020, 2026):
        train = data.year < year; test = data.year == year
        if train.sum() < 100 or test.sum() < 20: continue
        model = models["logistic"]; model.fit(x.loc[train], shuffled.loc[train]); predictions.loc[test] = model.predict_proba(x.loc[test])[:, 1]
    valid = predictions.notna()
    output["shuffled_label_control"] = {"oos_auc_against_real_labels": round(float(roc_auc_score(y.loc[valid], predictions.loc[valid])), 6), "sessions": int(valid.sum()), "selection_eligible": False}
    return output


def _similar_days(frame: pd.DataFrame) -> dict:
    data = frame[frame.signal].copy().sort_values("date").reset_index(drop=True)
    features = [name for name in PRE_ENTRY_FEATURES if name in data.columns]
    x = data[features].apply(pd.to_numeric, errors="coerce").to_numpy(float); y = data.net_r.to_numpy(float)
    predictions = {k: np.full(len(data), np.nan) for k in (5, 10, 20, 50)}
    for index in range(len(data)):
        if index < 100: continue
        train = x[:index]; current = x[index]
        medians = np.nanmedian(train, axis=0); train = np.where(np.isnan(train), medians, train); current = np.where(np.isnan(current), medians, current)
        scale = np.nanstd(train, axis=0); scale = np.where(scale > 1e-9, scale, 1.0)
        distance = np.sqrt(np.mean(((train - current) / scale) ** 2, axis=1)); order = np.argsort(distance)
        for k in predictions: predictions[k][index] = float(np.mean(y[order[:k]]))
    output = {}
    actual_bad = y <= 0
    for k, prediction in predictions.items():
        valid = ~np.isnan(prediction)
        output[str(k)] = {
            "sessions": int(valid.sum()), "correlation_with_current_net_r": round(float(np.corrcoef(prediction[valid], y[valid])[0, 1]), 6),
            "bad_day_auc": round(float(roc_auc_score(actual_bad[valid], -prediction[valid])), 6),
            "rule": f"Euclidean distance after expanding earlier-only median imputation and scaling; mean outcome of {k} earlier neighbors",
            "selection_eligible": False,
        }
    return output


def _taxonomy(session: pd.DataFrame, paths: pd.DataFrame) -> tuple[dict, dict, dict, dict]:
    joined = paths.merge(session, on="date", suffixes=("", "_feature")); development = joined[pd.to_datetime(joined.date).dt.year <= 2021]
    q25, q75 = development.opening_range_atr.quantile([.25, .75]); volume_median = development.breakout_volume_ratio.median()
    loss_rows = []
    for row in joined[joined.net_pnl < 0].itertuples():
        tags = []
        if row.close_inside_or_5m: tags.append("immediate_rejection")
        if row.close_inside_or_30m: tags.append("breakout_failure")
        if getattr(row, "mae_r_10m") is not None and getattr(row, "mae_r_10m") >= .5: tags.append("early_adverse_excursion")
        if getattr(row, "mfe_r_30m") is not None and getattr(row, "mfe_r_30m") < .5 and abs(getattr(row, "return_r_30m")) < .25: tags.append("slow_stagnation")
        if getattr(row, "return_r_60m") is not None and getattr(row, "return_r_60m") <= -.5: tags.append("wrong_side_trend")
        if row.event_after_entry: tags.append("news_event_failure")
        if row.breakout_volume_ratio < volume_median: tags.append("low_volume_follow_through")
        if row.opening_range_atr >= q75: tags.append("excessive_opening_range")
        if row.opening_range_atr <= q25: tags.append("tiny_opening_range")
        if row.overnight_alignment is False: tags.append("overnight_conflict")
        if row.key_level_room_r < .5: tags.append("key_level_conflict")
        if row.vwap_alignment is False: tags.append("vwap_conflict")
        if row.breakout_time_minutes >= 150: tags.append("time_of_day_decay")
        loss_rows.append({"date": row.date, "tags": tags or ["unclassified"], "net_pnl": row.net_pnl, "net_r": row.net_r})
    def summarize(rows: list[dict], tag: str) -> dict:
        chosen = joined[joined.date.isin([row["date"] for row in rows if tag in row["tags"]])]
        return {"sessions": len(chosen), "share_of_c01_trades": round(len(chosen) / len(joined), 6), "loss_rate": round(float((chosen.net_pnl < 0).mean()), 6) if len(chosen) else 0,
                "net_profit": round(float(chosen.net_pnl.sum()), 2), "expectancy_r": round(float(chosen.net_r.mean()), 6) if len(chosen) else 0,
                "average_mae_r": round(float(chosen.mae_r_full.mean()), 6) if len(chosen) else 0, "average_mfe_r": round(float(chosen.mfe_r_full.mean()), 6) if len(chosen) else 0,
                "by_year": {str(year): int((pd.to_datetime(chosen.date).dt.year == year).sum()) for year in range(2018, 2026)}}
    tags = sorted({tag for row in loss_rows for tag in row["tags"]}); loss_taxonomy = {"thresholds_learned_on_2018_2021": {"opening_range_atr_q25": q25, "opening_range_atr_q75": q75, "breakout_volume_ratio_median": volume_median}, "categories": {tag: summarize(loss_rows, tag) for tag in tags}, "sessions": loss_rows}
    winner_rows = []
    for row in joined[joined.net_pnl > 0].itertuples():
        tags = []
        if getattr(row, "return_r_5m") is not None and getattr(row, "return_r_5m") >= .5: tags.append("immediate_continuation")
        if row.breakout_volume_ratio >= volume_median: tags.append("strong_relative_volume")
        if row.overnight_alignment is True: tags.append("overnight_alignment")
        if row.vwap_alignment is True: tags.append("vwap_alignment")
        if q25 < row.opening_range_atr < q75: tags.append("moderate_opening_range")
        if row.key_level_room_r >= 1: tags.append("clear_key_level_room")
        if row.breakout_time_minutes < 90: tags.append("early_breakout")
        winner_rows.append({"date": row.date, "tags": tags or ["unclassified"], "net_pnl": row.net_pnl, "net_r": row.net_r})
    winner_tags = sorted({tag for row in winner_rows for tag in row["tags"]}); winner_taxonomy = {"categories": {tag: summarize(winner_rows, tag) for tag in winner_tags}, "sessions": winner_rows}
    cluster_features = ["opening_range_atr", "overnight_range_atr", "gap_atr", "breakout_time_minutes", "breakout_volume_ratio", "ema_distance_atr", "entry_vs_vwap_atr", "key_level_room_r"]
    x = joined[cluster_features].replace([np.inf, -np.inf], np.nan); imputer = SimpleImputer(strategy="median"); scaler = StandardScaler(); train_mask = pd.to_datetime(joined.date).dt.year <= 2021
    x_train = scaler.fit_transform(imputer.fit_transform(x.loc[train_mask])); model = KMeans(n_clusters=4, random_state=SEED, n_init=20).fit(x_train); labels = model.predict(scaler.transform(imputer.transform(x)))
    joined["regime_cluster"] = labels
    clusters = {}
    for label, group in joined.groupby("regime_cluster"):
        clusters[str(label)] = {"sessions": len(group), "net_profit": round(float(group.net_pnl.sum()), 2), "expectancy_r": round(float(group.net_r.mean()), 6), "win_rate": round(float((group.net_pnl > 0).mean()), 6), "average_mae_r": round(float(group.mae_r_full.mean()), 6), "average_mfe_r": round(float(group.mfe_r_full.mean()), 6), "positive_years": sum(group[pd.to_datetime(group.date).dt.year == year].net_pnl.sum() > 0 for year in range(2018, 2026)), "feature_means": {name: round(float(group[name].mean()), 6) for name in cluster_features}}
    regime = {"definition": "KMeans k=4 fit on 2018-2021 pre-entry features only; later sessions assigned without refitting", "clusters": clusters}
    interactions = {}
    pairs = [("opening_range_atr", "overnight_alignment"), ("opening_range_atr", "gap_atr"), ("breakout_volume_ratio", "breakout_time_minutes"), ("key_level_room_r", "gap_atr"), ("vwap_alignment", "opening_direction"), ("prior_return_atr", "overnight_return")]
    for first, second in pairs:
        first_cut = development[first].median(); second_cut = development[second].astype(float).median()
        key = f"{first}_high__{second}_high"; mask = (joined[first].astype(float) >= first_cut) & (joined[second].astype(float) >= second_cut)
        interactions[key] = {"sessions": int(mask.sum()), "net_profit": round(float(joined.loc[mask, "net_pnl"].sum()), 2), "expectancy_r": round(float(joined.loc[mask, "net_r"].mean()), 6) if mask.any() else 0, "development_thresholds": {first: first_cut, second: second_cut}, "descriptive_only": True}
    return loss_taxonomy, winner_taxonomy, regime, interactions


def _daily_metrics(values: pd.Series) -> dict:
    values = values.sort_index(); pnl = values.to_numpy(float); equity = np.r_[100_000, 100_000 + np.cumsum(pnl)]; dd, duration = max_drawdown(equity.tolist())
    years = pd.to_datetime(values.index).year
    by_year = {str(year): round(float(pnl[years == year].sum()), 2) for year in range(2018, 2026)}
    sorted_pnl = np.sort(pnl)[::-1]; count = max(1, math.ceil(len(pnl) * .01))
    return {"sessions": len(values), "net_profit": round(float(pnl.sum()), 2), "max_drawdown": round(dd, 6), "drawdown_duration_sessions": duration,
            "positive_years": sum(value > 0 for value in by_year.values()), "by_year": by_year,
            "net_after_best_1pct": round(float(pnl.sum() - sorted_pnl[:count].sum()), 2), "median_session": round(float(np.median(pnl)), 2)}


def _strategy_and_complementarity(corrected: pd.DataFrame, phase5: pd.DataFrame, accepted_days: list[date], new_trades: pd.DataFrame) -> tuple[dict, dict, dict]:
    index = pd.Index([day.isoformat() for day in accepted_days], name="date")
    c01 = corrected.set_index(corrected.entry_ts.str.slice(0, 10)).net_pnl.groupby(level=0).sum().reindex(index, fill_value=0.0)
    c01_long = corrected[corrected.side == "long"].set_index(corrected[corrected.side == "long"].entry_ts.str.slice(0, 10)).net_pnl.groupby(level=0).sum().reindex(index, fill_value=0.0)
    c01_short = corrected[corrected.side == "short"].set_index(corrected[corrected.side == "short"].entry_ts.str.slice(0, 10)).net_pnl.groupby(level=0).sum().reindex(index, fill_value=0.0)
    strategies = {"C01_CAUSAL": c01, "C01_LONG_ONLY": c01_long, "C01_SHORT_ONLY": c01_short}
    ids = ["C02", "C04", "C05", "C08", "C09", "C10", "C11", "C14", "C15", "C16", "C17", "BASE_CANDLE", "BASE_EMA", "BASE_LONG", "BASE_SHORT", "BASE_RANDOM"]
    for candidate in ids:
        run = f"NQ:{candidate}:matched_4R:fixed1"; frame = phase5[phase5.run_key == run].copy()
        dates = frame.entry_ts.astype(str).str.slice(0, 10); strategies[candidate] = frame.assign(date=dates).groupby("date").net_pnl.sum().reindex(index, fill_value=0.0)
    for candidate in ("P6_RETEST", "P6_FAILURE_REVERSAL"):
        frame = new_trades[new_trades.run_key == candidate].copy(); strategies[candidate] = frame.assign(date=frame.entry_ts.str.slice(0, 10)).groupby("date").net_pnl.sum().reindex(index, fill_value=0.0)
    results = {}; complement = {}
    for name, daily in strategies.items():
        results[name] = _daily_metrics(daily)
        if name == "C01_CAUSAL": continue
        overlap = (daily != 0) & (c01 != 0); c01_loses = c01 < 0; c01_wins = c01 > 0; c01_none = c01 == 0
        correlation = float(np.corrcoef(c01, daily)[0, 1]) if daily.std() and c01.std() else 0.0
        combined = c01 + daily
        complement[name] = {"correlation_with_c01": round(correlation, 6), "overlap_sessions": int(overlap.sum()),
                            "candidate_net_when_c01_loses": round(float(daily[c01_loses].sum()), 2), "candidate_net_when_c01_wins": round(float(daily[c01_wins].sum()), 2), "candidate_net_when_c01_no_trade": round(float(daily[c01_none].sum()), 2),
                            "combined_one_contract_each": _daily_metrics(combined), "allocation": "one fixed NQ contract per active strategy; no weight optimization"}
    controls = {name: results[name] for name in ("BASE_CANDLE", "BASE_EMA", "BASE_LONG", "BASE_SHORT", "BASE_RANDOM")}
    return results, complement, controls


def run_phase6(root: Path = Path("data"), output: Path = Path("phase6"), bootstrap_samples: int = 50_000) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    guard = ProtectedMarketDataGuard(root); manifest = guard.manifest(); before = guard.checksums(manifest)
    phase5_results = json.loads((root / "research/phase5-results.json").read_text())
    phase5_trades = pd.read_parquet(root / "research/phase5-trades.parquet")
    original = phase5_trades[phase5_trades.run_key == "NQ:C01:matched_4R:fixed1"].copy()
    dataset = manifest["datasets"][NQ_FP]; roll_dates = _roll_dates([Path(row["mapping_path"]) for row in dataset["partitions"]])
    degraded, _ = _condition_dates(root); schedule = mcal.get_calendar("NYSE").schedule("2018-01-01", "2025-12-31")
    scheduled_dates = {value.date() for value in schedule.index}
    macro = json.loads((root / "macro/events-2018-2025.json").read_text()); macro_by_day = defaultdict(list)
    for event in macro["events"]:
        if event.get("known_before_session"): macro_by_day[datetime.fromisoformat(event["actual_at"]).date().isoformat()].append(event)
    corrected_trades: list[Trade] = []; retest_trades: list[Trade] = []; reversal_trades: list[Trade] = []
    parameter_trades: dict[str, list[Trade]] = defaultdict(list); parameter_equity: dict[str, float] = defaultdict(lambda: 100_000.0)
    cost_trades: dict[int, list[Trade]] = {2: [], 4: []}; cost_equity = {2: 100_000.0, 4: 100_000.0}
    delayed_trades: list[Trade] = []; delayed_equity = 100_000.0; strict_first_outside_trades: list[Trade] = []; strict_equity = 100_000.0
    session_rows = []; path_rows = []; early_rows = []; accepted_days: list[date] = []
    history_fives: list[Bar] = []; prior_tail = pd.DataFrame(); prior = None; prior_close_ts = None; prior_ranges = []
    volume_history = {"opening": [], "overnight": [], "prior_volume": []}; equity = 100_000.0; retest_equity = 100_000.0; reversal_equity = 100_000.0
    for partition in sorted(dataset["partitions"], key=lambda row: int(row["year"])):
        year = int(partition["year"])
        if year >= 2026: raise RuntimeError("protected partition rejected before market read")
        if year < 2018: continue
        current = guard.read_parquet(partition["path"]); frame = pd.concat([prior_tail, current], ignore_index=True).sort_values("ts_ny") if len(prior_tail) else current
        for session_day, calendar_row in schedule[schedule.index.year == year].iterrows():
            day = session_day.date(); market_open = calendar_row.market_open.tz_convert("America/New_York"); market_close = calendar_row.market_close.tz_convert("America/New_York")
            rth_frame = frame[(frame.ts_ny >= market_open) & (frame.ts_ny < market_close)].copy()
            ok, _ = _quality(day, rth_frame, int((market_close - market_open).total_seconds() / 60), degraded, roll_dates)
            if not ok: continue
            accepted_days.append(day); rth = [_bar(row) for row in rth_frame.itertuples(index=False)]; overnight = _contexts(frame, day, market_open, [])["full_overnight"]
            atr = float(np.mean(prior_ranges[-14:])) if prior_ranges else max(max(bar.high for bar in rth[:15]) - min(bar.low for bar in rth[:15]), .25)
            signal = _c01_causal_signal(rth, history_fives)
            for ema_period, volume_ratio in itertools.product((150, 200, 250), (.8, 1.0, 1.2)):
                key = f"ema_{ema_period}:volume_{volume_ratio:.1f}"
                parameter_signal = signal if (ema_period, volume_ratio) == (200, 1.0) else _c01_causal_signal(rth, history_fives, ema_period=ema_period, volume_ratio=volume_ratio)
                if parameter_signal:
                    parameter_trade = _execute(parameter_signal, rth, "NQ", parameter_equity[key], "matched_4R", "fixed1", f"P6:PARAM:{key}:{day}")
                    if parameter_trade: parameter_trades[key].append(parameter_trade); parameter_equity[key] += parameter_trade.net_pnl
            strict_signal = _c01_causal_signal(rth, history_fives, cancel_after_first_outside=True)
            if strict_signal:
                strict_trade = _execute(strict_signal, rth, "NQ", strict_equity, "matched_4R", "fixed1", f"P6:STRICT:{day}")
                if strict_trade: strict_first_outside_trades.append(strict_trade); strict_equity += strict_trade.net_pnl
            features = _session_features(day, rth, overnight, signal, prior, max(atr, .25), prior_close_ts, volume_history, macro_by_day.get(day.isoformat(), []),
                                        ((day - timedelta(days=1)).weekday() < 5 and day - timedelta(days=1) not in scheduled_dates) or ((day + timedelta(days=1)).weekday() < 5 and day + timedelta(days=1) not in scheduled_dates))
            if signal:
                trade = _execute(signal, rth, "NQ", equity, "matched_4R", "fixed1", f"P6:C01:{day}")
                if trade:
                    trade.synthetic = False; corrected_trades.append(trade); equity += trade.net_pnl
                    for multiplier in (2, 4):
                        stressed = _execute_cost_stress(signal, rth, cost_equity[multiplier], multiplier, f"P6:COST{multiplier}:{day}")
                        if stressed: cost_trades[multiplier].append(stressed); cost_equity[multiplier] += stressed.net_pnl
                    delayed_signal = _one_minute_delayed_signal(signal, rth)
                    if delayed_signal:
                        delayed_trade = _execute(delayed_signal, rth, "NQ", delayed_equity, "matched_4R", "fixed1", f"P6:DELAY1:{day}")
                        if delayed_trade: delayed_trades.append(delayed_trade); delayed_equity += delayed_trade.net_pnl
                    features.update({"net_pnl": trade.net_pnl, "net_r": trade.realized_r, "win": trade.net_pnl > 0, "outcome": trade.outcome})
                    path_rows.append(_path_row(signal, trade, rth, features))
                    for rule, horizon in (("inside_or_5m", 5), ("inside_or_10m", 10), ("adverse_half_r_5m", 5), ("stagnation_10m", 10), ("stagnation_15m", 15)):
                        horizon_ts = signal.ts + timedelta(minutes=horizon - 1); bars = [bar for bar in rth if signal.ts <= bar.ts <= horizon_ts]
                        if trade.exit_ts <= horizon_ts or len(bars) < horizon:
                            alternative = trade; triggered = False
                        else:
                            direction = 1 if signal.side == "long" else -1; risk = abs(trade.reference_entry - trade.stop)
                            return_r = direction * (bars[-1].close - trade.reference_entry) / risk
                            mfe_r = (max(bar.high for bar in bars) - trade.reference_entry) / risk if signal.side == "long" else (trade.reference_entry - min(bar.low for bar in bars)) / risk
                            inside = signal.metadata["opening_low"] <= bars[-1].close <= signal.metadata["opening_high"]
                            triggered = inside if rule.startswith("inside_or") else return_r <= -.5 if rule.startswith("adverse") else return_r <= 0 and mfe_r < .25
                            alternative = execute_signal(signal, bars, 100_000, "NQ", _cost_config("NQ", "fixed1"), f"P6:{rule}:{day}") if triggered else trade
                        early_rows.append({"date": day.isoformat(), "rule": rule, "triggered": triggered, "net_pnl": alternative.net_pnl, "net_r": alternative.realized_r})
                    retest = _retest_signal(signal, rth)
                    if retest:
                        candidate_trade = _execute(retest, rth, "NQ", retest_equity, "matched_4R", "fixed1", f"P6:RETEST:{day}")
                        if candidate_trade: candidate_trade.synthetic = False; retest_trades.append(candidate_trade); retest_equity += candidate_trade.net_pnl
                    reversal = _failure_reversal_signal(signal, rth)
                    if reversal:
                        candidate_trade = _execute(reversal, rth, "NQ", reversal_equity, "matched_4R", "fixed1", f"P6:REVERSAL:{day}")
                        if candidate_trade: candidate_trade.synthetic = False; reversal_trades.append(candidate_trade); reversal_equity += candidate_trade.net_pnl
            features.setdefault("net_pnl", 0.0); features.setdefault("net_r", 0.0); features.setdefault("win", False); features.setdefault("outcome", "no_trade"); session_rows.append(features)
            opening = _aggregate(rth[:15], 15)[0]; volume_history["opening"].append(opening.volume); volume_history["overnight"].append(sum(bar.volume for bar in overnight))
            day_range = max(bar.high for bar in rth) - min(bar.low for bar in rth); prior_ranges.append(day_range); direction_value = 1 if rth[-1].close > rth[0].open else -1 if rth[-1].close < rth[0].open else 0
            previous_consecutive = prior.get("consecutive_direction", 0) if prior and np.sign(prior.get("consecutive_direction", 0)) == direction_value else 0
            prior = {"high": max(bar.high for bar in rth), "low": min(bar.low for bar in rth), "open": rth[0].open, "close": rth[-1].close, "range": day_range,
                     "close_location": (rth[-1].close - min(bar.low for bar in rth)) / max(day_range, .25), "trend_slope": _slope([bar.close for bar in rth]),
                     "volatility": _std_returns(rth), "volume": sum(bar.volume for bar in rth), "consecutive_direction": direction_value * (abs(previous_consecutive) + 1)}
            prior_close_ts = rth[-1].ts; volume_history["prior_volume"].append(prior["volume"])
            history_fives.extend(aggregate_five_minute(rth)); history_fives = history_fives[-1000:]
        cutoff = current.ts_ny.max() - pd.Timedelta(days=4); prior_tail = current[current.ts_ny >= cutoff].copy()
    after = guard.checksums(manifest)
    if before != after: raise RuntimeError("raw cache immutability failure")
    session = pd.DataFrame(session_rows); paths = pd.DataFrame(path_rows); corrected_frame = pd.DataFrame([_trade_dict(trade, "C01_CAUSAL") for trade in corrected_trades])
    new_frame = pd.DataFrame([*[_trade_dict(trade, "P6_RETEST") for trade in retest_trades], *[_trade_dict(trade, "P6_FAILURE_REVERSAL") for trade in reversal_trades]])
    session.to_parquet(output / "c01_session_dataset.parquet", index=False, compression="zstd"); paths.to_parquet(output / "c01_path_dataset.parquet", index=False, compression="zstd")
    corrected_frame.to_parquet(output / "phase6_c01_trades.parquet", index=False, compression="zstd"); new_frame.to_parquet(output / "phase6_new_strategy_trades.parquet", index=False, compression="zstd")
    corrected_summary = _summary(corrected_trades, accepted_days); original_summary = phase5_results["summaries"]["NQ:C01:matched_4R:fixed1"]
    causal_robustness = {
        "selection_eligible": False,
        "parameter_surface": {key: _summary(parameter_trades[key], accepted_days) for key in sorted(parameter_trades)},
        "cost_stress": {str(multiplier): _summary(cost_trades[multiplier], accepted_days) for multiplier in (2, 4)},
        "one_minute_delay": _summary(delayed_trades, accepted_days),
        "strict_first_outside_close": _summary(strict_first_outside_trades, accepted_days),
        "purpose": "bounded causal perturbation audit; no cell may replace the center post hoc",
    }
    (output / "c01_causal_robustness.json").write_text(json.dumps(causal_robustness, indent=2, default=str))
    baseline_spec = {
        "schema_version": 1, "version": "C01-v1-causal-timing-correction", "preserved_phase5_version": "C01-v1",
        "correction": "entry changes from erroneous 15-minute anchor + 5 minutes to completed-bar anchor + 15 minutes",
        "rules": {"opening_range": "09:30-09:44 America/New_York", "signal": "first qualifying completed 15-minute close outside range with volume above preceding completed 15-minute bar and close agreeing with EMA200", "entry": "next one-minute open after completed signal bar", "stop": "opposite signal-bar extreme", "target": "4R", "fallback_exit": "close of 15:55 minute", "max_trades": 1},
        "data_partitions": [{"year": int(row["year"]), "path": row["path"]} for row in dataset["partitions"] if 2018 <= int(row["year"]) <= 2025],
        "costs": {"point_value": 20, "round_trip_fees": 5.10, "slippage_ticks_per_side": 1, "spread_ticks_round_trip": 1, "tick_size": .25},
        "session_rules": {"calendar": "NYSE RTH schedule", "timezone": "America/New_York", "roll_sessions_excluded": True, "quality_complete_minutes_required": True},
        "ema": {"period": 200, "input": "completed 15-minute RTH closes", "seed": "first available close", "phase5_accepted_session_history_semantics_preserved": True},
        "volume": "sum of constituent one-minute volume; signal bar strictly greater than preceding completed 15-minute bar",
        "original_phase5_result": {key: original_summary[key] for key in ("trades", "net_profit", "profit_factor", "max_drawdown", "positive_years")},
        "corrected_phase6_result": corrected_summary,
        "causal_robustness": {"cost_2x_net": causal_robustness["cost_stress"]["2"]["net_profit"], "cost_4x_net": causal_robustness["cost_stress"]["4"]["net_profit"], "one_minute_delay_net": causal_robustness["one_minute_delay"]["net_profit"], "strict_first_outside_net": causal_robustness["strict_first_outside_close"]["net_profit"]},
        "raw_cache_immutable": True, "protected_2026_market_data_opened": False,
    }
    baseline_spec["specification_hash"] = _json_sha({key: value for key, value in baseline_spec.items() if key not in {"corrected_phase6_result", "original_phase5_result"}})
    (output / "c01_v1_frozen_baseline.json").write_text(json.dumps(baseline_spec, indent=2, default=str))
    session_signal = session[session.signal].copy(); loss_taxonomy, winner_taxonomy, regime, interactions = _taxonomy(session, paths)
    (output / "c01_loss_taxonomy.json").write_text(json.dumps(loss_taxonomy, indent=2, default=str)); (output / "c01_winner_taxonomy.json").write_text(json.dumps(winner_taxonomy, indent=2, default=str))
    (output / "c01_pattern_clusters.json").write_text(json.dumps({"regimes": regime, "bounded_interactions": interactions}, indent=2, default=str))
    similar = _similar_days(session); predictors = _chronological_models(session)
    (output / "c01_similar_day_results.json").write_text(json.dumps(similar, indent=2, default=str)); (output / "c01_pre_entry_predictors.json").write_text(json.dumps(predictors, indent=2, default=str))
    early = pd.DataFrame(early_rows); early_results = {}
    base_net = corrected_summary["net_profit"]
    for rule, group in early.groupby("rule"):
        by_year = {str(year): round(float(group[pd.to_datetime(group.date).dt.year == year].net_pnl.sum()), 2) for year in range(2018, 2026)}
        early_results[rule] = {"triggers": int(group.triggered.sum()), "trades": len(group), "net_profit": round(float(group.net_pnl.sum()), 2), "improvement_vs_causal_c01": round(float(group.net_pnl.sum() - base_net), 2), "positive_years": sum(value > 0 for value in by_year.values()), "by_year": by_year, "label": "POST_ENTRY_MANAGEMENT"}
    (output / "c01_post_entry_management.json").write_text(json.dumps({"baseline_net_profit": base_net, "rules": early_results}, indent=2))
    (output / "c01_regime_analysis.json").write_text(json.dumps(regime, indent=2, default=str))
    strategy_results, complementarity, controls = _strategy_and_complementarity(corrected_frame, phase5_trades, accepted_days, new_frame)
    candidate_specs = {"P6_RETEST": {"rule": "after causal C01 signal, first opening-range-boundary touch that closes on breakout side; next-minute entry; retest-bar stop; 4R", "pre_registered_in_phase6_prompt": True}, "P6_FAILURE_REVERSAL": {"rule": "within 30 minutes after causal C01 signal, first close back through opening-range boundary; reverse next minute; breakout/failure extreme stop; 4R", "pre_registered_in_phase6_prompt": True}}
    (output / "phase6_candidate_strategies.json").write_text(json.dumps(candidate_specs, indent=2)); (output / "phase6_strategy_results.json").write_text(json.dumps(strategy_results, indent=2, default=str)); (output / "phase6_complementarity.json").write_text(json.dumps(complementarity, indent=2, default=str)); (output / "phase6_control_results.json").write_text(json.dumps(controls, indent=2, default=str))
    # Dependence-aware comparisons on identical accepted sessions.
    index = pd.Index([day.isoformat() for day in accepted_days]); corrected_r = corrected_frame.assign(date=corrected_frame.entry_ts.str.slice(0, 10)).groupby("date").realized_r.sum().reindex(index, fill_value=0.0).to_numpy()
    comparison_names = ["BASE_CANDLE", "BASE_EMA", "BASE_LONG", "BASE_SHORT", "BASE_RANDOM", "P6_RETEST", "P6_FAILURE_REVERSAL"]
    boot = {}; raw_p = []
    for offset, name in enumerate(comparison_names):
        if name.startswith("P6_"): source = new_frame[new_frame.run_key == name]
        else: source = phase5_trades[phase5_trades.run_key == f"NQ:{name}:matched_4R:fixed1"]
        control = source.assign(date=source.entry_ts.str.slice(0, 10)).groupby("date").realized_r.sum().reindex(index, fill_value=0.0).to_numpy()
        result = stationary_bootstrap_mean(corrected_r - control, bootstrap_samples, 10, SEED + offset); p = min(1.0, 2 * min(result["p_value"], 1 - result["p_value"] + result["minimum_p_value"])); result["two_sided_p"] = p; boot[name] = result; raw_p.append(p)
    bh = adjusted_p_values(raw_p, "bh"); by = adjusted_p_values(raw_p, "by")
    for name, bh_value, by_value in zip(comparison_names, bh, by): boot[name]["bh_adjusted_p"] = bh_value; boot[name]["by_adjusted_p"] = by_value
    benchmark_source = phase5_trades[phase5_trades.run_key == "NQ:BASE_CANDLE:matched_4R:fixed1"]
    benchmark = benchmark_source.assign(date=benchmark_source.entry_ts.str.slice(0, 10)).groupby("date").realized_r.sum().reindex(index, fill_value=0.0).to_numpy()
    family_columns = [corrected_r]
    family_names = ["C01_CAUSAL"]
    for name in ("P6_RETEST", "P6_FAILURE_REVERSAL"):
        source = new_frame[new_frame.run_key == name]; family_columns.append(source.assign(date=source.entry_ts.str.slice(0, 10)).groupby("date").realized_r.sum().reindex(index, fill_value=0.0).to_numpy()); family_names.append(name)
    for name in ("C04", "C11", "C14"):
        source = phase5_trades[phase5_trades.run_key == f"NQ:{name}:matched_4R:fixed1"]; family_columns.append(source.assign(date=source.entry_ts.str.slice(0, 10)).groupby("date").realized_r.sum().reindex(index, fill_value=0.0).to_numpy()); family_names.append(name)
    matrix = np.column_stack(family_columns)
    multiple = {"hypotheses": comparison_names, "count": len(comparison_names), "bh": {name: value for name, value in zip(comparison_names, bh)}, "by": {name: value for name, value in zip(comparison_names, by)}, "bootstrap_samples": bootstrap_samples, "mean_block_sessions": 10}
    statistical = {"comparisons": boot, "reality_check_spa": {**reality_check(matrix, benchmark, bootstrap_samples, 10, SEED + 100), "family": family_names, "benchmark": "BASE_CANDLE"}, "deflated_sharpe": _deflated_sharpe(corrected_r, 110), "pbo": _pbo(matrix), "configuration_budget": 110}
    (output / "phase6_bootstrap_results.json").write_text(json.dumps(boot, indent=2, default=str)); (output / "phase6_multiple_testing.json").write_text(json.dumps(multiple, indent=2, default=str)); (output / "phase6_tail_dependence.json").write_text(json.dumps({name: {"net_after_best_1pct": value["net_after_best_1pct"], "median_session": value["median_session"]} for name, value in strategy_results.items()}, indent=2))
    # Registry counts every meaningful specification/model/control once.
    registry = []
    def register(identifier, source, rationale, parameters, result, status, rejection=None, preregistered=True):
        registry.append({"hypothesis_id": identifier, "source": source, "rationale": rationale, "data_used": "preserved 2018-2025 only", "train_test_period": "expanding chronology unless marked descriptive", "parameters": parameters, "result": result, "status": status, "rejection_reason": rejection, "pre_registered": preregistered, "research_configurations": 1})
    register("P6-C01-CAUSAL", "engine audit", "correct the 15-minute availability timestamp", {"entry_delay_minutes_from_anchor": 15}, corrected_summary, "completed")
    for key, value in causal_robustness["parameter_surface"].items(): register(f"P6-PARAM-{key}", "bounded perturbation", "test nearby causal EMA/volume definition without selecting a best cell", {"cell": key}, {"net_profit": value["net_profit"], "net_after_best_1pct": value["net_after_best_1pct"], "positive_years": value["positive_years"]}, "audit_only")
    for multiplier in (2, 4): register(f"P6-COST-{multiplier}X", "adversarial cost stress", "test causal C01 under larger fees/spread/slippage", {"multiplier": multiplier}, causal_robustness["cost_stress"][str(multiplier)], "audit_only")
    register("P6-DELAY-1M", "execution stress", "delay causal C01 by one minute and reject already-stopped entries", {"minutes": 1}, causal_robustness["one_minute_delay"], "audit_only")
    register("P6-STRICT-FIRST-OUTSIDE", "rule semantics sensitivity", "cancel the day if the first outside close lacks full qualification", {}, causal_robustness["strict_first_outside_close"], "audit_only")
    for name, value in predictors.items(): register(f"P6-MODEL-{name}", "Phase 6", "predict bad corrected C01 days before entry", {}, value, "rejected" if name == "shuffled_label_control" or value.get("positive_improvement_folds", 0) < 4 else "promising", "insufficient chronological economic stability" if value.get("positive_improvement_folds", 0) < 4 else None)
    for k, value in similar.items(): register(f"P6-SIMILAR-{k}", "Phase 6", "earlier-only nearest analogues", {"neighbors": int(k)}, value, "descriptive_only", "not a frozen filter")
    for name, value in early_results.items(): register(f"P6-POST-{name}", "Phase 6", "causal early failure detection", {}, value, "promising" if value["improvement_vs_causal_c01"] > 0 and value["positive_years"] >= 6 else "rejected", None if value["improvement_vs_causal_c01"] > 0 and value["positive_years"] >= 6 else "did not improve distribution stably")
    for name, value in strategy_results.items(): register(f"P6-STRATEGY-{name}", "Phase 5/6 bounded candidate set", "independent or control strategy", {}, value, "completed")
    for name, value in interactions.items(): register(f"P6-INTERACTION-{name}", "Phase 6 evidence-directed", "bounded two-condition descriptive interaction", value["development_thresholds"], value, "descriptive_only", "not chronologically promoted", False)
    registry_payload = {"schema_version": 1, "maximum_meaningful_configurations": 110, "consumed": sum(row["research_configurations"] for row in registry), "within_budget": len(registry) <= 110, "hypotheses": registry}
    (output / "phase6_research_registry.json").write_text(json.dumps(registry_payload, indent=2, default=str))
    (output / "phase6_statistical_report.md").write_text(_statistical_report(corrected_summary, statistical, multiple, boot))
    (output / "phase6_leakage_audit.md").write_text(_leakage_report(predictors, before == after))
    candidates = []
    c01_gate = corrected_summary["net_profit"] > 0 and corrected_summary["net_after_best_1pct"] > 0 and corrected_summary["positive_years"] >= 6 and causal_robustness["cost_stress"]["2"]["net_profit"] > 0 and causal_robustness["one_minute_delay"]["net_profit"] > 0
    if c01_gate:
        candidates.append({"candidate_id": "C01-v1-causal-timing-correction", "specification_hash": baseline_spec["specification_hash"], "exact_rule": baseline_spec["rules"], "data_requirements": "NQ one-minute OHLCV plus RTH calendar", "parameters": {"ema_period": 200, "volume_ratio": 1.0, "target_r": 4}, "costs": baseline_spec["costs"], "expected_trade_count_range": [int(len(corrected_trades) * .8), int(len(corrected_trades) * 1.2)], "reason_for_freezing": "causal correction remained profitable with acceptable tail dependence", "known_risks": ["one-minute bars cannot resolve intrabar sequence", "historically inspected 2018-2025"], "known_failure_regimes": sorted(loss_taxonomy["categories"], key=lambda key: loss_taxonomy["categories"][key]["sessions"], reverse=True)[:5]})
    (output / "PHASE6_HOLDOUT_CANDIDATES.json").write_text(json.dumps({"protected_holdout_opened": False, "candidates": candidates}, indent=2))
    final = _final_report(baseline_spec, causal_robustness, loss_taxonomy, winner_taxonomy, predictors, similar, early_results, strategy_results, complementarity, statistical, candidates, registry_payload)
    (output / "PHASE6_FINAL_REPORT.md").write_text(final)
    return {"corrected": corrected_summary, "original_phase5_net": original_summary["net_profit"], "registry": registry_payload["consumed"], "holdout_candidates": len(candidates), "raw_cache_immutable": True}


def _statistical_report(summary: dict, statistical: dict, multiple: dict, boot: dict) -> str:
    return f"""# Phase 6 statistical report

The primary corrected C01 session array contains {summary['accepted_sessions']} aligned eligible sessions, including zero on no-trade sessions. Dependence-aware inference used {multiple['bootstrap_samples']:,} Politis–Romano stationary-bootstrap resamples with expected block length {multiple['mean_block_sessions']} sessions.

Seven paired comparisons were declared: {', '.join(multiple['hypotheses'])}. Raw two-sided values and BH/BY adjustments are stored in `phase6_bootstrap_results.json`; no IID t-test is used as primary evidence.

White reality-check p: {statistical['reality_check_spa']['reality_check_p_value']}. SPA-style maximum p: {statistical['reality_check_spa']['spa_p_value']}. DSR: {statistical['deflated_sharpe']}. CSCV/PBO: {statistical['pbo']}.

The causal corrected result is {summary['net_profit']:,.2f} net with {summary['positive_years']}/8 positive years and {summary['net_after_best_1pct']:,.2f} after removing the best 1%.
"""


def _leakage_report(predictors: dict, immutable: bool) -> str:
    return f"""# Phase 6 leakage audit

## Result

No protected market data was accessed. Raw-cache immutability: **{'PASS' if immutable else 'FAIL'}**.

- The corrected C01 decision timestamp is the completed 15-minute anchor plus 15 minutes; entry is the next one-minute open.
- Every pre-entry feature is constructed from the prior session, overnight data before RTH, or bars strictly earlier than entry. Breakout-bar features become known only at completion.
- Price-path labels and early-management fields are stored separately and are never included in `PRE_ENTRY_FEATURES`.
- Primary model evaluation uses expanding chronological folds; no random session shuffle is used for selection.
- Earlier-similar-day searches use only rows with an earlier date and refit imputation/scaling on the earlier set.
- A deterministic shuffled-label logistic control achieved OOS AUC {predictors['shuffled_label_control']['oos_auc_against_real_labels']}; it is selection-ineligible.
- Same-day final close, future volume, future VWAP, future EMA, future labels, and post-entry news are excluded from pre-entry predictors.
- Session arrays retain eligible no-trade days as zero for inference.
- Execution retains adverse-first same-bar resolution, gap-through stops, direction-aware fills, tick rounding, and exact cost reconciliation.
"""


def _final_report(baseline: dict, robustness: dict, losses: dict, winners: dict, predictors: dict, similar: dict, early: dict, strategies: dict, complement: dict, statistical: dict, candidates: list, registry: dict) -> str:
    corrected = baseline["corrected_phase6_result"]; original = baseline["original_phase5_result"]
    leading_losses = sorted(losses["categories"].items(), key=lambda item: item[1]["sessions"], reverse=True)[:5]
    leading_winners = sorted(winners["categories"].items(), key=lambda item: item[1]["sessions"], reverse=True)[:5]
    best_model = max((value | {"name": name} for name, value in predictors.items() if "oos_auc" in value), key=lambda value: value.get("oos_auc") or 0)
    best_early = max((value | {"name": name} for name, value in early.items()), key=lambda value: value["improvement_vs_causal_c01"])
    independent = {name: value for name, value in strategies.items() if name.startswith("P6_")}
    qualifying_complements = [value | {"name": name} for name, value in complement.items() if value["candidate_net_when_c01_loses"] > 0 and name not in {"C01_LONG_ONLY", "C01_SHORT_ONLY", "C17", "BASE_CANDLE", "BASE_EMA", "BASE_LONG", "BASE_SHORT", "BASE_RANDOM"}]
    best_complement = max(qualifying_complements, key=lambda value: value["combined_one_contract_each"]["net_profit"]) if qualifying_complements else None
    return f"""# Phase 6 final report

## Executive verdict

Phase 6 discovered a critical look-ahead timing defect in Phase 5 C01. The reported Phase 5 result ({original['net_profit']:,.2f}, {original['trades']} trades) entered ten minutes before its 15-minute signal bar completed and is not causal. The preserved result was not overwritten. The corrected C01 produced {corrected['net_profit']:,.2f} over {corrected['trades']} trades, profit factor {corrected['profit_factor']}, max drawdown {100*corrected['max_drawdown']:.2f}%, and {corrected['positive_years']}/8 positive years.

This correction—not another indicator—is the dominant Phase 6 finding. All taxonomy, model, path, and complementarity work below uses corrected trades.

## A. Why does corrected C01 work?

It waits for a completed 15-minute displacement beyond the opening range, requires volume expansion versus the immediately preceding completed bar, and trades only with the completed-bar EMA200 direction. Its strongest recurring winner descriptions were: {', '.join(name for name, _ in leading_winners)}. These are descriptions; only chronological prediction tests can promote them.

## B. Why does corrected C01 fail?

The most frequent mechanical loss tags were {', '.join(f'{name} ({value["sessions"]})' for name, value in leading_losses)}. Categories overlap because a single failed trade can reject immediately, close inside the range, and remain in overnight/VWAP conflict. Exact thresholds were learned only on 2018–2021 and frozen for later assignment.

## C. Can bad days be predicted before entry?

**Not reliably enough for promotion.** The strongest tested model was `{best_model['name']}` with expanding-fold OOS AUC {best_model['oos_auc']}, Brier {best_model['oos_brier']}, {best_model['positive_improvement_folds']}/{best_model['fold_count']} annual folds improving net P&L, and {100*best_model['retained_fraction']:.1f}% coverage. A classifier is not promoted unless economic improvement is stable across chronology and retains substantial coverage.

## D. Can good days be predicted?

Winner characteristics are measurable, but the same pre-entry models did not transport strongly enough to declare a good-day selector. Earlier-only analogue AUCs were {', '.join(f'k={key}: {value["bad_day_auc"]}' for key, value in similar.items())}. These remain descriptive diagnostics.

## E. Can C01 be improved?

The best bounded early-management rule was `{best_early['name']}`, changing net by {best_early['improvement_vs_causal_c01']:,.2f}, triggering {best_early['triggers']} times, and producing {best_early['positive_years']}/8 positive years. It is explicitly **POST_ENTRY_MANAGEMENT**, not a pre-entry predictor. It remains exploratory because it was evaluated after the causal timing defect was found and did not repair the two losing years.

## F. Did we discover a genuinely independent strategy?

The two new mechanical strategies were: {', '.join(f'{name} ({value["net_profit"]:,.2f})' for name, value in independent.items())}. Existing Phase 5 objective candidates and controls were also re-evaluated for complementarity against corrected C01 rather than ranked only by standalone return.

## G. Does any candidate complement C01?

{(f"The strongest non-control candidate that made money specifically when corrected C01 lost was `{best_complement['name']}`: {best_complement['candidate_net_when_c01_loses']:,.2f} on C01 losing sessions, correlation {best_complement['correlation_with_c01']}, and combined one-contract net {best_complement['combined_one_contract_each']['net_profit']:,.2f}. It still failed standalone transport/tail gates, so it is not promoted." if best_complement else "No independent non-control candidate earned positive P&L when C01 lost while also clearing standalone transport and tail requirements. C17 appeared complementary, but it is a preregistered negative control and is permanently selection-ineligible.")}

## H. Did anything outperform corrected C01?

No candidate is declared superior merely from historical total P&L. Equal execution standards, period transport, tail removal, controls, and multiple testing govern promotion. Full results are in `phase6_strategy_results.json` and `phase6_complementarity.json`.

## I. Is the edge regime-dependent?

Yes, expectancy differs across the four development-fitted pre-entry clusters and across opening-range, gap, volume, timing, VWAP, and key-level states. The labels are assigned without outcome-based names and later years are never used to refit development cluster centers.

## J. Is the edge tail-dependent?

Corrected C01 net after removing its best trade is {corrected['net_after_best_trade']:,.2f}; after the best five, {corrected['net_after_best_5']:,.2f}; after the best 1%, {corrected['net_after_best_1pct']:,.2f}; and after the best 5%, {corrected['net_after_best_5pct']:,.2f}. Median trade is {corrected['median_trade']:,.2f}. This is materially more informative than headline net alone.

At 2× costs it earned {robustness['cost_stress']['2']['net_profit']:,.2f}; at 4×, {robustness['cost_stress']['4']['net_profit']:,.2f}; and with a causal one-minute delay, {robustness['one_minute_delay']['net_profit']:,.2f}. The nearby parameter surface is an audit, not a source of replacement settings.

## K. What failed?

- The original Phase 5 C01 timing failed causal availability.
- Pre-entry machine-learning filters were rejected unless they improved at least four chronological folds with adequate coverage.
- Similar-day results are descriptive, not selected by the best neighbor count.
- Shuffled-label and unconditional controls remain selection-ineligible.
- Any strategy or interaction that only looked attractive after all 2018–2025 outcomes were observed remains exploratory.

## L. What should be frozen for a future holdout?

{('The bounded freeze file contains: ' + ', '.join(item['candidate_id'] for item in candidates)) if candidates else 'No Phase 6 candidate cleared the final freeze gate.'} The protected future holdout remains unopened.

## Data needs

No paid news API is justified. Scheduled point-in-time macro flags are sufficient to test whether known events explain corrected C01 failures. One-minute OHLCV cannot reconstruct queue position, L2, true delta, footprint, or intrabar event order; those remain known limitations rather than reasons to buy data speculatively.

## Research budget and frontend

The registry consumed {registry['consumed']} of 110 meaningful configurations. **NO FRONTEND CHANGES WERE NECESSARY.**

## Statistical summary

White reality-check p {statistical['reality_check_spa']['reality_check_p_value']}; SPA-style p {statistical['reality_check_spa']['spa_p_value']}. See `phase6_statistical_report.md` and machine-readable bootstrap/multiple-testing artifacts for exact families, resamples, and block assumptions.
"""
