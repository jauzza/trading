# Phase 7 engine invariants

All invariants are enforced by executable tests in `backend/tests/` and Phase 7 artifact regression tests.

| Invariant | Status |
|---|---|
| No future bars / completed-candle availability | PASS |
| Protected 2026 rejection before read/hash | PASS |
| No future volume, VWAP, EMA, or macro predictor | PASS |
| Overnight boundaries, DST, Mondays, holidays, rolls | PASS |
| Post-entry predictor exclusion | PASS |
| Fee/spread/slippage/gross-to-net reconciliation | PASS |
| Tick rounding, gap-through stops, adverse-first ambiguity | PASS |
| Forced exits and one trade/session | PASS |
| Independent equity reset | PASS |
| Deterministic replay | PASS |
| Registry integrity and model train/test separation | PASS |
