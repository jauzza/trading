from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


FRED_URL = "https://api.stlouisfed.org/fred/series/observations"


def download_vix(root: Path = Path("data")) -> dict:
    """Cache daily VIX closes from FRED without exposing the server-only key."""
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        raise RuntimeError("FRED_API_KEY is not configured")
    params = {
        "api_key": api_key,
        "file_type": "json",
        "series_id": "VIXCLS",
        "observation_start": "2016-01-01",
        "observation_end": "2025-12-31",
    }
    with urlopen(f"{FRED_URL}?{urlencode(params)}", timeout=60) as response:
        payload = json.load(response)
    rows = [
        {"date": row["date"], "value": float(row["value"])}
        for row in payload.get("observations", [])
        if row.get("value") not in (None, ".")
    ]
    target = root / "fred" / "vixcls.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"series_id": "VIXCLS", "rows": rows}, indent=2))
    return {
        "status": "cached",
        "series_id": "VIXCLS",
        "observations": len(rows),
        "start": rows[0]["date"] if rows else None,
        "end": rows[-1]["date"] if rows else None,
        "path": str(target),
    }


def fred_status(root: Path = Path("data")) -> dict:
    path = root / "fred" / "vixcls.json"
    if not path.exists():
        return {"status": "empty", "series_id": "VIXCLS"}
    rows = json.loads(path.read_text()).get("rows", [])
    return {
        "status": "cached",
        "series_id": "VIXCLS",
        "observations": len(rows),
        "start": rows[0]["date"] if rows else None,
        "end": rows[-1]["date"] if rows else None,
    }
