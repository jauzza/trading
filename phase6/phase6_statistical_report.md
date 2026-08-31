# Phase 6 statistical report

The primary corrected C01 session array contains 1966 aligned eligible sessions, including zero on no-trade sessions. Dependence-aware inference used 50,000 Politis–Romano stationary-bootstrap resamples with expected block length 10 sessions.

Seven paired comparisons were declared: BASE_CANDLE, BASE_EMA, BASE_LONG, BASE_SHORT, BASE_RANDOM, P6_RETEST, P6_FAILURE_REVERSAL. Raw two-sided values and BH/BY adjustments are stored in `phase6_bootstrap_results.json`; no IID t-test is used as primary evidence.

White reality-check p: 0.89854203. SPA-style maximum p: 0.89426211. DSR: {'annualized_sharpe': 0.69899, 'expected_max_null_sharpe': 2.36189, 'dsr_probability': 0.0, 'trials': 110}. CSCV/PBO: {'status': 'computed', 'blocks': 8, 'splits': 70, 'pbo': 0.357143, 'median_logit': 0.287682}.

The causal corrected result is 117,590.50 net with 6/8 positive years and -7,373.00 after removing the best 1%.
