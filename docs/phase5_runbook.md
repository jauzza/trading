# Phase 5 reproduction runbook

Run from the repository root. These commands use only the preserved local market cache. Never change the protected boundary or point the runner at a later market partition.

```bash
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v
PYTHONPATH=backend .venv/bin/python backend/run_phase5.py --smoke --bootstrap-samples 200
PYTHONPATH=backend .venv/bin/python backend/run_phase5.py --bootstrap-samples 50000
PYTHONPATH=backend .venv/bin/python backend/run_phase5_analysis.py --bootstrap-samples 50000
PYTHONPATH=backend .venv/bin/python backend/run_published_challengers.py --bootstrap-samples 50000
PYTHONPATH=backend .venv/bin/python backend/run_phase5_robustness.py
PYTHONPATH=backend .venv/bin/python backend/run_phase5_supplemental.py
PYTHONPATH=backend .venv/bin/python backend/run_phase5_reporting.py
npm run build
node --test tests/rendered-html.test.mjs
```

Local preview:

```bash
npm run dev:api
npm run dev
```

Open `http://localhost:3000`. The Phase 5 API is `http://127.0.0.1:8000/api/research/phase5`.
