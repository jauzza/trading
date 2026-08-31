import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class Phase5RobustnessArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        research = ROOT / "data/research"
        cls.results = json.loads((research / "phase5-results.json").read_text())
        cls.robustness = json.loads((research / "phase5-c01-robustness.json").read_text())
        cls.supplemental = json.loads((research / "phase5-supplemental.json").read_text())

    def test_frozen_center_exactly_reproduces_authoritative_run(self):
        center = self.robustness["parameter_surface"]["ema_200:volume_1.0"]
        authoritative = self.results["summaries"]["NQ:C01:matched_4R:fixed1"]
        for field in ("accepted_sessions", "trades", "net_profit", "profit_factor", "max_drawdown"):
            self.assertEqual(center[field], authoritative[field])

    def test_neighboring_plateau_is_positive_but_not_selection_eligible(self):
        surface = self.robustness["parameter_surface"]
        self.assertEqual(len(surface), 9)
        self.assertTrue(all(cell["net_profit"] > 0 for cell in surface.values()))
        self.assertTrue(all(cell["tail"]["net_after_best_1pct"] > 0 for cell in surface.values()))
        self.assertTrue(all(cell["positive_years"] >= 7 for cell in surface.values()))
        self.assertFalse(self.robustness["selection_eligible"])
        self.assertTrue(self.robustness["raw_cache_immutable"])

    def test_expanding_walk_forward_is_complete_and_audit_only(self):
        rows = self.supplemental["expanding_walk_forward"]
        self.assertEqual([row["evaluation_year"] for row in rows], [2022, 2023, 2024, 2025])
        self.assertTrue(all(row["selected_from_prior_years"] == "C01" for row in rows))
        self.assertTrue(all(row["evaluation_net_profit"] > 0 for row in rows))
        self.assertFalse(self.supplemental["selection_eligible"])


if __name__ == "__main__":
    unittest.main()
