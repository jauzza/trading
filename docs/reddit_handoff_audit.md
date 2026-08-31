# Reddit research handoff integrity audit

Audit date: 2026-08-25 (Europe/Madrid)

## Result

**PASS.** The two locally supplied copies of `reddit_research_handoff` are byte-identical. The declared SHA-256 checksum for every substantive file passes. The checksum of `SHA256SUMS.txt` itself is `e3fa9005602adf304aa5371fde060f7b840207677f6c7681c3ac6fd4582e9d22`.

The package is Reddit text and metadata only. Its 2026 dates are source-vintage dates and are not protected market outcomes.

## Verified files

| File | Declared SHA-256 | Status |
|---|---|---|
| `HANDOFF_CAPSULE.txt` | `e7f6d3ac758526867d5713b188715fc728e20c399350b8b5e581f32188560a63` | pass |
| `MAIN_CODEX_START_HERE.md` | `da9de29de37e2e18865923b359c4f8e4a6b0fd71ee166b249bebed20d078059a` | pass |
| `README.md` | `abf6e958c66107ed97f7adf600c1aeeea5ed846ef1e8d6cfcc580d2d5458c51d` | pass |
| `corpus_audit.json` | `1b2e5ddacf8a7eafa187aebdb2f74ac7ab98bee9b5c03d5052ab9c8714d21351` | pass |
| `excluded_noise_summary.json` | `df3ae00c058bf5238e58caeabe5eb3a5102bd2b544d05338f267a5fcd280eed1` | pass |
| `failure_modes.json` | `87dc4e432f4de51db3cf004eace7fefa3459f50c3a4d35e3be82a6382fc0a4f4` | pass |
| `good_bad_day_hypotheses.json` | `bc8cb72351608c0af0c0c9040cffae2bbe9fd297822d7110b82b2adebb8ea87b` | pass |
| `representative_sources.csv` | `1fcc053a6f5f9258a4ea56ffa18d65024ed65f70f0fb069609768287e3fb03fb` | pass |
| `strategy_family_catalog.json` | `ebc11836367697d87815bb4a2406092b13831a5bb11c3b4674256a512c6f619c` | pass |
| `tournament_candidates.json` | `effed620f6c6b5fad43232c37a058bc0472d8d1f7e793319f6509642c21041eb` | pass |

The automated `shasum -a 256 -c SHA256SUMS.txt` result passed all ten substantive files in both copies.

## Reconciled package facts

- 2,214,102 parsed Reddit records: 208,679 posts and 2,005,423 comments.
- 298,926 records classified as strategy-related; 1,915,176 classified as noise.
- 66 broad families, 18 tournament candidates, 16 good/bad-day hypotheses, and 430 representative source rows.
- Candidate excerpts are sparse and mixed-stance; family counts are not endorsements of exact rules.
- C03 and C04 are downgraded from completeness A in the derived manifest because their terminal time exits are unknown.
- Source vintage after a tested market year is retrospective idea evaluation, never ex-ante evidence.

## Limitations carried into Phase 5

One-minute OHLCV cannot reconstruct tick order, queue priority, bid/ask history, Level 2, footprint, true delta, or faithful volume-at-price. Private-indicator, discretionary-pattern, and materially incomplete candidates are deferred rather than approximated.
