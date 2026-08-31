from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


def _period_extreme(series: pd.Series) -> dict:
    if series.empty:
        return {"period": None, "net_profit": 0.0}
    key = series.idxmin()
    return {"period": str(key), "net_profit": round(float(series.loc[key]), 2)}


def _run_audit(frame: pd.DataFrame, accepted_sessions: int, point_value: float, event_days: set[str]) -> dict:
    if frame.empty:
        return {"trades": 0, "exposure_fraction_nominal_rth": 0.0}
    chosen = frame.copy(); chosen["entry_ts"] = pd.to_datetime(chosen.entry_ts, utc=True); chosen["date"] = chosen.entry_ts.dt.date.astype(str)
    naive_entry = chosen.entry_ts.dt.tz_localize(None)
    chosen["month"] = naive_entry.dt.to_period("M"); chosen["quarter"] = naive_entry.dt.to_period("Q")
    chosen["week"] = naive_entry.dt.to_period("W-FRI"); chosen["year"] = chosen.entry_ts.dt.year
    wins = chosen[chosen.net_pnl > 0].net_pnl; losses = chosen[chosen.net_pnl < 0].net_pnl
    ordered = chosen.sort_values("entry_ts"); equity = 100_000 + ordered.net_pnl.cumsum(); drawdown_dollars = equity - equity.cummax()
    by_day = chosen.groupby("date").net_pnl.sum(); by_week = chosen.groupby("week").net_pnl.sum(); by_month = chosen.groupby("month").net_pnl.sum(); by_year = chosen.groupby("year").net_pnl.sum()
    rolling_6 = by_month.rolling(6).sum().dropna(); rolling_12 = by_month.rolling(12).sum().dropna()
    net = float(chosen.net_pnl.sum()); best_count = max(1, math.ceil(len(chosen) * .01)); sorted_pnl = chosen.net_pnl.sort_values()
    extra_open_friction = chosen.contracts * point_value * .25 * 3  # extra spread tick plus one extra slippage tick per side
    event_mask = chosen.date.isin(event_days); open_mask = chosen.entry_ts.dt.tz_convert("America/New_York").dt.time <= pd.Timestamp("10:00").time()
    return {
        "trades": len(chosen), "exposure_minutes": round(float(chosen.duration_minutes.sum()), 2),
        "exposure_fraction_nominal_rth": round(float(chosen.duration_minutes.sum() / (accepted_sessions * 390)), 6) if accepted_sessions else 0,
        "turnover_contracts": int(chosen.contracts.sum()), "average_cost_per_trade": round(float(chosen.total_costs.mean()), 4),
        "gross_pnl": round(float(chosen.gross_pnl.sum()), 2), "net_profit": round(net, 2),
        "average_win": round(float(wins.mean()), 2) if len(wins) else 0, "average_loss": round(float(losses.mean()), 2) if len(losses) else 0,
        "payoff_ratio": round(float(wins.mean() / abs(losses.mean())), 4) if len(wins) and len(losses) else None,
        "max_drawdown_dollars": round(float(drawdown_dollars.min()), 2),
        "recovery_factor": round(net / abs(float(drawdown_dollars.min())), 4) if float(drawdown_dollars.min()) < 0 else None,
        "cagr_fixed_contract_audit": round(float(((100_000 + net) / 100_000) ** (1 / 8) - 1), 6) if 100_000 + net > 0 else None,
        "worst_day": _period_extreme(by_day), "worst_week": _period_extreme(by_week), "worst_month": _period_extreme(by_month), "worst_year": _period_extreme(by_year),
        "rolling_6m_worst": _period_extreme(rolling_6), "rolling_12m_worst": _period_extreme(rolling_12),
        "by_quarter": {str(key): round(float(value), 2) for key, value in chosen.groupby("quarter").net_pnl.sum().items()},
        "long_short": {side: {"trades": len(group), "net_profit": round(float(group.net_pnl.sum()), 2), "win_rate": round(float((group.net_pnl > 0).mean()), 6)} for side, group in chosen.groupby("side")},
        "leave_one_year_out": {str(year): round(net - float(value), 2) for year, value in by_year.items()},
        "best_1pct_contribution": round(float(sorted_pnl.tail(best_count).sum()), 2), "worst_1pct_contribution": round(float(sorted_pnl.head(best_count).sum()), 2),
        "event_days": {"trades": int(event_mask.sum()), "net_profit": round(float(chosen.loc[event_mask, "net_pnl"].sum()), 2),
                       "non_event_net_profit": round(float(chosen.loc[~event_mask, "net_pnl"].sum()), 2)},
        "spread_expansion": {"open_or_before_1000_net": round(float(chosen.net_pnl.sum() - extra_open_friction.where(open_mask, 0).sum()), 2),
                             "open_and_event_net": round(float(chosen.net_pnl.sum() - extra_open_friction.where(open_mask | event_mask, 0).sum()), 2),
                             "assumption": "one extra spread tick plus one extra slippage tick per side on affected entries"},
    }


def build_supplemental(root: Path = Path("data")) -> dict:
    results = json.loads((root / "research/phase5-results.json").read_text())
    trades = pd.read_parquet(root / "research/phase5-trades.parquet")
    features = pd.read_parquet(root / "research/phase5-features.parquet")
    event_rows = features[(features.strategy == "C01") & (features.name == "scheduled_macro_event")]
    event_days = set(event_rows.loc[event_rows.value.astype(str).str.lower().isin({"true", "1", "1.0"}), "date"].astype(str))
    audits = {}
    for run_key, frame in trades.groupby("run_key"):
        summary = results["summaries"][run_key]; point_value = 20 if run_key.startswith("NQ:") else 2
        audits[run_key] = _run_audit(frame, summary["accepted_sessions"], point_value, event_days)
    for run_key, summary in results["summaries"].items():
        audits.setdefault(run_key, _run_audit(pd.DataFrame(), summary["accepted_sessions"], 20 if run_key.startswith("NQ:") else 2, event_days))

    eligible = [candidate for candidate, disposition in results["candidate_dispositions"].items() if "gates" in disposition]
    walk_forward = []
    for year in range(2022, 2026):
        scores = {}
        for candidate in eligible:
            summary = results["summaries"].get(f"NQ:{candidate}:matched_4R:fixed1", {})
            scores[candidate] = sum(float(value) for y, value in summary.get("by_year", {}).items() if int(y) < year)
        winner = max(scores, key=scores.get)
        evaluation = results["summaries"][f"NQ:{winner}:matched_4R:fixed1"]["by_year"].get(str(year), 0)
        walk_forward.append({"evaluation_year": year, "selected_from_prior_years": winner, "prior_cumulative_net": round(scores[winner], 2), "evaluation_net_profit": evaluation})
    result = {"schema_version": 1, "selection_eligible": False, "purpose": "post-selection descriptive audit views",
              "run_audits": audits, "expanding_walk_forward": walk_forward,
              "walk_forward_note": "Ranks only frozen candidates using cumulative earlier-year fixed-contract net; it is an audit view, not a replacement selection rule."}
    (root / "research/phase5-supplemental.json").write_text(json.dumps(result, indent=2, default=str))
    return result
