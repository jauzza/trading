# r/algotrading NQ/MNQ one-by-one historical test

## Verdict

These are corrected retrospective tests, not proof. Every causal, objectively recoverable Reddit rule was run separately on preserved 2018-2025 Databento data with instrument-specific NQ/MNQ costs. No 2026 market data was read. **No candidate is proven and none passed the full promotion gate.**

The strongest new family was `ALG02_IBS_RANGE`: NQ earned $151,105.00 over 100 trades (PF 1.91, mark-to-market/MAE drawdown -26.41%); MNQ earned $14,564.00 over 80 trades. Both validation and 2024-2025 evaluation were positive, and both remained positive after removing the best 1% of trades. It still failed family-adjusted significance (NQ raw two-sided p=0.0274, BH=0.2621, BY=1.0000) and has no protective stop.

`ALG09_BUY_DIP_20` was also historically positive: NQ $128,387.30, 377 trades, PF 1.31, drawdown -18.43%. But the impossible same-close source diagnostic showed $199,622.30; enforcing a causal next-open fill removed $71,235.00. Its raw two-sided p=0.0599 and BY-adjusted p=1.0000.

The tuned ADX+EMA200 rule made $134,180.50 on NQ but lost $7,922.60 in 2022-2023, so it is inconclusive. MNQ was positive in validation by only $292.80; that is not convincing independent evidence because NQ and MNQ share the same underlying signal.

The family-level White reality-check/SPA did not reject no edge: at the primary 10-session block NQ p=0.1174/SPA=0.1175, MNQ p=0.1227/SPA=0.1296. Block lengths 5 and 20 reached the same conclusion.

## One-by-one results

| Instrument | Candidate | Trades | Net | PF | Max DD | Validation | 2024-25 eval | Net ex best 1% | Evidence |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| NQ | ALG01_REVERSAL | 326 | $13,737.40 | 1.04 | -34.13% | $10,486.20 | $12,952.80 | $-13,147.20 | promising_exploratory |
| NQ | ALG01_DOWN_REVERSAL | 152 | $15,834.80 | 1.12 | -27.18% | $22,525.60 | $-22,003.40 | $1,355.00 | inconclusive |
| NQ | ALG01_MOMENTUM | 576 | $-11,717.60 | 0.98 | -41.75% | $42,827.10 | $-37,959.30 | $-49,577.00 | inconclusive |
| NQ | ALG02_IBS_RANGE | 100 | $151,105.00 | 1.91 | -26.41% | $10,366.50 | $60,213.00 | $136,105.10 | promising_exploratory |
| NQ | ALG04_RSI2_LONG | 33 | $35,311.70 | 1.60 | -24.08% | $9,864.30 | $-1,596.00 | $24,101.80 | inconclusive |
| NQ | ALG04_RSI2_LONG_SHORT | 45 | $58,470.50 | 1.70 | -23.04% | $34,623.50 | $-6,146.20 | $47,260.60 | inconclusive |
| NQ | ALG04_RSI2_ONE_DAY | 49 | $5,290.10 | 1.10 | -23.87% | $-645.80 | $213.10 | $-1,279.80 | inconclusive |
| NQ | ALG05_BB_BASIC_MID | 33 | $79,636.70 | 1.88 | -32.80% | $7,193.90 | $35,154.30 | $60,901.80 | promising_exploratory |
| NQ | ALG05_BB_TREND_MID | 22 | $58,657.80 | 1.84 | -34.63% | $12,419.50 | $20,759.40 | $39,922.90 | promising_exploratory |
| NQ | ALG05_BB_TREND_UPPER | 19 | $90,488.10 | 1.89 | -32.90% | $5,069.60 | $20,019.50 | $65,643.20 | promising_exploratory |
| NQ | ALG09_BUY_DIP_20 | 377 | $128,387.30 | 1.31 | -18.43% | $14,062.90 | $49,092.10 | $47,802.70 | promising_exploratory |
| NQ | ALG03_ADX_DI_INITIAL | 111 | $52,513.90 | 1.37 | -20.64% | $-11,412.80 | $43,976.40 | $23,564.10 | inconclusive |
| NQ | ALG03_ADX_TUNED | 214 | $123,873.60 | 1.29 | -30.32% | $-26,205.40 | $82,314.40 | $57,713.90 | inconclusive |
| NQ | ALG03_ADX_TUNED_EMA200 | 145 | $134,180.50 | 1.58 | -24.75% | $-7,922.60 | $85,511.00 | $94,790.70 | inconclusive |
| MNQ | ALG01_REVERSAL | 275 | $1,067.00 | 1.04 | -4.36% | $1,283.70 | $-120.20 | $-1,051.80 | inconclusive |
| MNQ | ALG01_DOWN_REVERSAL | 127 | $1,546.20 | 1.13 | -3.82% | $2,594.30 | $-2,200.20 | $101.50 | inconclusive |
| MNQ | ALG01_MOMENTUM | 473 | $-2,313.20 | 0.95 | -6.21% | $4,385.80 | $-4,241.10 | $-5,513.70 | inconclusive |
| MNQ | ALG02_IBS_RANGE | 80 | $14,564.00 | 2.00 | -5.59% | $1,445.50 | $5,989.50 | $13,067.40 | promising_exploratory |
| MNQ | ALG04_RSI2_LONG | 26 | $1,222.60 | 1.19 | -3.49% | $975.70 | $-1,117.50 | $103.50 | inconclusive |
| MNQ | ALG04_RSI2_LONG_SHORT | 36 | $3,230.60 | 1.37 | -3.87% | $3,443.00 | $-1,576.80 | $2,111.50 | inconclusive |
| MNQ | ALG04_RSI2_ONE_DAY | 40 | $500.00 | 1.10 | -2.84% | $-293.80 | $-6.60 | $-155.10 | inconclusive |
| MNQ | ALG05_BB_BASIC_MID | 29 | $9,442.40 | 2.23 | -5.42% | $701.10 | $3,509.70 | $7,570.80 | promising_exploratory |
| MNQ | ALG05_BB_TREND_MID | 18 | $5,377.80 | 1.90 | -4.07% | $1,234.50 | $2,068.60 | $3,506.20 | promising_exploratory |
| MNQ | ALG05_BB_TREND_UPPER | 15 | $6,775.50 | 1.82 | -4.48% | $498.90 | $1,057.00 | $4,291.40 | promising_exploratory |
| MNQ | ALG09_BUY_DIP_20 | 316 | $11,114.10 | 1.30 | -2.88% | $953.20 | $4,836.30 | $3,063.70 | promising_exploratory |
| MNQ | ALG03_ADX_DI_INITIAL | 97 | $5,438.20 | 1.41 | -2.79% | $-953.10 | $4,665.30 | $3,598.10 | inconclusive |
| MNQ | ALG03_ADX_TUNED | 189 | $10,956.40 | 1.26 | -6.27% | $-2,875.70 | $6,948.20 | $6,284.20 | inconclusive |
| MNQ | ALG03_ADX_TUNED_EMA200 | 128 | $13,195.30 | 1.58 | -4.19% | $292.80 | $7,762.60 | $9,256.60 | promising_exploratory |

