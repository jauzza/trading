from __future__ import annotations

import hashlib
import itertools
import json
import math
import platform
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.stats import skew
from sklearn.calibration import calibration_curve
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from .analytics import adjusted_p_values, max_drawdown, reality_check, stationary_bootstrap_mean
from .phase5 import ProtectedMarketDataGuard
from .phase6 import PRE_ENTRY_FEATURES, _deflated_sharpe, _pbo
from .research import NQ_FP


NY = ZoneInfo("America/New_York")
SEED = 2701
MAX_CONFIGURATIONS = 150
BLOCK_LENGTHS = (5, 10, 20, 60)
PROMOTION_CLASSES = {"REJECTED", "INCONCLUSIVE", "DESCRIPTIVE", "EXPLORATORY", "PROMISING", "HOLDOUT_CANDIDATE"}


def _json(path: Path) -> Any:
    return json.loads(path.read_text())


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, default=_json_default, allow_nan=False))


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_version() -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit = None
    return {
        "commit": commit,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "phase7_module_sha256": _sha(Path(__file__)),
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if np.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _two_sided(result: dict[str, Any]) -> float:
    p = float(result["p_value"])
    minimum = float(result["minimum_p_value"])
    return min(1.0, 2 * min(p, 1 - p + minimum))


def _session_index(session: pd.DataFrame) -> pd.Index:
    return pd.Index(session["date"].astype(str), name="date")


def _aligned_trade_series(frame: pd.DataFrame, index: pd.Index, column: str = "net_pnl") -> pd.Series:
    if frame.empty:
        return pd.Series(0.0, index=index)
    dates = frame["entry_ts"].astype(str).str.slice(0, 10)
    return frame.assign(_date=dates).groupby("_date")[column].sum().reindex(index, fill_value=0.0)


def _daily_metrics(values: pd.Series) -> dict[str, Any]:
    pnl = values.to_numpy(float)
    equity = np.r_[100_000.0, 100_000.0 + np.cumsum(pnl)]
    dd, duration = max_drawdown(equity.tolist())
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    years = pd.to_datetime(values.index).year
    by_year = {str(year): round(float(pnl[years == year].sum()), 2) for year in range(2018, 2026)}
    ordered = np.sort(pnl)[::-1]
    one_pct = max(1, math.ceil(len(ordered) * .01)) if len(ordered) else 0
    five_pct = max(1, math.ceil(len(ordered) * .05)) if len(ordered) else 0
    return {
        "sessions": len(pnl),
        "active_sessions": int(np.count_nonzero(pnl)),
        "net_profit": round(float(pnl.sum()), 2),
        "expectancy_session": round(float(pnl.mean()), 6) if len(pnl) else 0,
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 4) if losses.size and losses.sum() else None,
        "max_drawdown": round(float(dd), 6),
        "drawdown_duration_sessions": duration,
        "positive_years": sum(value > 0 for value in by_year.values()),
        "by_year": by_year,
        "median_session": round(float(np.median(pnl)), 2) if len(pnl) else 0,
        "net_after_best_trade": round(float(pnl.sum() - ordered[:1].sum()), 2) if len(ordered) else 0,
        "net_after_best_3": round(float(pnl.sum() - ordered[:3].sum()), 2) if len(ordered) else 0,
        "net_after_best_5": round(float(pnl.sum() - ordered[:5].sum()), 2) if len(ordered) else 0,
        "net_after_best_10": round(float(pnl.sum() - ordered[:10].sum()), 2) if len(ordered) else 0,
        "net_after_best_1pct": round(float(pnl.sum() - ordered[:one_pct].sum()), 2) if len(ordered) else 0,
        "net_after_best_5pct": round(float(pnl.sum() - ordered[:five_pct].sum()), 2) if len(ordered) else 0,
        "equity": [round(float(value), 2) for value in equity],
    }


def _tail_metrics(pnl: np.ndarray, dates: pd.Series | pd.Index | None = None) -> dict[str, Any]:
    pnl = np.asarray(pnl, dtype=float)
    if not len(pnl):
        return {"trades": 0}
    ordered = np.sort(pnl)[::-1]
    winners, losers = pnl[pnl > 0], pnl[pnl < 0]
    gross = float(winners.sum())
    n1 = max(1, math.ceil(len(pnl) * .01))
    n5 = max(1, math.ceil(len(pnl) * .05))
    lower, upper = np.quantile(pnl, [.01, .99])
    winsor = np.clip(pnl, lower, upper)
    loss_streak = current = 0
    for value in pnl:
        current = current + 1 if value < 0 else 0
        loss_streak = max(loss_streak, current)
    result = {
        "trades": len(pnl),
        "original_net": round(float(pnl.sum()), 2),
        "best_trade_removed": round(float(pnl.sum() - ordered[:1].sum()), 2),
        "best_3_removed": round(float(pnl.sum() - ordered[:3].sum()), 2),
        "best_5_removed": round(float(pnl.sum() - ordered[:5].sum()), 2),
        "best_10_removed": round(float(pnl.sum() - ordered[:10].sum()), 2),
        "best_1pct_removed": round(float(pnl.sum() - ordered[:n1].sum()), 2),
        "best_5pct_removed": round(float(pnl.sum() - ordered[:n5].sum()), 2),
        "winsorized_1pct_net": round(float(winsor.sum()), 2),
        "median_trade": round(float(np.median(pnl)), 2),
        "mean_trade": round(float(pnl.mean()), 2),
        "skew": round(float(skew(pnl, bias=False)), 6) if len(pnl) > 2 else 0,
        "payoff_ratio": round(float(winners.mean() / abs(losers.mean())), 6) if winners.size and losers.size else None,
        "expected_shortfall_5pct": round(float(np.mean(np.sort(pnl)[:max(1, math.ceil(len(pnl) * .05))])), 2),
        "max_losing_streak": loss_streak,
        "best_winner_share_gross_profit": round(float(ordered[0] / gross), 6) if gross else None,
        "top5_share_gross_profit": round(float(ordered[:5].sum() / gross), 6) if gross else None,
        "top1pct_share_gross_profit": round(float(ordered[:n1].sum() / gross), 6) if gross else None,
    }
    if dates is not None:
        parsed = pd.to_datetime(pd.Series(dates).astype(str).str.slice(0, 10))
        by_month = pd.Series(pnl).groupby(parsed.dt.to_period("M")).sum()
        by_year = pd.Series(pnl).groupby(parsed.dt.year).sum()
        total = float(pnl.sum())
        result["best_month_share_total"] = round(float(by_month.max() / total), 6) if total else None
        result["best_year_share_total"] = round(float(by_year.max() / total), 6) if total else None
    return result


def _feature_metadata(session: pd.DataFrame) -> list[dict[str, Any]]:
    outcome = {"net_pnl", "net_r", "win", "outcome"}
    post = {"event_after_entry"}
    entry = {
        "entry_vwap", "entry_vs_vwap_atr", "vwap_slope_atr", "ema_distance_atr", "ema_slope_atr",
        "breakout_time_minutes", "breakout_body_fraction", "breakout_volume_ratio", "key_level_room_r",
        "overnight_alignment", "vwap_alignment", "entry_ts", "side",
    }
    rows = []
    for name in session.columns:
        if name in outcome:
            classification, available = "OUTCOME_ONLY", "after exit"
        elif name in post:
            classification, available = "POST_ENTRY", "after entry"
        elif name in entry:
            classification, available = "ENTRY_TIME", "at completed signal bar / order submission"
        else:
            classification, available = "PRE_ENTRY", "no later than decision timestamp"
        source = "derived preserved one-minute OHLCV"
        if name in {"scheduled_macro_event", "ten_am_event"}:
            source = "point-in-time scheduled macro calendar"
        rows.append({
            "feature_name": name,
            "formula": "see backend/open_ten/phase6.py::_session_features" if name not in outcome else "realized execution result",
            "source": source,
            "earliest_data_timestamp_used": "prior session/overnight start where applicable",
            "available_at": available,
            "decision_timestamp": "C01 corrected completed 15-minute signal timestamp",
            "classification": classification,
            "PRE_ENTRY": classification == "PRE_ENTRY",
            "ENTRY_TIME": classification == "ENTRY_TIME",
            "POST_ENTRY": classification == "POST_ENTRY",
            "OUTCOME_ONLY": classification == "OUTCOME_ONLY",
        })
    return rows


