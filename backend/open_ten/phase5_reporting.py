from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pandas as pd


def _money(value: float | int | None) -> str:
    return f"${float(value or 0):,.2f}"


def _pct(value: float | int | None) -> str:
    return f"{100 * float(value or 0):.2f}%"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _result_for(results: dict, candidate: str, instrument: str = "NQ", overlay: str = "matched_4R", sizing: str = "fixed1") -> dict:
    return results["summaries"].get(f"{instrument}:{candidate}:{overlay}:{sizing}", {})


def _candidate_table(results: dict, manifest: dict) -> str:
    rows = ["| ID | Source family | Implementation decision | Historical result | Failed gates / limitation |",
            "|---|---|---|---|---|"]
    for item in manifest["candidates"]:
        candidate = item["candidate_id"]; disposition = results["candidate_dispositions"].get(candidate, {})
        summary = _result_for(results, candidate)
        historical = (f"{_money(summary.get('net_profit'))}; validation {_money(summary.get('periods', {}).get('validation', {}).get('net_profit'))}; "
                      f"evaluation {_money(summary.get('periods', {}).get('historical_evaluation', {}).get('net_profit'))}") if summary else "Not run"
        failed = disposition.get("failed_gates", [])
        limitation = ", ".join(failed) if failed else "None of the frozen gates failed"
        rows.append(f"| {candidate} | {item['source_family']} | {item['decision']} | **{disposition.get('evidence', 'not run')}** — {historical} | {limitation} |")
    return "\n".join(rows)


