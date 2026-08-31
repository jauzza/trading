# Opening-Candle Direction vs EMA — Phase 3 Technical Report

Generated from the preserved local Databento/FRED cache. All headline simulations use completed sessions dated 2018-01-01 through 2025-12-31. The prior evening needed to form an overnight session may occur before the research date boundary. No 2026 market observation was downloaded, read, or tested; 2026 remains the reserved holdout.

## Executive decision

The simplest historically attractive rule is: at the 09:35 New York one-minute open, trade in the body direction of the completed 09:30–09:34 opening candle, use the opposite side of that candle as the stop, and use a wide asymmetric exit such as 4R.

That is a promising exploratory candidate, not a proven edge. The EMA version earned more in this sample, but its incremental value was not statistically resolved (Hansen SPA p = 0.118). The simple rule itself was also not resolved against zero at 5% (p = 0.076). Therefore the EMA should not be part of the core rule, and no candidate should yet be frozen for a 2026 holdout.

## Data, execution, and validation controls

- Licensed cached one-minute NQ and MNQ data only; no new Databento purchase or redownload.
- America/New_York session construction with the actual previous-evening futures session, Sunday-to-Monday handling, daylight-saving transitions, holidays, early closes, and continuous-contract rolls.
- Signal is known only after the 09:30–09:34 five-minute candle closes; intended entry is the 09:35 one-minute open.
- NQ: $20/point, 0.25-point tick, one tick spread per round trip, one tick slippage on entry and exit, and $5.10 round-trip fees.
- MNQ: $2/point, the same tick assumptions, and $2.40 round-trip fees.
- Long/short fills, gap-through stops, adverse-first same-bar ambiguity, tick rounding, spread, slippage, fees, and gross-to-net reconciliation are applied to trade P&L.
- Fixed-one-contract results isolate strategy economics. Account feasibility is a separate 1%-risk, whole-contract, margin-aware replay; skipped trades are reported instead of silently shrinking the cost sample.
- Research-period simulations restart account equity rather than inheriting equity from an earlier period.
- Phase 3 raw 4R trades reconcile exactly to the corrected engine cache: 1,959 trades, zero maximum per-trade P&L difference, and $96,269.10 aggregate net profit.

## Primary NQ comparison

| Rule | Trades | Net profit | Avg/trade | Win rate | Profit factor | Max drawdown | Positive years |
|---|---:|---:|---:|---:|---:|---:|---:|
| First-candle direction | 1,959 | $96,269 | $49.14 | 27.11% | 1.095 | -27.97% | 7/8 |
| Full-overnight EMA | 1,966 | $113,383 | $57.67 | 27.87% | 1.117 | -26.35% | 7/8 |
| Candle and EMA agree | 1,740 | $97,666 | $56.13 | 28.28% | 1.107 | -23.67% | 7/8 |
| Overnight direction | 1,959 natural population | $30,744 | — | — | — | — | — |
| Seeded random direction | 1,959 natural population | $2,129 | — | — | — | — | — |
| Always long | 1,959 natural population | $5,929 | — | — | — | — | — |
| Always short | 1,959 natural population | $34,609 | — | — | — | — | — |

On the 1,959 sessions shared by the simple and EMA variants, EMA net was $114,919 versus $96,269 for simple, a matched difference of $18,650. The improvement is positive but uncertain. Same-day EMA produced the same directions and P&L as the full-overnight EMA in this particular sample; that equivalence is an empirical result, not permission to omit correct overnight construction.

The simple rule was not merely long equity-index drift: long trades earned $36,378 and short trades earned $59,891. Always-long and always-short controls were much weaker.

## Pure execution-cost stress

The exact same 1,959 matched trades are retained at every cost level.

| Cost multiple | All-in NQ round trip | Simple net | EMA net on matched sessions |
|---:|---:|---:|---:|
| 1.0× | $20.10 | $96,269 | $114,919 |
| 1.5× | $30.15 | $76,581 | $95,231 |
| 2.0× | $40.20 | $56,893 | $75,543 |
| 2.5× | $50.25 | $37,205 | $55,855 |
| 3.0× | $60.30 | $17,517 | $36,167 |
| 3.5× | $70.35 | -$2,171 | $16,479 |
| 4.0× | $80.40 | -$21,859 | -$3,209 |

The simple rule’s linear break-even all-in cost is approximately $69.24 per NQ round trip, about 3.44 times the $20.10 baseline. One additional slippage tick on each side leaves $76,679 net and PF 1.075. This is a useful buffer in fixed-contract economics, not proof that all real manual fills will resemble the model.

