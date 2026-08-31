# Phase 5 complete technical handoff

> Single-file transfer package for another IDE or coding agent.
>
> Repository: `/Users/jauzza/Documents/ChatGPT/trading`
>
> Protected boundary: 2026 market data remains untouched. The raw Databento/FRED cache was verified byte-identical before and after Phase 5.

## Transfer instructions

Treat the sections below as the authoritative Phase 5 handoff. The tournament report explains the result and candidate dispositions. The good/bad-day report explains the failed entry-filter research. The runbook contains exact reproduction commands. The frozen JSON is the immutable C01 specification. The final CSV block is the complete 174-entry experiment ledger.

---

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

---

# Phase 5 good-day / bad-day report

## Result

**No good/bad-day filter survives.** No filter was promoted and no composite meta-strategy was created.

The analysis used 1,530 executed C01 sessions and 20 lag-safe pre-entry features. Each long-form feature row records `known_at`, `source_timestamp`, `calculation_window`, and `available_for_this_entry`, plus net R/P&L, win, stop-out, MAE, MFE, tail-winner, and drawdown contribution. Unavailable values remain null.

## Model transport

| Period | Sessions | Logistic AUC | Logistic Brier | Ridge correlation | Actual win rate |
|---|---:|---:|---:|---:|---:|
| Development 2018–2021 | 762 | 0.594 | 0.238 | 0.185 | 41.86% |
| Validation 2022–2023 | 393 | 0.470 | 0.253 | -0.016 | 40.97% |
| Historical evaluation 2024–2025 | 375 | 0.489 | 0.259 | -0.030 | 44.27% |

Development-only logistic, ridge, and depth-2 tree models did not transport. The later AUCs were near or below 0.50 and Ridge correlations were near zero/negative.

## Leading rejected screen

The strongest development-descriptive screen was `options_expiration` with rule `equals` at `1.0`. It was rejected because the paired filtered-minus-unfiltered effect did not remain positive in every period. The artifact reports sessions kept/removed, skipped winners and skipped-winner R, period effects, 50,000-resample intervals, and BH/BY adjustments for every tested feature.

This answers the practical question: the available pre-entry variables did not consistently reduce bad days without deleting valuable winners. Descriptive buckets remain useful for explanation, but not for trade selection.

## Macro/event interpretation

The scheduled-event flag uses only calendar rows marked known before the session. Released values and surprises are not used. FOMC archive links not matching an official regular-meeting date are marked unavailable as a pre-session scheduled flag. The calendar has 661 rows spanning 2018-01-01 through 2025-12-31; it does not contain market outcomes.

## Limits

No post-entry label—trend day, final range, close location, full-day volatility, or later news—was used as an entry feature. Census retail-sales and private ISM historical point-in-time coverage was not verified, so those were excluded rather than guessed. No paid headlines were fetched.

---

# Phase 5 reproduction runbook

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

---

## Frozen C01 specification — exact JSON

Source file: `research/frozen_strategy_c01_v1.json`

```json
{
  "schema_version": 1,
  "candidate_id": "C01",
  "version": "C01-v1",
  "evidence_at_freeze": "robust_historical_candidate",
  "selection_eligible": true,
  "market_training_window": {
    "start": "2018-01-01",
    "end_inclusive": "2025-12-31"
  },
  "protected_future_market_data_opened": false,
  "candidate_specification_hash": "1cd8ab1a8d7512861a2814c10a805b02127bd7a3bf73c8ac058c49f296e99c1a",
  "rule": {
    "entry_timestamp": "first one-minute open after a completed 15-minute close beyond the 09:30-09:44 range",
    "feature_cutoff": "qualifying close",
    "indicator_formula": "200-period EMA of completed 15-minute RTH closes; breakout 15-minute volume > preceding completed 15-minute volume",
    "warmup": "200 completed 15-minute RTH bars",
    "stop": "opposite extreme of qualifying breakout 15-minute bar",
    "target": "matched overlay",
    "time_exit": "15:55 ET",
    "reentry": false,
    "max_trades": 1
  },
  "primary_contract": "NQ",
  "primary_management": "matched_4R",
  "primary_sizing": "fixed1",
  "execution": {
    "adverse_first_same_bar": true,
    "NQ_point_value": 20,
    "round_trip_fees": 5.1,
    "slippage_ticks_per_side": 1,
    "spread_ticks_round_trip": 1,
    "time_zone": "America/New_York"
  },
  "permitted_next_use": "prospective paper/manual rehearsal or separately authorized future holdout only",
  "prohibited_claims": [
    "validated",
    "live-ready",
    "approved for automation"
  ],
  "phase5_result_sha256": "32cdb5002701d30260c8b2072db1d624e5fa9538cca40146f0a43f6d3b54ff3e"
}
```

---

## Full Phase 5 experiment ledger — exact CSV

Source file: `data/research/phase5-experiment-ledger.csv`