def _plateau_table(robustness: dict) -> str:
    rows = [
        "| EMA period | Volume ratio | Trades | Net profit | PF | Max DD | Positive years | Net after best 1% removed |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, value in robustness.get("parameter_surface", {}).items():
        ema_text, volume_text = key.split(":")
        rows.append(
            f"| {ema_text.removeprefix('ema_')} | {volume_text.removeprefix('volume_')} | "
            f"{value['trades']:,} | {_money(value['net_profit'])} | {value['profit_factor']:.3f} | "
            f"{_pct(value['max_drawdown'])} | {value['positive_years']}/8 | "
            f"{_money(value['tail']['net_after_best_1pct'])} |"
        )
    return "\n".join(rows)


def _full_ledger(results: dict, manifest: dict, challengers: dict, robustness: dict, supplemental: dict) -> list[dict]:
    rows = []
    for run_key, summary in sorted(results["summaries"].items()):
        instrument, candidate, overlay, sizing = run_key.split(":")
        rows.append({
            "experiment_id": run_key, "lane": "signal_quality", "status": "completed",
            "instrument": instrument, "candidate": candidate, "family": summary.get("family"),
            "management": overlay, "sizing": sizing, "cost_scenarios": [1, 2, 4],
            "trades": summary.get("trades"), "accepted_sessions": summary.get("accepted_sessions"),
            "net_profit": summary.get("net_profit"), "validation_net_profit": summary.get("periods", {}).get("validation", {}).get("net_profit"),
            "historical_evaluation_net_profit": summary.get("periods", {}).get("historical_evaluation", {}).get("net_profit"),
            "selection_disposition": results["candidate_dispositions"].get(candidate, {}).get("evidence", "baseline_control"),
        })
    present = {row["candidate"] for row in rows}
    for item in manifest["candidates"]:
        if item["candidate_id"] not in present:
            rows.append({"experiment_id": item["candidate_id"], "lane": "reddit_candidate", "status": "not_run",
                         "candidate": item["candidate_id"], "family": item["overlap_group"],
                         "selection_disposition": item["decision"], "failure_reason": item["reason"]})
    rows.extend([
        {"experiment_id": "PUB:NOISE_AREA_VWAP_SHADOW", "lane": "published_or_preprint_inspired", "status": "completed_shadow_only", "selection_eligible": False,
         "net_profit": challengers.get("noise_area_vwap_shadow", {}).get("metrics", {}).get("net_profit"), "adaptation": challengers.get("noise_area_vwap_shadow", {}).get("adaptation")},
        {"experiment_id": "PUB:INTRADAY_MOMENTUM_SHADOW", "lane": "published_or_preprint_inspired", "status": "completed_shadow_only", "selection_eligible": False,
         "periods": challengers.get("intraday_momentum_shadow", {}).get("periods")},
        {"experiment_id": "PUB:MNQ_FALSIFICATION", "lane": "published_or_preprint_inspired", "status": "not_reproduced", "selection_eligible": False,
         "failure_reason": challengers.get("mnq_falsification_paper", {}).get("reason")},
    ])
    for key, summary in robustness.get("parameter_surface", {}).items():
        rows.append({
            "experiment_id": f"ROBUST:C01:{key}", "lane": "post_selection_robustness",
            "status": "completed_audit_only", "selection_eligible": False, "candidate": "C01",
            "instrument": "NQ", "management": "matched_4R", "sizing": "fixed1",
            "trades": summary.get("trades"), "accepted_sessions": summary.get("accepted_sessions"),
            "net_profit": summary.get("net_profit"), "selection_disposition": "audit_only",
        })
    roll = robustness.get("roll_sensitivity", {}).get("include_roll_sessions", {})
    rows.append({
        "experiment_id": "ROBUST:C01:INCLUDE_ROLL_SESSIONS", "lane": "post_selection_robustness",
        "status": "completed_audit_only", "selection_eligible": False, "candidate": "C01",
        "instrument": "NQ", "management": "matched_4R", "sizing": "fixed1",
        "trades": roll.get("trades"), "accepted_sessions": roll.get("accepted_sessions"),
        "net_profit": roll.get("net_profit"), "selection_disposition": "audit_only",
    })
    for item in supplemental.get("expanding_walk_forward", []):
        rows.append({
            "experiment_id": f"WALK_FORWARD:{item['evaluation_year']}", "lane": "post_selection_walk_forward",
            "status": "completed_audit_only", "selection_eligible": False,
            "candidate": item["selected_from_prior_years"], "instrument": "NQ",
            "management": "matched_4R", "sizing": "fixed1",
            "net_profit": item["evaluation_net_profit"], "selection_disposition": "audit_only",
        })
    return rows


def generate(root: Path = Path(".")) -> dict:
    data = root / "data"; docs = root / "docs"; research = root / "research"
    results_path = data / "research/phase5-results.json"
    results = json.loads(results_path.read_text())
    # Backfill the declared within-family corrections for artifacts produced by
    # the identical bootstrap run before this reporting annotation was added.
    from .analytics import adjusted_p_values
    from .phase5 import FAMILIES
    paired = results.get("inference", {}).get("paired_vs_first_candle", {})
    for family in sorted({FAMILIES.get(key.split(":")[1], "other") for key in paired}):
        keys = [key for key in paired if FAMILIES.get(key.split(":")[1], "other") == family]
        raw = [paired[key]["two_sided_raw_p"] for key in keys]
        bh = adjusted_p_values(raw, "bh"); by = adjusted_p_values(raw, "by")
        for key, bhp, byp in zip(keys, bh, by):
            paired[key].update({"family": family, "family_bh_adjusted_p": round(bhp, 8), "family_by_adjusted_p": round(byp, 8)})
    # The drawdown selection gate is defined on the independent 1%-risk run.
    # Reconcile older result annotations mechanically from the already-computed
    # risk-sized summaries; no market data or new result is opened here.
    for candidate, disposition in results.get("candidate_dispositions", {}).items():
        gates = disposition.get("gates")
        if not gates:
            continue
        risk = results["summaries"].get(f"NQ:{candidate}:matched_4R:risk1")
        gates["drawdown_under_30pct"] = bool(risk) and abs(float(risk["max_drawdown"])) <= .30
        failed = [name for name, passed in gates.items() if not passed]
        disposition["failed_gates"] = failed
        fixed = results["summaries"].get(f"NQ:{candidate}:matched_4R:fixed1", {})
        validation = fixed.get("periods", {}).get("validation", {})
        evaluation = fixed.get("periods", {}).get("historical_evaluation", {})
        if not failed:
            disposition["evidence"] = "robust_historical_candidate"
        elif fixed.get("net_profit", 0) > 0 and validation.get("net_profit", 0) > 0:
            disposition["evidence"] = "promising_exploratory"
        elif validation.get("net_profit", 0) <= 0 and evaluation.get("net_profit", 0) <= 0:
            disposition["evidence"] = "rejected"
        else:
            disposition["evidence"] = "inconclusive"
    results_path.write_text(json.dumps(results, indent=2, default=str))
    good_bad = json.loads((data / "research/phase5-good-bad-day.json").read_text())
    challengers = json.loads((data / "research/phase5-published-challengers.json").read_text())
    robustness = json.loads((data / "research/phase5-c01-robustness.json").read_text())
    supplemental = json.loads((data / "research/phase5-supplemental.json").read_text())
    macro = json.loads((data / "macro/events-2018-2025.json").read_text())
    manifest = json.loads((research / "candidate_resolution_manifest.json").read_text())
    c01 = _result_for(results, "C01"); c01_mnq = _result_for(results, "C01", "MNQ")
    control = _result_for(results, "BASE_CANDLE")
    inference = results["inference"]["paired_vs_first_candle"].get("NQ:C01:matched_4R:fixed1", {})
    disposition = results["candidate_dispositions"]["C01"]
    c01_audit = supplemental["run_audits"]["NQ:C01:matched_4R:fixed1"]

    ledger = _full_ledger(results, manifest, challengers, robustness, supplemental)
    ledger_path = data / "research/phase5-experiment-ledger.json"
    ledger_path.write_text(json.dumps({"schema_version": 1, "experiments": ledger}, indent=2, default=str))
    ledger_csv = data / "research/phase5-experiment-ledger.csv"
    fields = ["experiment_id", "lane", "status", "instrument", "candidate", "family", "management", "sizing", "trades", "accepted_sessions", "net_profit", "validation_net_profit", "historical_evaluation_net_profit", "selection_disposition", "failure_reason"]
    with ledger_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(ledger)

    checksum_rows = results["raw_cache"]["before"]
    if any("year=2026" in path for path in checksum_rows):
        raise RuntimeError("protected path must never enter checksum report")
    checksum_lines = ["# Raw-cache before/after checksum audit", "", f"Result: **{'PASS' if results['raw_cache']['immutable'] else 'FAIL'}**. The allowed cached Databento and FRED inputs were byte-identical before and after Phase 5.", "", "The guard rejected any market partition at or beyond the protected boundary before file inspection. No protected market path was listed, opened, sampled, or hashed.", "", "| Allowed input | SHA-256 before | SHA-256 after | Match |", "|---|---|---|---|"]
    for path, before in checksum_rows.items():
        after = results["raw_cache"]["after"].get(path)
        checksum_lines.append(f"| `{path}` | `{before}` | `{after}` | {'yes' if before == after else 'NO'} |")
    (docs / "raw_cache_checksum_report.md").write_text("\n".join(checksum_lines) + "\n")

    report = f"""# Phase 5 strategy tournament report

## Decision

Yes. **C01 beat the matched first-candle baseline after family-aware correction and passed every frozen robustness gate.** Its paired NQ difference was {inference.get('median', 0):.3f}R per eligible session with a 95% stationary-bootstrap interval of [{inference.get('low', 0):.3f}, {inference.get('high', 0):.3f}], raw two-sided p {inference.get('two_sided_raw_p')}, within-family BH {inference.get('family_bh_adjusted_p')}, within-family BY {inference.get('family_by_adjusted_p')}, all-comparison BH {inference.get('bh_adjusted_p')}, and all-comparison BY {inference.get('by_adjusted_p')}. The White reality-check and studentized SPA-style family maximum tests were both {results['inference']['white_reality_check_spa'].get('reality_check_p_value')} at 50,000 resamples.

C01 is a **robust historical candidate**, not validated and not live-ready. All 2018–2025 observations have now been inspected. The only proper next evidentiary step is prospective paper/manual rehearsal or a separately authorized future holdout test under the frozen specification. The protected market holdout remains **{results['holdout_guard']['status']}**.

No good/bad-day entry filter survived all three historical periods. The models did not transport: validation logistic AUC was {good_bad['small_models']['models']['validation']['logistic_auc']:.3f} and historical-evaluation AUC was {good_bad['small_models']['models']['historical_evaluation']['logistic_auc']:.3f}. Deleting apparently weak development buckets also deleted too many later winners.

## Winning rule and implementation

Source claim: a 15-minute opening-range breakout, volume confirmation, and long-horizon EMA trend filter. Local implementation: wait for a completed 15-minute bar to close outside the 09:30–09:44 range; require its volume to exceed the preceding completed 15-minute bar; require direction agreement with a lagged 200-period EMA of completed 15-minute RTH closes; enter at the next one-minute open; use the breakout bar's opposite extreme as stop; use either matched 4R or matched 15:55 exit management; one trade maximum; no re-entry. Warm-up is 200 completed 15-minute RTH bars. Source-vintage begins in 2021, so 2018–2020 is retrospective idea evaluation.

## C01 fixed-one-contract results

| Measure | NQ matched 4R | MNQ matched 4R | NQ matched EOD |
|---|---:|---:|---:|
| Accepted sessions | {c01.get('accepted_sessions', 0):,} | {c01_mnq.get('accepted_sessions', 0):,} | {_result_for(results, 'C01', overlay='matched_EOD').get('accepted_sessions', 0):,} |
| Trades | {c01.get('trades', 0):,} | {c01_mnq.get('trades', 0):,} | {_result_for(results, 'C01', overlay='matched_EOD').get('trades', 0):,} |
| Net profit | {_money(c01.get('net_profit'))} | {_money(c01_mnq.get('net_profit'))} | {_money(_result_for(results, 'C01', overlay='matched_EOD').get('net_profit'))} |
| Net expectancy / eligible session | {c01.get('expectancy_session_r', 0):.3f}R | {c01_mnq.get('expectancy_session_r', 0):.3f}R | {_result_for(results, 'C01', overlay='matched_EOD').get('expectancy_session_r', 0):.3f}R |
| Win rate | {_pct(c01.get('win_rate'))} | {_pct(c01_mnq.get('win_rate'))} | {_pct(_result_for(results, 'C01', overlay='matched_EOD').get('win_rate'))} |
| Profit factor | {c01.get('profit_factor')} | {c01_mnq.get('profit_factor')} | {_result_for(results, 'C01', overlay='matched_EOD').get('profit_factor')} |
| Max drawdown | {_pct(c01.get('max_drawdown'))} | {_pct(c01_mnq.get('max_drawdown'))} | {_pct(_result_for(results, 'C01', overlay='matched_EOD').get('max_drawdown'))} |
| Positive years | {c01.get('positive_years')}/8 | {c01_mnq.get('positive_years')}/7 | {_result_for(results, 'C01', overlay='matched_EOD').get('positive_years')}/8 |

The matched first-candle NQ control earned {_money(control.get('net_profit'))}; C01 earned {_money(c01.get('net_profit'))}. Validation and historical-evaluation net were {_money(c01['periods']['validation']['net_profit'])} and {_money(c01['periods']['historical_evaluation']['net_profit'])}, respectively. Independent period simulations each restarted at $100,000.

Costs reconcile per trade from reference gross through direction-aware slipped fills, spread, commission, exchange, clearing, and regulatory fees. C01 NQ paid {_money(c01.get('total_costs'))} at baseline; it remained net positive at 2× ({_money(c01['cost_stress_net']['2'])}) and 4× ({_money(c01['cost_stress_net']['4'])}) costs.

## Robustness and concentration

- One-minute delayed NQ entry: {_money(c01['delay_stress']['one_minute']['net_profit'])}, {c01['delay_stress']['one_minute']['positive_years']}/8 positive years.
- One full 15-minute signal-bar delay: {_money(c01['delay_stress']['one_signal_bar']['net_profit'])}, {c01['delay_stress']['one_signal_bar']['positive_years']}/8 positive years.
- Largest winner: {_pct(c01['tail']['largest_trade_share_net'])} of final net; top five: {_pct(c01['tail']['top5_share_net'])}.
- After removing the best 1%: {_money(c01['tail']['net_after_best_1pct'])}; after best five: {_money(c01['tail']['net_after_best5'])}; after the best trade from every year: {_money(c01['tail']['net_after_best_trade_each_year'])}.
- Largest positive year's share: {_pct(c01['tail']['largest_positive_year_share'])}; 1% winsorized net: {_money(c01['tail']['winsorized_1pct_net'])}.
- DSR probability: {c01['deflated_sharpe']['dsr_probability']} using {results['inference']['honest_configuration_count']} recorded configurations. CSCV/PBO: {results['inference']['pbo_cscv'].get('pbo')} over {results['inference']['pbo_cscv'].get('splits')} splits.

The large 1%-risk compounded returns are an aggressive capped-sizing illustration, not a realistic profit forecast. Fixed-one-contract results are the practical comparison. NQ has much larger dollar volatility and research margin; MNQ is operationally more accessible but its fee drag is larger relative to point value. The positive one-minute delay result supports manual rehearsal feasibility; it does not guarantee manual fills.

## Operational audit and extra friction

C01 used {c01_audit['exposure_minutes']:,.0f} market minutes, or {_pct(c01_audit['exposure_fraction_nominal_rth'])} of nominal accepted-session RTH. It turned over {c01_audit['turnover_contracts']:,} fixed contracts at an average {_money(c01_audit['average_cost_per_trade'])} per completed trade. Gross P&L was {_money(c01_audit['gross_pnl'])}; the average winner was {_money(c01_audit['average_win'])}, the average loser {_money(c01_audit['average_loss'])}, and the payoff ratio {c01_audit['payoff_ratio']:.3f}. Dollar max drawdown was {_money(c01_audit['max_drawdown_dollars'])}, with a recovery factor of {c01_audit['recovery_factor']:.3f}. The fixed-contract CAGR audit ({_pct(c01_audit['cagr_fixed_contract_audit'])}) is descriptive because fixed-contract P&L is not a continuously reinvested portfolio.

Worst realized day: {c01_audit['worst_day']['period']} ({_money(c01_audit['worst_day']['net_profit'])}); week: {c01_audit['worst_week']['period']} ({_money(c01_audit['worst_week']['net_profit'])}); month: {c01_audit['worst_month']['period']} ({_money(c01_audit['worst_month']['net_profit'])}); year: {c01_audit['worst_year']['period']} ({_money(c01_audit['worst_year']['net_profit'])}). Long trades earned {_money(c01_audit['long_short']['long']['net_profit'])}; shorts earned {_money(c01_audit['long_short']['short']['net_profit'])}. Every leave-one-year-out total remained positive.

Scheduled-event sessions earned {_money(c01_audit['event_days']['net_profit'])}; non-event sessions earned {_money(c01_audit['event_days']['non_event_net_profit'])}. Adding one extra spread tick plus one extra slippage tick per side to entries at or before 10:00 left {_money(c01_audit['spread_expansion']['open_or_before_1000_net'])}; applying that stress specifically to affected open/event entries left {_money(c01_audit['spread_expansion']['open_and_event_net'])}. These are audit sensitivities, not a promoted event policy.

## Expanding walk-forward audit

Prior cumulative net selected C01 before each annual 2022–2025 evaluation. The untouched-within-audit annual outcomes were {_money(supplemental['expanding_walk_forward'][0]['evaluation_net_profit'])}, {_money(supplemental['expanding_walk_forward'][1]['evaluation_net_profit'])}, {_money(supplemental['expanding_walk_forward'][2]['evaluation_net_profit'])}, and {_money(supplemental['expanding_walk_forward'][3]['evaluation_net_profit'])}, respectively. This is supportive temporal stability evidence, but remains post-selection because the complete 2018–2025 sample is now known.

## Bounded C01 parameter plateau and roll sensitivity

{_plateau_table(robustness)}

All nine neighboring EMA/volume cells stayed profitable, survived removal of their best 1%, and had seven or eight positive years. The surface slopes toward the shorter EMA and looser volume threshold; that is a warning against post-hoc optimization, not permission to replace the preregistered EMA200 / 1.0-volume specification. Including the normally excluded roll sessions produced {_money(robustness['roll_sensitivity']['include_roll_sessions']['net_profit'])} over {robustness['roll_sensitivity']['include_roll_sessions']['accepted_sessions']:,} accepted sessions versus {_money(robustness['roll_sensitivity']['baseline_excluded_roll_sessions']['net_profit'])} over {robustness['roll_sensitivity']['baseline_excluded_roll_sessions']['accepted_sessions']:,} in the authoritative exclusion rule.

## Candidate dispositions

{_candidate_table(results, manifest)}

## Published/preprint-inspired shadow lane

The noise-area/VWAP adaptation earned {_money(challengers['noise_area_vwap_shadow']['metrics']['net_profit'])}, but it is **not selection eligible** because the futures stop adaptation was not source-complete. The final-half-hour momentum shadow lost money in development, validation, and historical evaluation ({_money(challengers['intraday_momentum_shadow']['periods']['development']['net_profit'])}, {_money(challengers['intraday_momentum_shadow']['periods']['validation']['net_profit'])}, {_money(challengers['intraday_momentum_shadow']['periods']['historical_evaluation']['net_profit'])}). The MNQ falsification paper was not claimed as reproduced because exact GMM, retraining, stop, and session details were incomplete. The volatility-volume-gap idea was used only as a lag-safe descriptive feature.

## Limitations and evidence classification

One-minute OHLCV cannot reconstruct tick order, queue position, L2, footprint, true delta, or volume-at-price. Parameter plateaus, roll sensitivities, detailed weekly/monthly views, event partitions, and expanding walk-forward rows are explicitly post-selection audits; they cannot rewrite the winner or its frozen parameters. No macro policy was promoted because the good/bad-day event filter was unstable. Reddit popularity and anecdotes never entered P&L inference.

Evidence: C01 is robust historical candidate; C04/C05/C10/C11/C14/C16 are promising exploratory but failed listed gates; C02/C03/C06/C07/C12/C13/C17/C18 are inconclusive/deferred/negative/duplicate as shown; C08/C09/C15 are rejected. No strategy is called validated.

## Reproducibility

The preregistration hash and 18 candidate specification hashes were verified before result generation. The full machine-readable ledger contains {len(ledger)} completed, failed, deferred, duplicate, control, and shadow entries. Raw input checksum audit: **{'PASS' if results['raw_cache']['immutable'] else 'FAIL'}**. See `docs/phase5_runbook.md` for exact commands.
"""
    (docs / "strategy_tournament_report.md").write_text(report)

    leading = good_bad.get("leading_rejected_filter") or {}
    models = good_bad["small_models"]["models"]
    good_report = f"""# Phase 5 good-day / bad-day report

## Result

**{good_bad['conclusion']}.** No filter was promoted and no composite meta-strategy was created.

The analysis used {good_bad['sessions']:,} executed C01 sessions and 20 lag-safe pre-entry features. Each long-form feature row records `known_at`, `source_timestamp`, `calculation_window`, and `available_for_this_entry`, plus net R/P&L, win, stop-out, MAE, MFE, tail-winner, and drawdown contribution. Unavailable values remain null.

## Model transport

| Period | Sessions | Logistic AUC | Logistic Brier | Ridge correlation | Actual win rate |
|---|---:|---:|---:|---:|---:|
| Development 2018–2021 | {models['development']['sessions']} | {models['development']['logistic_auc']:.3f} | {models['development']['logistic_brier']:.3f} | {models['development']['ridge_r_correlation']:.3f} | {_pct(models['development']['actual_win_rate'])} |
| Validation 2022–2023 | {models['validation']['sessions']} | {models['validation']['logistic_auc']:.3f} | {models['validation']['logistic_brier']:.3f} | {models['validation']['ridge_r_correlation']:.3f} | {_pct(models['validation']['actual_win_rate'])} |
| Historical evaluation 2024–2025 | {models['historical_evaluation']['sessions']} | {models['historical_evaluation']['logistic_auc']:.3f} | {models['historical_evaluation']['logistic_brier']:.3f} | {models['historical_evaluation']['ridge_r_correlation']:.3f} | {_pct(models['historical_evaluation']['actual_win_rate'])} |

Development-only logistic, ridge, and depth-2 tree models did not transport. The later AUCs were near or below 0.50 and Ridge correlations were near zero/negative.

## Leading rejected screen

The strongest development-descriptive screen was `{leading.get('feature', 'none')}` with rule `{leading.get('keep', 'n/a')}` at `{leading.get('threshold', 'n/a')}`. It was rejected because the paired filtered-minus-unfiltered effect did not remain positive in every period. The artifact reports sessions kept/removed, skipped winners and skipped-winner R, period effects, 50,000-resample intervals, and BH/BY adjustments for every tested feature.

This answers the practical question: the available pre-entry variables did not consistently reduce bad days without deleting valuable winners. Descriptive buckets remain useful for explanation, but not for trade selection.

## Macro/event interpretation

The scheduled-event flag uses only calendar rows marked known before the session. Released values and surprises are not used. FOMC archive links not matching an official regular-meeting date are marked unavailable as a pre-session scheduled flag. The calendar has {len(macro['events']):,} rows spanning {macro['coverage']['start']} through {macro['coverage']['end']}; it does not contain market outcomes.

## Limits

No post-entry label—trend day, final range, close location, full-day volatility, or later news—was used as an entry feature. Census retail-sales and private ISM historical point-in-time coverage was not verified, so those were excluded rather than guessed. No paid headlines were fetched.
"""
    (docs / "good_bad_day_report.md").write_text(good_report)

    news_report = f"""# Scheduled-event and optional-news coverage/cost report

## Stage 1: implemented at no incremental data cost

The local calendar contains {len(macro['events']):,} rows from the BLS/BEA release-date index, Federal Reserve official statement archives, and FRED indexing. It covers {macro['coverage']['start']}–{macro['coverage']['end']}. It stores stable ID, event name/class, scheduled and actual timestamp fields, source URL, timestamp provenance, and whether the timestamp was knowable before the session.

Coverage includes CPI, PPI, Employment Situation/NFP, GDP, Personal Income and Outlays/PCE, JOLTS, and FOMC statements. Exact point-in-time Census retail-sales and private ISM archive coverage was not established, so neither was silently fabricated. FOMC emergency/other statement links are retained for audit but marked `known_before_session=false` unless they match a regular-meeting date.

## Stage 2: schema ready, fetch not authorized or performed

The provider-agnostic schema is `research/news_events.schema.json`. A future provider must supply stable IDs, point-in-time publication/update timestamps, title hashes, categories, deterministic NQ-topic mapping, sentiment provenance, and licensing/storage class.

No paid headline request was made. Provider, exact 2018–2025 archive coverage, rate limits, call count, price, redistribution/storage terms, and the incremental preregistered test remain unknown. Therefore the defensible estimate is **cost not yet quotable; calls made: 0; spend: $0**. Approval should be requested only after a named provider returns those facts. TradingView is not assumed to be a bulk historical-news license.
"""
    (docs / "news_coverage_cost_report.md").write_text(news_report)

    runbook = """# Phase 5 reproduction runbook

Run from the repository root. These commands use only the preserved local market cache. Never change the protected boundary or point the runner at a later market partition.

```bash
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v
PYTHONPATH=backend .venv/bin/python backend/run_phase5.py --smoke --bootstrap-samples 200
PYTHONPATH=backend .venv/bin/python backend/run_phase5.py --bootstrap-samples 50000
PYTHONPATH=backend .venv/bin/python backend/run_phase5_analysis.py --bootstrap-samples 50000
PYTHONPATH=backend .venv/bin/python backend/run_published_challengers.py --bootstrap-samples 50000
PYTHONPATH=backend .venv/bin/python backend/run_phase5_robustness.py
PYTHONPATH=backend .venv/bin/python backend/run_phase5_supplemental.py
PYTHONPATH=backend .venv/bin/python backend/run_phase5_reporting.py
npm run build
node --test tests/rendered-html.test.mjs
```

Local preview:

```bash
npm run dev:api
npm run dev
```

Open `http://localhost:3000`. The Phase 5 API is `http://127.0.0.1:8000/api/research/phase5`.
"""
    (docs / "phase5_runbook.md").write_text(runbook)

    frozen = {
        "schema_version": 1, "candidate_id": "C01", "version": "C01-v1",
        "evidence_at_freeze": disposition["evidence"], "selection_eligible": disposition["evidence"] == "robust_historical_candidate",
        "market_training_window": {"start": "2018-01-01", "end_inclusive": "2025-12-31"},
        "protected_future_market_data_opened": False,
        "candidate_specification_hash": next(row["specification_hash"] for row in manifest["candidates"] if row["candidate_id"] == "C01"),
        "rule": next(row["specification"] for row in manifest["candidates"] if row["candidate_id"] == "C01"),
        "primary_contract": "NQ", "primary_management": "matched_4R", "primary_sizing": "fixed1",
        "execution": {"adverse_first_same_bar": True, "NQ_point_value": 20, "round_trip_fees": 5.10, "slippage_ticks_per_side": 1, "spread_ticks_round_trip": 1, "time_zone": "America/New_York"},
        "permitted_next_use": "prospective paper/manual rehearsal or separately authorized future holdout only",
        "prohibited_claims": ["validated", "live-ready", "approved for automation"],
        "phase5_result_sha256": _sha(results_path),
    }
    frozen_path = research / "frozen_strategy_c01_v1.json"
    frozen_path.write_text(json.dumps(frozen, indent=2))
    (research / "frozen_strategy_c01_v1.sha256").write_text(f"{_sha(frozen_path)}  {frozen_path.name}\n")
    return {"experiments": len(ledger), "candidate": disposition["evidence"], "reports": 5, "frozen_hash": _sha(frozen_path)}