## Account feasibility at 1% risk and baseline costs

| Instrument | Start | Executed / eligible | Skipped | Net profit | Max drawdown |
|---|---:|---:|---:|---:|---:|
| NQ | $10,000 | 0 / 1,959 | 1,959 | $0 | 0.0% |
| NQ | $25,000 | 230 / 1,959 | 1,729 | -$1,488 | -18.47% |
| NQ | $50,000 | 972 / 1,959 | 987 | $28,220 | -21.72% |
| NQ | $100,000 | 1,889 / 1,959 | 70 | $186,849 | -30.43% |
| MNQ | $10,000 | 1,302 / 1,632 | 330 | $3,514 | -38.46% |
| MNQ | $25,000 | 1,628 / 1,632 | 4 | $17,007 | -40.26% |
| MNQ | $50,000 | 1,632 / 1,632 | 0 | $47,974 | -37.78% |
| MNQ | $100,000 | 1,632 / 1,632 | 0 | $108,597 | -32.49% |

NQ is not usable at $10,000 under these risk/margin constraints. At $25,000 it misses most sessions and was negative. At $50,000 it is only partially available; at $100,000 it is operationally much more representative, but its drawdown is still severe. These path-dependent figures are feasibility scenarios, not expected account returns.

MNQ fixed-one-contract economics are positive but thin: 1,632 trades, $6,059 net, $3.71 average trade, $6,365 total costs, and PF 1.064. MNQ is the more sensible rehearsal/small-account instrument, but fees consume a meaningful share of its gross edge. Four-times-cost scenarios were negative for both instruments.

## Profit concentration and missed trades

Profitability depends materially on the upper tail:

| Removed observation | Removed P&L | Share of net | Remaining net |
|---|---:|---:|---:|
| Best 5 trades | $39,150 | 40.67% | $57,120 |
| Best 10 trades | $69,804 | 72.51% | $26,465 |
| Best 20 trades | $125,318 | 130.17% | -$29,049 |
| Best month (2022-10) | $22,583 | 23.46% | $73,686 |
| Best quarter (2022 Q2) | $30,384 | 31.56% | $65,885 |
| Best year (2022) | $47,905 | 49.76% | $48,364 |

The best five are only 3.54% of winning-trade gross profit, but 40.67% of final net profit. Reporting only the gross-profit share would understate concentration. The result is not supported by only five trades, but it fails after removing the best 20. Wide-target trend capture necessarily creates this upper-tail dependence.

In 5,000 seeded simulations per scenario, random omissions were comparatively survivable:

| Random trades missed | Median remaining net | 95% interval | Probability positive |
|---:|---:|---:|---:|
| 5% | $92,256 | $62,341 to $118,675 | 100.0% |
| 10% | $86,423 | $46,031 to $125,015 | 100.0% |
| 20% | $77,637 | $22,803 to $128,379 | 99.7% |

Missing trades is not harmless when the omissions are correlated with fast continuation. A deliberately pessimistic one-minute “no chase if the 09:36 open is at least one tick worse” proxy retained only 918 trades and lost $192,362 because it excluded 250 target winners. Conversely, excluding openings above the discovery-period 90th-percentile range left $102,062. The implementation problem is therefore not simply “fast candles”; it is failure to participate in the extended continuation winners.

## What appears to create the edge

The evidence is most consistent with the opening candle carrying some directional information which, combined with a highly asymmetric payoff, captures a small number of extended intraday trends. It is not explained by long-only market drift, and it does not require the EMA to be positive historically.

Large body-ratio candles were a stable-looking exploratory subgroup, but an expanding walk-forward filter earned $68,640 in 2022–2025 versus $77,977 for the unfiltered rule. No tested side, range, wick/body, overnight, gap, VIX, weekday, or broad bull/bear filter improved combined walk-forward net over the unfiltered rule. No extra filter is recommended.

## Is 4R special?

| Target | Net profit | PF | Positive years |
|---:|---:|---:|---:|
| 1R | -$23,251 | 0.967 | 2/8 |
| 1.5R | -$14,396 | 0.983 | 3/8 |
| 2R | -$546 | 0.999 | 3/8 |
| 2.5R | $46,519 | 1.049 | 4/8 |
| 3R | $51,864 | 1.053 | 5/8 |
| 3.5R | $89,059 | 1.089 | 5/8 |
| 4R | $96,269 | 1.095 | 7/8 |
| 4.5R | $103,914 | 1.102 | 6/8 |
| 5R | $123,494 | 1.121 | 6/8 |