```csv
experiment_id,lane,status,instrument,candidate,family,management,sizing,trades,accepted_sessions,net_profit,validation_net_profit,historical_evaluation_net_profit,selection_disposition,failure_reason
MNQ:BASE_CANDLE:matched_4R:fixed1,signal_quality,completed,MNQ,BASE_CANDLE,opening_momentum_range,matched_4R,fixed1,1632,1636,6059.2,2070.6,4346.5,baseline_control,
MNQ:BASE_CANDLE:matched_4R:risk1,signal_quality,completed,MNQ,BASE_CANDLE,opening_momentum_range,matched_4R,risk1,1632,1636,108597.0,10863.1,54237.2,baseline_control,
MNQ:BASE_CANDLE:matched_EOD:fixed1,signal_quality,completed,MNQ,BASE_CANDLE,opening_momentum_range,matched_EOD,fixed1,1632,1636,11527.2,3718.6,7746.0,baseline_control,
MNQ:BASE_CANDLE:matched_EOD:risk1,signal_quality,completed,MNQ,BASE_CANDLE,opening_momentum_range,matched_EOD,risk1,1632,1636,188018.3,29179.8,87092.1,baseline_control,
MNQ:BASE_EMA:matched_4R:fixed1,signal_quality,completed,MNQ,BASE_EMA,opening_momentum_range,matched_4R,fixed1,1636,1636,6737.1,725.2,5272.2,baseline_control,
MNQ:BASE_EMA:matched_4R:risk1,signal_quality,completed,MNQ,BASE_EMA,opening_momentum_range,matched_4R,risk1,1636,1636,142468.1,19327.1,67144.4,baseline_control,
MNQ:BASE_EMA:matched_EOD:fixed1,signal_quality,completed,MNQ,BASE_EMA,opening_momentum_range,matched_EOD,fixed1,1636,1636,15362.1,3936.2,10310.2,baseline_control,
MNQ:BASE_EMA:matched_EOD:risk1,signal_quality,completed,MNQ,BASE_EMA,opening_momentum_range,matched_EOD,risk1,1636,1636,299297.9,76499.3,132287.3,baseline_control,
MNQ:BASE_LONG:matched_4R:fixed1,signal_quality,completed,MNQ,BASE_LONG,baselines,matched_4R,fixed1,1632,1636,-2938.3,817.7,-2097.4,baseline_control,
MNQ:BASE_LONG:matched_4R:risk1,signal_quality,completed,MNQ,BASE_LONG,baselines,matched_4R,risk1,1632,1636,-59523.6,-21185.4,-31499.6,baseline_control,
MNQ:BASE_LONG:matched_EOD:fixed1,signal_quality,completed,MNQ,BASE_LONG,baselines,matched_EOD,fixed1,1632,1636,6725.7,5331.7,3361.1,baseline_control,
MNQ:BASE_LONG:matched_EOD:risk1,signal_quality,completed,MNQ,BASE_LONG,baselines,matched_EOD,risk1,1632,1636,71484.2,63989.0,33562.9,baseline_control,
MNQ:BASE_NONE:matched_4R:fixed1,signal_quality,completed,MNQ,BASE_NONE,other,matched_4R,fixed1,0,1636,0.0,0.0,0.0,baseline_control,
MNQ:BASE_NONE:matched_4R:risk1,signal_quality,completed,MNQ,BASE_NONE,other,matched_4R,risk1,0,1636,0.0,0.0,0.0,baseline_control,
MNQ:BASE_NONE:matched_EOD:fixed1,signal_quality,completed,MNQ,BASE_NONE,other,matched_EOD,fixed1,0,1636,0.0,0.0,0.0,baseline_control,
MNQ:BASE_NONE:matched_EOD:risk1,signal_quality,completed,MNQ,BASE_NONE,other,matched_EOD,risk1,0,1636,0.0,0.0,0.0,baseline_control,
MNQ:BASE_RANDOM:matched_4R:fixed1,signal_quality,completed,MNQ,BASE_RANDOM,baselines,matched_4R,fixed1,1631,1636,-1892.4,-826.1,2204.1,baseline_control,
MNQ:BASE_RANDOM:matched_4R:risk1,signal_quality,completed,MNQ,BASE_RANDOM,baselines,matched_4R,risk1,1630,1636,-70768.6,-33112.2,14923.7,baseline_control,
MNQ:BASE_RANDOM:matched_EOD:fixed1,signal_quality,completed,MNQ,BASE_RANDOM,baselines,matched_EOD,fixed1,1631,1636,-2593.9,438.9,3917.1,baseline_control,
MNQ:BASE_RANDOM:matched_EOD:risk1,signal_quality,completed,MNQ,BASE_RANDOM,baselines,matched_EOD,risk1,1553,1636,-91765.9,-14169.6,20245.3,baseline_control,
MNQ:BASE_SHORT:matched_4R:fixed1,signal_quality,completed,MNQ,BASE_SHORT,baselines,matched_4R,fixed1,1627,1636,332.2,-1237.7,4200.0,baseline_control,
MNQ:BASE_SHORT:matched_4R:risk1,signal_quality,completed,MNQ,BASE_SHORT,baselines,matched_4R,risk1,1627,1636,-64580.9,-24756.5,22535.2,baseline_control,
MNQ:BASE_SHORT:matched_EOD:fixed1,signal_quality,completed,MNQ,BASE_SHORT,baselines,matched_EOD,fixed1,1627,1636,-474.3,-1857.2,4931.0,baseline_control,
MNQ:BASE_SHORT:matched_EOD:risk1,signal_quality,completed,MNQ,BASE_SHORT,baselines,matched_EOD,risk1,1570,1636,-87159.5,-47018.1,35586.6,baseline_control,
MNQ:C01:matched_4R:fixed1,signal_quality,completed,MNQ,C01,opening_momentum_range,matched_4R,fixed1,1259,1636,35566.9,13188.0,15404.8,robust_historical_candidate,
MNQ:C01:matched_4R:risk1,signal_quality,completed,MNQ,C01,opening_momentum_range,matched_4R,risk1,1259,1636,675557.6,243613.8,240345.6,robust_historical_candidate,
MNQ:C01:matched_EOD:fixed1,signal_quality,completed,MNQ,C01,opening_momentum_range,matched_EOD,fixed1,1259,1636,40727.4,15762.5,18160.3,robust_historical_candidate,
MNQ:C01:matched_EOD:risk1,signal_quality,completed,MNQ,C01,opening_momentum_range,matched_EOD,risk1,1259,1636,780573.5,312302.7,302449.5,robust_historical_candidate,
MNQ:C02:matched_4R:fixed1,signal_quality,completed,MNQ,C02,opening_momentum_range,matched_4R,fixed1,1322,1636,-3583.3,-2393.2,1880.6,inconclusive,
MNQ:C02:matched_4R:risk1,signal_quality,completed,MNQ,C02,opening_momentum_range,matched_4R,risk1,1322,1636,-61645.7,-31781.1,1954.1,inconclusive,
MNQ:C02:matched_EOD:fixed1,signal_quality,completed,MNQ,C02,opening_momentum_range,matched_EOD,fixed1,1322,1636,-3623.8,850.3,-989.4,inconclusive,
MNQ:C02:matched_EOD:risk1,signal_quality,completed,MNQ,C02,opening_momentum_range,matched_EOD,risk1,1322,1636,-40348.8,15248.3,-28012.0,inconclusive,
MNQ:C03:matched_4R:fixed1,signal_quality,completed,MNQ,C03,trend_pullback_channel,matched_4R,fixed1,1190,1636,-8536.5,1075.0,-6323.4,inconclusive,
MNQ:C03:matched_4R:risk1,signal_quality,completed,MNQ,C03,trend_pullback_channel,matched_4R,risk1,1160,1636,-82567.5,-14418.9,-49489.3,inconclusive,
MNQ:C03:matched_EOD:fixed1,signal_quality,completed,MNQ,C03,trend_pullback_channel,matched_EOD,fixed1,1190,1636,-8330.5,1682.5,-7425.9,inconclusive,
MNQ:C03:matched_EOD:risk1,signal_quality,completed,MNQ,C03,trend_pullback_channel,matched_EOD,risk1,1164,1636,-82057.0,-7075.9,-53912.5,inconclusive,
MNQ:C04:matched_4R:fixed1,signal_quality,completed,MNQ,C04,trend_pullback_channel,matched_4R,fixed1,1609,1636,4967.4,8833.8,-3553.4,promising_exploratory,
MNQ:C04:matched_4R:risk1,signal_quality,completed,MNQ,C04,trend_pullback_channel,matched_4R,risk1,1602,1636,34231.2,87672.3,-21797.5,promising_exploratory,
MNQ:C04:matched_EOD:fixed1,signal_quality,completed,MNQ,C04,trend_pullback_channel,matched_EOD,fixed1,1609,1636,4090.4,10193.8,-4306.9,promising_exploratory,
MNQ:C04:matched_EOD:risk1,signal_quality,completed,MNQ,C04,trend_pullback_channel,matched_EOD,risk1,1598,1636,19399.1,108035.9,-24764.3,promising_exploratory,
MNQ:C05:matched_4R:fixed1,signal_quality,completed,MNQ,C05,trend_pullback_channel,matched_4R,fixed1,1630,1636,2532.5,6817.6,-2196.0,promising_exploratory,
MNQ:C05:matched_4R:risk1,signal_quality,completed,MNQ,C05,trend_pullback_channel,matched_4R,risk1,1612,1636,-297.1,25159.3,-2060.4,promising_exploratory,
MNQ:C05:matched_EOD:fixed1,signal_quality,completed,MNQ,C05,trend_pullback_channel,matched_EOD,fixed1,1630,1636,1358.5,7102.1,-2991.5,promising_exploratory,
MNQ:C05:matched_EOD:risk1,signal_quality,completed,MNQ,C05,trend_pullback_channel,matched_EOD,risk1,1601,1636,-12531.4,30158.4,-17403.2,promising_exploratory,
MNQ:C08:matched_4R:fixed1,signal_quality,completed,MNQ,C08,objective_levels,matched_4R,fixed1,869,1636,-7006.1,-4404.1,-2886.6,rejected,
MNQ:C08:matched_4R:risk1,signal_quality,completed,MNQ,C08,objective_levels,matched_4R,risk1,868,1636,-64611.7,-37120.8,-27106.8,rejected,
MNQ:C08:matched_EOD:fixed1,signal_quality,completed,MNQ,C08,objective_levels,matched_EOD,fixed1,869,1636,-5091.1,-2475.1,-3448.1,rejected,
MNQ:C08:matched_EOD:risk1,signal_quality,completed,MNQ,C08,objective_levels,matched_EOD,risk1,869,1636,-52969.2,-5605.6,-47441.8,rejected,
MNQ:C09:matched_4R:fixed1,signal_quality,completed,MNQ,C09,objective_levels,matched_4R,fixed1,959,1636,-8877.6,-3853.9,-655.6,rejected,
MNQ:C09:matched_4R:risk1,signal_quality,completed,MNQ,C09,objective_levels,matched_4R,risk1,942,1636,-87378.1,-55216.7,-27636.1,rejected,
MNQ:C09:matched_EOD:fixed1,signal_quality,completed,MNQ,C09,objective_levels,matched_EOD,fixed1,959,1636,-8111.1,-3277.4,169.9,rejected,
MNQ:C09:matched_EOD:risk1,signal_quality,completed,MNQ,C09,objective_levels,matched_EOD,risk1,922,1636,-91388.2,-54177.6,-33413.1,rejected,
MNQ:C10:matched_4R:fixed1,signal_quality,completed,MNQ,C10,objective_levels,matched_4R,fixed1,1507,1636,-1440.8,964.2,-2006.1,promising_exploratory,
MNQ:C10:matched_4R:risk1,signal_quality,completed,MNQ,C10,objective_levels,matched_4R,risk1,1506,1636,-7265.7,7519.6,-9785.8,promising_exploratory,
MNQ:C10:matched_EOD:fixed1,signal_quality,completed,MNQ,C10,objective_levels,matched_EOD,fixed1,1507,1636,-1759.3,2753.2,-2257.6,promising_exploratory,
MNQ:C10:matched_EOD:risk1,signal_quality,completed,MNQ,C10,objective_levels,matched_EOD,risk1,1506,1636,-25136.7,24658.0,-4520.7,promising_exploratory,
MNQ:C11:matched_4R:fixed1,signal_quality,completed,MNQ,C11,vwap,matched_4R,fixed1,1598,1636,1631.8,-1853.4,4745.0,promising_exploratory,
MNQ:C11:matched_4R:risk1,signal_quality,completed,MNQ,C11,vwap,matched_4R,risk1,1598,1636,26005.5,-39727.6,98633.5,promising_exploratory,
MNQ:C11:matched_EOD:fixed1,signal_quality,completed,MNQ,C11,vwap,matched_EOD,fixed1,1598,1636,7773.8,1370.1,5706.5,promising_exploratory,
MNQ:C11:matched_EOD:risk1,signal_quality,completed,MNQ,C11,vwap,matched_EOD,risk1,1598,1636,186088.6,10734.1,122450.9,promising_exploratory,
MNQ:C14:matched_4R:fixed1,signal_quality,completed,MNQ,C14,gap,matched_4R,fixed1,815,1636,2617.0,2126.3,2318.5,promising_exploratory,
MNQ:C14:matched_4R:risk1,signal_quality,completed,MNQ,C14,gap,matched_4R,risk1,815,1636,32953.7,1541.5,29651.9,promising_exploratory,
MNQ:C14:matched_EOD:fixed1,signal_quality,completed,MNQ,C14,gap,matched_EOD,fixed1,815,1636,4974.5,3249.8,3803.0,promising_exploratory,
MNQ:C14:matched_EOD:risk1,signal_quality,completed,MNQ,C14,gap,matched_EOD,risk1,815,1636,34947.3,14583.6,18465.4,promising_exploratory,
MNQ:C15:matched_4R:fixed1,signal_quality,completed,MNQ,C15,objective_levels,matched_4R,fixed1,1093,1636,-12369.2,-4399.3,-4014.0,rejected,
MNQ:C15:matched_4R:risk1,signal_quality,completed,MNQ,C15,objective_levels,matched_4R,risk1,1088,1636,-74031.2,-35881.9,-32358.1,rejected,
MNQ:C15:matched_EOD:fixed1,signal_quality,completed,MNQ,C15,objective_levels,matched_EOD,fixed1,1093,1636,-7212.2,-1460.8,-4960.0,rejected,
MNQ:C15:matched_EOD:risk1,signal_quality,completed,MNQ,C15,objective_levels,matched_EOD,risk1,1092,1636,-38048.5,-2561.2,-46817.7,rejected,
MNQ:C16:matched_4R:fixed1,signal_quality,completed,MNQ,C16,opening_momentum_range,matched_4R,fixed1,1521,1636,-2476.9,-366.9,-621.9,promising_exploratory,
MNQ:C16:matched_4R:risk1,signal_quality,completed,MNQ,C16,opening_momentum_range,matched_4R,risk1,1521,1636,-54850.1,-27912.7,-22197.4,promising_exploratory,
MNQ:C16:matched_EOD:fixed1,signal_quality,completed,MNQ,C16,opening_momentum_range,matched_EOD,fixed1,1521,1636,1661.1,2055.1,518.1,promising_exploratory,
MNQ:C16:matched_EOD:risk1,signal_quality,completed,MNQ,C16,opening_momentum_range,matched_EOD,risk1,1521,1636,5216.3,10618.5,-10593.7,promising_exploratory,
MNQ:C17:matched_4R:fixed1,signal_quality,completed,MNQ,C17,opening_momentum_range,matched_4R,fixed1,1603,1636,-393.7,110.8,424.8,inconclusive,
MNQ:C17:matched_4R:risk1,signal_quality,completed,MNQ,C17,opening_momentum_range,matched_4R,risk1,1603,1636,-28606.9,-46.6,8224.2,inconclusive,
MNQ:C17:matched_EOD:fixed1,signal_quality,completed,MNQ,C17,opening_momentum_range,matched_EOD,fixed1,1603,1636,2729.8,-469.7,2914.3,inconclusive,
MNQ:C17:matched_EOD:risk1,signal_quality,completed,MNQ,C17,opening_momentum_range,matched_EOD,risk1,1603,1636,17250.0,-22198.3,58286.0,inconclusive,
NQ:BASE_CANDLE:matched_4R:fixed1,signal_quality,completed,NQ,BASE_CANDLE,opening_momentum_range,matched_4R,fixed1,1959,1966,96269.1,34926.0,43050.8,baseline_control,
NQ:BASE_CANDLE:matched_4R:risk1,signal_quality,completed,NQ,BASE_CANDLE,opening_momentum_range,matched_4R,risk1,1889,1966,186848.6,5975.1,18380.1,baseline_control,
NQ:BASE_CANDLE:matched_EOD:fixed1,signal_quality,completed,NQ,BASE_CANDLE,opening_momentum_range,matched_EOD,fixed1,1959,1966,155114.1,45716.0,65425.8,baseline_control,
NQ:BASE_CANDLE:matched_EOD:risk1,signal_quality,completed,NQ,BASE_CANDLE,opening_momentum_range,matched_EOD,risk1,1940,1966,458969.9,236.4,16889.8,baseline_control,
NQ:BASE_EMA:matched_4R:fixed1,signal_quality,completed,NQ,BASE_EMA,opening_momentum_range,matched_4R,fixed1,1966,1966,113383.4,17755.7,56585.8,baseline_control,
NQ:BASE_EMA:matched_4R:risk1,signal_quality,completed,NQ,BASE_EMA,opening_momentum_range,matched_4R,risk1,1944,1966,448058.2,37904.2,27550.4,baseline_control,
NQ:BASE_EMA:matched_EOD:fixed1,signal_quality,completed,NQ,BASE_EMA,opening_momentum_range,matched_EOD,fixed1,1966,1966,201103.4,48450.7,93875.8,baseline_control,
NQ:BASE_EMA:matched_EOD:risk1,signal_quality,completed,NQ,BASE_EMA,opening_momentum_range,matched_EOD,risk1,1962,1966,1448650.1,104952.7,116442.7,baseline_control,
NQ:BASE_LONG:matched_4R:fixed1,signal_quality,completed,NQ,BASE_LONG,baselines,matched_4R,fixed1,1961,1966,5928.9,21665.9,-15939.2,baseline_control,
NQ:BASE_LONG:matched_4R:risk1,signal_quality,completed,NQ,BASE_LONG,baselines,matched_4R,risk1,1715,1966,-20010.6,-25941.1,-20292.4,baseline_control,
NQ:BASE_LONG:matched_EOD:fixed1,signal_quality,completed,NQ,BASE_LONG,baselines,matched_EOD,fixed1,1961,1966,103658.9,66755.9,26275.8,baseline_control,
NQ:BASE_LONG:matched_EOD:risk1,signal_quality,completed,NQ,BASE_LONG,baselines,matched_EOD,risk1,1907,1966,160503.3,41034.6,7412.2,baseline_control,
NQ:BASE_NONE:matched_4R:fixed1,signal_quality,completed,NQ,BASE_NONE,other,matched_4R,fixed1,0,1966,0.0,0.0,0.0,baseline_control,
NQ:BASE_NONE:matched_4R:risk1,signal_quality,completed,NQ,BASE_NONE,other,matched_4R,risk1,0,1966,0.0,0.0,0.0,baseline_control,
NQ:BASE_NONE:matched_EOD:fixed1,signal_quality,completed,NQ,BASE_NONE,other,matched_EOD,fixed1,0,1966,0.0,0.0,0.0,baseline_control,
NQ:BASE_NONE:matched_EOD:risk1,signal_quality,completed,NQ,BASE_NONE,other,matched_EOD,risk1,0,1966,0.0,0.0,0.0,baseline_control,
NQ:BASE_RANDOM:matched_4R:fixed1,signal_quality,completed,NQ,BASE_RANDOM,baselines,matched_4R,fixed1,1962,1966,14283.8,2615.9,25140.9,baseline_control,
NQ:BASE_RANDOM:matched_4R:risk1,signal_quality,completed,NQ,BASE_RANDOM,baselines,matched_4R,risk1,1472,1966,-52511.3,-17253.2,-18787.2,baseline_control,
NQ:BASE_RANDOM:matched_EOD:fixed1,signal_quality,completed,NQ,BASE_RANDOM,baselines,matched_EOD,fixed1,1962,1966,15078.8,14425.9,39845.9,baseline_control,
NQ:BASE_RANDOM:matched_EOD:risk1,signal_quality,completed,NQ,BASE_RANDOM,baselines,matched_EOD,risk1,1222,1966,-67451.0,-26162.8,-24126.3,baseline_control,
NQ:BASE_SHORT:matched_4R:fixed1,signal_quality,completed,NQ,BASE_SHORT,baselines,matched_4R,fixed1,1957,1966,34609.3,-2799.1,43921.0,baseline_control,
NQ:BASE_SHORT:matched_4R:risk1,signal_quality,completed,NQ,BASE_SHORT,baselines,matched_4R,risk1,1371,1966,-62182.7,-18457.7,-15673.5,baseline_control,
NQ:BASE_SHORT:matched_EOD:fixed1,signal_quality,completed,NQ,BASE_SHORT,baselines,matched_EOD,fixed1,1957,1966,33294.3,-8574.1,47996.0,baseline_control,
NQ:BASE_SHORT:matched_EOD:risk1,signal_quality,completed,NQ,BASE_SHORT,baselines,matched_EOD,risk1,913,1966,-78115.9,-46812.6,-12072.2,baseline_control,
NQ:C01:matched_4R:fixed1,signal_quality,completed,NQ,C01,opening_momentum_range,matched_4R,fixed1,1530,1966,375752.0,105545.7,164142.5,robust_historical_candidate,
NQ:C01:matched_4R:risk1,signal_quality,completed,NQ,C01,opening_momentum_range,matched_4R,risk1,1529,1966,6400704.0,747665.0,989918.0,robust_historical_candidate,
NQ:C01:matched_EOD:fixed1,signal_quality,completed,NQ,C01,opening_momentum_range,matched_EOD,fixed1,1530,1966,443347.0,139980.7,172007.5,robust_historical_candidate,
NQ:C01:matched_EOD:risk1,signal_quality,completed,NQ,C01,opening_momentum_range,matched_EOD,risk1,1530,1966,8058628.9,1573724.1,1137600.8,robust_historical_candidate,
NQ:C02:matched_4R:fixed1,signal_quality,completed,NQ,C02,opening_momentum_range,matched_4R,fixed1,1590,1966,-11179.0,-11831.1,24505.5,inconclusive,
NQ:C02:matched_4R:risk1,signal_quality,completed,NQ,C02,opening_momentum_range,matched_4R,risk1,1173,1966,-55690.4,-24046.9,12903.7,inconclusive,
NQ:C02:matched_EOD:fixed1,signal_quality,completed,NQ,C02,opening_momentum_range,matched_EOD,fixed1,1590,1966,-9459.0,20368.9,-3524.5,inconclusive,
NQ:C02:matched_EOD:risk1,signal_quality,completed,NQ,C02,opening_momentum_range,matched_EOD,risk1,1442,1966,-391.3,36261.8,-9136.8,inconclusive,
NQ:C03:matched_4R:fixed1,signal_quality,completed,NQ,C03,trend_pullback_channel,matched_4R,fixed1,1379,1966,-78282.9,17455.0,-64711.4,inconclusive,
NQ:C03:matched_4R:risk1,signal_quality,completed,NQ,C03,trend_pullback_channel,matched_4R,risk1,629,1966,-67498.1,-10556.5,-26766.9,inconclusive,
NQ:C03:matched_EOD:fixed1,signal_quality,completed,NQ,C03,trend_pullback_channel,matched_EOD,fixed1,1432,1966,-78713.2,21110.0,-68866.4,inconclusive,
NQ:C03:matched_EOD:risk1,signal_quality,completed,NQ,C03,trend_pullback_channel,matched_EOD,risk1,615,1966,-69045.4,-16659.2,-34168.4,inconclusive,
NQ:C04:matched_4R:fixed1,signal_quality,completed,NQ,C04,trend_pullback_channel,matched_4R,fixed1,1935,1966,72301.5,96326.6,-32448.7,promising_exploratory,
NQ:C04:matched_4R:risk1,signal_quality,completed,NQ,C04,trend_pullback_channel,matched_4R,risk1,880,1966,53709.4,78453.0,-11637.8,promising_exploratory,
NQ:C04:matched_EOD:fixed1,signal_quality,completed,NQ,C04,trend_pullback_channel,matched_EOD,fixed1,1935,1966,67511.5,107611.6,-40433.7,promising_exploratory,
NQ:C04:matched_EOD:risk1,signal_quality,completed,NQ,C04,trend_pullback_channel,matched_EOD,risk1,847,1966,35668.7,97947.7,-13303.0,promising_exploratory,
NQ:C05:matched_4R:fixed1,signal_quality,completed,NQ,C05,trend_pullback_channel,matched_4R,fixed1,1959,1966,36469.1,80175.8,-8844.0,promising_exploratory,
NQ:C05:matched_4R:risk1,signal_quality,completed,NQ,C05,trend_pullback_channel,matched_4R,risk1,510,1966,14428.5,21471.4,5864.3,promising_exploratory,
NQ:C05:matched_EOD:fixed1,signal_quality,completed,NQ,C05,trend_pullback_channel,matched_EOD,fixed1,1959,1966,13879.1,81915.8,-26164.0,promising_exploratory,
NQ:C05:matched_EOD:risk1,signal_quality,completed,NQ,C05,trend_pullback_channel,matched_EOD,risk1,412,1966,-27058.0,25340.3,-11394.3,promising_exploratory,
NQ:C08:matched_4R:fixed1,signal_quality,completed,NQ,C08,objective_levels,matched_4R,fixed1,1046,1966,-78344.6,-40203.2,-28656.1,rejected,
NQ:C08:matched_4R:risk1,signal_quality,completed,NQ,C08,objective_levels,matched_4R,risk1,739,1966,-57176.9,-32679.3,-23842.2,rejected,
NQ:C08:matched_EOD:fixed1,signal_quality,completed,NQ,C08,objective_levels,matched_EOD,fixed1,1064,1966,-56276.4,-29788.2,-36191.1,rejected,
NQ:C08:matched_EOD:risk1,signal_quality,completed,NQ,C08,objective_levels,matched_EOD,risk1,790,1966,-56431.0,-4563.4,-44276.4,rejected,
NQ:C09:matched_4R:fixed1,signal_quality,completed,NQ,C09,objective_levels,matched_4R,fixed1,957,1966,-78105.7,-37365.1,-548.0,rejected,
NQ:C09:matched_4R:risk1,signal_quality,completed,NQ,C09,objective_levels,matched_4R,risk1,779,1966,-61164.5,-48106.2,-17681.5,rejected,
NQ:C09:matched_EOD:fixed1,signal_quality,completed,NQ,C09,objective_levels,matched_EOD,fixed1,964,1966,-78351.4,-35640.1,4912.0,rejected,
NQ:C09:matched_EOD:risk1,signal_quality,completed,NQ,C09,objective_levels,matched_EOD,risk1,754,1966,-70493.2,-54486.3,-39257.3,rejected,
NQ:C10:matched_4R:fixed1,signal_quality,completed,NQ,C10,objective_levels,matched_4R,fixed1,1818,1966,20303.2,18827.8,-14001.0,promising_exploratory,
NQ:C10:matched_4R:risk1,signal_quality,completed,NQ,C10,objective_levels,matched_4R,risk1,1729,1966,99233.7,8365.7,4001.3,promising_exploratory,
NQ:C10:matched_EOD:fixed1,signal_quality,completed,NQ,C10,objective_levels,matched_EOD,fixed1,1818,1966,19943.2,38182.8,-26601.0,promising_exploratory,
NQ:C10:matched_EOD:risk1,signal_quality,completed,NQ,C10,objective_levels,matched_EOD,risk1,1671,1966,97740.5,18071.7,6472.4,promising_exploratory,
NQ:C11:matched_4R:fixed1,signal_quality,completed,NQ,C11,vwap,matched_4R,fixed1,1918,1966,60953.2,4492.2,39736.8,promising_exploratory,
NQ:C11:matched_4R:risk1,signal_quality,completed,NQ,C11,vwap,matched_4R,risk1,1902,1966,210878.9,-13609.3,78683.4,promising_exploratory,
NQ:C11:matched_EOD:fixed1,signal_quality,completed,NQ,C11,vwap,matched_EOD,fixed1,1918,1966,128833.2,30612.2,46636.8,promising_exploratory,
NQ:C11:matched_EOD:risk1,signal_quality,completed,NQ,C11,vwap,matched_EOD,risk1,1917,1966,1376355.4,31220.4,130619.8,promising_exploratory,
NQ:C14:matched_4R:fixed1,signal_quality,completed,NQ,C14,gap,matched_4R,fixed1,971,1966,41217.9,27331.3,20264.5,promising_exploratory,
NQ:C14:matched_4R:risk1,signal_quality,completed,NQ,C14,gap,matched_4R,risk1,813,1966,28364.7,-14157.8,12011.8,promising_exploratory,
NQ:C14:matched_EOD:fixed1,signal_quality,completed,NQ,C14,gap,matched_EOD,fixed1,971,1966,74927.9,36871.3,32159.5,promising_exploratory,
NQ:C14:matched_EOD:risk1,signal_quality,completed,NQ,C14,gap,matched_EOD,risk1,829,1966,11787.6,1830.2,-2693.7,promising_exploratory,
NQ:C15:matched_4R:fixed1,signal_quality,completed,NQ,C15,objective_levels,matched_4R,fixed1,876,1966,-78157.6,-41585.2,-42651.8,rejected,
NQ:C15:matched_4R:risk1,signal_quality,completed,NQ,C15,objective_levels,matched_4R,risk1,899,1966,-53559.6,-26523.5,-26384.1,rejected,
NQ:C15:matched_EOD:fixed1,signal_quality,completed,NQ,C15,objective_levels,matched_EOD,fixed1,1169,1966,-78136.9,-25345.2,-78148.9,rejected,
NQ:C15:matched_EOD:risk1,signal_quality,completed,NQ,C15,objective_levels,matched_EOD,risk1,950,1966,-47983.3,-25494.4,-41079.2,rejected,
NQ:C16:matched_4R:fixed1,signal_quality,completed,NQ,C16,opening_momentum_range,matched_4R,fixed1,1826,1966,9737.4,9953.8,-96.0,promising_exploratory,
NQ:C16:matched_4R:risk1,signal_quality,completed,NQ,C16,opening_momentum_range,matched_4R,risk1,1639,1966,-15021.9,-28107.1,-14976.4,promising_exploratory,
NQ:C16:matched_EOD:fixed1,signal_quality,completed,NQ,C16,opening_momentum_range,matched_EOD,fixed1,1826,1966,61647.4,37803.8,8939.0,promising_exploratory,
NQ:C16:matched_EOD:risk1,signal_quality,completed,NQ,C16,opening_momentum_range,matched_EOD,risk1,1818,1966,166905.4,27308.1,-15760.7,promising_exploratory,
NQ:C17:matched_4R:fixed1,signal_quality,completed,NQ,C17,opening_momentum_range,matched_4R,fixed1,1918,1966,42818.2,8641.8,11351.7,inconclusive,
NQ:C17:matched_4R:risk1,signal_quality,completed,NQ,C17,opening_momentum_range,matched_4R,risk1,1918,1966,92093.6,6069.3,15584.1,inconclusive,
NQ:C17:matched_EOD:fixed1,signal_quality,completed,NQ,C17,opening_momentum_range,matched_EOD,fixed1,1918,1966,61598.2,2166.8,24831.7,inconclusive,
NQ:C17:matched_EOD:risk1,signal_quality,completed,NQ,C17,opening_momentum_range,matched_EOD,risk1,1918,1966,84311.6,-18032.3,33587.9,inconclusive,
C06,reddit_candidate,not_run,,C06,vwap,,,,,,,,defer_subjective,Divergence window and scanner behavior are core and not reconstructable objectively without inventing the rule.
C07,reddit_candidate,not_run,,C07,trend_pullback_channel,,,,,,,,defer_subjective,"ATR period, multi-horizon aggregation, and overlapping-position policy are core unknowns."
C12,reddit_candidate,not_run,,C12,vwap,,,,,,,,defer_subjective,Band construction and non-trending regime are both core and inconsistent across sources.
C13,reddit_candidate,not_run,,C13,consolidation_relative_volume,,,,,,,,defer_subjective,Consolidation shape and relative-volume threshold cannot be sourced without visual discretion or a new strategy invention.
C18,reddit_candidate,not_run,,C18,objective_levels,,,,,,,,duplicate_excluded,Not distinct from the mechanically separated C02/C09/C10 level-specific break-retest rules.
PUB:NOISE_AREA_VWAP_SHADOW,published_or_preprint_inspired,completed_shadow_only,,,,,,,,184493.1,,,,
PUB:INTRADAY_MOMENTUM_SHADOW,published_or_preprint_inspired,completed_shadow_only,,,,,,,,,,,,
PUB:MNQ_FALSIFICATION,published_or_preprint_inspired,not_reproduced,,,,,,,,,,,,"Exact GMM features, retraining cadence, stops, and session rules were not all source-complete."
ROBUST:C01:ema_150:volume_0.8,post_selection_robustness,completed_audit_only,NQ,C01,,matched_4R,fixed1,1635,1966,505071.5,,,audit_only,
ROBUST:C01:ema_150:volume_1.0,post_selection_robustness,completed_audit_only,NQ,C01,,matched_4R,fixed1,1583,1966,426816.7,,,audit_only,
ROBUST:C01:ema_150:volume_1.2,post_selection_robustness,completed_audit_only,NQ,C01,,matched_4R,fixed1,1491,1966,318070.9,,,audit_only,
ROBUST:C01:ema_200:volume_0.8,post_selection_robustness,completed_audit_only,NQ,C01,,matched_4R,fixed1,1582,1966,463421.8,,,audit_only,
ROBUST:C01:ema_200:volume_1.0,post_selection_robustness,completed_audit_only,NQ,C01,,matched_4R,fixed1,1530,1966,375752.0,,,audit_only,
ROBUST:C01:ema_200:volume_1.2,post_selection_robustness,completed_audit_only,NQ,C01,,matched_4R,fixed1,1429,1966,288217.1,,,audit_only,
ROBUST:C01:ema_250:volume_0.8,post_selection_robustness,completed_audit_only,NQ,C01,,matched_4R,fixed1,1536,1966,417931.4,,,audit_only,
ROBUST:C01:ema_250:volume_1.0,post_selection_robustness,completed_audit_only,NQ,C01,,matched_4R,fixed1,1483,1966,329286.7,,,audit_only,
ROBUST:C01:ema_250:volume_1.2,post_selection_robustness,completed_audit_only,NQ,C01,,matched_4R,fixed1,1384,1966,247391.6,,,audit_only,
ROBUST:C01:INCLUDE_ROLL_SESSIONS,post_selection_robustness,completed_audit_only,NQ,C01,,matched_4R,fixed1,1558,1995,384704.2,,,audit_only,
WALK_FORWARD:2022,post_selection_walk_forward,completed_audit_only,NQ,C01,,matched_4R,fixed1,,,66400.6,,,audit_only,
WALK_FORWARD:2023,post_selection_walk_forward,completed_audit_only,NQ,C01,,matched_4R,fixed1,,,39145.1,,,audit_only,
WALK_FORWARD:2024,post_selection_walk_forward,completed_audit_only,NQ,C01,,matched_4R,fixed1,,,57661.2,,,audit_only,
WALK_FORWARD:2025,post_selection_walk_forward,completed_audit_only,NQ,C01,,matched_4R,fixed1,,,106481.3,,,audit_only,
```

