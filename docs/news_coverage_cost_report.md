# Scheduled-event and optional-news coverage/cost report

## Stage 1: implemented at no incremental data cost

The local calendar contains 661 rows from the BLS/BEA release-date index, Federal Reserve official statement archives, and FRED indexing. It covers 2018-01-01–2025-12-31. It stores stable ID, event name/class, scheduled and actual timestamp fields, source URL, timestamp provenance, and whether the timestamp was knowable before the session.

Coverage includes CPI, PPI, Employment Situation/NFP, GDP, Personal Income and Outlays/PCE, JOLTS, and FOMC statements. Exact point-in-time Census retail-sales and private ISM archive coverage was not established, so neither was silently fabricated. FOMC emergency/other statement links are retained for audit but marked `known_before_session=false` unless they match a regular-meeting date.

## Stage 2: schema ready, fetch not authorized or performed

The provider-agnostic schema is `research/news_events.schema.json`. A future provider must supply stable IDs, point-in-time publication/update timestamps, title hashes, categories, deterministic NQ-topic mapping, sentiment provenance, and licensing/storage class.

No paid headline request was made. Provider, exact 2018–2025 archive coverage, rate limits, call count, price, redistribution/storage terms, and the incremental preregistered test remain unknown. Therefore the defensible estimate is **cost not yet quotable; calls made: 0; spend: $0**. Approval should be requested only after a named provider returns those facts. TradingView is not assumed to be a bulk historical-news license.
