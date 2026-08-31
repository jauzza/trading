# Phase 7 final report

## Executive verdict

Corrected causal C01 reproduces Phase 6 exactly at **$117,590.50**, 1495 trades, PF 1.1621, -14.68% max drawdown, and 6/8 positive years. The old Phase 5 result remains `INVALID_LOOKAHEAD_HISTORICAL_RESULT`.

The core conclusion did not improve: corrected C01 is historically positive and execution-cost tolerant, but it is right-skew/tail dependent, not superior to the strongest matched benchmark family after data-snooping correction, and has no reliable pre-entry bad-day filter or robust independent complement. No candidate qualifies for the protected holdout.

## Direct answers

1. **Corrected C01 result:** $117,590.50, 1495 trades, PF 1.1621, -14.68% maximum drawdown, 6/8 positive years.
2. **Phase 6 reproduction:** yes—entries, exits, stops, targets, costs, P&L, equity summary, and yearly results match exactly.
3. **Why C01 wins:** infrequent completed-breakout extensions pay for frequent ordinary losses; overnight/VWAP agreement, volume, and room to levels are supporting descriptions, not proven causes.
4. **Why C01 loses:** failed follow-through is the main latent description: early adverse movement, range re-entry, contextual conflict, and key-level obstruction overlap.
5. **Pre-entry failure patterns:** overnight/prior-trend/gap/volatility/range/event context plus VWAP/EMA and key-level state known by entry.
6. **Post-entry-only failures:** adverse excursion, range re-entry, rapid reversal, chop, no follow-through, momentum decay, and observed event volatility.
7. **Predict bad trades before entry:** no. Best shallow-GB AUC was about 0.57, but paired improvement was not significant after correction.
8. **Predict good trades before entry:** no; winner traits and similar-day representations remain DESCRIPTIVE.
9. **Early management help:** `ADVERSE_0_5R_5M` added $7,915.00 historically.
10. **Does management destroy rare winners:** it cut 47 historically profitable trades and only barely remained positive after best-1% removal ($542.00); not robust enough to freeze.
11. **Is 4R special:** not established. The frozen 4R path is exact; alternate exits are exploratory and some target ordering is unresolved with one-minute bars.
12. **EMA incremental value:** unresolved versus matched EMA/first-candle benchmarks.
13. **Simpler version outperform:** no simpler control passed superiority plus tail gates.
14. **Independent strategy outperform C01:** none under equal causal, cost, chronology, and tail treatment.
15. **Independent complement:** `C04` was best on C01-loss sessions among historically positive candidates, but failed standalone/tail/chronological gates.
16. **Least tail-dependent serious candidate:** C01 was least bad in the bounded tournament, yet still failed after best-1% removal.
17. **Most year-stable:** C01 and C11 tied at 6/8 positive years; C11 still failed later/tail/cost gates.
18. **Most cost-stress resistant:** corrected C01; it alone among the serious tournament set remained positive at 4x modeled costs ($27,442.00).
19. **Easiest manual execution:** C01, because it is one deterministic bracket decision at a completed 15-minute boundary; missed-tail-day risk remains material.
20. **Easiest automation:** C01, because its inputs and orders are deterministic; this is not deployment authorization.
21. **Regime rotation:** no outcome-free pre-entry regime supported a stable C01/alternate rotation.
22. **What Reddit identified correctly:** testable opening-range, VWAP, gap, prior-level, trend, and reversal mechanism families.
23. **What Reddit got wrong:** popularity and anecdotes were not evidence; the original C01 headline was invalidated by implementation timing, and several rules were subjective/incomplete.
24. **Similar-day matching:** no reliable chronological value across opening, overnight, gap, volatility, or volume representations.
25. **ML:** simple causal classifiers were DESCRIPTIVE; model-filter improvement BY-adjusted p-values were not significant.
26. **TCN:** not run and therefore unknown. The exact 64x12 sequence specification and trainable TCN framework were unavailable, and the mechanical escalation gate failed; no substitute was mislabeled.
27. **Risk map:** not run because no predictor/TCN reached its gate. Dynamic sizing was not allowed to hide a weak signal.
28. **Source of apparent ML improvement:** historically excluding roughly the highest predicted-loss quintile changed exposure, but the paired improvement did not survive correction; no incremental prediction claim remains.
29. **Macro/news:** known scheduled-event partitions were descriptive and did not justify a policy; no outcomes or revisions were used.
30. **Additional data:** tick bid/ask/trades could resolve execution; verified point-in-time macro archives and cross-market data need a new preregistered question before purchase.
31. **Tail removal:** base C01 failed best-1% removal ($-7,373.00); no standalone strategy survived every tail gate. The early-management variant's $542.00 remainder is too marginal/post-selected for promotion.
32. **4x costs:** corrected C01 survived at $27,442.00; other serious candidates did not.
33. **Missed trades:** random 5/10/20% removal retained positive median net, but adversarially missing the best 5% produced $-237,617.00; operational tail-day capture matters.
34. **Exceptional-day concentration:** the best 1% contributed 14.82% of gross profit and removing them made net negative.
35. **Ready for future holdout:** none; `FUTURE_HOLDOUT_FREEZE.json` is empty.
36. **What changes the conclusion:** genuinely untouched prospective signals/fills, acceptable prospective tails, stable benchmark superiority, or a newly preregistered independent mechanism. Exact gates are in `WHAT_WOULD_CHANGE_OUR_MIND.md`.

