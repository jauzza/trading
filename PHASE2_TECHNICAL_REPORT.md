# Phase 2 technical correction report

Generated from the corrected local 2018–2025 Databento cache. No raw Databento or FRED file changed. No 2026 file exists and the research runner rejects any 2026 partition before reading it.

## Executive conclusion

The corrected 09:30 full-overnight-EMA 4R strategy is profitable in the historical sample after the stated baseline costs, but the EMA direction filter is not proven to add value. The matched first-candle-direction control is also profitable. Their session-aligned difference is statistically unresolved after stationary bootstrap and multiple-comparison correction. Therefore the result is **promising exploratory evidence**, not a validated edge, and no 2026 holdout specification was frozen.

The corrected 10:00 confirmed-pivot rule does not show stable evidence. Its 4R form is approximately flat overall and loses in the 2024–2025 historical evaluation. The mechanical 2R form is rejected.

## Corrections implemented

- Applied the round-trip spread directly to every trade’s net P&L.
- Split reference prices from actual slipped entry/exit fills and made gross-to-net reconciliation exact.
- Separated commission, exchange, clearing, and regulatory fees with distinct NQ and MNQ assumptions.
- Corrected direction-aware long/short fills, gap-through stops, tick rounding, target rounding, conservative same-bar handling, and forced session exits.
- Added whole-contract risk sizing, fixed-dollar/fixed-contract modes, max-contract limits, and contract-specific margin constraints ($22,000 NQ; $2,200 MNQ research assumptions).
- Reconstructed the 12 EMA from the prior calendar day at 18:00 New York through 09:29, including Sunday evening for Monday, timezone-aware DST, year boundaries, holidays, and roll-session exclusions.
- Added same-day EMA and prior-RTH EMA contexts as matched controls.
- Made discovery, validation, and historical-evaluation simulations start from independent $100,000 equity. Anchored-period results are retained separately for audit only.
- Made Strategy A’s structural stop use only pivots whose right-hand confirmation bars were already available. The sweep-extreme interpretation is separately labeled.
- Added matched 4R controls: candle direction, always long, always short, seeded random, overnight direction, same-day EMA, full-overnight EMA, RTH EMA, EMA slope, EMA/candle agreement, EMA slope+candle agreement, and 09:35/09:40/09:45 shifted windows.
- Replaced trade-only bootstrap inference with accepted-session alignment where no-trade sessions equal zero, 50,000 Politis–Romano stationary resamples, BH and BY adjustments, a White reality check, and a studentized SPA-style maximum test.
- Rebuilt the UI as a simple dark strategy tester with real cached metrics, a large 1m/5m candlestick chart, EMA and trade markers, stop/target areas, clickable trades, cost reconciliation, equity/year charts, controls comparison, and an optional advanced-research panel.

## Execution assumptions

| Contract | Point value | Round-trip fees | Slippage | Spread | Margin assumption |
|---|---:|---:|---:|---:|---:|
| NQ | $20 | $5.10 | 1 tick per side | 1 tick round trip | $22,000 |
| MNQ | $2 | $2.40 | 1 tick per side | 1 tick round trip | $2,200 |

All baseline same-bar ambiguities resolve adverse-first. Stops gap through at the opening price if the market opens beyond the stop. Remaining positions exit at 15:55 New York.

## Corrected Strategy B results

| Run | Net P&L | Return | Trades | Win rate | Profit factor | Avg. R | Max DD | Positive years |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NQ full-overnight EMA, 1 contract | $113,383 | 113.38% | 1,966 | 27.87% | 1.117 | 0.1075R | −26.35% | 7/8 |
| NQ first-candle control, 1 contract | $96,269 | 96.27% | 1,959 | 27.11% | 1.095 | 0.0792R | −27.97% | 7/8 |
| NQ full-overnight EMA, independent 1% sizing | $448,058 | 448.06% | 1,944 | 27.88% | 1.156 | 0.1087R | −25.38% | 7/8 |
| NQ EMA, 2× cost stress, 1% sizing | $183,662 | 183.66% | 1,893 | 28.00% | 1.104 | 0.0593R | −25.45% | 7/8 |
| NQ EMA, 4× cost stress, 1% sizing | −$62,747 | −62.75% | 786 | 25.57% | 0.791 | −0.2998R | −63.66% | 0/8 |
| MNQ full-overnight EMA, 1 contract | $6,737 | 6.74% | 1,636 | 27.63% | 1.073 | 0.0493R | −4.40% | 5/7 |
| MNQ full-overnight EMA, independent 1% sizing | $142,468 | 142.47% | 1,636 | 27.63% | 1.103 | 0.0493R | −29.79% | 5/7 |

