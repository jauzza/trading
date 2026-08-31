# r/algotrading bundle assessment for the NQ/MNQ research application

## Executive summary

The bundle is useful primarily as a **research and operational-risk checklist**, not as evidence that a new trading rule works. Its strongest, most repeated lessons—causal timestamps, chronological evaluation, realistic fills, explicit search accounting, data checks, reproducible artifacts, staged deployment, and operational safeguards—largely agree with the application's existing research design.

The application is already strong on the historical-research side: it has protected-2026 pre-read guards, completed-bar causality, realistic and reconcilable NQ/MNQ costs, contract-specific sizing, stationary block bootstrap, multiple-testing controls, deterministic replay, and frozen specifications. The material gap is after research: the current paper subsystem is an immutable local journal with **no broker connection, no common backtest/paper/live runtime, no intended-versus-realized fill reconciliation, no restart recovery, no heartbeat/alert system, and no executable kill switches**.

None of the 11 bundled strategy leads is complete enough to reproduce exactly without inventing material rules. The most interesting families are longer-horizon trend following (SL06) and RSI2-style short-horizon mean reversion (SL04), because they may diversify the opening/level-heavy prior slate. They remain background research until a complete rule set is supplied and frozen. No alpha backtest was run.

The first implementation should therefore be a **prospective execution-parity and safety layer**: a shared event schema, intended-order/fill ledger, deterministic state reconstruction, broker/paper reconciliation, alerting, and fail-closed controls. This creates genuinely new prospective evidence without opening the 2026 market holdout.

`2026 MARKET HOLDOUT: UNTOUCHED`

## Bundle integrity and evidentiary limits

- The supplied archive's declared SHA-256 checks passed for all bundled files.
- The corpus audit reports 57,799 posts and 452,401 comments (510,200 records), 210,690 lexically relevant records, 299,510 excluded records, 303 selected source rows, and zero parse failures.
- The export contains Reddit text and metadata only. Linked code, papers, websites, and performance records were not fetched or verified.
- Topic membership, stance, completeness, flags, and quality scores are deterministic lexical classifications. Counts are discussion volume, not independent endorsements.
- Reddit dates in 2026 were used only as provenance. No 2026 market outcome, file, partition, hash, or backtest was accessed.
- Source-vintage after a tested market period makes an idea retrospective. It cannot turn 2018-2025 into a fresh holdout.

Every source ID cited below resolves in `best_sources.csv`. Reddit score, screenshots, Hall of Fame labels, confidence, and reported returns are not treated as proof.

## Most valuable findings

### 1. Research rigor is already the application's strongest area

The bundle emphasizes chronological holdouts, leakage prevention, realistic fills, explicit search control, and reproducibility (`src_post_1f8v70e`, `src_post_m9y9k6`, `src_post_qtyuxb`, `src_post_1j187b3`). The current engine already implements these unusually well:

- completed-bar feature availability and causal pivots;
- protected-2026 rejection before file inspection;
- separate NQ/MNQ point values and fee assumptions;
- spread, direction-aware slippage, fees, tick rounding, gap-through stops, and adverse-first ambiguous-bar handling;
- exact gross-to-net reconciliation;
- aligned-session stationary bootstrap, BH/BY correction, White reality check, SPA-style testing, Deflated Sharpe, and PBO;
- frozen specifications, checksums, deterministic seeds, experiment registries, and artifact regression tests.

The bundle does not justify replacing this engine or adding another backtesting framework.

### 2. The research-to-live boundary is the major gap

The application can record prospective paper events, but it cannot establish that a signal calculated in research would become the same order in paper or live execution. The strongest relevant bundle sources discuss simulated-to-live transition, monitoring, architecture, and fill-quality tracking (`src_post_1anohov`, `src_post_qrj76v`, `src_post_1rvk302`, `src_post_1e4xk9m`). These support an audit requirement, not a profitability claim.

The missing proof chain is:

`market event -> feature snapshot -> signal -> intended order -> acknowledgement -> fill(s) -> position -> fees/cash -> exit -> reconciliation`

Each transition needs a timestamp, deterministic ID, original payload, runtime/configuration hash, and reconciliation state. The same strategy adapter should run in historical replay, shadow, paper, and any future live mode.

### 3. Operational risk controls should be independent of strategy code

