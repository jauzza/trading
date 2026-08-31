# Phase 5 strategy tournament report

## Decision

Yes. **C01 beat the matched first-candle baseline after family-aware correction and passed every frozen robustness gate.** Its paired NQ difference was 0.512R per eligible session with a 95% stationary-bootstrap interval of [0.401, 0.622], raw two-sided p 4e-05, within-family BH 0.00024, within-family BY 0.000588, all-comparison BH 0.00019, and all-comparison BY 0.00067407. The White reality-check and studentized SPA-style family maximum tests were both 2e-05 at 50,000 resamples.

C01 is a **robust historical candidate**, not validated and not live-ready. All 2018–2025 observations have now been inspected. The only proper next evidentiary step is prospective paper/manual rehearsal or a separately authorized future holdout test under the frozen specification. The protected market holdout remains **UNTOUCHED**.

No good/bad-day entry filter survived all three historical periods. The models did not transport: validation logistic AUC was 0.470 and historical-evaluation AUC was 0.489. Deleting apparently weak development buckets also deleted too many later winners.

## Winning rule and implementation

Source claim: a 15-minute opening-range breakout, volume confirmation, and long-horizon EMA trend filter. Local implementation: wait for a completed 15-minute bar to close outside the 09:30–09:44 range; require its volume to exceed the preceding completed 15-minute bar; require direction agreement with a lagged 200-period EMA of completed 15-minute RTH closes; enter at the next one-minute open; use the breakout bar's opposite extreme as stop; use either matched 4R or matched 15:55 exit management; one trade maximum; no re-entry. Warm-up is 200 completed 15-minute RTH bars. Source-vintage begins in 2021, so 2018–2020 is retrospective idea evaluation.

## C01 fixed-one-contract results

| Measure | NQ matched 4R | MNQ matched 4R | NQ matched EOD |
|---|---:|---:|---:|
| Accepted sessions | 1,966 | 1,636 | 1,966 |
| Trades | 1,530 | 1,259 | 1,530 |
| Net profit | $375,752.00 | $35,566.90 | $443,347.00 |
| Net expectancy / eligible session | 0.590R | 0.536R | 1.344R |
| Win rate | 42.22% | 42.49% | 31.31% |
| Profit factor | 1.839 | 1.8735 | 1.9017 |
| Max drawdown | -5.55% | -0.78% | -5.75% |
| Positive years | 7/8 | 7/7 | 8/8 |

The matched first-candle NQ control earned $96,269.10; C01 earned $375,752.00. Validation and historical-evaluation net were $105,545.70 and $164,142.50, respectively. Independent period simulations each restarted at $100,000.

Costs reconcile per trade from reference gross through direction-aware slipped fills, spread, commission, exchange, clearing, and regulatory fees. C01 NQ paid $30,753.00 at baseline; it remained net positive at 2× ($344,999.00) and 4× ($283,493.00) costs.

## Robustness and concentration

- One-minute delayed NQ entry: $333,903.80, 8/8 positive years.
- One full 15-minute signal-bar delay: $47,683.80, 6/8 positive years.
- Largest winner: 7.09% of final net; top five: 15.37%.
- After removing the best 1%: $264,408.60; after best five: $318,002.50; after the best trade from every year: $319,612.80.
- Largest positive year's share: 28.33%; 1% winsorized net: $336,357.20.
- DSR probability: 1.0 using 170 recorded configurations. CSCV/PBO: 0.0 over 70 splits.

The large 1%-risk compounded returns are an aggressive capped-sizing illustration, not a realistic profit forecast. Fixed-one-contract results are the practical comparison. NQ has much larger dollar volatility and research margin; MNQ is operationally more accessible but its fee drag is larger relative to point value. The positive one-minute delay result supports manual rehearsal feasibility; it does not guarantee manual fills.

## Operational audit and extra friction

C01 used 109,176 market minutes, or 14.24% of nominal accepted-session RTH. It turned over 1,530 fixed contracts at an average $20.10 per completed trade. Gross P&L was $406,505.00; the average winner was $1,274.92, the average loser $-506.62, and the payoff ratio 2.517. Dollar max drawdown was $-10,876.60, with a recovery factor of 34.547. The fixed-contract CAGR audit (21.53%) is descriptive because fixed-contract P&L is not a continuously reinvested portfolio.

