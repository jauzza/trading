from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

from .analytics import adjusted_p_values, stationary_bootstrap_mean

FEATURES = [
    "opening_range_size", "overnight_opening_alignment", "distance_to_overnight_high", "distance_to_overnight_low",
    "distance_to_prior_day_high", "distance_to_prior_day_low", "prior_day_regime", "lagged_vix_regime",
    "scheduled_macro_event", "time_to_scheduled_event_minutes", "ten_am_event", "overnight_gap",
    "same_time_relative_volume", "lag_safe_vwap_slope", "holiday_adjacency", "weekday",
    "options_expiration", "month_quarter_end", "lagged_large_prior_move", "vvg_regime_score",
]
PERIODS = {"development": (2018, 2021), "validation": (2022, 2023), "historical_evaluation": (2024, 2025)}


def _wide(frame: pd.DataFrame, strategy: str) -> pd.DataFrame:
    chosen = frame[frame.strategy == strategy].copy()
    values = chosen.pivot_table(index=["date", "entry_ts"], columns="name", values="value", aggfunc="first")
    outcomes = chosen.groupby(["date", "entry_ts"])[["net_r", "net_pnl", "win", "stop_out", "mae_points", "mfe_points", "tail_winner", "drawdown_contribution"]].first()
    wide = values.join(outcomes).reset_index(); wide["year"] = pd.to_datetime(wide.date).dt.year
    for name in FEATURES:
        if name not in wide: wide[name] = np.nan
        if wide[name].dtype == object: wide[name] = wide[name].map({True: 1.0, False: 0.0, "true": 1.0, "false": 0.0}).astype(float)
    return wide


def _period(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    start, end = PERIODS[name]
    return frame[(frame.year >= start) & (frame.year <= end)]


def _bucket_edges(development: pd.Series) -> list[float]:
    values = development.dropna().astype(float)
    if values.nunique() <= 2: return sorted(values.unique().tolist())
    edges = np.unique(np.quantile(values, [0, .25, .5, .75, 1])).tolist()
    edges[0], edges[-1] = -np.inf, np.inf
    return edges


def _bucket_summary(frame: pd.DataFrame, feature: str, edges: list[float]) -> list[dict]:
    values = frame[feature].astype(float)
    if len(edges) <= 2:
        labels = values.astype("Int64").astype(str)
    else:
        labels = pd.cut(values, edges, include_lowest=True, duplicates="drop").astype(str)
    rows = []
    for bucket, group in frame.assign(_bucket=labels).groupby("_bucket", observed=True):
        rows.append({"bucket": bucket, "sessions": len(group), "coverage": round(len(group)/len(frame), 6) if len(frame) else 0,
                     "mean_net_r": round(float(group.net_r.mean()), 6), "win_rate": round(float(group.win.mean()), 6),
                     "stop_rate": round(float(group.stop_out.mean()), 6), "mean_mae": round(float(group.mae_points.mean()), 4),
                     "mean_mfe": round(float(group.mfe_points.mean()), 4), "tail_winner_rate": round(float(group.tail_winner.mean()), 6),
                     "drawdown_contribution": round(float(group.drawdown_contribution.sum()), 2)})
    return rows


def _models(wide: pd.DataFrame) -> dict:
    development = _period(wide, "development")
    columns = [name for name in FEATURES if development[name].notna().mean() >= .5 and development[name].nunique(dropna=True) > 1]
    x_train = development[columns]; y_win = development.win.astype(int); y_r = development.net_r.astype(float)
    logistic = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=.25, max_iter=2000, random_state=5701))
    ridge = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=10.0))
    tree = make_pipeline(SimpleImputer(strategy="median"), DecisionTreeClassifier(max_depth=2, min_samples_leaf=40, random_state=5702))
    logistic.fit(x_train, y_win); ridge.fit(x_train, y_r); tree.fit(x_train, y_win)
    output = {"features": columns, "training_period": "2018-2021", "models": {}}
    for period in PERIODS:
        sample = _period(wide, period); x = sample[columns]; actual = sample.win.astype(int)
        probability = logistic.predict_proba(x)[:, 1]; prediction = ridge.predict(x); tree_probability = tree.predict_proba(x)[:, 1]
        output["models"][period] = {
            "sessions": len(sample), "logistic_brier": round(float(brier_score_loss(actual, probability)), 6),
            "logistic_auc": round(float(roc_auc_score(actual, probability)), 6) if actual.nunique() > 1 else None,
            "ridge_r_correlation": round(float(np.corrcoef(prediction, sample.net_r)[0, 1]), 6) if len(sample) > 2 else None,
            "tree_brier": round(float(brier_score_loss(actual, tree_probability)), 6),
            "mean_predicted_win_probability": round(float(probability.mean()), 6), "actual_win_rate": round(float(actual.mean()), 6),
        }
    fitted_tree = tree.named_steps["decisiontreeclassifier"]
    output["tree_rules"] = export_text(fitted_tree, feature_names=columns)
    output["classification"] = "descriptive_small_models_only"
    return output


