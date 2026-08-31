from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
START = "2018-01-01"
END = "2025-12-31"
FRED_RELEASES = {
    10: ("Consumer Price Index", "BLS", time(8, 30), "inflation"),
    46: ("Producer Price Index", "BLS", time(8, 30), "inflation"),
    50: ("Employment Situation", "BLS", time(8, 30), "employment"),
    53: ("Gross Domestic Product", "BEA", time(8, 30), "growth"),
    54: ("Personal Income and Outlays", "BEA", time(8, 30), "income_inflation"),
    192: ("Job Openings and Labor Turnover Survey", "BLS", time(10, 0), "employment"),
}

# Regular-meeting statement dates from the Federal Reserve's official calendars.
# Statement links outside this set are emergency/unscheduled actions and cannot be
# used as a pre-session scheduled-event feature.
SCHEDULED_FOMC_DATES = {
    "2018-01-31", "2018-03-21", "2018-05-02", "2018-06-13", "2018-08-01", "2018-09-26", "2018-11-08", "2018-12-19",
    "2019-01-30", "2019-03-20", "2019-05-01", "2019-06-19", "2019-07-31", "2019-09-18", "2019-10-30", "2019-12-11",
    "2020-01-29", "2020-04-29", "2020-06-10", "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
}


def _json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "OPEN-TEN local research/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "OPEN-TEN local research/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def _fred_events(api_key: str) -> list[dict]:
    events = []
    for release_id, (name, agency, release_time, event_class) in FRED_RELEASES.items():
        query = urllib.parse.urlencode({"release_id": release_id, "realtime_start": START, "realtime_end": END,
                                        "include_release_dates_with_no_data": "true", "api_key": api_key, "file_type": "json", "limit": 1000})
        url = f"https://api.stlouisfed.org/fred/release/dates?{query}"
        payload = _json(url)
        for row in payload.get("release_dates", []):
            day = row["date"]
            if not START <= day <= END:
                continue
            timestamp = datetime.combine(datetime.fromisoformat(day).date(), release_time, NY)
            events.append({
                "source": f"{agency} schedule indexed by Federal Reserve Economic Data",
                "stable_id": f"fred-release-{release_id}-{day}", "event_name": name,
                "originally_scheduled_at": timestamp.isoformat(), "actual_at": timestamp.isoformat(),
                "source_url": url.split("?", 1)[0], "event_class": event_class,
                "known_before_session": True, "timestamp_provenance": "FRED release date plus agency standard release time",
            })
    return events


def _fomc_events() -> list[dict]:
    events = []
    sources = {year: (f"https://www.federalreserve.gov/monetarypolicy/fomchistorical{year}.htm" if year <= 2020 else "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm") for year in range(2018, 2026)}
    pages = {url: _text(url) for url in set(sources.values())}
    for year, url in sources.items():
        dates = sorted(set(re.findall(rf"monetary({year}[0-9]{{4}})a(?:1)?\.(?:htm|pdf)", pages[url])))
        for compact in dates:
            day = datetime.strptime(compact, "%Y%m%d").date()
            timestamp = datetime.combine(day, time(14, 0), NY)
            scheduled = day.isoformat() in SCHEDULED_FOMC_DATES
            events.append({
                "source": "Federal Reserve Board", "stable_id": f"fomc-statement-{day.isoformat()}",
                "event_name": "FOMC statement", "originally_scheduled_at": timestamp.isoformat(),
                "actual_at": timestamp.isoformat(), "source_url": url, "event_class": "fomc",
                "known_before_session": scheduled,
                "timestamp_provenance": "Official statement date; regular-meeting dates are matched to the official calendar. Unmatched emergency actions are not eligible as pre-session schedule features.",
            })
    return events


def build_calendar(destination: Path = Path("data/macro/events-2018-2025.json")) -> dict:
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise RuntimeError("FRED_API_KEY is required for the free release-date index")
    events = sorted(_fred_events(api_key) + _fomc_events(), key=lambda row: (row["actual_at"], row["stable_id"]))
    if any(datetime.fromisoformat(row["actual_at"]).year >= 2026 for row in events):
        raise RuntimeError("protected market boundary crossed in event calendar")
    payload = {
        "schema_version": 1, "coverage": {"start": START, "end": END}, "paid_data": False,
        "providers": ["BLS", "BEA", "Federal Reserve Board", "FRED release-date index"],
        "events": events,
        "limitations": [
            "FRED provides release dates but not an originally-scheduled-versus-delayed distinction; standard agency times are used.",
            "Historical Census retail-sales and private ISM timestamps were not included because exact point-in-time archive coverage was not verified in this bounded run.",
            "FOMC statement links not matching an official regular-meeting date are marked known_before_session=false and must not be used as scheduled entry filters.",
            "This calendar contains schedules only, never released values or surprises.",
        ],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2))
    return payload


def validate_calendar(payload: dict) -> None:
    seen = set()
    for row in payload.get("events", []):
        if row["stable_id"] in seen: raise ValueError("duplicate event stable ID")
        seen.add(row["stable_id"])
        timestamp = datetime.fromisoformat(row["actual_at"])
        if timestamp.tzinfo is None: raise ValueError("event timestamp must be timezone-aware")
        if timestamp.year >= 2026: raise ValueError("event outside permitted historical window")
        for required in ("source", "event_name", "originally_scheduled_at", "source_url", "event_class", "known_before_session"):
            if required not in row: raise ValueError(f"missing event field: {required}")
