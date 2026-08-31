# OPEN / TEN

A local, causal research lab for auditing the 10:00 New York opening-price strategy and the first-five-minute-candle + 12 EMA strategy on NQ/MNQ futures.

The interface reads only completed, corrected research artifacts. If the local API or verified artifacts are unavailable it shows an unavailable state; it never substitutes synthetic performance.

## Current evidence verdict

**NO STRATEGY QUALIFIES FOR THE UNTOUCHED 2026 HOLDOUT.** The final bounded Phase 4 audit recommends the simple first-candle rule with its original stop and a fixed 15:55-bar-close exit, with no target, for **prospective paper trading only**. It had the strongest historical economics of the predeclared 4R/5R/15:55 comparison, but its advantage over 4R was not statistically resolved and its rare-winner concentration is substantial.

- NQ: 3,494,738 one-minute bars in 10 yearly partitions; 1,966 clean core sessions accepted for 2018–2025.
- MNQ: 2,345,932 one-minute bars in 7 yearly partitions; 1,636 post-launch sessions accepted.
- FRED VIXCLS: 2,541 daily observations cached for 2016–2025. Conditioning uses the **prior available close**, never a same-day close before it was known.
- 2026 remains untouched and was not purchased or loaded.

Across the same 1,959 NQ sessions, 4R earned $96,269, 5R earned $123,494, and stop-plus-15:55 earned $155,114 after baseline costs. The 15:55 rule had PF 1.149, -25.37% drawdown, and a $99.28 estimated all-in cost break-even, but its best five trades supplied 55.9% of net profit. The expanding prior-years selector chose it before every 2022–2025 test year; all four were positive. The exit-family SPA p-value versus 4R is 0.07698, so this remains historical exploratory evidence. See [PHASE4_FINAL_AUDIT.md](./PHASE4_FINAL_AUDIT.md).

## Start locally

Requirements: Node 22+, Python 3.11+.

```bash
npm install
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm run dev:api
```

In a second terminal:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The research API listens only on `127.0.0.1:8000`.

## Configuration

Copy `.env.example` to `.env` and set server-only values. `.env*` is ignored by Git. Keys never enter browser JavaScript or rendered HTML.

The Data Vault workflow is deliberately two-step:

1. Estimate the exact Databento request using `metadata.get_cost`.
2. Check explicit approval for that request fingerprint before download.

Raw licensed data is private, cached under `data/`, and excluded from version control. The intended on-disk format is partitioned Parquet plus a reproducible manifest. Higher-resolution data requires a separate estimate and approval.

To reproduce the derived evidence from the existing private cache:

```bash
.venv/bin/python backend/run_research.py
.venv/bin/python backend/run_opening_research.py
.venv/bin/python backend/run_phase4_audit.py
```

To refresh the free FRED VIX series using the server-only `FRED_API_KEY`:

```bash
.venv/bin/python backend/download_fred.py
```

## Tests

```bash
npm test
```

The 44 engine/data/research/journal tests cover the existing execution and session invariants plus no-target time exits, exact three-exit reconciliation, causal delayed entries, complete finite-resolution SPA reporting, immutable paper activation, pre-activation rejection, append-only event enforcement, and strict historical/prospective separation. Two rendering tests check the safe unavailable state and secret exclusion.

## Prospective paper journal

The interface can schedule a future activation for the recommended paper-only rule. Configuration becomes immutable, the SQLite audit log is append-only, sessions before activation are rejected, historical results are never merged, and no broker or live-order adapter exists.

## Current limitations

- One-minute OHLC cannot identify event order inside an ambiguous bar; the authoritative baseline assumes the adverse event first.
- One-minute bars cannot reproduce queue position or transient intrabar spread changes; cost stress tests bracket this uncertainty.
- New or higher-resolution Databento requests still stop after cost estimation until the exact paid request is explicitly approved.
- No broker adapter exists and this project never places live orders.