Worst realized day: 2022-09-21 ($-5,100.10); week: 2022-09-17/2022-09-23 ($-4,745.40); month: 2022-09 ($-8,981.70); year: 2019 ($-168.20). Long trades earned $156,474.60; shorts earned $219,277.40. Every leave-one-year-out total remained positive.

Scheduled-event sessions earned $98,372.30; non-event sessions earned $277,379.70. Adding one extra spread tick plus one extra slippage tick per side to entries at or before 10:00 left $375,137.00; applying that stress specifically to affected open/event entries left $368,237.00. These are audit sensitivities, not a promoted event policy.

## Expanding walk-forward audit

Prior cumulative net selected C01 before each annual 2022–2025 evaluation. The untouched-within-audit annual outcomes were $66,400.60, $39,145.10, $57,661.20, and $106,481.30, respectively. This is supportive temporal stability evidence, but remains post-selection because the complete 2018–2025 sample is now known.

## Bounded C01 parameter plateau and roll sensitivity

| EMA period | Volume ratio | Trades | Net profit | PF | Max DD | Positive years | Net after best 1% removed |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 150 | 0.8 | 1,635 | $505,071.50 | 2.111 | -3.14% | 8/8 | $384,343.20 |
| 150 | 1.0 | 1,583 | $426,816.70 | 1.959 | -4.31% | 8/8 | $312,668.30 |
| 150 | 1.2 | 1,491 | $318,070.90 | 1.766 | -3.91% | 8/8 | $214,502.40 |
| 200 | 0.8 | 1,582 | $463,421.80 | 2.024 | -3.42% | 8/8 | $349,098.40 |
| 200 | 1.0 | 1,530 | $375,752.00 | 1.839 | -5.55% | 7/8 | $264,408.60 |
| 200 | 1.2 | 1,429 | $288,217.10 | 1.706 | -6.44% | 8/8 | $183,453.60 |
| 250 | 0.8 | 1,536 | $417,931.40 | 1.932 | -3.98% | 8/8 | $324,573.00 |
| 250 | 1.0 | 1,483 | $329,286.70 | 1.751 | -5.35% | 7/8 | $247,088.20 |
| 250 | 1.2 | 1,384 | $247,391.60 | 1.623 | -7.08% | 7/8 | $169,253.00 |

All nine neighboring EMA/volume cells stayed profitable, survived removal of their best 1%, and had seven or eight positive years. The surface slopes toward the shorter EMA and looser volume threshold; that is a warning against post-hoc optimization, not permission to replace the preregistered EMA200 / 1.0-volume specification. Including the normally excluded roll sessions produced $384,704.20 over 1,995 accepted sessions versus $375,752.00 over 1,966 in the authoritative exclusion rule.

## Candidate dispositions

