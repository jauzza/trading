import json
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from open_ten.models import Bar, Signal
from open_ten.phase5 import (
    MANIFEST, ProtectedMarketDataGuard, _feature_rows, _tail_tests, _two_sided_p,
    candidate_signals, verify_preregistration,
)

NY = ZoneInfo("America/New_York")


class Phase5GuardTests(unittest.TestCase):
    def test_preregistration_and_candidate_hashes_are_frozen(self):
        payload = verify_preregistration()
        self.assertEqual(len(payload["candidates"]), 18)
        self.assertFalse(any(row["specification_hash"] == "PENDING" for row in payload["candidates"]))

    def test_holdout_partition_is_rejected_from_manifest_before_file_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.json").write_text(json.dumps({"datasets": {"x": {"request": {"end": "2026-01-01"}, "partitions": [{"year": 2026, "path": "/does/not/exist"}]}}}))
            with self.assertRaisesRegex(RuntimeError, "protected partition rejected"):
                ProtectedMarketDataGuard(root).manifest()

    def test_holdout_path_is_rejected_before_path_inspection(self):
        with self.assertRaisesRegex(RuntimeError, "protected partition rejected"):
            ProtectedMarketDataGuard.assert_allowed_path("never-touch/year=2026/bars.parquet")

    def test_allowed_raw_cache_checksum_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "fred").mkdir()
            raw = root / "year=2025"; raw.mkdir()
            (raw / "bars.parquet").write_bytes(b"preserved-bars")
            (raw / "mapping.json").write_text("{}")
            manifest = {"datasets": {"x": {"request": {"end": "2026-01-01"}, "partitions": [{"year": 2025, "path": str(raw / "bars.parquet"), "mapping_path": str(raw / "mapping.json")} ]}}}
            (root / "manifest.json").write_text(json.dumps(manifest))
            guard = ProtectedMarketDataGuard(root)
            self.assertEqual(guard.checksums(manifest), guard.checksums(manifest))

    def test_two_sided_p_for_exact_zero_control_is_one(self):
        bootstrap = {"low": 0.0, "median": 0.0, "high": 0.0, "p_value": 1.0, "minimum_p_value": .00002}
        self.assertEqual(_two_sided_p(bootstrap), 1.0)


class Phase5FeatureTests(unittest.TestCase):
    def bars(self, day=date(2025, 3, 7), count=20):
        start = datetime.combine(day, time(9, 30), NY)
        return [Bar(start + timedelta(minutes=i), 100+i*.1, 101+i*.1, 99+i*.1, 100.5+i*.1, 1000+i) for i in range(count)]

    def test_feature_metadata_is_entry_time_safe(self):
        bars = self.bars(); entry = bars[10]
        signal = Signal(entry.ts, "fixture", "fixture", "long", entry.open, entry.open-2, 4, "fixture", entry.ts)
        rows = _feature_rows(entry.ts.date(), signal, bars, [], None, 20.0, {}, [], False, [])
        self.assertEqual(len(rows), 20)
        self.assertTrue(all(datetime.fromisoformat(row["known_at"]) == entry.ts for row in rows))
        self.assertTrue(all(row["source_timestamp"] is None or datetime.fromisoformat(row["source_timestamp"]) < entry.ts for row in rows))

    def test_same_time_relative_volume_uses_prior_sessions_only(self):
        bars = self.bars(); entry = bars[10]
        signal = Signal(entry.ts, "fixture", "fixture", "long", entry.open, entry.open-2, 4, "fixture", entry.ts)
        history = {bars[9].ts.time(): [500.0] * 20}
        row = next(item for item in _feature_rows(entry.ts.date(), signal, bars, [], None, 20.0, history, [], False, []) if item["name"] == "same_time_relative_volume")
        self.assertAlmostEqual(row["value"], bars[9].volume / 500.0)

    def test_candidate_signals_are_deterministic_and_lagged(self):
        bars = self.bars(count=390)
        first = candidate_signals(bars, [], [], {"high": 99, "low": 90, "close": 95, "efficiency": .4, "range_z": 0})
        second = candidate_signals(bars, [], [], {"high": 99, "low": 90, "close": 95, "efficiency": .4, "range_z": 0})
        serial = lambda payload: [(key, [(s.ts.isoformat(), s.side, s.entry, s.stop) for s in value]) for key, value in payload.items()]
        self.assertEqual(serial(first), serial(second))
        self.assertTrue(all(s.available_at <= s.ts for signals in first.values() for s in signals))

    def test_tail_gate_rejects_extreme_winner_dependence(self):
        class T:
            def __init__(self, pnl, year, index):
                self.net_pnl = pnl
                self.entry_ts = datetime(year, 1, min(28, index+1), 10, tzinfo=NY)
        result = _tail_tests([T(10000, 2024, 0)] + [T(-10, 2025, i) for i in range(30)])
        self.assertFalse(result["low_tail_dependence_components_without_period_signs"])


if __name__ == "__main__":
    unittest.main()
