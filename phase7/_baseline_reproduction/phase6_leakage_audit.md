# Phase 6 leakage audit

## Result

No protected market data was accessed. Raw-cache immutability: **PASS**.

- The corrected C01 decision timestamp is the completed 15-minute anchor plus 15 minutes; entry is the next one-minute open.
- Every pre-entry feature is constructed from the prior session, overnight data before RTH, or bars strictly earlier than entry. Breakout-bar features become known only at completion.
- Price-path labels and early-management fields are stored separately and are never included in `PRE_ENTRY_FEATURES`.
- Primary model evaluation uses expanding chronological folds; no random session shuffle is used for selection.
- Earlier-similar-day searches use only rows with an earlier date and refit imputation/scaling on the earlier set.
- A deterministic shuffled-label logistic control achieved OOS AUC 0.546787; it is selection-ineligible.
- Same-day final close, future volume, future VWAP, future EMA, future labels, and post-entry news are excluded from pre-entry predictors.
- Session arrays retain eligible no-trade days as zero for inference.
- Execution retains adverse-first same-bar resolution, gap-through stops, direction-aware fills, tick rounding, and exact cost reconciliation.