| ID | Source family | Implementation decision | Historical result | Failed gates / limitation |
|---|---|---|---|---|
| C01 | opening_range_breakout | implement_primary | **robust_historical_candidate** — $375,752.00; validation $105,545.70; evaluation $164,142.50 | None of the frozen gates failed |
| C02 | opening_range_breakout | implement_primary | **inconclusive** — $-11,179.00; validation $-11,831.10; evaluation $24,505.50 | positive_validation, six_positive_years, positive_2x_costs, low_tail_dependence, drawdown_under_30pct, positive_paired_effect_validation, positive_paired_effect_historical_evaluation |
| C03 | keltner_strategy | implement_primary | **inconclusive** — $-78,282.90; validation $17,455.00; evaluation $-64,711.40 | positive_validation, positive_historical_evaluation, six_positive_years, positive_2x_costs, low_tail_dependence, one_minute_delay_positive, one_signal_bar_delay_positive, drawdown_under_30pct, positive_paired_effect_validation, positive_paired_effect_historical_evaluation |
| C04 | bollinger_reversion | implement_primary | **promising_exploratory** — $72,301.50; validation $96,326.60; evaluation $-32,448.70 | positive_historical_evaluation, six_positive_years, low_tail_dependence, drawdown_under_30pct, positive_paired_effect_historical_evaluation |
| C05 | ema_pullback | implement_primary | **promising_exploratory** — $36,469.10; validation $80,175.80; evaluation $-8,844.00 | positive_historical_evaluation, six_positive_years, positive_2x_costs, low_tail_dependence, positive_paired_effect_historical_evaluation |
| C06 | moving_average_trend | defer_subjective | **inconclusive** — Not run | defer_subjective |
| C07 | atr_stop_breakout | defer_subjective | **inconclusive** — Not run | defer_subjective |
| C08 | liquidity_sweep | implement_primary | **rejected** — $-78,344.60; validation $-40,203.20; evaluation $-28,656.10 | positive_validation, positive_historical_evaluation, six_positive_years, positive_2x_costs, low_tail_dependence, one_minute_delay_positive, one_signal_bar_delay_positive, drawdown_under_30pct, positive_paired_effect_validation, positive_paired_effect_historical_evaluation |
| C09 | previous_day_levels | implement_primary | **rejected** — $-78,105.70; validation $-37,365.10; evaluation $-548.00 | positive_validation, positive_historical_evaluation, six_positive_years, positive_2x_costs, low_tail_dependence, one_minute_delay_positive, one_signal_bar_delay_positive, drawdown_under_30pct, positive_paired_effect_validation, positive_paired_effect_historical_evaluation |
| C10 | overnight_breakout | implement_primary | **promising_exploratory** — $20,303.20; validation $18,827.80; evaluation $-14,001.00 | six_positive_years, positive_2x_costs, low_tail_dependence, one_signal_bar_delay_positive, positive_paired_effect_validation, positive_paired_effect_historical_evaluation |
| C11 | vwap_trend | implement_primary | **promising_exploratory** — $60,953.20; validation $4,492.20; evaluation $39,736.80 | positive_validation, low_tail_dependence, drawdown_under_30pct, positive_paired_effect_validation |
| C12 | vwap_mean_reversion | defer_subjective | **inconclusive** — Not run | defer_subjective |
| C13 | relative_volume_breakout | defer_subjective | **inconclusive** — Not run | defer_subjective |
| C14 | gap_fill | implement_primary | **promising_exploratory** — $41,217.90; validation $27,331.30; evaluation $20,264.50 | six_positive_years, low_tail_dependence, one_signal_bar_delay_positive, positive_paired_effect_validation, positive_paired_effect_historical_evaluation |
| C15 | failed_breakout | implement_primary | **rejected** — $-78,157.60; validation $-41,585.20; evaluation $-42,651.80 | positive_validation, positive_historical_evaluation, six_positive_years, positive_2x_costs, low_tail_dependence, one_minute_delay_positive, one_signal_bar_delay_positive, drawdown_under_30pct, positive_paired_effect_validation, positive_paired_effect_historical_evaluation |
| C16 | initial_balance_breakout | implement_primary | **promising_exploratory** — $9,737.40; validation $9,953.80; evaluation $-96.00 | positive_validation, positive_historical_evaluation, six_positive_years, positive_2x_costs, low_tail_dependence, drawdown_under_30pct, positive_paired_effect_validation, positive_paired_effect_historical_evaluation |
| C17 | first_candle_momentum | negative_control | **inconclusive** — $42,818.20; validation $8,641.80; evaluation $11,351.70 | negative_control_not_selection_eligible |
| C18 | breakout_retest | duplicate_excluded | **inconclusive** — Not run | duplicate_excluded |

## Published/preprint-inspired shadow lane

The noise-area/VWAP adaptation earned $184,493.10, but it is **not selection eligible** because the futures stop adaptation was not source-complete. The final-half-hour momentum shadow lost money in development, validation, and historical evaluation ($-5,132.20, $-5,184.00, $-13,943.70). The MNQ falsification paper was not claimed as reproduced because exact GMM, retraining, stop, and session details were incomplete. The volatility-volume-gap idea was used only as a lag-safe descriptive feature.

## Limitations and evidence classification

One-minute OHLCV cannot reconstruct tick order, queue position, L2, footprint, true delta, or volume-at-price. Parameter plateaus, roll sensitivities, detailed weekly/monthly views, event partitions, and expanding walk-forward rows are explicitly post-selection audits; they cannot rewrite the winner or its frozen parameters. No macro policy was promoted because the good/bad-day event filter was unstable. Reddit popularity and anecdotes never entered P&L inference.

Evidence: C01 is robust historical candidate; C04/C05/C10/C11/C14/C16 are promising exploratory but failed listed gates; C02/C03/C06/C07/C12/C13/C17/C18 are inconclusive/deferred/negative/duplicate as shown; C08/C09/C15 are rejected. No strategy is called validated.

## Reproducibility

The preregistration hash and 18 candidate specification hashes were verified before result generation. The full machine-readable ledger contains 174 completed, failed, deferred, duplicate, control, and shadow entries. Raw input checksum audit: **PASS**. See `docs/phase5_runbook.md` for exact commands.
