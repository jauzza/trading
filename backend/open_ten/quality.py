from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, asdict
from datetime import timedelta, time

from .models import Bar


@dataclass
class QualityReport:
    accepted: bool
    duplicates: int
    missing_minutes: int
    has_0930: bool
    has_0935: bool
    has_1000: bool
    timestamp_ordered: bool
    suspicious_bars: int

    def to_dict(self) -> dict:
        return asdict(self)


def audit_session(bars: list[Bar]) -> QualityReport:
    timestamps = [b.ts for b in bars]
    duplicates = len(timestamps) - len(set(timestamps))
    ordered = timestamps == sorted(timestamps)
    times = {b.ts.time() for b in bars}
    missing = 0
    if timestamps:
        expected = timestamps[0]
        for ts in sorted(set(timestamps)):
            if ts > expected:
                missing += int((ts - expected) / timedelta(minutes=1))
            expected = ts + timedelta(minutes=1)
    ranges = [b.high - b.low for b in bars]
    median = sorted(ranges)[len(ranges)//2] if ranges else 0
    suspicious = sum(r > max(50, median * 20) for r in ranges)
    report = QualityReport(False, duplicates, missing, time(9,30) in times, time(9,35) in times, time(10,0) in times, ordered, suspicious)
    report.accepted = duplicates == 0 and ordered and report.has_0930 and report.has_0935 and report.has_1000 and suspicious == 0
    return report


def mapping_changes(bars: list[Bar]) -> list[dict]:
    changes = []
    previous = None
    for bar in bars:
        if bar.instrument_id is not None and previous is not None and bar.instrument_id != previous:
            changes.append({"ts": bar.ts.isoformat(), "from": previous, "to": bar.instrument_id})
        if bar.instrument_id is not None:
            previous = bar.instrument_id
    return changes
