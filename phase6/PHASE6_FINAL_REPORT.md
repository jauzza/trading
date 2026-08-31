# Phase 6 final report

## Executive verdict

Phase 6 discovered a critical look-ahead timing defect in Phase 5 C01. The reported Phase 5 result (375,752.00, 1530 trades) entered ten minutes before its 15-minute signal bar completed and is not causal. The preserved result was not overwritten. The corrected C01 produced 117,590.50 over 1495 trades, profit factor 1.1621, max drawdown -14.68%, and 6/8 positive years.

This correction—not another indicator—is the dominant Phase 6 finding. All taxonomy, model, path, and complementarity work below uses corrected trades.

## A. Why does corrected C01 work?

It waits for a completed 15-minute displacement beyond the opening range, requires volume expansion versus the immediately preceding completed bar, and trades only with the completed-bar EMA200 direction. Its strongest recurring winner descriptions were: vwap_alignment, clear_key_level_room, overnight_alignment, moderate_opening_range, strong_relative_volume. These are descriptions; only chronological prediction tests can promote them.

## B. Why does corrected C01 fail?

The most frequent mechanical loss tags were low_volume_follow_through (522), early_adverse_excursion (426), overnight_conflict (423), wrong_side_trend (417), breakout_failure (413). Categories overlap because a single failed trade can reject immediately, close inside the range, and remain in overnight/VWAP conflict. Exact thresholds were learned only on 2018–2021 and frozen for later assignment.

## C. Can bad days be predicted before entry?

**Not reliably enough for promotion.** The strongest tested model was `gradient_boosting_shallow` with expanding-fold OOS AUC 0.57053, Brier 0.229092, 4/6 annual folds improving net P&L, and 80.7% coverage. A classifier is not promoted unless economic improvement is stable across chronology and retains substantial coverage.

## D. Can good days be predicted?

Winner characteristics are measurable, but the same pre-entry models did not transport strongly enough to declare a good-day selector. Earlier-only analogue AUCs were k=5: 0.498066, k=10: 0.510269, k=20: 0.525094, k=50: 0.513273. These remain descriptive diagnostics.

## E. Can C01 be improved?

The best bounded early-management rule was `inside_or_5m`, changing net by 12,180.00, triggering 87 times, and producing 6/8 positive years. It is explicitly **POST_ENTRY_MANAGEMENT**, not a pre-entry predictor. It remains exploratory because it was evaluated after the causal timing defect was found and did not repair the two losing years.

## F. Did we discover a genuinely independent strategy?

The two new mechanical strategies were: P6_RETEST (-1,282.90), P6_FAILURE_REVERSAL (-7,432.80). Existing Phase 5 objective candidates and controls were also re-evaluated for complementarity against corrected C01 rather than ranked only by standalone return.

## G. Does any candidate complement C01?

The strongest non-control candidate that made money specifically when corrected C01 lost was `C04`: 8,140.30 on C01 losing sessions, correlation 0.144873, and combined one-contract net 189,892.00. It still failed standalone transport/tail gates, so it is not promoted.

## H. Did anything outperform corrected C01?

No candidate is declared superior merely from historical total P&L. Equal execution standards, period transport, tail removal, controls, and multiple testing govern promotion. Full results are in `phase6_strategy_results.json` and `phase6_complementarity.json`.

## I. Is the edge regime-dependent?

Yes, expectancy differs across the four development-fitted pre-entry clusters and across opening-range, gap, volume, timing, VWAP, and key-level states. The labels are assigned without outcome-based names and later years are never used to refit development cluster centers.

## J. Is the edge tail-dependent?

Corrected C01 net after removing its best trade is 99,385.60; after the best five, 58,426.00; after the best 1%, -7,373.00; and after the best 5%, -237,617.00. Median trade is -270.10. This is materially more informative than headline net alone.

At 2× costs it earned 87,541.00; at 4×, 27,442.00; and with a causal one-minute delay, 90,794.40. The nearby parameter surface is an audit, not a source of replacement settings.

## K. What failed?

- The original Phase 5 C01 timing failed causal availability.
- Pre-entry machine-learning filters were rejected unless they improved at least four chronological folds with adequate coverage.
- Similar-day results are descriptive, not selected by the best neighbor count.
- Shuffled-label and unconditional controls remain selection-ineligible.
- Any strategy or interaction that only looked attractive after all 2018–2025 outcomes were observed remains exploratory.

## L. What should be frozen for a future holdout?

No Phase 6 candidate cleared the final freeze gate. The protected future holdout remains unopened.

## Data needs

No paid news API is justified. Scheduled point-in-time macro flags are sufficient to test whether known events explain corrected C01 failures. One-minute OHLCV cannot reconstruct queue position, L2, true delta, footprint, or intrabar event order; those remain known limitations rather than reasons to buy data speculatively.

## Research budget and frontend

The registry consumed 56 of 110 meaningful configurations. **NO FRONTEND CHANGES WERE NECESSARY.**

## Statistical summary

White reality-check p 0.89854203; SPA-style p 0.89426211. See `phase6_statistical_report.md` and machine-readable bootstrap/multiple-testing artifacts for exact families, resamples, and block assumptions.
