# Phase 6 engine audit

## Scope and protected boundary

The audit covers the frozen Phase 5 C01 implementation, execution engine, NQ/MNQ specifications, session construction, aggregation, indicators, exclusions, controls, and inference code. It uses repository code and preserved 2018–2025 artifacts only. The `ProtectedMarketDataGuard` rejects any manifest partition or path with `year >= 2026` before a market file is opened or hashed.

## Executive finding

**A critical C01 signal-timing bug is confirmed.** The Phase 5 implementation aggregates a 15-minute bar whose timestamp is its opening minute, but `_next_minute` advances that timestamp by only five minutes. A completed bar beginning at 09:45 is not known until 10:00, yet Phase 5 could enter at 09:50. All 1,530 stored NQ C01 trades have entry-minute modulo 15 equal to five, proving the systematic error. The Phase 5 result must remain preserved as the originally reported result, but it is not a causal C01 baseline.

Phase 6 will not silently rewrite C01-v1. It will produce a separately identified corrected causal implementation and compare it with the preserved Phase 5 artifact.

## Classified audit table

| Area | Classification | Evidence and disposition |
|---|---|---|
| 15-minute C01 decision timing | **incorrect** | `_aggregate` timestamps the 15-minute bar at its first minute. `c01_signals` passes that bar to `_next_minute`, whose five-minute branch produces entry at anchor + 5 rather than anchor + 15. Every stored NQ C01 entry occurs at minute 05/20/35/50. Correct in a new Phase 6 causal implementation. |
| C01 one-trade-per-session | confirmed correct | `_first_signal` limits the signal list to one; the runner executes only `candidate_items[0]`. |
| Opening range construction | confirmed correct | `_aggregate(rth, 15)` requires fifteen consecutive one-minute bars; the first bar is 09:30–09:44. |
| Volume definition | confirmed correct | Fifteen-minute volume is the sum of constituent one-minute trade volume. The comparison uses the immediately preceding completed 15-minute bar. |
| EMA causality | confirmed correct with caveat | EMA uses only completed 15-minute closes through the signal bar. Including the just-completed signal bar is causal at its close. |
| EMA warm-up count | potentially questionable | The `index < ema_period` condition requires 200 prior bars plus the current bar (201 total), although the text says a 200-bar warm-up. Phase 6 will report this and keep an explicit definition. |
| EMA history population | potentially questionable | History is updated only after accepted, non-roll sessions. This is reproducible but is not literally every completed RTH bar. Test as a sensitivity rather than silently changing the baseline. |
| First outside close versus first qualifying outside close | potentially questionable | The loop continues after an outside close that fails volume. This implements “first qualifying breakout,” whereas a stricter reading could cancel the day after the first low-volume break. Treat as a rule sensitivity. |
| Entry reference price | confirmed correct once timing is corrected | Entry is the next eligible one-minute open; execution applies adverse one-tick slippage. |
| Stop definition and tick rounding | confirmed correct | Long stops round down, short stops round up, and invalid/crossed stops are rejected. |
| Target definition | confirmed correct | Target is four times reference entry-to-stop distance and is tick-rounded. |
| Same-bar stop/target ambiguity | confirmed correct | Both touched in one minute resolves adverse-first. |
| Gap-through stop | confirmed correct | Long stops fill at `min(open, stop)` and shorts at `max(open, stop)`, followed by adverse exit slippage. |
| Forced session exit | confirmed correct | Future bars are limited through the 15:55 New York minute; unresolved positions use that minute's close. |
| Spread, slippage, fees | confirmed correct | Stored C01 trades reconcile `gross - total_costs = net` to floating-point precision. One NQ contract pays $5 spread, $10 two-sided slippage, and $5.10 fees, or $20.10 total. |
| NQ/MNQ assumptions | confirmed correct | Point values are $20/$2; fee presets total $5.10/$2.40 round trip; margins are $22,000/$2,200. |
| MAE/MFE on exit bar | potentially questionable | Full one-minute high/low is incorporated before exit detection, so MAE/MFE may include movement after the actual intrabar exit. Do not use stored MAE/MFE for fine path timing; rebuild causal minute-path measures. |
| Session timezone/DST | confirmed correct | Timestamps are converted from UTC to `America/New_York`; NYSE schedule supplies DST-aware opens, holidays, and early closes. Existing DST and Monday overnight tests pass. |
| Data-quality exclusions | confirmed correct | Missing minutes, duplicates, suspicious bars, degraded dates, and roll dates are rejected before trading. |
| Independent-period equity | confirmed correct | Development, validation, and historical-evaluation states each begin at $100,000. |
| Eligible no-trade inference rows | confirmed correct | Session arrays map absent trades to zero rather than dropping the session. |
| Multiple-testing and dependence | confirmed correct for Phase 5 scope | Session-aligned stationary bootstrap, BH/BY, White reality check, SPA-style maximum, DSR, and CSCV/PBO are present. |
| Protected market holdout | confirmed correct | Guard checks manifest metadata and path partition labels before reads/hashes. No Phase 6 process may enumerate or inspect a protected market partition. |

## Required correction policy

1. Preserve the original Phase 5 C01 summaries and trades unchanged.
2. Introduce a new causal Phase 6 C01 implementation whose decision becomes available at the end of the complete 15-minute bar and whose entry is the following one-minute open.
3. Give the corrected result a distinct version and specification hash.
4. Rebuild path, taxonomy, predictor, and complementarity research from the corrected trades—not the contaminated Phase 5 timestamps.
5. Re-run execution reconciliation, timing, leakage, and deterministic-output tests before interpreting Phase 6 results.
