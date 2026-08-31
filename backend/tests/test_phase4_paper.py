import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import closing

from open_ten.paper import PaperJournal


class Phase4ArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads(Path("data/research/phase4-results.json").read_text())

    def test_three_exits_preserve_and_reconcile_same_sessions(self):
        self.assertEqual(set(self.result["variants"]), {"fixed_4r", "fixed_5r", "stop_and_1555"})
        for item in self.result["variants"].values():
            self.assertEqual(item["metrics"]["trades"], 1959)
            self.assertTrue(item["reconciliation"]["exact"])
            self.assertEqual(item["reconciliation"]["gross_to_net_maximum_error"], 0)

    def test_eod_has_no_target_and_delay_matching_is_causal(self):
        self.assertEqual(self.result["execution_specification"]["profit_targets"]["stop_and_1555"], "none")
        for key in ("delay_1m", "delay_2m"):
            item = self.result["delayed_entry"][key]
            self.assertEqual(item["matched_sessions"], item["delayed"]["trades"])
            self.assertEqual(item["matched_sessions"], item["baseline_0935_same_sessions"]["trades"])
            self.assertGreater(item["rejections"]["stop_touched_before_entry"], 0)

    def test_bootstrap_reporting_has_full_metadata_and_finite_display(self):
        for name in ("fixed_4r_vs_zero", "exit_family_vs_fixed_4r"):
            item = self.result["statistical_reporting"][name]
            self.assertEqual(item["resamples"], 50000)
            self.assertEqual(item["expected_block_length"], 10)
            self.assertGreater(item["observations"], 1000)
            self.assertIsInstance(item["seed"], int)
            self.assertEqual(set(item["pvalues"]), {"lower", "consistent", "upper"})
            self.assertNotIn("0.00000", json.dumps(item))


class PaperJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.clock = [datetime(2030, 1, 1, 12, tzinfo=timezone.utc)]
        self.path = Path(self.temp.name) / "paper.sqlite"
        self.journal = PaperJournal(self.path, now=lambda: self.clock[0])

    def tearDown(self):
        self.temp.cleanup()

    def test_activation_is_future_only_and_immutable(self):
        with self.assertRaises(ValueError):
            self.journal.activate(self.clock[0].isoformat(), "stop_and_1555")
        activation = self.clock[0] + timedelta(days=1)
        status = self.journal.activate(activation.isoformat(), "stop_and_1555")
        self.assertEqual(status["status"], "scheduled")
        self.assertTrue(status["configuration"]["immutable"])
        self.assertFalse(status["configuration"]["live_execution"])
        with self.assertRaises(ValueError):
            self.journal.activate((activation + timedelta(days=1)).isoformat(), "fixed_4r")
        with closing(sqlite3.connect(self.path)) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE paper_activation SET exit_method='fixed_4r' WHERE id=1")

    def test_append_only_forward_event_and_separate_results(self):
        activation = self.clock[0] + timedelta(days=1)
        self.journal.activate(activation.isoformat(), "stop_and_1555")
        self.clock[0] = activation + timedelta(days=1)
        with self.assertRaises(ValueError):
            self.journal.append("missed_signal", (activation - timedelta(minutes=1)).isoformat(), {"session_date": "2030-01-02", "intended_entry_ts": "09:35", "reason": "fixture"})
        payload = {
            "session_date": "2030-01-02", "intended_entry_ts": "2030-01-02T14:35:00Z",
            "available_market_price": 25000, "spread_estimate_points": .25,
            "simulated_fill": 25000.25, "stop_price": 24970,
            "exit_ts": "2030-01-02T20:55:00Z", "exit_price": 25050,
            "net_pnl": 974.9, "status": "completed", "manual_deviation": "none",
        }
        event = self.journal.append("eligible_session", (activation + timedelta(hours=1)).isoformat(), payload)
        self.assertEqual(event["event_type"], "eligible_session")
        status = self.journal.status()
        self.assertEqual(status["prospective_results"]["net_profit"], 974.9)
        self.assertFalse(status["historical_results_merged"])
        self.assertFalse(status["broker_connected"])
        with closing(sqlite3.connect(self.path)) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM paper_events")


if __name__ == "__main__":
    unittest.main()