Failure and live-deployment sources repeatedly raise outages, duplicated actions, state divergence, oversizing, and restart risk (`src_post_1u7ixpv`, `src_post_13c623e`, `src_post_qfksk2`, `src_comment_k8qjrpg`). The application currently has research-level daily-loss and margin parameters but no production risk service.

Add independent controls for stale data, lost heartbeat, order rejects, partial fills, duplicate client-order IDs, position/cash mismatch, excessive slippage, daily loss, rolling drawdown, maximum open risk, and manual emergency disable. A breached hard control must fail closed and require an audited reset.

### 4. A degradation policy must be frozen before prospective results

The bundle's nonstationarity and failed-strategy material (`src_post_m9y9k6`, `src_post_1um3mn2`, `src_post_1pnzf9l`) reinforces Phase 7's own result: historical positivity can coexist with tail dependence and weak control-relative evidence. A future strategy needs warning/pause/retire states based on pre-registered prospective metrics, including realized slippage, missed signals, control-relative expectancy, drawdown, and tail concentration. Thresholds cannot be moved after seeing a bad run.

### 5. New Reddit strategy ideas are much weaker than the methodology lessons

The strategy-lead file assigns B or C completeness, but the bundle's excerpts omit material rules for every lead. A familiar label such as “Connors RSI2” or “ADX” is not permission to fill gaps from memory. Exact missing rules remain `unknown`.

Negative evidence is equally important. The selected corpus includes reports of 17 dead MNQ/NQ strategies (`src_post_1spd5nf`), nine MNQ L2 approaches near chance (`src_post_1sarhz3`), generic moving-average underperformance (`src_post_1eqnbrw`), overfit and failed systems (`src_post_1um3mn2`), and NQ development lessons without reproducible rules (`src_post_1lksn3f`). These are also unverified anecdotes, but they argue against treating idea frequency as edge evidence.

## Research-engine gap analysis

The machine-readable assessment is in `research_engine_gap_analysis.json`. Summary:

| Area | Status | Decision |
|---|---|---|
| Chronological validation and protected holdout | Covered | Preserve; 2024-2025 remains historical evaluation, not untouched holdout. |
| Completed-bar causality and leakage guards | Covered | Require feature-availability metadata for every addition. |
| Multiple testing and aligned bootstrap | Covered | Freeze the whole candidate/control family before future tournaments. |
| NQ/MNQ costs, fills, and gross-to-net | Covered | Calibrate future slippage from prospective fills; do not infer queue/L2 behavior. |
| Reproducibility and registries | Covered | Extend hashes and event provenance into paper/live operation. |
| Futures roll point-in-time handling | Audit | Persist active-contract and mapping-change audits by timestamp. |
| Data-quality validation | Audit | Add a durable anomaly ledger and broader OHLCV/roll checks. |
| Parameter stability | Audit | Create a generic isolated-peak rejection gate. |
| Portfolio and tail risk | Audit | Move account-level limits into an independent runtime risk service. |
| Backtest/paper/live equivalence | Missing | Build one shared strategy/order state machine and golden replay tests. |
| Paper-to-live promotion | Missing | Freeze quantitative and operational promotion gates. |
| Monitoring and reconciliation | Missing | Add health, fill, position, cash, fee, and incident reconciliation. |
| Restart recovery and idempotency | Missing | Durable transitions, deterministic order IDs, startup reconciliation, crash tests. |
| Alerts and kill switches | Missing | Fail closed on hard breaches; audited manual reset only. |
| Strategy degradation shutdown | Missing | Pre-register warning/pause/retire metrics using prospective data. |
| Equity corporate actions | Not relevant | Only relevant if the project expands beyond futures; rolls are the analogue. |

## Strategy-lead assessment

Full field-level assessments—including exact available rules, every unknown, data requirements, look-ahead and execution risks—are in `algotrading_strategy_assessment.json`.