def _keep_mask(frame: pd.DataFrame, rule: dict) -> pd.Series:
    if rule["keep"] == "equals": return frame[rule["feature"]] == rule["threshold"]
    if rule["keep"] == "at_or_above": return frame[rule["feature"]] >= rule["threshold"]
    return frame[rule["feature"]] < rule["threshold"]


def analyze(root: Path = Path("data"), samples: int = 50_000) -> dict:
    frame = pd.read_parquet(root / "research/phase5-features.parquet")
    wide = _wide(frame, "C01"); development = _period(wide, "development")
    descriptive = {}; filters = []
    for feature in FEATURES:
        coverage = float(development[feature].notna().mean()) if len(development) else 0
        if coverage < .5 or development[feature].nunique(dropna=True) < 2:
            descriptive[feature] = {"coverage": round(coverage, 6), "status": "insufficient_coverage"}; continue
        edges = _bucket_edges(development[feature]); by_period = {name: _bucket_summary(_period(wide, name), feature, edges) for name in PERIODS}
        unique = sorted(development[feature].dropna().unique().tolist())
        if len(unique) <= 2:
            means = {value: development.loc[development[feature] == value, "net_r"].mean() for value in unique}
            selected_value = max(means, key=means.get)
            threshold, keep, effect = float(selected_value), "equals", float(max(means.values())-min(means.values()))
            upper = means.get(unique[-1], np.nan); lower = means.get(unique[0], np.nan)
        else:
            median = float(development[feature].median())
            upper = development[development[feature] >= median].net_r.mean(); lower = development[development[feature] < median].net_r.mean()
            threshold, keep, effect = median, "at_or_above" if upper >= lower else "below", float(abs(upper-lower))
        filters.append({"feature": feature, "threshold": threshold, "keep": keep, "development_effect": effect})
        descriptive[feature] = {"coverage": round(coverage, 6), "development_edges": edges, "buckets": by_period, "development_high_minus_low_r": round(float(upper-lower), 6)}
    filters.sort(key=lambda row: row["development_effect"], reverse=True)
    raw_p = []
    for index, candidate in enumerate(filters):
        keep = _keep_mask(development, candidate)
        difference = np.where(keep.fillna(False), development.net_r, 0.0) - development.net_r.to_numpy()
        boot = stationary_bootstrap_mean(difference, samples, 10, 5800+index)
        candidate["development_filter_bootstrap"] = boot
        raw_p.append(min(1.0, 2*min(boot["p_value"], 1-boot["p_value"]+boot["minimum_p_value"])))
    bh = adjusted_p_values(raw_p, "bh"); by = adjusted_p_values(raw_p, "by")
    for index, (row, raw, bhp, byp) in enumerate(zip(filters, raw_p, bh, by)):
        row.update({"raw_two_sided_p": round(raw, 8), "bh_adjusted_p": round(bhp, 8), "by_adjusted_p": round(byp, 8)})
        row["periods"] = {}
        for period_index, name in enumerate(PERIODS):
            sample = _period(wide, name); period_keep = _keep_mask(sample, row).fillna(False)
            filtered = np.where(period_keep, sample.net_r, 0.0); period_difference = filtered-sample.net_r.to_numpy()
            row["periods"][name] = {"sessions": len(sample), "kept": int(period_keep.sum()), "removed": int((~period_keep).sum()),
                "unfiltered_net_r": round(float(sample.net_r.sum()), 6), "filtered_net_r": round(float(filtered.sum()), 6),
                "skipped_winners": int(((~period_keep)&(sample.net_r>0)).sum()), "skipped_winner_r": round(float(sample.loc[(~period_keep)&(sample.net_r>0),"net_r"].sum()), 6),
                "paired_effect_mean_r": round(float(period_difference.mean()), 6),
                "paired_ci": stationary_bootstrap_mean(period_difference, samples, 10, 6100+100*index+period_index)}
        row["survives_all_periods"] = all(row["periods"][name]["paired_effect_mean_r"] > 0 for name in PERIODS)
    selected = next((row for row in filters if row["survives_all_periods"]), None)
    proposed = None
    if selected:
        proposed = {key: value for key, value in selected.items() if key != "development_filter_bootstrap"}
        proposed["provenance"] = "learned_on_development_2018_2021"
        proposed["plain_english_rule"] = f"Take C01 only when {selected['feature']} is {selected['keep'].replace('_',' ')} {selected['threshold']:.4g}."
        proposed["known_at_entry"] = "C01 actual entry; source value is strictly prior/completed-bar data"
        proposed["periods"] = selected["periods"]
        proposed["cost_sensitivity_note"] = "A filter changes opportunity count; retained trades use the identical baseline-cost C01 outcomes."
        proposed["tail_concentration_note"] = "Reported with skipped-winner opportunity cost; no composite strategy was formed."
    leading = filters[0] if filters else None
    result = {"schema_version": 1, "strategy": "C01", "sessions": len(wide), "features": descriptive,
              "small_models": _models(wide), "candidate_filters": filters, "proposed_filter": proposed,
              "leading_rejected_filter": leading if proposed is None else None,
              "conclusion": "No good/bad-day filter survives" if proposed is None else "One development-learned filter remains exploratory after paired later-period checks"}
    (root / "research/phase5-good-bad-day.json").write_text(json.dumps(result, indent=2, default=str))
    return result
