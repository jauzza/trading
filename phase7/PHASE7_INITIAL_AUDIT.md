# Phase 7 initial audit

## Executive status

The corrected causal Phase 6 C01 is reproducible: **PASS**. The protected-market guard is effective before file access: **PASS**. Discovery may proceed only because both gates passed.

## Frozen

- `C01-v1-causal-timing-correction`: completed 15-minute signal, next one-minute entry, EMA200, prior-bar volume expansion, breakout-bar extreme stop, 4R target, 15:55 fallback, one trade/session, fixed NQ execution costs.
- Phase 6 artifacts and preserved paid Databento/FRED cache.
- 2026 as the untouched market holdout.

## Invalid

- Phase 5 C01: `INVALID_LOOKAHEAD_HISTORICAL_RESULT`. Its 15-minute bar was entered ten minutes before completion and it is never evidence in Phase 7.

## Exploratory

- Phase 5 candidates C04/C05/C10/C11/C14/C16, Phase 6 post-entry management, regime clusters, interactions, and all 2018-2025 model findings.

## Data present

- Preserved NQ one-minute OHLCV 2016-2025; MNQ from launch through 2025; lagged FRED VIX; scheduled macro calendar; execution ledgers; Phase 2-6 derived artifacts; Reddit-derived candidate catalog and audit.

## Data absent

- Tick order, bid/ask history, queue position, Level 2, true delta, volume-at-price, verified point-in-time private ISM/retail-sales history, breadth, ES/rates/DXY, and trainable TCN framework.

## Previously tested and redundant

- Core fills/costs/session/DST/holiday/roll rules, matched first-candle/EMA/long/short/random controls, the 3x3 EMA-volume surface, basic similar-day k grid, and broad Phase 5 candidate tournament are not blindly repeated. Phase 7 reuses them only for equal-treatment comparison or bounded stress.

## Open questions prioritized

1. Whether corrected C01 failures have a transportable pre-entry signature.
2. Whether causal early management improves tails without deleting rare winners.
3. Whether any independent strategy earns on corrected-C01 losing sessions and survives its own tails.
4. Whether 4R is structurally special or merely right-skew selection.
5. Whether any result survives aligned multiple testing, block sensitivity, 4x costs, and missed trades.

## Known historical bugs

- Phase 5 C01 incomplete-bar look-ahead; earlier phases also corrected spread omission, fill direction, stops, cost reconciliation, independent equity resets, overnight EMA, DST/holiday/roll handling, and confirmed-pivot availability.

## Reproducibility and protection

- The isolated Phase 7 replay matched all 1,495 corrected entries/exits/stops/targets/costs/P&L values and $117,590.50 net.
- Guard scans manifest metadata first and rejects `year >= 2026` before path reads or hashing.
- Current pre-Phase-7 registry count: 56 completed Phase 6 configurations; Phase 7 receives a separate hard budget of 150.

## Repository limitations

- `MAIN_CODEX_START_HERE.md` from the external Reddit handoff is not present in this repository; its integrity and reconciled facts are available in `docs/reddit_handoff_audit.md`.
- Git contains no resolvable commit and the working tree is entirely untracked, so the contract records `commit: null` plus content hashes.
