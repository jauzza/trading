---
title: Video TCN Risk Map
tags: [video-hypothesis, ml, phase7]
status: INCONCLUSIVE
---

# Video TCN Risk Map

## Claims

- 64 x 12 feature windows, causal temporal convolution, next-bar probability, neutral-zone deadband, inverse forecast-volatility scaling, and exposure cap.
- Claimed difficult-period profitability is unverified.

## Testable

- Causal window construction, chronological walk-forward scoring, neutral zone, volatility scaling, and exposure caps.

## Not testable from supplied material

- Proprietary features, exact labels, optimizer, loss, risk-map equations, trading costs, source universe, and claimed performance.

## Possible C01 overlap

The visible opening behavior may resemble opening-range/4R trading, but there is no evidence the shown chart strategy and described neural system are the same system.

## Phase 7 disposition

Simple causal models are evaluated first. A true TCN is not substituted with a different architecture when its dependency and exact feature sequence are unavailable. See [[ML Hypotheses]] and [[Final Decision]].