## What survived and what failed

- **Best candidate for further prospective work:** `ALG02_IBS_RANGE`. It had the strongest combination of PF, period consistency, cost tolerance, and tail-removal survival. It remains exploratory because the search-adjusted tests failed and the source has no stop.
- **Second candidate:** `ALG09_BUY_DIP_20`. It has enough trades and positive validation/evaluation, but its edge shrank materially when the impossible same-close fill was corrected, and it failed family-adjusted inference.
- **Bollinger variants:** positive in both later periods, but only 15-33 trades, no stop, NQ drawdowns around 33-35%, and no adjusted significance. Too sparse for a trading conclusion.
- **ADX variants:** headline full-sample profits came mainly outside the 2022-2023 validation period. The tuned NQ variants failed validation.
- **RSI2:** long and long/short variants lost money in 2024-2025; the one-day version was weak and tail-dependent. Not promoted.
- **Daily reversal/momentum:** reversal profits were unstable by year and tail-sensitive; momentum lost money overall and badly in 2024-2025. Not promoted.

## Relation to the earlier r/Daytrading tournament

The objective Daytrading slate was already executed in Phase 5 and corrected again in Phases 6-7. Corrected C01 earned $117,590.50 over 1,495 NQ trades with PF 1.1621 and -14.68% maximum drawdown, but failed the stronger conclusion because profits were right-tail dependent, the best 1% removal made it negative, and reality-check/SPA evidence did not establish superiority. The present r/algotrading run does not overturn that result. ALG02 and ALG09 diversify the entry horizon, but neither passes adjusted significance or operational-risk gates.

So the combined answer is: **some rules made money historically; no Reddit rule is proven; no rule is authorized for live trading; the most defensible next test is frozen prospective MNQ paper execution of ALG02 and ALG09, not another retrospective parameter search.**

## Interpretation rules

- `robust_historical_candidate_not_proven` means every frozen historical gate passed; it still is not proof or a clean holdout result.
- `promising_exploratory` means full, validation, and historical-evaluation P&L were positive but at least one robustness gate failed.
- `inconclusive` means the periods or robustness checks disagree.
- `rejected_historically` means full and validation evidence are non-positive under the frozen implementation.
- Strategies without explicit stops fail the protective-stop gate even when historical P&L is positive.

## Source fidelity and corrections

Daily close-based signals are entered at the next RTH open so the completed close is actually known. The source-literal same-close ALG09 diagnostic is recorded separately and excluded from inference because it is not executable without look-ahead. ADX/DMI/ATR use standard Wilder period 14 because the Reddit post did not state a period. Bollinger bands use 20 SMA and two population standard deviations. Continuous-contract mapping changes force a flat exit so roll gaps cannot manufacture profit. Drawdown is the worse of daily mark-to-market and an intratrade MAE proxy, not merely the closed-trade equity curve.

## Non-reproducible leads

SL06 is a trend-feature tutorial rather than a trade rule; SL07 needs two calendar-spread legs; SL08 needs a point-in-time ETF universe; SL10 is methodology; SL11 omits its oscillator/filter/exit definitions. They were not approximated.

## Statistical warning

All 2018-2025 observations were previously inspected. Bootstrap and multiple-testing corrections measure historical uncertainty and search burden; they do not create a new holdout. Reddit publication dates are provenance, not ex-ante evidence.

`2026 MARKET HOLDOUT: UNTOUCHED`