| Lead | What is actually available | Tier | Relationship to prior slate | Decision |
|---|---|---:|---|---|
| SL01 daily lower-high/lower-low reversal | Setup only; entry, stop, exits, sizing, and instrument unknown | 4 | Partial daily analogue of failed-breakout/reversal C15 | Research only |
| SL02 IBS/range mean reversion | One close-based formula and IBS < 0.3; execution and all exits unknown | 4 | Daily cousin of C04/C12 mean reversion | Research only |
| SL03 ADX/DMI | Trend-strength concept only; period, thresholds, direction, timeframe, and exits unknown | 4 | Filter variant of C05/C06 trend family | Research only |
| SL04 Connors RSI2 | RSI period 2 and “three indicators”; other rules unknown | 4 | New slower oscillator family; potentially diversifying | Research only; highest strategy follow-up after full rules |
| SL05 Bollinger mean reversion | Buy below lower band; exit above middle; band parameters/fills/stop unknown | 4 | Duplicate family of C04 and C12 | Research only, low priority |
| SL06 longer-horizon trend following | Daily/longer horizon and OBV context; actual signal and exits unknown | 4 | Most distinct from opening-heavy slate; broad overlap with C06 | Research only; highest strategic interest |
| SL07 OU statistical arbitrage | OU threshold concept; spread, hedge, estimation, and rules unknown | 2 | Distinct, but NQ/MNQ are the same underlying and not a valid pair | Research only; needs a second market |
| SL08 ETF-universe momentum | Long-only portfolio concept; universe/ranking/rebalance unknown | 4 | Outside single-futures scope | Reject |
| SL09 buy the dip | Incomplete phrase only; extraordinary-return flag | 4 | Weaker duplicate of other mean-reversion ideas | Reject |
| SL10 walk-forward trend system | Methodology, not a reproducible signal | 4 | Already covered by research engine | Research background only |
| SL11 crypto oscillator confluence | 15-minute generic oscillator/filter concept; exact rules unknown | 4 | Asset-specific generic indicator family | Reject |

Tier 4 here means the **source strategy** cannot be reproduced objectively. It does not mean the named indicator is impossible to compute.

### Strategy priority after complete rules are supplied

1. SL06, as a frozen slow time-series-trend family, because it is structurally less correlated with opening-candle and intraday-level strategies.
2. SL04, as one exact RSI2 mean-reversion variant, because it may provide a different return shape and more frequent modest outcomes than rare 4R breakouts.
3. SL01, as a daily two-candle reversal, if a complete entry/exit rule is supplied.
4. SL03 only as one pre-registered ADX regime filter, never as an open threshold search.

No item is ready for backtesting from this bundle alone.

## Additional bundle search

The complete 303-row selected-source table and all 41 topic clusters were reviewed. No additional alpha idea met the promotion standard of substantive, reproducible rules plus NQ/MNQ compatibility.

Examples not promoted:

- a moving-average strategy has a negative stance but insufficient exact rules (`src_post_1eqnbrw`);
- an NQ London/NY time-zone claim supplies a headline statistic, not a complete causal entry/exit definition (`src_post_1kns9oo`);
- a WTI mean-reversion report is a different market and lacks a complete transferable rule (`src_post_1e6d5h7`);
- a market-making tutorial cannot be reproduced from one-minute OHLCV and would require quote/order-book/queue data (`src_post_ucskm1`);
- an intraday order-book analysis idea explicitly requires unavailable granular data (`src_post_ldjyuz`).

Two non-alpha candidates do deserve formalization and are included as `ALG-ADD01` and `ALG-ADD02` in the JSON:

1. a prospective intended-versus-realized fill-quality and reconciliation monitor (`src_post_1rvk302`, `src_post_1anohov`, `src_post_qrj76v`);
2. a frozen strategy warning/pause/retire state machine based on prospective degradation and operational health (`src_post_m9y9k6`, `src_post_1um3mn2`, `src_post_1pnzf9l`).

## Comparison with the prior Daytrading slate

- **Opening momentum/range:** C01, C02, C16, and control C17 remain one correlated family. This bundle provides no independently specified superior opening rule.
- **Intraday mean reversion:** C04 and deferred C12 already cover Bollinger/VWAP reversion. SL05 is corroboration of a broad theme only, not independent evidence for the exact variants.
- **Trend/pullback:** C03, C05, deferred C06/C07, and SL03/SL06 share trend-state exposure. SL06's slower horizon is the only potentially meaningful diversification; it must be evaluated as a separate family.
- **Objective levels/failed breakouts:** C08, C09, C10, C15, and duplicate C18 already exhaust many prior-day/overnight/retest ideas. SL01 differs by using daily candle structure but is still a reversal hypothesis.
- **Gap behavior:** C14 already covers the objective gap-fill family. No better complete definition appeared.
- **Tail dependence:** Phase 7 found corrected C01 historically positive but dependent on rare winners and not superior to the strongest matched family after search correction. The bundle supplies no credible filter that fixes this. SL04/SL06 are interesting specifically because distinct return shapes may diversify tail dependence—not because Reddit establishes that they work.
- **Tournament design:** Future families should count every attempted variant and control, group correlated rules before adjustment, freeze parameters and feature availability, include tail-removal and cost-stress gates, and reserve promotion for prospective evidence.