## WHAT WE KNOW

- Corrected C01 exactly reproduces Phase 6 and is positive under baseline through 4x modeled costs.
- Its median trade is negative and its best 1% are necessary for positive historical net.
- Failed-follow-through descriptions overlap; available pre-entry features do not reliably identify them.
- No independent strategy or portfolio clears all gates.

## WHAT WE DO NOT KNOW

- Prospective performance, broker-realized fills, tick-order outcomes, and whether tail dependence persists in unseen data.

## WHAT FAILED

- Pre-entry ML filters, similar-day matching, outcome-free regime rotation, new Phase 6 strategies, and robust complement promotion.

## WHY C01 WINS

Historically, infrequent extended displacement pays for frequent ordinary losses when breakout direction aligns with broader context and has room to travel. This is a plausible description, not proven causality.

## WHY C01 LOSES

Most losses are manifestations of failed follow-through: immediate adverse movement, return inside the range, contextual conflict, or obstruction before a 4R extension.

## BEST BAD-DAY SIGNAL

None is genuinely predictive before entry.

## BEST GOOD-DAY SIGNAL

None is genuinely predictive before entry; VWAP/overnight/key-level alignment remain descriptive.

## BEST EARLY-MANAGEMENT RULE

`ADVERSE_0_5R_5M` is the best bounded historical rule but remains EXPLORATORY and is not frozen.

## BEST INDEPENDENT STRATEGY

None.

## BEST COMPLEMENT TO C01

None survives standalone, tail, chronological, and multiple-testing requirements.

## BEST ROBUST PORTFOLIO

None justified; C01 unchanged is the do-nothing comparison.

## ML / TCN VERDICT

Simple models did not clear promotion. TCN value is unknown, not zero: it was correctly gated rather than replaced by a non-TCN model. The risk map was not run because no predictor reached that stage.

## TAIL-RISK VERDICT

Material and disqualifying for holdout promotion: corrected C01 net after best-1% removal is $-7,373.00.

## COST / EXECUTION VERDICT

Modeled cost tolerance is better than tail tolerance. One-minute bars still cannot prove real fill quality or intrabar order.

## MANUAL TRADING VERDICT

Possible only with prepared bracket orders and strict no-chase behavior; exceptional-trade dependence makes missed-trade risk material. Not recommended for capital deployment from this evidence.

## AUTOMATION VERDICT

Deterministic and automation-friendly, but research readiness is not deployment authorization. Broker safeguards, monitoring, paper execution, and prospective evidence are missing.

## DATA GAPS

Tick/bid-ask execution data, verified point-in-time macro releases, and explicitly justified cross-market inputs.

## HOLDOUT STATUS

`2026 MARKET HOLDOUT: UNTOUCHED`

## FINAL RESEARCH CLASSIFICATION

- C01_CAUSAL: EXPLORATORY
- C04/C05/C10/C11/C14/C16: EXPLORATORY or REJECTED as detailed in the tournament
- Pre-entry filters, regime rotation, independent Phase 6 strategies: REJECTED/DESCRIPTIVE
- Holdout candidates: none

## NEXT ACTION

`NO FURTHER DEVELOPMENT IS JUSTIFIED WITHOUT NEW DATA OR A NEW HYPOTHESIS.`