The 4R strategy remains profitable under the stated baseline and 2× costs, but not at 4× costs. This makes execution quality material.

### Independent period results: NQ EMA 4R, one contract

| Period | Net P&L | Return | Trades | Avg. R |
|---|---:|---:|---:|---:|
| Discovery 2018–2021 | $39,042 | 39.04% | 981 | 0.1113R |
| Validation 2022–2023 | $17,756 | 17.76% | 493 | 0.0794R |
| Historical evaluation 2024–2025 | $56,586 | 56.59% | 492 | 0.1280R |

The 2024–2025 period is not called blind because it was already inspected during the earlier research cycle.

## Does EMA add value?

No statistically defensible incremental EMA value was demonstrated.

- Confirmatory aligned window: 2018–2023.
- Observed EMA-minus-candle difference: +0.03287R per accepted session.
- Stationary-bootstrap 95% interval: −0.02168R to +0.08767R.
- Raw paired p-value: 0.11944.
- BH-adjusted p-value: 0.17252.
- BY-adjusted p-value: 0.54864.
- White reality-check p-value: 0.76236.
- SPA-style p-value: 0.26299.
- 2024–2025 EMA-minus-candle difference: +0.01584R per session; p=0.39531.

Both EMA and candle direction may be proxying the same opening-candle behavior. The historical profit is interesting, but the EMA-specific story is not supported.

## Corrected Strategy A results

| Run | Net P&L | Return | Trades | Avg. R | Max DD | Classification |
|---|---:|---:|---:|---:|---:|---|
| Confirmed pivot, 4R, 1% | −$522 | −0.52% | 1,185 | 0.0042R | −32.30% | Inconclusive; 2024–2025 negative |
| Confirmed pivot, 2R, 1% | −$39,192 | −39.19% | 1,044 | −0.0672R | −42.18% | Inconclusive/weak |
| Sweep-extreme stop, 4R, 1% | $16,606 | 16.61% | 1,305 | 0.0331R | −32.31% | Exploratory only; discovery negative |
| Mechanical 2R, 1% | −$73,138 | −73.14% | 1,258 | −0.2082R | −74.02% | Rejected |

The structurally correct pivot implementation does not justify further parameter optimization.

## Concentration and exceptional trades

The NQ one-contract EMA run was positive in seven of eight years. Its five largest winners are only 3.63% of gross profit, and net P&L remains $74,054 after removing them. The result is not driven by a few isolated trades. It is still year-sensitive: 2023 lost $9,975 while 2024 earned $40,035, so stability is imperfect.

## NQ, MNQ, and manual practicality

- NQ has the stronger historical dollars and expectancy, but one contract has a median 28.75-point stop (about $575 reference risk before costs), a median $20.10 round-trip cost under the assumptions, and materially larger day-to-day P&L. A $100,000 account is much more credible than a small account for one NQ.
- MNQ has the same signal timing with one-tenth point value, much smaller fixed-contract drawdown, and is operationally better for small accounts or manual rehearsal. Its edge estimate is weaker and nearly flat in 2022–2023.
- The rule requires a decision immediately after the 09:30–09:34 candle and entry at the 09:35 open. Median trade duration is about 87 minutes. This is manually executable only with a prepared order ticket, bracket orders, reliable clock/data, and disciplined no-chase rules.
- One-minute testing cannot model queue position, fast-spread expansion, or exact intrabar sequence. Because profitability fails at 4× costs, manual fills should be paper-tracked against these assumptions before any live use.

## Evidence classification

- Strategy B full-overnight EMA 4R: **promising exploratory**, not EMA-validated.
- Strategy B first-candle 4R control: **promising exploratory**.
- Always-long and always-short controls: **rejected**.
- Strategy A confirmed pivot 4R: **inconclusive**.
- Strategy A confirmed pivot 2R: **weak/inconclusive**.
- Strategy A mechanical 2R: **rejected**.
- Strategy A sweep-extreme 4R: **exploratory only**, not the confirmed-pivot hypothesis.
- Any claim of genuine holdout evidence: **not available**.

## Holdout decision

A frozen 2026 test is not justified. The candidate fails the predeclared incremental-value gate against the matched candle control and fails the family-level reality-check/SPA tests. 2026 remains completely untouched.

## Verification

- 34 Python engine/data/statistics/session tests passed.
- Production frontend build passed.
- Two rendered-HTML safety tests passed.
- API overview, trades, and session/EMA endpoints passed integration checks.
- Browser checks passed for real-data rendering, 1m/5m switching, NQ/MNQ switching, trade navigation, advanced-research toggle, and the mobile breakpoint.
- All 34 raw cache file SHA-256 hashes matched before and after both corrected research runs.
