# Phase 5 strategy tournament preregistration

Status: **frozen before Phase 5 result generation**  
Frozen date: 2026-08-25  
Market data permitted: preserved Databento/FRED observations through 2025-12-31 only  
Protected holdout: all market observations after 2025-12-31; reject before opening a market partition

## Purpose and decision rule

This is a falsification tournament, not a return-maximization exercise. Candidate eligibility and all robustness gates below are fixed before results. No failed gate may be weakened after inspection.

Periods start with independent $100,000 equity:

- development: 2018–2021;
- validation: 2022–2023;
- historical evaluation: 2024–2025;
- 2026 market holdout: untouched.

Expanding walk-forward audit: train/describe through year *t-1*, evaluate year *t*, beginning with 2022. Labels that extend to 15:55 receive a one-session embargo at fold boundaries. Development-learned transforms are frozen for later periods.

## Execution and sizing

- NQ: $20/point, 0.25 tick, baseline fees $5.10 round trip, one tick slippage per side, one tick round-trip spread.
- MNQ: $2/point, 0.25 tick, baseline fees $2.40 round trip, one tick slippage per side, one tick round-trip spread.
- Adverse-first ordering when stop and target are both inside one minute bar.
- Gap-through stops fill at the worse bar open; prices are directionally tick-rounded.
- Costs are reconciled as reference gross minus spread minus slippage minus itemized fees equals net.
- Run fixed one-contract and whole-contract 1% initial-risk sizing subject to the existing margin and 20-contract cap.
- Cost stress is the identical trade path at 1×, 2×, and 4× total friction.

## Tournament families and experiments

Reddit families: opening momentum/range; objective prior/overnight levels; VWAP; trend/pullback/channel; consolidation/relative volume; gap. Published/preprint-inspired challengers are a separate family. Native management is a separate family and is allowed only when fully specified before results.

Every eligible signal receives two matched overlays:

- `matched_4R`: candidate-specific objective initial stop, fixed 4R target, adverse-first sequencing, 15:55 fallback exit;
- `matched_EOD`: same entry and stop, no target, 15:55 exit.

Maximum one trade per strategy/session. No break-even move, partial exit, trailing stop, scale-in, or re-entry is allowed in the matched tournament. Existing baselines include no-trade, always-long, always-short, seeded random direction, first-candle direction 4R, full-overnight EMA 4R, and Phase-4 first-candle EOD.

Candidate dispositions and exact formulas are frozen in `research/candidate_resolution_manifest.json`. C03/C04 are completeness B locally because their terminal exits were missing. C06, C07, C12, and C13 are deferred for core ambiguity; C17 is a negative control; C18 is excluded as a duplicate of the objective-level retest family.

## Research-inspired lane

- Noise-area/VWAP momentum: RTH open; minute-of-session absolute move from open averaged over the trailing 14 completed sessions and shifted one full session; bands around the more conservative of RTH open and adjusted prior close; RTH VWAP; decisions every 30 completed minutes. Futures adaptation uses the continuous contract and the same corrected execution engine.
- Intraday-momentum shadow test: first 30-minute and penultimate 30-minute returns are completed inputs for a final-30-minute directional trade; no overlapping leakage.
- MNQ falsification paper: shadow controls only unless every GMM feature, retraining cadence, stop, and session rule is available.
- VVG: descriptive feature only—overnight gap, completed first-30-minute return, and first-bar volume divided by trailing 20-session same-time volume. Expanding development thresholds; no standalone edge claim.

The 2026 publication dates are idea provenance only and never a 2026 market test.

## Lag-safe good/bad-day registry

One row per strategy/session is captured at that strategy's actual decision time. Every value records `known_at`, `source_timestamp`, `calculation_window`, and `available_for_this_entry`. Missing-at-entry values remain null. Registered features are opening-range size, overnight alignment, distances to overnight and prior-day extremes, prior-day regime, lagged VIX, scheduled-event flag/time-to-event, 10:00 event, overnight gap, trailing same-minute relative volume, lag-safe VWAP slope/reclaim, holiday adjacency, weekday, options expiration, month/quarter end, and lagged large prior move. VVG is the only added sourced composite.

Forbidden entry features include current-day trend label, final range, close location, full-day realized volatility, post-entry releases/news, and any pivot not yet confirmed.

Development-only models: regularized linear/logistic regression and depth-2 tree. Continuous transforms use development medians/IQRs. The interaction set is limited to opening range × relative volume, overnight alignment × distance to overnight extreme, and event flag × time-to-event. Any learned filter is frozen and tested as a session-paired filtered-versus-unfiltered strategy, including skipped winners.

## Inference and multiplicity

- Unit: eligible session; eligible no-trade sessions are zero, never missing.
- 50,000 Politis–Romano stationary-bootstrap resamples, expected block length 10 sessions, deterministic declared seeds.
- Two-sided raw p-values and 95% confidence intervals for mean session R and paired differences.
- BH and BY correction within declared families and across family winners.
- White reality check and studentized SPA-style maximum test.
- Deflated Sharpe Ratio with the complete tried-configuration count; CSCV/PBO only when the variant matrix has enough configurations and folds.
- Experiment ledger includes failures, deferrals, sensitivities, and abandoned runs.

## Robustness and tail gates

For family winners and near-selection candidates: 1×/2×/4× costs, one-minute and one-signal-bar delays, adverse sequencing, event/open spread expansion, local parameter perturbations, roll-session exclusion, completeness/missing-bar audit, NQ/MNQ, fixed/risk sizing, long/short, random/unconditional controls, top-trade removal, and leave-one-year-out.

`low_tail_dependence` requires all of: positive after removing the best 1% of trades; largest trade ≤10% of net; largest positive year ≤40% of all positive-year P&L; positive validation and historical evaluation.

A `robust_historical_candidate` must additionally have positive validation and historical-evaluation expectancy, at least 200 total signals with at least 40 in each later period, positive results in at least 6/8 calendar years, positive at 2× costs, no collapse under delay, ≤30% maximum drawdown under independent 1% sizing, positive paired effect over its matched simple control in both later periods, and no critical integrity/accounting/timestamp failure. Nothing may be labeled validated, live-ready, or approved.

## Macro/news boundary

Stage 1 may cache point-in-time scheduled-event timestamps only from official BLS, Federal Reserve, BEA, Census, and objectively verifiable exchange calendars. Event values/surprises are post-release information. Stage 2 is schema and coverage/cost research only; no paid headlines and no API-key request in this phase.

## Frozen specification hash

The SHA-256 of this file is recorded in the machine-readable experiment ledger before the first result row is generated. Any later change starts a new version and invalidates claims that validation/evaluation remained frozen.