Four R is not special. The historical payoff becomes positive around 2.5R and continues improving through 5R. A fixed end-of-day exit earned $155,114, while break-even and trailing-stop variants earned less than fixed 4R. That pattern reinforces the upper-tail/trend-capture interpretation.

An expanding walk-forward target selector trained only on prior years chose 5R in each test year from 2022 through 2025 and earned $94,167, versus $77,977 for fixed 4R over those same years. This is exploratory target research; because the family was examined after seeing historical outcomes, 5R is not a frozen specification.

## Execution practicality

- The modeled action time is 09:35:00 New York. One-minute OHLC cannot identify 15-second or 30-second delay effects, so no claim is made at those horizons.
- A one-minute delayed-entry proxy retained $94,261 net, PF 1.094, and 6/8 positive years. A two-minute proxy retained $53,515, but normalized expectancy fell to 0.0043R and the long side became negative. The dollar result alone overstates the remaining normalized edge.
- Median stop distance was 30.5 NQ points, median holding time 24 minutes, average holding time 89 minutes, and the worst baseline streak was 18 losses.
- Manual execution is plausible only with advance preparation, a strict no-discretion process, and immediately placed bracket orders. It is psychologically demanding because of the low win rate, long losing streaks, and winner concentration.
- Automation could materially improve timestamp consistency, order/bracket placement, logging, and prevention of discretionary overrides. It cannot establish an edge or guarantee modeled fills. A human-assisted bracket workflow is a defensible intermediate implementation.

## Statistical benchmark clarification

All established tests use `arch.bootstrap.SPA` 8.0.0 with 50,000 stationary-bootstrap resamples, expected block length 10, aligned accepted 2018–2023 sessions, and zero returns assigned to no-trade days. Returns are supplied as negative losses, as required by the loss-comparison API.

| Statistical question | Hansen SPA p | White upper p | Result |
|---|---:|---:|---|
| Simple rule vs zero | 0.07608 | 0.07608 | Not resolved at 5% |
| EMA vs simple rule | 0.11808 | 0.11808 | EMA increment not resolved |
| Simple rule vs seeded random | 0.00000 | 0.00000 | Resolved against this random benchmark |
| Any tested family member vs simple | 0.12362 | 0.61182 | No family member resolved |

The earlier “SPA-style” number was a custom studentized maximum-bootstrap approximation with the simple strategy as benchmark. It was not a test of the simple strategy against zero. Failing to prove EMA increment does not prove the simple rule has no edge; these are different null hypotheses.

## Evidence classification and final answers

1. **Simplest historically attractive strategy:** first-candle body direction at 09:35, opposite-candle stop, wide asymmetric exit such as 4R. Classification: promising exploratory.
2. **Keep the EMA?** Not in the core rule. Its historical increment is positive but statistically unconvincing; keep it only as an optional chart diagnostic.
3. **Approximate break-even cost:** $69.24 all-in per NQ round trip for the fixed matched sample, versus $20.10 baseline.
4. **Survives missed trades?** Random 5–20% omissions usually do; systematic failure to enter continuation winners can destroy the result.
5. **Major-winner dependence:** material. Best five account for 40.67% of net; removing best 20 makes net negative.
6. **NQ practicality:** unsuitable at $10k and mostly unavailable at $25k under 1% risk; partial at $50k; materially more representative at $100k, with high drawdown.
7. **MNQ economics:** positive but modest after fees; useful for rehearsal/smaller sizing, not a large-dollar edge.
8. **Manual realism:** plausible with preparation and brackets; one-minute delay survived historically, while two-minute normalized edge nearly disappeared. Sub-minute impact is unknown.
9. **Automation value:** useful for consistency, brackets, and auditability; it does not create statistical evidence.
10. **Frozen future holdout:** not justified yet. Simple-vs-zero p = 0.076, EMA increment is unresolved, and target/filter work remains exploratory. 2026 must remain untouched.

## Delivered artifacts and verification

- Research artifact: `data/research/opening-candle-results.json`
- Feature/target/exit artifacts: `data/research/opening-candle-features.parquet`, `opening-candle-targets.parquet`, and `opening-candle-exits.parquet`
- Runner: `backend/run_opening_research.py`
- API: `GET /api/research/opening`
- Tests: 38 Python engine/research tests, production frontend build, and 2 rendered-HTML checks passed.
- Raw paid-cache SHA-256 inventory is byte-for-byte unchanged from before Phase 3.
- The redesigned local interface is available at `http://localhost:3000/` with NQ/MNQ comparison cards, trade replay, 1/5-minute charts, EMA toggle, strategy/control comparison, practical execution panels, and optional advanced research.
