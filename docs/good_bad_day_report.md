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