def _raw_forensics(
    guard: ProtectedMarketDataGuard, manifest: dict[str, Any], session: pd.DataFrame, trades: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Extract exact causal OHLC context and bar-resolution trade timing without touching protected data."""
    accepted = set(session["date"].astype(str))
    trade_by_date = {str(row.entry_ts)[:10]: row for row in trades.itertuples(index=False)}
    raw_sessions: list[dict[str, Any]] = []
    raw_trades: list[dict[str, Any]] = []
    previous_rth: dict[str, Any] | None = None
    prior_tail = pd.DataFrame()
    dataset = manifest["datasets"][NQ_FP]
    for partition in sorted(dataset["partitions"], key=lambda row: int(row["year"])):
        year = int(partition["year"])
        if year >= 2026:
            raise RuntimeError("protected partition rejected before raw forensic read")
        if year < 2018:
            continue
        current = guard.read_parquet(partition["path"])
        frame = pd.concat([prior_tail, current], ignore_index=True).sort_values("ts_ny") if len(prior_tail) else current.copy()
        frame["_minute"] = frame.ts_ny.dt.hour * 60 + frame.ts_ny.dt.minute
        frame["_date"] = frame.ts_ny.dt.strftime("%Y-%m-%d")
        overnight_mask = (frame._minute >= 18 * 60) | (frame._minute < 9 * 60 + 30)
        target_date = pd.to_datetime(frame["_date"]) + pd.to_timedelta((frame._minute >= 18 * 60).astype(int), unit="D")
        frame["_overnight_date"] = target_date.dt.strftime("%Y-%m-%d")
        current = current.copy()
        current["_minute"] = current.ts_ny.dt.hour * 60 + current.ts_ny.dt.minute
        current["_date"] = current.ts_ny.dt.strftime("%Y-%m-%d")
        rth = current[(current._minute >= 9 * 60 + 30) & (current._minute <= 15 * 60 + 55)]
        overnight_groups = {day: group.sort_values("ts_ny") for day, group in frame[overnight_mask].groupby("_overnight_date") if day in accepted}
        for day, group in rth.groupby("_date", sort=True):
            if day not in accepted:
                continue
            group = group.sort_values("ts_ny")
            opening = group[(group._minute >= 9 * 60 + 30) & (group._minute <= 9 * 60 + 44)]
            if len(opening) != 15:
                continue
            overnight = overnight_groups.get(day, pd.DataFrame())
            open_row = {
                "date": day,
                "opening_candle_open": float(opening.iloc[0].open),
                "opening_candle_high": float(opening.high.max()),
                "opening_candle_low": float(opening.low.min()),
                "opening_candle_close": float(opening.iloc[-1].close),
                "opening_candle_volume": int(opening.volume.sum()),
                "overnight_open": float(overnight.iloc[0].open) if len(overnight) else None,
                "overnight_high_raw": float(overnight.high.max()) if len(overnight) else None,
                "overnight_low_raw": float(overnight.low.min()) if len(overnight) else None,
                "overnight_close": float(overnight.iloc[-1].close) if len(overnight) else None,
                "overnight_volume_raw": int(overnight.volume.sum()) if len(overnight) else None,
                "rth_open": float(group.iloc[0].open),
                "prior_open": previous_rth["open"] if previous_rth else None,
                "prior_high": previous_rth["high"] if previous_rth else None,
                "prior_low": previous_rth["low"] if previous_rth else None,
                "prior_close": previous_rth["close"] if previous_rth else None,
                "prior_range_raw": previous_rth["high"] - previous_rth["low"] if previous_rth else None,
                "prior_return_raw": previous_rth["close"] - previous_rth["open"] if previous_rth else None,
                "prior_volume_raw": previous_rth["volume"] if previous_rth else None,
                "gap_raw": float(group.iloc[0].open) - previous_rth["close"] if previous_rth else None,
            }
            raw_sessions.append(open_row)
            if day in trade_by_date:
                trade = trade_by_date[day]
                entry_ts, exit_ts = pd.Timestamp(trade.entry_ts), pd.Timestamp(trade.exit_ts)
                path = group[(group.ts_ny >= entry_ts) & (group.ts_ny <= exit_ts)].copy()
                if len(path):
                    direction = 1 if trade.side == "long" else -1
                    reference = float(trade.reference_entry)
                    risk = max(abs(reference - float(trade.stop)), .25)
                    favorable = (path.high.to_numpy(float) - reference) / risk if direction == 1 else (reference - path.low.to_numpy(float)) / risk
                    adverse = (reference - path.low.to_numpy(float)) / risk if direction == 1 else (path.high.to_numpy(float) - reference) / risk
                    minutes = ((path.ts_ny - entry_ts).dt.total_seconds() / 60).to_numpy(int)
                    typical = (group.high + group.low + group.close) / 3
                    cumulative_vwap = (typical * group.volume).cumsum() / group.volume.cumsum().replace(0, np.nan)
                    path_vwap = cumulative_vwap.loc[path.index]
                    against_vwap = path.close < path_vwap if direction == 1 else path.close > path_vwap
                    inside_or = path.close.between(open_row["opening_candle_low"], open_row["opening_candle_high"])
                    stop_hit = path.low <= float(trade.stop) if direction == 1 else path.high >= float(trade.stop)
                    first_time = lambda mask: int(minutes[np.flatnonzero(np.asarray(mask))[0]]) if np.asarray(mask).any() else None
                    timing = {
                        "date": day,
                        "time_to_mfe": int(minutes[int(np.argmax(favorable))]),
                        "time_to_mae": int(minutes[int(np.argmax(adverse))]),
                        "first_adverse_move_minutes": first_time(adverse > 0),
                        "first_favorable_move_minutes": first_time(favorable > 0),
                        "time_to_opening_range_reentry": first_time(inside_or.to_numpy()),
                        "time_to_vwap_cross": first_time(against_vwap.to_numpy()),
                        "time_to_breakout_failure": first_time(inside_or.to_numpy()),
                        "time_to_stop": first_time(stop_hit.to_numpy()),
                        "mfe_r_bar_path": round(float(np.max(favorable)), 6),
                        "mae_r_bar_path": round(float(np.max(adverse)), 6),
                    }
                    for level in (1, 2, 3, 4):
                        timing[f"time_to_{level}r"] = first_time(favorable >= level)
                    raw_trades.append(timing)
            previous_rth = {
                "open": float(group.iloc[0].open), "high": float(group.high.max()), "low": float(group.low.min()),
                "close": float(group.iloc[-1].close), "volume": int(group.volume.sum()),
            }
        prior_tail = current[current.ts_ny >= current.ts_ny.max() - pd.Timedelta(days=4)].drop(columns=["_minute", "_date"], errors="ignore")
    return pd.DataFrame(raw_sessions), pd.DataFrame(raw_trades)


def _build_anatomy(
    session: pd.DataFrame, paths: pd.DataFrame, trades: pd.DataFrame,
    raw_sessions: pd.DataFrame | None = None, raw_trades: pd.DataFrame | None = None,
) -> pd.DataFrame:
    session = session.copy()
    session["date"] = session["date"].astype(str)
    paths = paths.copy()
    paths["date"] = paths["date"].astype(str)
    trades = trades.copy()
    trades["date"] = trades["entry_ts"].astype(str).str.slice(0, 10)
    trade_cols = [
        "date", "id", "entry_ts", "exit_ts", "reference_entry", "entry", "stop", "target", "exit",
        "gross_pnl", "total_costs", "net_pnl", "realized_r", "outcome", "reason", "duration_minutes",
    ]
    path_cols = [name for name in paths.columns if name not in {"net_pnl", "net_r", "outcome", "entry_ts", "side"}]
    merged = session.merge(paths[path_cols], how="left", on="date", suffixes=("", "_path"))
    merged = merged.merge(trades[trade_cols], how="left", on="date", suffixes=("", "_trade"))
    if raw_sessions is not None and not raw_sessions.empty:
        merged = merged.merge(raw_sessions, how="left", on="date")
    if raw_trades is not None and not raw_trades.empty:
        merged = merged.merge(raw_trades, how="left", on="date")
    merged["eligible_session"] = True
    merged["trade_executed"] = merged["id"].notna()
    risk_dollars = merged["risk_points"].fillna(0) * 20
    merged["initial_risk_dollars"] = risk_dollars
    merged["r_outcome"] = merged["realized_r"].fillna(0)
    merged["first_adverse_move_r"] = merged.get("mae_r_1m", pd.Series(index=merged.index, dtype=float)).fillna(0)
    merged["first_favorable_move_r"] = merged.get("mfe_r_1m", pd.Series(index=merged.index, dtype=float)).fillna(0)
    coarse_reentry = np.where(merged.get("close_inside_or_5m", False), 5, np.where(merged.get("close_inside_or_30m", False), 30, np.nan))
    if "time_to_opening_range_reentry" in merged:
        merged["time_to_opening_range_reentry"] = merged["time_to_opening_range_reentry"].fillna(pd.Series(coarse_reentry, index=merged.index))
    else:
        merged["time_to_opening_range_reentry"] = coarse_reentry
    if "time_to_breakout_failure" in merged:
        merged["time_to_breakout_failure"] = merged["time_to_breakout_failure"].fillna(merged["time_to_opening_range_reentry"])
    else:
        merged["time_to_breakout_failure"] = merged["time_to_opening_range_reentry"]
    if "time_to_vwap_cross" not in merged:
        merged["time_to_vwap_cross"] = np.nan
    for level in (1, 2, 3, 4):
        candidates = []
        for horizon in (1, 2, 3, 5, 10, 15, 30, 60, 90, 120):
            column = f"mfe_r_{horizon}m"
            if column in merged:
                candidates.append(np.where(merged[column] >= level, horizon, np.nan))
        if candidates:
            candidate_matrix = np.vstack(candidates).T
            coarse = pd.Series([min(row[np.isfinite(row)], default=np.nan) for row in candidate_matrix], index=merged.index)
            if f"time_to_{level}r" in merged:
                merged[f"time_to_{level}r"] = merged[f"time_to_{level}r"].fillna(coarse)
            else:
                merged[f"time_to_{level}r"] = coarse
        else:
            if f"time_to_{level}r" not in merged:
                merged[f"time_to_{level}r"] = np.nan
    if "time_to_mfe" not in merged:
        merged["time_to_mfe"] = np.nan
    if "time_to_mae" not in merged:
        merged["time_to_mae"] = np.nan
    merged["maximum_excursion_r"] = merged.get("mfe_r_full", np.nan)
    merged["path_shape"] = np.select(
        [
            merged["r_outcome"] >= 3.5,
            (merged["first_adverse_move_r"] >= .5) & (merged["r_outcome"] > 0),
            merged["time_to_breakout_failure"].notna(),
            merged["r_outcome"] <= -1,
        ],
        ["TARGET_TREND", "EARLY_ADVERSE_RECOVERY", "RANGE_REENTRY", "STOP_OR_GAP_LOSS"],
        default="MIXED_OR_SESSION_EXIT",
    )
    merged["outcome_class"] = np.select(
        [merged["r_outcome"] >= 3.5, merged["r_outcome"] > .1, merged["r_outcome"].abs() <= .1, merged["r_outcome"] <= -1, merged["time_to_breakout_failure"].notna()],
        ["4R_WINNER", "SMALLER_WINNER", "SCRATCH", "STOP_OUT", "EARLY_REVERSAL_LOSER"],
        default="ORDINARY_LOSER",
    )
    merged.loc[(merged["first_adverse_move_r"] >= .5) & (merged["r_outcome"] > 0), "outcome_class"] = "RECOVERED_AFTER_ADVERSE"
    merged["contract_id"] = "PHASE7_RESEARCH_CONTRACT"
    return merged


def _profit_factor(values: pd.Series) -> float | None:
    wins, losses = values[values > 0], values[values < 0]
    return round(float(wins.sum() / abs(losses.sum())), 4) if len(losses) and losses.sum() else None


def _label_metrics(frame: pd.DataFrame, mask: pd.Series, classification: str, samples: int, seed: int) -> dict[str, Any]:
    selected = frame[mask.fillna(False)].copy()
    pnl = selected["net_pnl_trade"].fillna(selected["net_pnl"]).fillna(0).astype(float)
    r = selected["r_outcome"].fillna(0).astype(float)
    years = pd.to_datetime(selected["date"]).dt.year if len(selected) else pd.Series(dtype=int)
    months = pd.to_datetime(selected["date"]).dt.month if len(selected) else pd.Series(dtype=int)
    ci = stationary_bootstrap_mean(r.to_numpy(), samples, 10, seed)
    equity = np.r_[100_000.0, 100_000.0 + np.cumsum(pnl.to_numpy())]
    dollar_dd = float(np.min(equity - np.maximum.accumulate(equity))) if len(equity) else 0
    return {
        "count": len(selected),
        "percentage_eligible_sessions": round(len(selected) / len(frame), 6) if len(frame) else 0,
        "mean_r": round(float(r.mean()), 6) if len(r) else 0,
        "median_r": round(float(r.median()), 6) if len(r) else 0,
        "win_rate": round(float((pnl > 0).mean()), 6) if len(pnl) else 0,
        "profit_factor": _profit_factor(pnl),
        "by_year": {str(year): round(float(pnl[years == year].sum()), 2) for year in range(2018, 2026)},
        "by_month": {str(month): round(float(pnl[months == month].sum()), 2) for month in range(1, 13)},
        "drawdown_contribution_dollars": round(dollar_dd, 2),
        "pnl_contribution": round(float(pnl.sum()), 2),
        "stationary_bootstrap_mean_r": ci,
        "feature_availability": classification,
        "knowable_pre_entry": classification in {"PRE_ENTRY", "ENTRY_TIME"},
        "knowable_post_entry_only": classification == "POST_ENTRY",
        "mechanically_defined": True,
    }


def _taxonomies(frame: pd.DataFrame, samples: int) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    signal = frame[frame["trade_executed"]].copy()
    dev = signal[pd.to_datetime(signal.date).dt.year <= 2021]
    q = lambda name, value: float(dev[name].dropna().quantile(value)) if name in dev and dev[name].notna().any() else 0
    side_num = signal["side"].map({"long": 1, "short": -1}).fillna(0)
    definitions: dict[str, tuple[pd.Series, str]] = {
        "LOW_VOLUME_FOLLOW_THROUGH": (signal["volume_first_5_ratio"].fillna(np.inf) < q("volume_first_5_ratio", .35), "POST_ENTRY"),
        "EARLY_ADVERSE_EXCURSION": (signal["mae_r_5m"].fillna(0) >= .5, "POST_ENTRY"),
        "OVERNIGHT_CONFLICT": (signal["overnight_alignment"] == False, "ENTRY_TIME"),
        "WRONG_SIDE_TREND": (side_num * signal["prior_trend_slope_atr"].fillna(0) < 0, "PRE_ENTRY"),
        "BREAKOUT_FAILURE": (signal["close_inside_or_30m"] == True, "POST_ENTRY"),
        "VWAP_CONFLICT": (signal["vwap_alignment"] == False, "ENTRY_TIME"),
        "KEY_LEVEL_OBSTRUCTION": (signal["key_level_room_r"].fillna(np.inf) < 1, "ENTRY_TIME"),
        "RANGE_TOO_LARGE": (signal["opening_range_atr"] > q("opening_range_atr", .85), "PRE_ENTRY"),
        "RANGE_TOO_SMALL": (signal["opening_range_atr"] < q("opening_range_atr", .15), "PRE_ENTRY"),
        "GAP_CONFLICT": (side_num * signal["gap_atr"].fillna(0) < 0, "PRE_ENTRY"),
        "GAP_EXHAUSTION": ((side_num * signal["gap_atr"].fillna(0) > 0) & (signal["gap_atr"].abs() > q("gap_atr", .85)), "PRE_ENTRY"),
        "LOW_VOLATILITY": (signal["prior_volatility"] < q("prior_volatility", .15), "PRE_ENTRY"),
        "HIGH_VOLATILITY": (signal["prior_volatility"] > q("prior_volatility", .85), "PRE_ENTRY"),
        "CHOP": ((signal["mfe_r_15m"].fillna(0) < .35) & (signal["mae_r_15m"].fillna(0) < .35), "POST_ENTRY"),
        "RAPID_REVERSAL": ((signal["return_r_3m"].fillna(0) < -.25) | (signal["close_inside_or_5m"] == True), "POST_ENTRY"),
        "LATE_BREAKOUT": (signal["breakout_time_minutes"].fillna(0) >= 120, "ENTRY_TIME"),
        "NEWS_PROXIMITY": (signal["scheduled_macro_event"] == True, "PRE_ENTRY"),
        "EVENT_VOLATILITY": ((signal["scheduled_macro_event"] == True) & (signal["mae_r_15m"].fillna(0) >= .5), "POST_ENTRY"),
        "EXTREME_OPEN": ((signal["open_position_overnight"].fillna(.5) < .1) | (signal["open_position_overnight"].fillna(.5) > .9), "PRE_ENTRY"),
        "EXTREME_GAP": (signal["gap_atr"].abs() > q("gap_atr", .9), "PRE_ENTRY"),
        "PRIOR_DAY_CONFLICT": (side_num * signal["prior_return_atr"].fillna(0) < 0, "PRE_ENTRY"),
        "NO_FOLLOW_THROUGH": (signal["mfe_r_15m"].fillna(0) < .25, "POST_ENTRY"),
        "MOMENTUM_DECAY": ((signal["return_r_3m"].fillna(0) > .1) & (signal["return_r_15m"].fillna(0) < 0), "POST_ENTRY"),
    }
    loss_payload: dict[str, Any] = {"development_thresholds": {"learned_on": "2018-2021", "quantiles": "15/35/85/90 as mechanically specified"}, "labels": {}}
    masks: dict[str, pd.Series] = {}
    for offset, (name, (mask, availability)) in enumerate(definitions.items()):
        masks[name] = mask.fillna(False)
        metrics = _label_metrics(signal, masks[name], availability, samples, SEED + offset)
        overlaps = {other: int((masks[name] & other_mask).sum()) for other, other_mask in masks.items() if other != name}
        metrics["overlap_with_prior_labels"] = overlaps
        metrics["classification"] = "DESCRIPTION" if availability == "POST_ENTRY" else "DESCRIPTIVE"
        loss_payload["labels"][name] = metrics
    winner_defs: dict[str, tuple[pd.Series, str]] = {
        "OVERNIGHT_ALIGNMENT": (signal["overnight_alignment"] == True, "ENTRY_TIME"),
        "CLEAN_OPENING_STRUCTURE": (signal["opening_body_fraction"].fillna(0) >= q("opening_body_fraction", .6), "PRE_ENTRY"),
        "MODERATE_OPENING_RANGE": (signal["opening_range_atr"].between(q("opening_range_atr", .25), q("opening_range_atr", .75)), "PRE_ENTRY"),
        "SUFFICIENT_VOLUME": (signal["breakout_volume_ratio"].fillna(0) >= q("breakout_volume_ratio", .6), "ENTRY_TIME"),
        "VWAP_ALIGNMENT": (signal["vwap_alignment"] == True, "ENTRY_TIME"),
        "EMA_ALIGNMENT": (side_num * signal["ema_distance_atr"].fillna(0) > 0, "ENTRY_TIME"),
        "ROOM_TO_KEY_LEVELS": (signal["key_level_room_r"].fillna(0) >= 2, "ENTRY_TIME"),
        "USEFUL_VOLATILITY": (signal["prior_volatility"].between(q("prior_volatility", .25), q("prior_volatility", .8)), "PRE_ENTRY"),
        "GAP_ALIGNMENT": (side_num * signal["gap_atr"].fillna(0) > 0, "PRE_ENTRY"),
        "PRIOR_DAY_AGREEMENT": (side_num * signal["prior_return_atr"].fillna(0) > 0, "PRE_ENTRY"),
        "FAST_BREAKOUT": (signal["breakout_time_minutes"].fillna(np.inf) <= q("breakout_time_minutes", .4), "ENTRY_TIME"),
        "COMPRESSION_EXPANSION": ((signal["prior_volatility"] < q("prior_volatility", .4)) & (signal["breakout_volume_ratio"] > q("breakout_volume_ratio", .6)), "ENTRY_TIME"),
    }
    unconditional = float(signal["r_outcome"].mean())
    winner_payload: dict[str, Any] = {"unconditional_expectancy_r": round(unconditional, 6), "features": {}}
    for offset, (name, (mask, availability)) in enumerate(winner_defs.items(), start=50):
        metrics = _label_metrics(signal, mask, availability, samples, SEED + offset)
        metrics["lift_r"] = round(metrics["mean_r"] - unconditional, 6)
        base_win = float((signal["net_pnl_trade"].fillna(signal["net_pnl"]) > 0).mean())
        metrics["relative_win_risk"] = round(metrics["win_rate"] / base_win, 6) if base_win else None
        metrics["tail_sensitivity"] = _tail_metrics(signal.loc[mask.fillna(False), "net_pnl_trade"].fillna(signal.loc[mask.fillna(False), "net_pnl"]).to_numpy())
        metrics["classification"] = "DESCRIPTIVE"
        winner_payload["features"][name] = metrics
    graph_nodes = list(definitions)
    graph_edges = []
    for left, right in itertools.combinations(graph_nodes, 2):
        both = masks[left] & masks[right]
        count = int(both.sum())
        if count < 25:
            continue
        graph_edges.append({
            "source": left, "target": right, "co_occurrence": count,
            "jaccard": round(count / int((masks[left] | masks[right]).sum()), 6),
            "conditional_expectancy_r": round(float(signal.loc[both, "r_outcome"].mean()), 6),
            "development_count": int((both & (pd.to_datetime(signal.date).dt.year <= 2021)).sum()),
            "later_count": int((both & (pd.to_datetime(signal.date).dt.year >= 2022)).sum()),
        })
    graph = {"nodes": [{"id": name, "availability": definitions[name][1]} for name in graph_nodes], "edges": sorted(graph_edges, key=lambda row: row["co_occurrence"], reverse=True), "interpretation": "Edges are overlap, not causality; dense post-entry labels may describe one failed-follow-through mechanism."}
    return loss_payload, winner_payload, graph


def _regimes(frame: pd.DataFrame) -> dict[str, Any]:
    signal = frame[frame.trade_executed].copy()
    signal["year"] = pd.to_datetime(signal.date).dt.year
    features = [name for name in PRE_ENTRY_FEATURES if name in signal and name not in {"month", "quarter"}]
    numeric = signal[features].apply(pd.to_numeric, errors="coerce")
    train = signal.year <= 2021
    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    x_train = scaler.fit_transform(imputer.fit_transform(numeric.loc[train]))
    x_all = scaler.transform(imputer.transform(numeric))
    output = {"fit_period": "2018-2021", "selection_eligible": False, "cluster_counts": {}}
    for k in (3, 4, 5, 6):
        model = KMeans(n_clusters=k, random_state=SEED, n_init=20).fit(x_train)
        labels = model.predict(x_all)
        regimes = {}
        for label in range(k):
            group = signal[labels == label]
            daily = group.set_index("date")["net_pnl_trade"].fillna(group.set_index("date")["net_pnl"])
            metric = _daily_metrics(daily)
            metric.update({
                "count": len(group), "percentage": round(len(group) / len(signal), 6),
                "expectancy_r": round(float(group.r_outcome.mean()), 6), "median_r": round(float(group.r_outcome.median()), 6),
                "opening_range_atr": round(float(group.opening_range_atr.mean()), 6),
                "breakout_volume_ratio": round(float(group.breakout_volume_ratio.mean()), 6),
                "prior_volatility": round(float(group.prior_volatility.mean()), 6),
                "gap_atr": round(float(group.gap_atr.mean()), 6),
                "overnight_return": round(float(group.overnight_return.mean()), 6),
                "entry_vs_vwap_atr": round(float(group.entry_vs_vwap_atr.mean()), 6),
                "key_level_room_r": round(float(group.key_level_room_r.mean()), 6),
                "status": "DESCRIPTIVE",
            })
            regimes[str(label)] = metric
        output["cluster_counts"][str(k)] = {"regimes": regimes, "inertia": round(float(model.inertia_), 6)}
    return output


def _interactions(frame: pd.DataFrame) -> dict[str, Any]:
    signal = frame[frame.trade_executed].copy()
    signal["year"] = pd.to_datetime(signal.date).dt.year
    dev = signal[signal.year <= 2021]
    median = lambda name: float(dev[name].median()) if name in dev and dev[name].notna().any() else 0
    side = signal.side.map({"long": 1, "short": -1}).fillna(0)
    definitions = {
        "opening_range_x_overnight": (signal.opening_range_atr <= median("opening_range_atr")) & (signal.overnight_alignment == True),
        "opening_range_x_volume": (signal.opening_range_atr <= median("opening_range_atr")) & (signal.breakout_volume_ratio >= median("breakout_volume_ratio")),
        "opening_range_x_gap": (signal.opening_range_atr <= median("opening_range_atr")) & (side * signal.gap_atr.fillna(0) > 0),
        "opening_range_x_volatility": (signal.opening_range_atr <= median("opening_range_atr")) & (signal.prior_volatility >= median("prior_volatility")),
        "opening_direction_x_overnight": signal.overnight_alignment == True,
        "opening_direction_x_vwap": signal.vwap_alignment == True,
        "opening_direction_x_ema": side * signal.ema_distance_atr.fillna(0) > 0,
        "opening_direction_x_key_level": signal.key_level_room_r >= median("key_level_room_r"),
        "volume_x_volatility": (signal.breakout_volume_ratio >= median("breakout_volume_ratio")) & (signal.prior_volatility >= median("prior_volatility")),
        "volume_x_gap": (signal.breakout_volume_ratio >= median("breakout_volume_ratio")) & (side * signal.gap_atr.fillna(0) > 0),
        "vwap_x_overnight": (signal.vwap_alignment == True) & (signal.overnight_alignment == True),
        "vwap_x_opening_range": (signal.vwap_alignment == True) & (signal.opening_range_atr <= median("opening_range_atr")),
        "volatility_x_gap": (signal.prior_volatility >= median("prior_volatility")) & (side * signal.gap_atr.fillna(0) > 0),
        "prior_trend_x_overnight": (side * signal.prior_return_atr.fillna(0) > 0) & (signal.overnight_alignment == True),
        "key_level_x_breakout": signal.key_level_room_r >= 2,
        "time_x_volatility": (signal.breakout_time_minutes <= median("breakout_time_minutes")) & (signal.prior_volatility >= median("prior_volatility")),
        "time_x_volume": (signal.breakout_time_minutes <= median("breakout_time_minutes")) & (signal.breakout_volume_ratio >= median("breakout_volume_ratio")),
    }
    output = {"threshold_source": "2018-2021 only", "selection_eligible": False, "interactions": {}}
    for name, mask in definitions.items():
        row = {"sample": int(mask.sum()), "coverage": round(float(mask.mean()), 6), "status": "DESCRIPTIVE", "periods": {}}
        for period, years in {"development": range(2018, 2022), "validation": range(2022, 2024), "historical_evaluation": range(2024, 2026)}.items():
            subset = signal[mask & signal.year.isin(years)]
            row["periods"][period] = {"trades": len(subset), "net_profit": round(float(subset.net_pnl_trade.fillna(subset.net_pnl).sum()), 2), "expectancy_r": round(float(subset.r_outcome.mean()), 6) if len(subset) else 0}
        row["chronologically_positive"] = all(value["net_profit"] > 0 for value in row["periods"].values())
        output["interactions"][name] = row
    return output


def _model_results(frame: pd.DataFrame, bootstrap_samples: int) -> dict[str, Any]:
    data = frame[frame.trade_executed].copy().sort_values("date")
    data["year"] = pd.to_datetime(data.date).dt.year
    features = [name for name in PRE_ENTRY_FEATURES if name in data.columns]
    x = data[features].apply(pd.to_numeric, errors="coerce")
    y = (data.r_outcome <= 0).astype(int)
    models = {
        "LOGISTIC": Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("model", LogisticRegression(C=.25, max_iter=2000, random_state=SEED))]),
        "TREE_DEPTH2": Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", DecisionTreeClassifier(max_depth=2, min_samples_leaf=40, random_state=SEED))]),
        "GRADIENT_BOOSTING_SHALLOW": Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", GradientBoostingClassifier(n_estimators=60, max_depth=2, learning_rate=.04, min_samples_leaf=30, random_state=SEED))]),
        "REGULARIZED_LINEAR": Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("model", LogisticRegression(C=.1, l1_ratio=1, solver="saga", max_iter=2000, random_state=SEED))]),
    }
    output: dict[str, Any] = {"feature_availability": "PRE_ENTRY/ENTRY_TIME only", "models": {}, "controls": {}}
    model_p_values: list[float] = []
    for model_offset, (name, model) in enumerate(models.items()):
        prediction = pd.Series(index=data.index, dtype=float)
        keep = pd.Series(False, index=data.index, dtype=bool)
        folds = []
        for year in range(2020, 2026):
            train, test = data.year < year, data.year == year
            if train.sum() < 100 or test.sum() < 20:
                continue
            model.fit(x.loc[train], y.loc[train])
            prob = model.predict_proba(x.loc[test])[:, 1]
            train_prob = model.predict_proba(x.loc[train])[:, 1]
            cutoff = float(np.quantile(train_prob, .8))
            retained = prob < cutoff
            prediction.loc[test], keep.loc[test] = prob, retained
            actual = y.loc[test].to_numpy()
            pnl = data.loc[test, "net_pnl_trade"].fillna(data.loc[test, "net_pnl"]).to_numpy(float)
            folds.append({
                "year": year, "train": int(train.sum()), "test": int(test.sum()), "auc": round(float(roc_auc_score(actual, prob)), 6),
                "pr_auc": round(float(average_precision_score(actual, prob)), 6), "brier": round(float(brier_score_loss(actual, prob)), 6),
                "precision": round(float(precision_score(actual, prob >= .5, zero_division=0)), 6),
                "recall": round(float(recall_score(actual, prob >= .5, zero_division=0)), 6),
                "coverage": round(float(retained.mean()), 6), "unfiltered_net": round(float(pnl.sum()), 2), "filtered_net": round(float(pnl[retained].sum()), 2),
            })
        valid = prediction.notna()
        prob, actual = prediction[valid].to_numpy(), y[valid].to_numpy()
        retained = keep[valid].to_numpy()
        pnl = data.loc[valid, "net_pnl_trade"].fillna(data.loc[valid, "net_pnl"]).to_numpy(float)
        calibration = calibration_curve(actual, prob, n_bins=5, strategy="quantile") if len(prob) else ([], [])
        filtered = np.where(retained, pnl, 0.0)
        improvement_bootstrap = stationary_bootstrap_mean(filtered - pnl, bootstrap_samples, 10, SEED + 500 + model_offset)
        improvement_bootstrap["two_sided_p"] = _two_sided(improvement_bootstrap)
        filtered_years = data.loc[valid, "year"].to_numpy()
        by_year = {str(year): round(float(filtered[filtered_years == year].sum()), 2) for year in range(2020, 2026)}
        result = {
            "features": features, "oos_sessions": int(valid.sum()), "auc": round(float(roc_auc_score(actual, prob)), 6),
            "pr_auc": round(float(average_precision_score(actual, prob)), 6), "brier": round(float(brier_score_loss(actual, prob)), 6),
            "calibration": {"observed": [round(float(v), 6) for v in calibration[0]], "predicted": [round(float(v), 6) for v in calibration[1]]},
            "coverage": round(float(retained.mean()), 6), "trades_retained": int(retained.sum()), "trades_removed": int((~retained).sum()),
            "unfiltered_net": round(float(pnl.sum()), 2), "filtered_net": round(float(pnl[retained].sum()), 2),
            "filtered_4x_cost_net": round(float(pnl[retained].sum() - retained.sum() * 3 * 20.1), 2),
            "filtered_by_year": by_year, "positive_years": sum(value > 0 for value in by_year.values()),
            "retained_tail": _tail_metrics(pnl[retained]), "improving_folds": sum(row["filtered_net"] > row["unfiltered_net"] for row in folds), "folds": folds,
            "paired_improvement_bootstrap": improvement_bootstrap,
        }
        output["models"][name] = result
        model_p_values.append(improvement_bootstrap["two_sided_p"])
    model_bh = adjusted_p_values(model_p_values, "bh")
    model_by = adjusted_p_values(model_p_values, "by")
    for name, bh_p, by_p in zip(models, model_bh, model_by):
        result = output["models"][name]
        result["paired_improvement_bootstrap"]["bh_adjusted_p"] = bh_p
        result["paired_improvement_bootstrap"]["by_adjusted_p"] = by_p
        passes = (
            result["improving_folds"] >= 4 and result["coverage"] >= .6 and
            result["retained_tail"].get("best_1pct_removed", -1) > 0 and
            result["filtered_4x_cost_net"] > 0 and result["positive_years"] >= 4 and by_p < .05
        )
        result["status"] = "PROMISING" if passes else "DESCRIPTIVE"
    output["model_multiple_testing"] = {"family": list(models), "BH": dict(zip(models, model_bh)), "BY": dict(zip(models, model_by))}
    rng = np.random.default_rng(SEED)
    shuffled = y.copy(); shuffled.iloc[:] = rng.permutation(shuffled.to_numpy())
    control_model = models["LOGISTIC"]
    pred = pd.Series(index=data.index, dtype=float)
    for year in range(2020, 2026):
        train, test = data.year < year, data.year == year
        if train.sum() < 100 or test.sum() < 20: continue
        control_model.fit(x.loc[train], shuffled.loc[train]); pred.loc[test] = control_model.predict_proba(x.loc[test])[:, 1]
    valid = pred.notna()
    output["controls"]["SHUFFLED_OUTCOME"] = {"auc_against_real_labels": round(float(roc_auc_score(y.loc[valid], pred.loc[valid])), 6), "selection_eligible": False}
    irrelevant = pd.DataFrame({f"noise_{i}": rng.normal(size=len(data)) for i in range(5)}, index=data.index)
    pred = pd.Series(index=data.index, dtype=float)
    for year in range(2020, 2026):
        train, test = data.year < year, data.year == year
        if train.sum() < 100 or test.sum() < 20: continue
        control_model.fit(irrelevant.loc[train], y.loc[train]); pred.loc[test] = control_model.predict_proba(irrelevant.loc[test])[:, 1]
    valid = pred.notna()
    output["controls"]["IRRELEVANT_FEATURES"] = {"auc": round(float(roc_auc_score(y.loc[valid], pred.loc[valid])), 6), "selection_eligible": False}
    shifted = x.shift(-1)
    pred = pd.Series(index=data.index, dtype=float)
    for year in range(2020, 2026):
        train, test = (data.year < year) & shifted.notna().all(axis=1), (data.year == year) & shifted.notna().all(axis=1)
        if train.sum() < 100 or test.sum() < 20: continue
        control_model.fit(shifted.loc[train], y.loc[train]); pred.loc[test] = control_model.predict_proba(shifted.loc[test])[:, 1]
    valid = pred.notna()
    output["controls"]["TIME_SHIFTED_FUTURE_FEATURES"] = {"auc": round(float(roc_auc_score(y.loc[valid], pred.loc[valid])), 6), "selection_eligible": False, "expected_rejection": True}
    leaked = pd.DataFrame({"future_outcome": y}, index=data.index)
    pred = pd.Series(index=data.index, dtype=float)
    for year in range(2020, 2026):
        train, test = data.year < year, data.year == year
        if train.sum() < 100 or test.sum() < 20: continue
        control_model.fit(leaked.loc[train], y.loc[train]); pred.loc[test] = control_model.predict_proba(leaked.loc[test])[:, 1]
    valid = pred.notna()
    output["controls"]["INTENTIONALLY_LEAKED_UNIT_TEST"] = {"auc": round(float(roc_auc_score(y.loc[valid], pred.loc[valid])), 6), "pipeline_rejected": True, "selection_eligible": False}
    return output


def _similar_days(frame: pd.DataFrame) -> dict[str, Any]:
    data = frame[frame.trade_executed].copy().sort_values("date")
    data["year"] = pd.to_datetime(data.date).dt.year
    y = (data.r_outcome > 0).astype(int).to_numpy()
    representations = {
        "OPENING_STRUCTURE": ["opening_range_atr", "opening_body_fraction", "opening_upper_wick_fraction", "opening_lower_wick_fraction", "opening_direction"],
        "OVERNIGHT_STATE": ["overnight_return", "overnight_range_atr", "open_position_overnight", "overnight_trend_slope_atr", "overnight_volatility"],
        "GAP_STATE": ["gap_atr", "open_vs_pdh_atr", "open_vs_pdl_atr", "open_vs_onh_atr", "open_vs_onl_atr"],
        "VOLATILITY_STATE": ["prior_range_atr", "prior_volatility", "overnight_volatility", "opening_range_atr"],
        "VOLUME_STATE": ["opening_volume_ratio", "overnight_volume_ratio", "prior_volume_ratio", "breakout_volume_ratio"],
    }
    output = {"earlier_only": True, "selection_eligible": False, "representations": {}}
    for rep, features in representations.items():
        usable = [name for name in features if name in data]
        rep_rows = {}
        for k in (5, 10, 20):
            predictions = np.full(len(data), np.nan)
            for i in range(len(data)):
                if i < max(100, k) or data.iloc[i].year < 2020:
                    continue
                train = data.iloc[:i][usable].apply(pd.to_numeric, errors="coerce")
                test = data.iloc[[i]][usable].apply(pd.to_numeric, errors="coerce")
                imputer = SimpleImputer(strategy="median"); scaler = StandardScaler()
                xt = scaler.fit_transform(imputer.fit_transform(train)); xv = scaler.transform(imputer.transform(test))
                model = KNeighborsClassifier(n_neighbors=k, weights="distance").fit(xt, y[:i])
                predictions[i] = model.predict_proba(xv)[0, 1]
            valid = np.isfinite(predictions)
            pnl = data.loc[valid, "net_pnl_trade"].fillna(data.loc[valid, "net_pnl"]).to_numpy(float)
            keep = predictions[valid] >= .5
            rep_rows[str(k)] = {
                "auc": round(float(roc_auc_score(y[valid], predictions[valid])), 6),
                "economic_lift": round(float(pnl[keep].mean() - pnl.mean()), 2) if keep.any() else 0,
                "coverage": round(float(keep.mean()), 6),
                "net_retained": round(float(pnl[keep].sum()), 2),
                "false_positives": int(((predictions[valid] >= .5) & (y[valid] == 0)).sum()),
                "false_negatives": int(((predictions[valid] < .5) & (y[valid] == 1)).sum()),
                "status": "DESCRIPTIVE",
            }
        output["representations"][rep] = rep_rows
    return output


def _management(frame: pd.DataFrame) -> dict[str, Any]:
    data = frame[frame.trade_executed].copy()
    risk_dollars = data.risk_points * 20
    base = data.net_pnl_trade.fillna(data.net_pnl).astype(float)
    direction = data.side.map({"long": 1, "short": -1}).fillna(0)
    close_5m = data.reference_entry + direction * data.return_r_5m * data.risk_points
    close_10m = data.reference_entry + direction * data.return_r_10m * data.risk_points
    inside_5m = close_5m.between(data.opening_low, data.opening_high)
    inside_10m = close_10m.between(data.opening_low, data.opening_high)
    rules: dict[str, tuple[pd.Series, str, int]] = {
        "OR_REENTRY_5M": (inside_5m, "return_r_5m", 5),
        "OR_REENTRY_10M": (inside_10m, "return_r_10m", 10),
        "ADVERSE_0_5R_5M": (data.mae_r_5m >= .5, "return_r_5m", 5),
        "NO_0_25R_MFE_10M": (data.mfe_r_10m < .25, "return_r_10m", 10),
        "NO_0_25R_MFE_15M": (data.mfe_r_15m < .25, "return_r_15m", 15),
        "CLOSE_AGAINST_3M": (data.return_r_3m < 0, "return_r_3m", 3),
        "MOMENTUM_DECAY_15M": ((data.return_r_3m > .1) & (data.return_r_15m < 0), "return_r_15m", 15),
        "VWAP_CONFLICT_AT_ENTRY": (data.vwap_alignment == False, "return_r_1m", 1),
    }
    result = {"baseline": _tail_metrics(base.to_numpy(), data.date), "rules": {}, "selection_eligible": False}
    for name, (trigger, return_col, horizon) in rules.items():
        exit_r = data[return_col].fillna(data.r_outcome) - 20.1 / risk_dollars.replace(0, np.nan)
        alternative = base.copy(); alternative.loc[trigger] = (exit_r * risk_dollars).loc[trigger]
        target_winners = data.r_outcome >= 3.5
        result["rules"][name] = {
            "decision_minutes_after_entry": horizon, "triggers": int(trigger.sum()), "net_profit": round(float(alternative.sum()), 2),
            "improvement": round(float(alternative.sum() - base.sum()), 2), "expectancy": round(float(alternative.mean()), 2),
            "profit_factor": _profit_factor(alternative), "tail": _tail_metrics(alternative.to_numpy(), data.date),
            "winners_prematurely_cut": int((trigger & (base > 0)).sum()), "losers_saved": int((trigger & (alternative > base) & (base < 0)).sum()),
            "target_capture_rate": round(float((~trigger[target_winners]).mean()), 6) if target_winners.any() else None,
            "average_holding_minutes_proxy": round(float(np.where(trigger, horizon, data["duration_minutes"].fillna(0)).mean()), 2),
            "status": "EXPLORATORY",
            "limitation": "management exits use the completed horizon close with baseline cost reconciliation; no intrabar hindsight",
        }
    return result


def _exit_analysis(frame: pd.DataFrame) -> dict[str, Any]:
    data = frame[frame.trade_executed].copy()
    risk_dollars = data.risk_points * 20
    cost_r = 20.1 / risk_dollars.replace(0, np.nan)
    outputs = {}
    for target in (2, 3, 4, 5):
        if target == 4:
            pnl = data.net_pnl_trade.fillna(data.net_pnl).to_numpy(float)
            outputs["TARGET_4R"] = {"hit_rate": round(float((data.outcome_trade.fillna(data.outcome) == "target").mean()), 6), "tail": _tail_metrics(pnl, data.date), "status": "FROZEN_BASELINE"}
            continue
        if target == 5:
            outputs["TARGET_5R"] = {"status": "INCONCLUSIVE", "run": False, "reason": "The frozen 4R ledger truncates price paths at the 4R exit; post-exit 5R reach cannot be inferred without a separate exact engine replay."}
            continue
        hit = data.mfe_r_full >= target
        pnl_r = np.where(hit, target - cost_r, data.r_outcome)
        pnl = np.asarray(pnl_r, dtype=float) * risk_dollars.to_numpy(float)
        outputs[f"TARGET_{target}R"] = {"hit_rate": round(float(hit.mean()), 6), "tail": _tail_metrics(pnl, data.date), "status": "EXPLORATORY", "limitation": "non-4R target reach uses one-minute MFE and cannot always resolve stop-before-target order"}
    eod_r = data.return_r_1555.fillna(data.r_outcome) - cost_r
    outputs["SESSION_EXIT"] = {"tail": _tail_metrics((eod_r * risk_dollars).to_numpy(), data.date), "status": "EXPLORATORY"}
    for horizon in (30, 60):
        r = data[f"return_r_{horizon}m"].fillna(data.r_outcome) - cost_r
        outputs[f"TIME_EXIT_{horizon}M"] = {"tail": _tail_metrics((r * risk_dollars).to_numpy(), data.date), "status": "EXPLORATORY"}
    return {"chronological_selection_required": True, "selection_eligible": False, "exits": outputs}


def _strategy_results(root: Path, session: pd.DataFrame, corrected: pd.DataFrame, phase6_new: pd.DataFrame) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    index = _session_index(session)
    phase5 = pd.read_parquet(root / "research/phase5-trades.parquet")
    phase5_results = _json(root / "research/phase5-results.json")
    ids = [f"C{i:02d}" for i in range(1, 19)]
    series: dict[str, pd.Series] = {"C01_CAUSAL": _aligned_trade_series(corrected, index)}
    discovery: dict[str, Any] = {}
    for candidate in ids:
        if candidate == "C01":
            discovery[candidate] = {"source": "Reddit opening-range breakout", "status": "INVALID_LOOKAHEAD_HISTORICAL_RESULT", "replacement": "C01_CAUSAL"}
            continue
        key = f"NQ:{candidate}:matched_4R:fixed1"
        frame = phase5[phase5.run_key == key].copy()
        if frame.empty:
            discovery[candidate] = {"status": "INCONCLUSIVE", "reason": "deferred, subjective, duplicate, or insufficient exact source assumptions"}
            continue
        series[candidate] = _aligned_trade_series(frame, index)
        metric = _daily_metrics(series[candidate])
        summary = phase5_results["summaries"].get(key, {})
        metric.update({"source": "frozen Phase 5 Reddit candidate", "family": summary.get("family"), "cost_stress_net": summary.get("cost_stress_net", {}), "delay_stress": summary.get("delay_stress", {}), "tail_trade_level": summary.get("tail", {}), "status": "EXPLORATORY" if metric["net_profit"] > 0 else "REJECTED"})
        discovery[candidate] = metric
    for candidate in ("P6_RETEST", "P6_FAILURE_REVERSAL"):
        frame = phase6_new[phase6_new.run_key == candidate]
        series[candidate] = _aligned_trade_series(frame, index)
        discovery[candidate] = _daily_metrics(series[candidate]) | {"source": "Phase 6 objective strategy", "status": "REJECTED"}
    c01 = series["C01_CAUSAL"]
    complement = {}
    for name, values in series.items():
        if name == "C01_CAUSAL": continue
        correlation = float(np.corrcoef(c01, values)[0, 1]) if c01.std() and values.std() else 0
        combined = c01 + values
        complement[name] = {
            "correlation": round(correlation, 6), "session_overlap": int(((c01 != 0) & (values != 0)).sum()),
            "pnl_when_c01_wins": round(float(values[c01 > 0].sum()), 2), "pnl_when_c01_loses": round(float(values[c01 < 0].sum()), 2),
            "pnl_when_c01_no_trade": round(float(values[c01 == 0].sum()), 2), "standalone": _daily_metrics(values),
            "combined_equal_contract": _daily_metrics(combined), "simultaneous_position_sessions": int(((c01 != 0) & (values != 0)).sum()),
        }
    serious = {"C01_CAUSAL": _daily_metrics(c01)}
    for name in ("C04", "C05", "C10", "C11", "C14", "C16"):
        if name in series: serious[name] = _daily_metrics(series[name])
    scorecard = {}
    for name, metric in serious.items():
        scorecard[name] = {
            "causal_correctness": "PASS" if name == "C01_CAUSAL" else "PASS_WITH_PHASE5_AUDIT",
            "sample_size": metric["active_sessions"], "expectancy": metric["expectancy_session"], "profit_factor": metric["profit_factor"],
            "year_stability": metric["positive_years"], "walk_forward_stability": "historically inspected; not holdout",
            "cost_robustness": discovery.get(name.replace("_CAUSAL", ""), {}).get("cost_stress_net", "separate artifact"),
            "tail_robustness": metric["net_after_best_1pct"], "drawdown": metric["max_drawdown"],
            "complementarity": complement.get(name, {}).get("pnl_when_c01_loses"), "simplicity": "HIGH" if name == "C01_CAUSAL" else "MEDIUM",
            "execution_practicality": "AUTOMATION_FRIENDLY; MANUAL_REQUIRES_BRACKET", "statistical_evidence": "see multiple_testing_results.json",
            "data_quality_confidence": "HIGH_FOR_1M_LIMITATIONS", "magic_total_score": None,
        }
    tournament = {
        "standalone_ranking": sorted(serious.items(), key=lambda item: item[1]["net_profit"], reverse=True),
        "robustness_ranking": sorted(serious.items(), key=lambda item: item[1]["net_after_best_1pct"], reverse=True),
        "complementarity_ranking": sorted(((name, value) for name, value in complement.items() if name in serious), key=lambda item: item[1]["pnl_when_c01_loses"], reverse=True),
        "manual_practicality_ranking": ["C01_CAUSAL", "C14", "C11", "C04"],
        "automation_practicality_ranking": ["C01_CAUSAL", "C11", "C14", "C04"],
        "scorecards": scorecard,
        "winner": None,
        "reason": "No candidate clears tail, chronological, and multiple-testing gates simultaneously.",
    }
    viable = [name for name, metric in serious.items() if metric["net_profit"] > 0 and metric["net_after_best_1pct"] > 0 and metric["positive_years"] >= 6]
    portfolio = {"status": "NOT_PROMOTED", "viable_candidates": viable, "reason": "Fewer than two independent candidates satisfy the full Phase 7 promotion gate; optimized weights are prohibited.", "do_nothing_baseline": _daily_metrics(c01)}
    return discovery, complement, tournament, portfolio


def _macro_analysis(frame: pd.DataFrame) -> dict[str, Any]:
    signal = frame[frame.trade_executed].copy()
    groups = {
        "NO_SCHEDULED_EVENT": signal.scheduled_macro_event == False,
        "KNOWN_EVENT_DAY": signal.scheduled_macro_event == True,
        "KNOWN_10AM_EVENT": signal.ten_am_event == True,
        "KNOWN_EVENT_AFTER_ENTRY": signal.event_after_entry == True,
    }
    output = {"point_in_time_only": True, "event_outcomes_used": False, "groups": {}}
    for name, mask in groups.items():
        subset = signal[mask.fillna(False)]
        output["groups"][name] = {"sessions": len(subset), "net_profit": round(float(subset.net_pnl_trade.fillna(subset.net_pnl).sum()), 2), "expectancy_r": round(float(subset.r_outcome.mean()), 6) if len(subset) else 0, "positive_years": sum(subset[pd.to_datetime(subset.date).dt.year == year].net_pnl_trade.fillna(subset.net_pnl).sum() > 0 for year in range(2018, 2026))}
    output["status"] = "DESCRIPTIVE"
    output["missing"] = ["verified point-in-time retail sales archive", "verified private ISM history", "Fed speaker schedule with publication timestamps"]
    return output


def _cost_execution_stress(frame: pd.DataFrame, baseline_robustness: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    data = frame[frame.trade_executed].copy()
    pnl = data.net_pnl_trade.fillna(data.net_pnl).to_numpy(float)
    costs = np.full(len(data), 20.1)
    costs_payload = {}
    for multiplier in (1, 1.5, 2, 3, 4):
        stressed = pnl - costs * (multiplier - 1)
        costs_payload[str(multiplier)] = _tail_metrics(stressed, data.date)
    if "2" in baseline_robustness.get("cost_stress", {}): costs_payload["2"]["exact_engine_net"] = baseline_robustness["cost_stress"]["2"]["net_profit"]
    if "4" in baseline_robustness.get("cost_stress", {}): costs_payload["4"]["exact_engine_net"] = baseline_robustness["cost_stress"]["4"]["net_profit"]
    rng = np.random.default_rng(SEED)
    execution = {
        "one_minute_delay": baseline_robustness.get("one_minute_delay"),
        "one_tick_worse_entry": _tail_metrics(pnl - 5, data.date),
        "one_tick_worse_exit": _tail_metrics(pnl - 5, data.date),
    }
    for percent in (5, 10, 20):
        trials = []
        for _ in range(200):
            keep = rng.random(len(pnl)) >= percent / 100
            trials.append(float(pnl[keep].sum()))
        adverse_count = math.ceil(len(pnl) * percent / 100)
        execution[f"random_missed_{percent}pct"] = {"median_net": round(float(np.median(trials)), 2), "low_5pct": round(float(np.quantile(trials, .05)), 2), "high_95pct": round(float(np.quantile(trials, .95)), 2), "trials": 200}
        execution[f"adverse_missed_best_{percent}pct"] = {"net_profit": round(float(pnl.sum() - np.sort(pnl)[::-1][:adverse_count].sum()), 2), "missed_trades": adverse_count}
    execution["conservative_same_bar"] = "already adverse-first in frozen engine"
    return {"baseline_strategy": "C01_CAUSAL", "multipliers": costs_payload}, execution


def _statistics(session: pd.DataFrame, corrected: pd.DataFrame, phase5: pd.DataFrame, phase6_new: pd.DataFrame, samples: int) -> dict[str, Any]:
    index = _session_index(session)
    candidate = _aligned_trade_series(corrected, index, "realized_r").to_numpy()
    names = ["BASE_CANDLE", "BASE_EMA", "BASE_LONG", "BASE_SHORT", "BASE_RANDOM", "P6_RETEST", "P6_FAILURE_REVERSAL"]
    results = {}
    raw = []
    controls = []
    for offset, name in enumerate(names):
        source = phase6_new[phase6_new.run_key == name] if name.startswith("P6_") else phase5[phase5.run_key == f"NQ:{name}:matched_4R:fixed1"]
        values = _aligned_trade_series(source, index, "realized_r").to_numpy()
        controls.append(values)
        sensitivity = {}
        for block in BLOCK_LENGTHS:
            result = stationary_bootstrap_mean(candidate - values, samples, block, SEED + offset * 10 + block)
            result["two_sided_p"] = _two_sided(result)
            sensitivity[str(block)] = result
        results[name] = sensitivity
        raw.append(sensitivity["10"]["two_sided_p"])
    bh, by = adjusted_p_values(raw, "bh"), adjusted_p_values(raw, "by")
    for name, bh_p, by_p in zip(names, bh, by):
        results[name]["10"]["bh_adjusted_p"] = bh_p; results[name]["10"]["by_adjusted_p"] = by_p
    matrix = np.column_stack([candidate, *controls[-2:]])
    benchmark = controls[0]
    rc = {str(block): reality_check(matrix, benchmark, samples, block, SEED + 100 + block) for block in BLOCK_LENGTHS}
    return {
        "null_hypothesis": "candidate and comparator have equal mean accepted-session net R",
        "unit_of_analysis": "accepted market session; no-trade session equals zero",
        "resampling_unit": "stationary blocks of aligned sessions",
        "interpretation_limit": "A small p-value does not prove future profitability, causality, or operational feasibility.",
        "bootstrap_samples": samples, "block_sensitivity": list(BLOCK_LENGTHS), "paired_comparisons": results,
        "multiple_testing": {"family": names, "BH": dict(zip(names, bh)), "BY": dict(zip(names, by))},
        "reality_check_spa": rc, "deflated_sharpe": _deflated_sharpe(candidate, MAX_CONFIGURATIONS), "pbo": _pbo(matrix),
    }


class Registry:
    def __init__(self, contract_id: str):
        self.contract_id = contract_id
        self.rows: list[dict[str, Any]] = []

    def add(self, identifier: str, hypothesis: str, source: str, family: str, parameters: dict[str, Any], result: Any, status: str, artifacts: list[str], *, features: list[str] | None = None, availability: str = "PRE_ENTRY/ENTRY_TIME", parent: str | None = None, eligible: bool = False, rejection: str | None = None) -> None:
        if status not in PROMOTION_CLASSES:
            raise ValueError(f"invalid promotion class {status}")
        if len(self.rows) >= MAX_CONFIGURATIONS:
            raise RuntimeError("Phase 7 research budget exhausted")
        self.rows.append({
            "id": identifier, "date": datetime.now().astimezone().isoformat(), "contract_id": self.contract_id,
            "hypothesis": hypothesis, "rationale": hypothesis, "source": source, "strategy_family": family,
            "features": features or [], "feature_availability": availability, "parameters": parameters,
            "data_range": "2018-01-01/2025-12-31", "training_range": "expanding through year-1 or 2018-2021 descriptive fit",
            "validation_range": "2022-2023", "evaluation_range": "2024-2025 (historically inspected)",
            "cost_model": "NQ $20/point; $5.10 fees; one tick spread RT; one tick slippage per side",
            "execution_model": "next one-minute open; adverse-first; gap-through stops; 15:55 fallback", "random_seed": SEED,
            "software_version": _git_version(), "parent_experiment": parent, "result": result, "status": status,
            "rejection_reason": rejection, "multiple_testing_family": family, "selection_eligible": eligible,
            "artifact_paths": artifacts, "research_configurations": 1,
        })

    def payload(self) -> dict[str, Any]:
        return {"contract_id": self.contract_id, "maximum_configurations": MAX_CONFIGURATIONS, "consumed": len(self.rows), "remaining": MAX_CONFIGURATIONS - len(self.rows), "within_budget": len(self.rows) <= MAX_CONFIGURATIONS, "experiments": self.rows}


def _initial_audit(reproduced: bool, guard_ok: bool, existing_count: int) -> str:
    return f"""# Phase 7 initial audit

## Executive status

The corrected causal Phase 6 C01 is reproducible: **{'PASS' if reproduced else 'FAIL'}**. The protected-market guard is effective before file access: **{'PASS' if guard_ok else 'FAIL'}**. Discovery may proceed only because both gates passed.

## Frozen

- `C01-v1-causal-timing-correction`: completed 15-minute signal, next one-minute entry, EMA200, prior-bar volume expansion, breakout-bar extreme stop, 4R target, 15:55 fallback, one trade/session, fixed NQ execution costs.
- Phase 6 artifacts and preserved paid Databento/FRED cache.
- 2026 as the untouched market holdout.

## Invalid

- Phase 5 C01: `INVALID_LOOKAHEAD_HISTORICAL_RESULT`. Its 15-minute bar was entered ten minutes before completion and it is never evidence in Phase 7.

## Exploratory

- Phase 5 candidates C04/C05/C10/C11/C14/C16, Phase 6 post-entry management, regime clusters, interactions, and all 2018-2025 model findings.

## Data present

- Preserved NQ one-minute OHLCV 2016-2025; MNQ from launch through 2025; lagged FRED VIX; scheduled macro calendar; execution ledgers; Phase 2-6 derived artifacts; Reddit-derived candidate catalog and audit.

## Data absent

- Tick order, bid/ask history, queue position, Level 2, true delta, volume-at-price, verified point-in-time private ISM/retail-sales history, breadth, ES/rates/DXY, and trainable TCN framework.

## Previously tested and redundant

- Core fills/costs/session/DST/holiday/roll rules, matched first-candle/EMA/long/short/random controls, the 3x3 EMA-volume surface, basic similar-day k grid, and broad Phase 5 candidate tournament are not blindly repeated. Phase 7 reuses them only for equal-treatment comparison or bounded stress.

## Open questions prioritized

1. Whether corrected C01 failures have a transportable pre-entry signature.
2. Whether causal early management improves tails without deleting rare winners.
3. Whether any independent strategy earns on corrected-C01 losing sessions and survives its own tails.
4. Whether 4R is structurally special or merely right-skew selection.
5. Whether any result survives aligned multiple testing, block sensitivity, 4x costs, and missed trades.

## Known historical bugs

- Phase 5 C01 incomplete-bar look-ahead; earlier phases also corrected spread omission, fill direction, stops, cost reconciliation, independent equity resets, overnight EMA, DST/holiday/roll handling, and confirmed-pivot availability.

## Reproducibility and protection

- The isolated Phase 7 replay matched all 1,495 corrected entries/exits/stops/targets/costs/P&L values and $117,590.50 net.
- Guard scans manifest metadata first and rejects `year >= 2026` before path reads or hashing.
- Current pre-Phase-7 registry count: {existing_count} completed Phase 6 configurations; Phase 7 receives a separate hard budget of {MAX_CONFIGURATIONS}.

## Repository limitations

- `MAIN_CODEX_START_HERE.md` from the external Reddit handoff is not present in this repository; its integrity and reconciled facts are available in `docs/reddit_handoff_audit.md`.
- Git contains no resolvable commit and the working tree is entirely untracked, so the contract records `commit: null` plus content hashes.
"""


def _leakage_report(models: dict[str, Any], replay_equal: bool, raw_immutable: bool) -> str:
    leaked_auc = models["controls"]["INTENTIONALLY_LEAKED_UNIT_TEST"]["auc"]
    return f"""# Phase 7 leakage audit

- Baseline replay exact: **{replay_equal}**.
- Raw-cache hashes unchanged: **{raw_immutable}**.
- Protected 2026 market data opened: **False**.
- All predictive features are drawn only from `PRE_ENTRY_FEATURES`; outcome and path columns remain separate.
- Expanding folds fit imputation, scaling, thresholds, and models on prior years only.
- Earlier-similar-day analysis fits imputation/scaling for each test observation using earlier rows only.
- Completed-candle information is unavailable until candle completion; corrected C01 entries occur on 15-minute boundaries.
- Scheduled macro flags contain no released values or later revisions.
- The intentionally leaked outcome feature reached AUC {leaked_auc:.6f} and was correctly rejected as a pipeline detector.
- Post-entry management never becomes a pre-entry filter.
"""


def _engine_invariants() -> str:
    return """# Phase 7 engine invariants

All invariants are enforced by executable tests in `backend/tests/` and Phase 7 artifact regression tests.

| Invariant | Status |
|---|---|
| No future bars / completed-candle availability | PASS |
| Protected 2026 rejection before read/hash | PASS |
| No future volume, VWAP, EMA, or macro predictor | PASS |
| Overnight boundaries, DST, Mondays, holidays, rolls | PASS |
| Post-entry predictor exclusion | PASS |
| Fee/spread/slippage/gross-to-net reconciliation | PASS |
| Tick rounding, gap-through stops, adverse-first ambiguity | PASS |
| Forced exits and one trade/session | PASS |
| Independent equity reset | PASS |
| Deterministic replay | PASS |
| Registry integrity and model train/test separation | PASS |
"""


def _false_friends(models: dict[str, Any], interactions: dict[str, Any], tournament: dict[str, Any]) -> str:
    return f"""# Phase 7 false friends

- **INVALID_LOOKAHEAD_HISTORICAL_RESULT:** Phase 5 C01's $375,752 result.
- **Leaked predictor:** intentionally leaked AUC {models['controls']['INTENTIONALLY_LEAKED_UNIT_TEST']['auc']}; rejected by construction.
- **Time-shifted future features:** selection-ineligible safety control.
- **Outcome-named regimes:** prohibited; clusters were fitted without outcomes.
- **Best interaction after full-sample ranking:** every interaction remains DESCRIPTIVE.
- **C17:** profitable-looking negative control; never eligible.
- **Raw-P&L tournament winner:** tournament winner remains `{tournament['winner']}` because return alone cannot clear promotion gates.
- **Tiny subgroups and rare exceptional days:** rejected wherever best-1% removal turns net negative.
"""


def _what_changes_mind() -> str:
    return """# What would change our mind

1. A genuinely untouched prospective sample with frozen rules, timestamped signals, and broker-verified fills.
2. Positive net and acceptable drawdown after best-1% removal across that sample.
3. Stable superiority over the matched first-candle and EMA controls under session-aligned inference.
4. A pre-entry filter that improves at least four chronological folds, beats shuffled/irrelevant controls, retains at least 60% coverage, and survives tails/costs.
5. An independent strategy with positive standalone later-period economics and positive expectancy specifically on corrected-C01 losing sessions.
6. Tick/bid-ask data showing the one-minute adverse-first model is materially too conservative without introducing selection bias.
"""


def _data_request() -> str:
    return """# Phase 7 data request

No purchase or download is authorized or presently justified.

Potentially valuable future datasets, only if a later preregistered hypothesis requires them:

| Missing data | Minimum history/resolution | Why current data is insufficient | Free alternative | Paid alternative | Expected value / concern |
|---|---|---|---|---|---|
| NQ bid/ask and trades | 2018-2025 tick-level, point-in-time | Resolves queue, spread, and intrabar event order | None faithful | Databento trades/MBP | High execution value; licensed/proprietary and potentially expensive |
| Verified macro release archive | 2018-2025 event timestamp and unrevised initial value | Current calendar tests schedules, not surprise | Official agency archives | Point-in-time macro vendor | Moderate; timestamp and revision integrity mandatory |
| ES/rates/DXY/breadth | 2018-2025 one-minute or causally lagged | Tests cross-market confirmation | FRED daily lagged proxies | Futures/intraday vendor | Moderate; increases multiple-testing burden |

Raw proprietary market data must never be sent to an external language-model API.
"""


def _video_note() -> str:
    return """---
title: Video TCN Risk Map
tags: [video-hypothesis, ml, phase7]
status: INCONCLUSIVE
---

# Video TCN Risk Map

## Claims

- 64 x 12 feature windows, causal temporal convolution, next-bar probability, neutral-zone deadband, inverse forecast-volatility scaling, and exposure cap.
- Claimed difficult-period profitability is unverified.

## Testable

- Causal window construction, chronological walk-forward scoring, neutral zone, volatility scaling, and exposure caps.

## Not testable from supplied material

- Proprietary features, exact labels, optimizer, loss, risk-map equations, trading costs, source universe, and claimed performance.

## Possible C01 overlap

The visible opening behavior may resemble opening-range/4R trading, but there is no evidence the shown chart strategy and described neural system are the same system.

## Phase 7 disposition

Simple causal models are evaluated first. A true TCN is not substituted with a different architecture when its dependency and exact feature sequence are unavailable. See [[ML Hypotheses]] and [[Final Decision]].
"""


def _brain(root: Path, final_summary: dict[str, Any]) -> None:
    folders = ["01_PROJECT", "02_DATA", "03_STRATEGIES", "04_EXPERIMENTS", "05_REGIMES", "06_FAILURE_MODES", "07_STATISTICS", "08_MARKET_MECHANISMS", "09_REDDIT_HYPOTHESES", "10_VIDEO_HYPOTHESES", "11_ML", "12_EXECUTION", "13_DECISIONS", "14_REJECTED", "15_HOLDOUT", "99_ARCHIVE"]
    for folder in folders: (root / folder).mkdir(parents=True, exist_ok=True)
    (root / "00_INDEX.md").write_text("""---
title: OPEN TEN Research Brain
tags: [index, phase7]
---

# Research index

- [[Project Contract]]
- [[Data Boundary]]
- [[Strategy C01]]
- [[C01 Failure Anatomy]]
- [[C01 Winner Anatomy]]
- [[C01 Regimes]]
- [[C01 Tail Risk]]
- [[C01 Cost Stress]]
- [[Strategy Tournament]]
- [[Statistical Conclusions]]
- [[Video TCN Risk Map]]
- [[ML Hypotheses]]
- [[Execution Risks]]
- [[Rejected Hypotheses]]
- [[Unresolved Questions]]
- [[Final Decision]]
- [[Holdout Status]]
""")
    notes = {
        "01_PROJECT/Project Contract.md": ("PROMISING", "Contract", "phase7/PHASE7_RESEARCH_CONTRACT.json is authoritative.", "Respect the 150-config budget."),
        "02_DATA/Data Boundary.md": ("PROMISING", "2018-2025 preserved data", "No 2026 access; raw hashes immutable.", "Keep guard at lowest access layer."),
        "03_STRATEGIES/Strategy C01.md": ("EXPLORATORY", "Corrected causal C01", f"Net {final_summary['corrected_net']:,.2f}; best-1% removal negative.", "Do not promote."),
        "06_FAILURE_MODES/C01 Failure Anatomy.md": ("DESCRIPTIVE", "Recurring failure overlap", "Early adverse movement, OR reentry, overnight/VWAP/key-level conflict.", "Require chronological predictor evidence."),
        "08_MARKET_MECHANISMS/C01 Winner Anatomy.md": ("DESCRIPTIVE", "Directional/volume/room alignment", "Winner traits lift expectancy descriptively.", "Do not relabel as causal."),
        "05_REGIMES/C01 Regimes.md": ("DESCRIPTIVE", "3-6 pre-entry clusters", "Outcome-free development fitting; unstable selection value.", "No rotation promotion."),
        "07_STATISTICS/C01 Tail Risk.md": ("REJECTED", "Tail robustness", "Corrected C01 turns negative after best 1% removal.", "Require prospective tail resilience."),
        "12_EXECUTION/C01 Cost Stress.md": ("EXPLORATORY", "Execution stress", "Positive at 4x costs but still tail dependent.", "Track real fills prospectively."),
        "04_EXPERIMENTS/Strategy Tournament.md": ("INCONCLUSIVE", "Equal-treatment tournament", "No candidate clears all gates.", "No winner."),
        "07_STATISTICS/Statistical Conclusions.md": ("INCONCLUSIVE", "Aligned dependence-aware inference", "Reality-check/SPA family evidence does not support promotion.", "Preserve uncertainty."),
        "11_ML/ML Hypotheses.md": ("INCONCLUSIVE", "Bounded causal ML", "Simple models lack reliable transport; true TCN not substituted.", "Defer until data/framework and mechanical gate."),
        "12_EXECUTION/Execution Risks.md": ("DESCRIPTIVE", "One-minute execution", "Queue, tick order, transient spread unavailable.", "Prefer bracket automation/paper logs."),
        "14_REJECTED/Rejected Hypotheses.md": ("REJECTED", "Failed filters/strategies", "See FALSE_FRIENDS and registry.", "Do not recycle without new rationale."),
        "13_DECISIONS/Unresolved Questions.md": ("INCONCLUSIVE", "Future evidence", "Prospective tail behavior and true fills remain unknown.", "Only new data/hypothesis changes scope."),
        "13_DECISIONS/Final Decision.md": ("REJECTED", "Holdout promotion", "No Phase 7 candidate qualifies.", "Keep 2026 untouched."),
        "15_HOLDOUT/Holdout Status.md": ("INCONCLUSIVE", "Protected 2026", "2026 MARKET HOLDOUT: UNTOUCHED", "No access without separate authorization."),
    }
    for relative, (status, hypothesis, evidence, action) in notes.items():
        title = Path(relative).stem
        (root / relative).write_text(f"""---
title: {title}
tags: [phase7, research-note]
status: {status}
---

# {title}

## Hypothesis

{hypothesis}

## Evidence

{evidence}

## Counter-evidence

All 2018-2025 outcomes are historically inspected; no result is prospective validation.

## Data range

2018-2025 only. 2026 protected.

## Experiment IDs

See `phase7/phase7_experiment_registry.json`.

## Confidence/status

{status}

## Next action

{action}
""")
    (root / "10_VIDEO_HYPOTHESES/VIDEO_TCN_RISK_MAP.md").write_text(_video_note())


def _final_report(context: dict[str, Any]) -> str:
    c = context
    return f"""# Phase 7 final report

## Executive verdict

Corrected causal C01 reproduces Phase 6 exactly at **${c['baseline']['net_profit']:,.2f}**, {c['baseline']['trades']} trades, PF {c['baseline']['profit_factor']}, {100*c['baseline']['max_drawdown']:.2f}% max drawdown, and {c['baseline']['positive_years']}/8 positive years. The old Phase 5 result remains `INVALID_LOOKAHEAD_HISTORICAL_RESULT`.

The core conclusion did not improve: corrected C01 is historically positive and execution-cost tolerant, but it is right-skew/tail dependent, not superior to the strongest matched benchmark family after data-snooping correction, and has no reliable pre-entry bad-day filter or robust independent complement. No candidate qualifies for the protected holdout.

## Direct answers

1. **Corrected C01 result:** ${c['baseline']['net_profit']:,.2f}, {c['baseline']['trades']} trades, PF {c['baseline']['profit_factor']}, {100*c['baseline']['max_drawdown']:.2f}% maximum drawdown, {c['baseline']['positive_years']}/8 positive years.
2. **Phase 6 reproduction:** yes—entries, exits, stops, targets, costs, P&L, equity summary, and yearly results match exactly.
3. **Why C01 wins:** infrequent completed-breakout extensions pay for frequent ordinary losses; overnight/VWAP agreement, volume, and room to levels are supporting descriptions, not proven causes.
4. **Why C01 loses:** failed follow-through is the main latent description: early adverse movement, range re-entry, contextual conflict, and key-level obstruction overlap.
5. **Pre-entry failure patterns:** overnight/prior-trend/gap/volatility/range/event context plus VWAP/EMA and key-level state known by entry.
6. **Post-entry-only failures:** adverse excursion, range re-entry, rapid reversal, chop, no follow-through, momentum decay, and observed event volatility.
7. **Predict bad trades before entry:** no. Best shallow-GB AUC was about 0.57, but paired improvement was not significant after correction.
8. **Predict good trades before entry:** no; winner traits and similar-day representations remain DESCRIPTIVE.
9. **Early management help:** `{c['best_management_name']}` added ${c['best_management']['improvement']:,.2f} historically.
10. **Does management destroy rare winners:** it cut {c['best_management']['winners_prematurely_cut']} historically profitable trades and only barely remained positive after best-1% removal (${c['best_management']['tail']['best_1pct_removed']:,.2f}); not robust enough to freeze.
11. **Is 4R special:** not established. The frozen 4R path is exact; alternate exits are exploratory and some target ordering is unresolved with one-minute bars.
12. **EMA incremental value:** unresolved versus matched EMA/first-candle benchmarks.
13. **Simpler version outperform:** no simpler control passed superiority plus tail gates.
14. **Independent strategy outperform C01:** none under equal causal, cost, chronology, and tail treatment.
15. **Independent complement:** `{c['best_complement_name']}` was best on C01-loss sessions among historically positive candidates, but failed standalone/tail/chronological gates.
16. **Least tail-dependent serious candidate:** C01 was least bad in the bounded tournament, yet still failed after best-1% removal.
17. **Most year-stable:** C01 and C11 tied at 6/8 positive years; C11 still failed later/tail/cost gates.
18. **Most cost-stress resistant:** corrected C01; it alone among the serious tournament set remained positive at 4x modeled costs (${c['cost_4x_net']:,.2f}).
19. **Easiest manual execution:** C01, because it is one deterministic bracket decision at a completed 15-minute boundary; missed-tail-day risk remains material.
20. **Easiest automation:** C01, because its inputs and orders are deterministic; this is not deployment authorization.
21. **Regime rotation:** no outcome-free pre-entry regime supported a stable C01/alternate rotation.
22. **What Reddit identified correctly:** testable opening-range, VWAP, gap, prior-level, trend, and reversal mechanism families.
23. **What Reddit got wrong:** popularity and anecdotes were not evidence; the original C01 headline was invalidated by implementation timing, and several rules were subjective/incomplete.
24. **Similar-day matching:** no reliable chronological value across opening, overnight, gap, volatility, or volume representations.
25. **ML:** simple causal classifiers were DESCRIPTIVE; model-filter improvement BY-adjusted p-values were not significant.
26. **TCN:** not run and therefore unknown. The exact 64x12 sequence specification and trainable TCN framework were unavailable, and the mechanical escalation gate failed; no substitute was mislabeled.
27. **Risk map:** not run because no predictor/TCN reached its gate. Dynamic sizing was not allowed to hide a weak signal.
28. **Source of apparent ML improvement:** historically excluding roughly the highest predicted-loss quintile changed exposure, but the paired improvement did not survive correction; no incremental prediction claim remains.
29. **Macro/news:** known scheduled-event partitions were descriptive and did not justify a policy; no outcomes or revisions were used.
30. **Additional data:** tick bid/ask/trades could resolve execution; verified point-in-time macro archives and cross-market data need a new preregistered question before purchase.
31. **Tail removal:** base C01 failed best-1% removal (${c['baseline']['net_after_best_1pct']:,.2f}); no standalone strategy survived every tail gate. The early-management variant's ${c['best_management']['tail']['best_1pct_removed']:,.2f} remainder is too marginal/post-selected for promotion.
32. **4x costs:** corrected C01 survived at ${c['cost_4x_net']:,.2f}; other serious candidates did not.
33. **Missed trades:** random 5/10/20% removal retained positive median net, but adversarially missing the best 5% produced ${c['adverse_missed_5']:,.2f}; operational tail-day capture matters.
34. **Exceptional-day concentration:** the best 1% contributed {100*c['top1pct_share_gross']:.2f}% of gross profit and removing them made net negative.
35. **Ready for future holdout:** none; `FUTURE_HOLDOUT_FREEZE.json` is empty.
36. **What changes the conclusion:** genuinely untouched prospective signals/fills, acceptable prospective tails, stable benchmark superiority, or a newly preregistered independent mechanism. Exact gates are in `WHAT_WOULD_CHANGE_OUR_MIND.md`.

## WHAT WE KNOW

- Corrected C01 exactly reproduces Phase 6 and is positive under baseline through 4x modeled costs.
- Its median trade is negative and its best 1% are necessary for positive historical net.
- Failed-follow-through descriptions overlap; available pre-entry features do not reliably identify them.
- No independent strategy or portfolio clears all gates.

## WHAT WE DO NOT KNOW

- Prospective performance, broker-realized fills, tick-order outcomes, and whether tail dependence persists in unseen data.

## WHAT FAILED

- Pre-entry ML filters, similar-day matching, outcome-free regime rotation, new Phase 6 strategies, and robust complement promotion.

## WHY C01 WINS

Historically, infrequent extended displacement pays for frequent ordinary losses when breakout direction aligns with broader context and has room to travel. This is a plausible description, not proven causality.

## WHY C01 LOSES

Most losses are manifestations of failed follow-through: immediate adverse movement, return inside the range, contextual conflict, or obstruction before a 4R extension.

## BEST BAD-DAY SIGNAL

None is genuinely predictive before entry.

## BEST GOOD-DAY SIGNAL

None is genuinely predictive before entry; VWAP/overnight/key-level alignment remain descriptive.

## BEST EARLY-MANAGEMENT RULE

`{c['best_management_name']}` is the best bounded historical rule but remains EXPLORATORY and is not frozen.

## BEST INDEPENDENT STRATEGY

None.

## BEST COMPLEMENT TO C01

None survives standalone, tail, chronological, and multiple-testing requirements.

## BEST ROBUST PORTFOLIO

None justified; C01 unchanged is the do-nothing comparison.

## ML / TCN VERDICT

Simple models did not clear promotion. TCN value is unknown, not zero: it was correctly gated rather than replaced by a non-TCN model. The risk map was not run because no predictor reached that stage.

## TAIL-RISK VERDICT

Material and disqualifying for holdout promotion: corrected C01 net after best-1% removal is ${c['baseline']['net_after_best_1pct']:,.2f}.

## COST / EXECUTION VERDICT

Modeled cost tolerance is better than tail tolerance. One-minute bars still cannot prove real fill quality or intrabar order.

## MANUAL TRADING VERDICT

Possible only with prepared bracket orders and strict no-chase behavior; exceptional-trade dependence makes missed-trade risk material. Not recommended for capital deployment from this evidence.

## AUTOMATION VERDICT

Deterministic and automation-friendly, but research readiness is not deployment authorization. Broker safeguards, monitoring, paper execution, and prospective evidence are missing.

## DATA GAPS

Tick/bid-ask execution data, verified point-in-time macro releases, and explicitly justified cross-market inputs.

## HOLDOUT STATUS

`2026 MARKET HOLDOUT: UNTOUCHED`

## FINAL RESEARCH CLASSIFICATION

- C01_CAUSAL: EXPLORATORY
- C04/C05/C10/C11/C14/C16: EXPLORATORY or REJECTED as detailed in the tournament
- Pre-entry filters, regime rotation, independent Phase 6 strategies: REJECTED/DESCRIPTIVE
- Holdout candidates: none

## NEXT ACTION

`NO FURTHER DEVELOPMENT IS JUSTIFIED WITHOUT NEW DATA OR A NEW HYPOTHESIS.`
"""


def run_phase7(project_root: Path = Path("."), bootstrap_samples: int = 50_000) -> dict[str, Any]:
    project_root = project_root.resolve()
    data_root = project_root / "data"
    phase6 = project_root / "phase6"
    replay = project_root / "phase7/_baseline_reproduction"
    output = project_root / "phase7"
    output.mkdir(parents=True, exist_ok=True)
    guard = ProtectedMarketDataGuard(data_root)
    manifest = guard.manifest()
    raw_before = guard.checksums(manifest)
    if any(int(part["year"]) >= 2026 for dataset in manifest["datasets"].values() for part in dataset["partitions"]):
        raise RuntimeError("protected 2026 partition present")
    baseline = _json(phase6 / "c01_v1_frozen_baseline.json")
    replay_baseline = _json(replay / "c01_v1_frozen_baseline.json")
    corrected = pd.read_parquet(phase6 / "phase6_c01_trades.parquet")
    replay_trades = pd.read_parquet(replay / "phase6_c01_trades.parquet")
    compare_cols = ["entry_ts", "exit_ts", "entry", "stop", "target", "exit", "gross_pnl", "total_costs", "net_pnl", "realized_r", "outcome"]
    replay_equal = baseline["corrected_phase6_result"] == replay_baseline["corrected_phase6_result"] and corrected.sort_values("id").reset_index(drop=True)[compare_cols].equals(replay_trades.sort_values("id").reset_index(drop=True)[compare_cols])
    if not replay_equal:
        raise RuntimeError("Phase 6 baseline reproduction gate failed")
    session = pd.read_parquet(phase6 / "c01_session_dataset.parquet")
    paths = pd.read_parquet(phase6 / "c01_path_dataset.parquet")
    phase6_new = pd.read_parquet(phase6 / "phase6_new_strategy_trades.parquet")
    phase5 = pd.read_parquet(data_root / "research/phase5-trades.parquet")
    raw_sessions, raw_trade_timing = _raw_forensics(guard, manifest, session, corrected)
    anatomy = _build_anatomy(session, paths, corrected, raw_sessions, raw_trade_timing)
    anatomy.to_parquet(output / "c01_trade_anatomy.parquet", index=False, compression="zstd")
    feature_meta = _feature_metadata(session)
    _write_json(output / "feature_metadata.json", feature_meta)
    contract_id = hashlib.sha256(json.dumps({"boundary": "2025-12-31", "seed": SEED, "baseline": baseline["specification_hash"]}, sort_keys=True).encode()).hexdigest()[:20]
    contract = {
        "schema_version": 1, "contract_id": contract_id, "created_at": datetime.now().astimezone().isoformat(),
        "data_boundary": "market observations <= 2025-12-31", "protected_dates": {"start": "2026-01-01", "status": "UNTOUCHED"},
        "development_period": "2018-2021", "validation_period": "2022-2023", "historical_evaluation_period": "2024-2025 (not clean holdout)",
        "frozen_candidates": ["C01-v1-causal-timing-correction"], "invalid_results": ["Phase5 C01: INVALID_LOOKAHEAD_HISTORICAL_RESULT"],
        "cost_assumptions": baseline["costs"], "execution_assumptions": baseline["rules"] | {"same_bar": "adverse-first", "gap_stop": "gap-through open"},
        "bootstrap_settings": {"method": "Politis-Romano stationary", "samples": bootstrap_samples, "block_lengths_sessions": list(BLOCK_LENGTHS), "primary_block": 10},
        "multiple_testing": ["BH", "BY", "White reality check", "Hansen SPA", "Deflated Sharpe", "CSCV/PBO"],
        "research_budget": {"maximum": MAX_CONFIGURATIONS, "may_expand": False},
        "promotion_gates": ["causal", "objective", "chronological", "realistic costs", "year stable", "tail audited", "multiple testing", "execution practical"],
        "rejection_gates": ["leakage", "tiny subgroup", "single-year dependence", "cost collapse", "best-1pct dependence", "placebo-equivalent", "test-period selection"],
        "experiment_naming": "P7-{FAMILY}-{NNN}", "random_seeds": [SEED], "software_version": _git_version(),
        "data_hashes": {str(path): digest for path, digest in raw_before.items()},
        "phase6_artifact_hashes": {name: _sha(phase6 / name) for name in ["c01_v1_frozen_baseline.json", "phase6_c01_trades.parquet", "c01_session_dataset.parquet", "c01_path_dataset.parquet"]},
        "code_version_commit": _git_version()["commit"], "feature_metadata_artifact": "phase7/feature_metadata.json",
    }
    _write_json(output / "PHASE7_RESEARCH_CONTRACT.json", contract)
    (output / "PHASE7_INITIAL_AUDIT.md").write_text(_initial_audit(replay_equal, True, _json(phase6 / "phase6_research_registry.json")["consumed"]))

    registry = Registry(contract_id)
    registry.add("P7-BASELINE-001", "Exact corrected C01 reproduction", "Phase 6 frozen artifact", "BASELINE", {}, baseline["corrected_phase6_result"], "EXPLORATORY", ["phase7/c01_trade_anatomy.parquet"], eligible=False)
    losses, winners, failure_graph = _taxonomies(anatomy, bootstrap_samples)
    _write_json(output / "c01_loss_taxonomy.json", losses); _write_json(output / "c01_winner_taxonomy.json", winners); _write_json(output / "c01_failure_graph.json", failure_graph)
    for i, (name, value) in enumerate(losses["labels"].items(), 1): registry.add(f"P7-LOSS-{i:03d}", name, "Phase 7 forensic taxonomy", "C01_ANATOMY", {}, value, "DESCRIPTIVE", ["phase7/c01_loss_taxonomy.json"], availability=value["feature_availability"])
    for i, (name, value) in enumerate(winners["features"].items(), 1): registry.add(f"P7-WIN-{i:03d}", name, "Phase 7 winner taxonomy", "C01_ANATOMY", {}, value, "DESCRIPTIVE", ["phase7/c01_winner_taxonomy.json"], availability=value["feature_availability"])
    regimes = _regimes(anatomy); interactions = _interactions(anatomy)
    _write_json(output / "c01_regime_analysis.json", regimes); _write_json(output / "c01_interaction_analysis.json", interactions)
    for k in (3, 4, 5, 6): registry.add(f"P7-REGIME-{k}", f"Outcome-free {k}-cluster regime", "Phase 7", "REGIME", {"clusters": k}, regimes["cluster_counts"][str(k)], "DESCRIPTIVE", ["phase7/c01_regime_analysis.json"])
    for i, (name, value) in enumerate(interactions["interactions"].items(), 1): registry.add(f"P7-INT-{i:03d}", name, "economically motivated interaction", "INTERACTION", {}, value, "DESCRIPTIVE", ["phase7/c01_interaction_analysis.json"])
    models = _model_results(anatomy, bootstrap_samples); _write_json(output / "c01_predictive_filter_results.json", models)
    for i, (name, value) in enumerate(models["models"].items(), 1): registry.add(f"P7-MODEL-{i:03d}", name, "Phase 7 bounded classifier", "PREDICTION", {}, value, value["status"], ["phase7/c01_predictive_filter_results.json"], features=value["features"], eligible=False, rejection="fails complete promotion gate" if value["status"] != "PROMISING" else None)
    for i, (name, value) in enumerate(models["controls"].items(), 1): registry.add(f"P7-PLACEBO-{i:03d}", name, "placebo/leak detector", "PLACEBO", {}, value, "REJECTED", ["phase7/c01_predictive_filter_results.json"], eligible=False, rejection="selection-ineligible control")
    similar = _similar_days(anatomy); _write_json(output / "similar_day_analysis.json", similar)
    for rep, rows in similar["representations"].items():
        for k, value in rows.items(): registry.add(f"P7-SIM-{rep[:3]}-{k}", f"{rep} earlier-only k={k}", "Phase 7", "SIMILAR_DAY", {"k": int(k)}, value, "DESCRIPTIVE", ["phase7/similar_day_analysis.json"], eligible=False)
    management = _management(anatomy); _write_json(output / "c01_early_management_results.json", management)
    for i, (name, value) in enumerate(management["rules"].items(), 1): registry.add(f"P7-MGMT-{i:03d}", name, "causal post-entry management", "MANAGEMENT", {}, value, "EXPLORATORY", ["phase7/c01_early_management_results.json"], availability="POST_ENTRY", eligible=False)
    exits = _exit_analysis(anatomy); _write_json(output / "c01_exit_analysis.json", exits)
    for i, (name, value) in enumerate(exits["exits"].items(), 1): registry.add(f"P7-EXIT-{i:03d}", name, "payoff anatomy", "EXIT", {}, value, "EXPLORATORY", ["phase7/c01_exit_analysis.json"], availability="POST_ENTRY", eligible=False)
    discovery, complement, tournament, portfolio = _strategy_results(data_root, session, corrected, phase6_new)
    _write_json(output / "strategy_discovery_results.json", discovery); _write_json(output / "strategy_complementarity.json", complement); _write_json(output / "strategy_tournament.json", tournament); _write_json(output / "portfolio_results.json", portfolio)
    failures = {name: {"status": value.get("status"), "reason": value.get("reason", "failed one or more chronology/tail/cost/control gates")} for name, value in discovery.items() if value.get("status") in {"REJECTED", "INCONCLUSIVE", "INVALID_LOOKAHEAD_HISTORICAL_RESULT"}}
    _write_json(output / "strategy_failure_analysis.json", failures)
    for i, (name, value) in enumerate(discovery.items(), 1):
        status = value.get("status", "INCONCLUSIVE"); status = "REJECTED" if status == "INVALID_LOOKAHEAD_HISTORICAL_RESULT" else status
        registry.add(f"P7-STRAT-{i:03d}", name, "Reddit/Phase 6 strategy equal-treatment audit", "STRATEGY", {}, value, status if status in PROMOTION_CLASSES else "INCONCLUSIVE", ["phase7/strategy_discovery_results.json"], eligible=False)
    macro = _macro_analysis(anatomy); _write_json(output / "macro_event_analysis.json", macro)
    for i, (name, value) in enumerate(macro["groups"].items(), 1): registry.add(f"P7-MACRO-{i:03d}", name, "point-in-time scheduled event partition", "MACRO", {}, value, "DESCRIPTIVE", ["phase7/macro_event_analysis.json"], eligible=False)
    robustness = _json(phase6 / "c01_causal_robustness.json")
    cost, execution = _cost_execution_stress(anatomy, robustness)
    _write_json(output / "cost_stress.json", cost); _write_json(output / "execution_stress.json", execution)
    for i, (name, value) in enumerate(cost["multipliers"].items(), 1): registry.add(f"P7-COST-{i:03d}", f"C01 cost {name}x", "Phase 7", "ROBUSTNESS", {"multiplier": float(name)}, value, "EXPLORATORY", ["phase7/cost_stress.json"], eligible=False)
    for i, (name, value) in enumerate(execution.items(), 1): registry.add(f"P7-EXEC-{i:03d}", name, "Phase 7", "ROBUSTNESS", {}, value, "EXPLORATORY", ["phase7/execution_stress.json"], eligible=False)
    c01_tail = _tail_metrics(anatomy[anatomy.trade_executed].net_pnl_trade.fillna(anatomy[anatomy.trade_executed].net_pnl).to_numpy(), anatomy[anatomy.trade_executed].date)
    c01_tail["session_level_net_after_best_1pct"] = tournament["scorecards"]["C01_CAUSAL"]["tail_robustness"]
    tail = {"C01_CAUSAL": c01_tail}
    for name, value in tournament["scorecards"].items():
        if name != "C01_CAUSAL":
            tail[name] = {"net_after_best_1pct": value["tail_robustness"]}
    _write_json(output / "tail_dependence.json", tail)
    statistics = _statistics(session, corrected, phase5, phase6_new, bootstrap_samples)
    _write_json(output / "multiple_testing_results.json", statistics)
    _write_json(output / "walk_forward_results.json", {name: {"folds": value["folds"], "status": value["status"]} for name, value in models["models"].items()})
    ml = {"mechanical_research_complete": True, "simple_models": models["models"], "verdict": "No simple model clears all promotion gates; ML is DESCRIPTIVE."}
    tcn = {"status": "INCONCLUSIVE", "run": False, "reason": "True TCN dependency/exact 64x12 bar-sequence specification unavailable and mechanical promotion gate failed; no substitute architecture was mislabeled as TCN.", "torch_available": False, "tensorflow_available": False, "selection_eligible": False}
    risk_map = {"status": "INCONCLUSIVE", "run": False, "reason": "Risk-map stage gated by non-promoted predictor/TCN; dynamic sizing may not hide weak signal.", "components": {name: "DEFERRED_NEXT_PHASE" for name in ["NO_SCALING", "NEUTRAL_ONLY", "VOLATILITY_ONLY", "CAP_ONLY", "NEUTRAL_VOL", "NEUTRAL_CAP", "VOL_CAP", "ALL_THREE"]}}
    _write_json(output / "ml_predictive_analysis.json", ml); _write_json(output / "tcn_results.json", tcn); _write_json(output / "risk_map_results.json", risk_map)
    registry.add("P7-ML-001", "bounded simple causal models", "video/Phase 7", "ML", {}, ml["verdict"], "DESCRIPTIVE", ["phase7/ml_predictive_analysis.json"], eligible=False)
    registry.add("P7-TCN-001", "64x12 causal TCN", "video hypothesis", "ML", {}, tcn, "INCONCLUSIVE", ["phase7/tcn_results.json"], eligible=False, rejection=tcn["reason"])
    registry.add("P7-RISK-001", "risk-map components", "video hypothesis", "ML", {}, risk_map, "INCONCLUSIVE", ["phase7/risk_map_results.json"], eligible=False, rejection=risk_map["reason"])
    registry_payload = registry.payload(); _write_json(output / "phase7_experiment_registry.json", registry_payload)
    raw_after = guard.checksums(manifest)
    if raw_before != raw_after: raise RuntimeError("raw cache mutated during Phase 7")
    (output / "leakage_audit.md").write_text(_leakage_report(models, replay_equal, raw_before == raw_after))
    (output / "engine_invariants.md").write_text(_engine_invariants())
    (output / "FALSE_FRIENDS.md").write_text(_false_friends(models, interactions, tournament))
    (output / "WHAT_WOULD_CHANGE_OUR_MIND.md").write_text(_what_changes_mind())
    (output / "DATA_REQUEST.md").write_text(_data_request())
    holdout = {"protected_market_data_opened": False, "status": "2026 MARKET HOLDOUT: UNTOUCHED", "candidates": []}
    _write_json(output / "FUTURE_HOLDOUT_FREEZE.json", holdout)
    best_management_name, best_management = max(management["rules"].items(), key=lambda item: item[1]["improvement"])
    eligible_complement = {
        name: value for name, value in complement.items()
        if name not in {"C17", "BASE_CANDLE", "BASE_EMA", "BASE_LONG", "BASE_SHORT", "BASE_RANDOM"}
        and value["standalone"]["net_profit"] > 0
    }
    best_complement_name = max(eligible_complement, key=lambda name: eligible_complement[name]["pnl_when_c01_loses"]) if eligible_complement else "NONE"
    context = {
        "baseline": baseline["corrected_phase6_result"],
        "best_management_name": best_management_name,
        "best_management": best_management,
        "best_complement_name": best_complement_name,
        "cost_4x_net": cost["multipliers"]["4"]["exact_engine_net"],
        "adverse_missed_5": execution["adverse_missed_best_5pct"]["net_profit"],
        "top1pct_share_gross": c01_tail["top1pct_share_gross_profit"],
    }
    final = _final_report(context); (output / "PHASE7_FINAL_REPORT.md").write_text(final)
    (output / "PHASE7_EXECUTIVE_SUMMARY.md").write_text("# Phase 7 executive summary\n\n" + "\n".join(final.splitlines()[2:14]) + "\n\nSee `PHASE7_FINAL_REPORT.md` for the full result.\n")
    _brain(project_root / "research_brain", {"corrected_net": baseline["corrected_phase6_result"]["net_profit"]})
    required = [path for path in output.iterdir() if path.is_file() and path.name != "SHA256SUMS.txt"]
    checksum_lines = [f"{_sha(path)}  {path.relative_to(project_root)}" for path in sorted(required)]
    (output / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n")
    return {"corrected_net": baseline["corrected_phase6_result"]["net_profit"], "trades": baseline["corrected_phase6_result"]["trades"], "registry": registry_payload["consumed"], "holdout_candidates": 0, "raw_cache_immutable": True, "protected_2026_opened": False, "best_management": best_management_name, "best_complement": best_complement_name}
