# Phase 7 leakage audit

- Baseline replay exact: **True**.
- Raw-cache hashes unchanged: **True**.
- Protected 2026 market data opened: **False**.
- All predictive features are drawn only from `PRE_ENTRY_FEATURES`; outcome and path columns remain separate.
- Expanding folds fit imputation, scaling, thresholds, and models on prior years only.
- Earlier-similar-day analysis fits imputation/scaling for each test observation using earlier rows only.
- Completed-candle information is unavailable until candle completion; corrected C01 entries occur on 15-minute boundaries.
- Scheduled macro flags contain no released values or later revisions.
- The intentionally leaked outcome feature reached AUC 1.000000 and was correctly rejected as a pipeline detector.
- Post-entry management never becomes a pre-entry filter.