## Failure and credibility findings

The most important credibility rule is simple: **no strategy in this bundle is demonstrated profitable**. Common warning patterns include extraordinary-return flags (`src_post_1f0689m`), screenshot/equity-curve-only evidence (`src_post_1pnzf9l`, `src_post_1spd5nf`), post-selection after thousands of trials (`src_post_1q5op3l`, `src_post_1qcp07r`), same-close/look-ahead risk, missing costs, unstable parameters, and live/backtest divergence.

The source table's “negative” stance is also lexical and can describe either criticism or an adverse result. It is useful for locating failure hypotheses, not for vote counting. Similarly, one Reddit thread may appear in several topic clusters; those appearances are not independent observations.

One-minute OHLCV remains unsuitable for faithful market making, queue priority, bid/ask reconstruction, footprint, true delta, volume-at-price, transient spread, or market-impact research. Such ideas must not be silently approximated.

## Prioritized action plan

### A. Research-engine improvements

1. Add a reusable point-in-time futures roll/mapping audit and durable data-anomaly ledger.
2. Add a generic parameter-neighborhood stability and isolated-peak rejection report.
3. Make feature-availability metadata mandatory for every candidate and control.
4. Preserve the complete attempted-rule family in multiple-testing registries.

### B. Strategy candidates worth formalizing

1. Do not formalize an alpha rule from this bundle yet.
2. If complete source rules are later supplied, freeze one SL06 slow-trend variant first, then one SL04 RSI2 variant.
3. Keep these in separate families from the opening slate and do not optimize them indefinitely.

### C. Risk or exit enhancements

1. Formalize account-level risk independently of strategies: open risk, daily loss, drawdown, stale price, and correlated-strategy exposure.
2. Pre-register a degradation state machine with warning, pause, retire, and reviewed-reset states.
3. Continue tail-removal, cost-stress, gap-risk, and year-concentration reports for every candidate.

### D. Live/paper operational safeguards

1. Build one event-driven strategy adapter for replay, shadow, paper, and future live use.
2. Add immutable intended-order, acknowledgement, fill, fee, position, cash, and incident events.
3. Implement deterministic client-order IDs, idempotent transitions, restart reconstruction, and startup broker reconciliation.
4. Add heartbeats, stale-data checks, alerts, partial/rejected-order handling, and manual/automatic kill switches.
5. Freeze paper-to-live gates before collecting prospective observations.

### E. Ideas requiring unavailable data

- OU/statistical-arbitrage pairs require at least one additional timestamp-aligned economic futures series and two-leg execution modeling.
- Market making, L2/order-book, queue, footprint, and true-delta ideas require granular quote/order data.
- ETF cross-sectional momentum requires a point-in-time universe, corporate actions, and multi-asset execution data.

### F. Ideas to reject

- SL08 ETF-universe momentum for this single-futures application.
- SL09 incomplete extraordinary-return buy-the-dip claim.
- SL11 incomplete crypto oscillator bot as an NQ/MNQ candidate.
- Any rule inferred solely from a title, familiar strategy name, topic count, score, screenshot, or reported win rate.
- Any tick/L2 proxy fabricated from one-minute OHLCV.

## Recommended implementation/testing order

1. Specify and test the common operational event model and deterministic state machine.
2. Add shadow/paper adapters plus golden replay parity tests.
3. Add reconciliation, restart/crash-boundary tests, alerts, and kill switches.
4. Add prospective fill-quality and degradation dashboards with thresholds initially unset, then freeze thresholds before evidence collection.
5. Audit data/roll and parameter-stability gates.
6. Only after complete rules are supplied, pre-register one slow-trend candidate and one RSI2 candidate; then request explicit authorization before any historical run.

## Final recommendation

Implement `ALG-ADD01` first: the prospective execution-parity, fill-quality, and reconciliation subsystem. It closes the application's largest real gap and creates trustworthy paper evidence. Do not backtest another Reddit alpha idea until its entry, stop, target, time exit, sizing, instrument, timeframe, and execution timing are all explicitly known and frozen.

**Reddit evidence in this report is hypothesis generation, not proof of profitability.**
