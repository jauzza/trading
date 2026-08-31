import unittest
from datetime import datetime

from open_ten.macro_calendar import SCHEDULED_FOMC_DATES, validate_calendar


class MacroCalendarTests(unittest.TestCase):
    def test_timestamp_availability_and_provenance(self):
        payload = {"events": [{
            "source": "Federal Reserve Board", "stable_id": "fixture", "event_name": "FOMC statement",
            "originally_scheduled_at": "2025-01-29T14:00:00-05:00", "actual_at": "2025-01-29T14:00:00-05:00",
            "source_url": "https://www.federalreserve.gov/", "event_class": "fomc", "known_before_session": True,
        }]}
        validate_calendar(payload)
        self.assertLess(datetime.fromisoformat(payload["events"][0]["actual_at"]).year, 2026)

    def test_protected_event_year_is_rejected(self):
        payload = {"events": [{
            "source": "x", "stable_id": "x", "event_name": "x", "originally_scheduled_at": "2026-01-01T08:30:00-05:00",
            "actual_at": "2026-01-01T08:30:00-05:00", "source_url": "https://example.com", "event_class": "x", "known_before_session": True,
        }]}
        with self.assertRaisesRegex(ValueError, "outside permitted"):
            validate_calendar(payload)

    def test_emergency_fomc_date_is_not_in_known_schedule(self):
        self.assertNotIn("2020-03-03", SCHEDULED_FOMC_DATES)
        self.assertIn("2020-04-29", SCHEDULED_FOMC_DATES)
