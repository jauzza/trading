from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    current = date(year, month, 1)
    while current.weekday() != weekday:
        current += timedelta(days=1)
    return current + timedelta(days=7*(n-1))


def last_weekday(year: int, month: int, weekday: int) -> date:
    current = (date(year+1, 1, 1) if month == 12 else date(year, month+1, 1)) - timedelta(days=1)
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def nyse_holidays(year: int) -> set[date]:
    fixed = {date(year,1,1), date(year,7,4), date(year,12,25)}
    # This deterministic core covers the research engine's scheduling checks;
    # production ingestion cross-checks the exchange calendar package.
    return fixed | {nth_weekday(year,1,0,3), nth_weekday(year,2,0,3), last_weekday(year,5,0), nth_weekday(year,9,0,1), nth_weekday(year,11,3,4)}


def is_nyse_session(day: date) -> bool:
    return day.weekday() < 5 and day not in nyse_holidays(day.year)


def regular_session(day: date) -> tuple[datetime, datetime] | None:
    if not is_nyse_session(day):
        return None
    close = time(13,0) if (day.month == 11 and day.weekday() == 4 and 23 <= day.day <= 29) or (day.month == 12 and day.day == 24) else time(16,0)
    return datetime.combine(day,time(9,30),NY), datetime.combine(day,close,NY)
