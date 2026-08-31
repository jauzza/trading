import hashlib
import json
import unittest
from pathlib import Path

import pandas as pd

from open_ten.api import (
    _phase7_summary,
    phase7_c01_anatomy,
    phase7_c01_failures,
    phase7_c01_management,
    phase7_c01_regimes,
    phase7_c01_winners,
    phase7_complementarity,
    phase7_experiments,
    phase7_statistics,
    phase7_strategies,
    phase7_tournament,
)


ROOT = Path(__file__).resolve().parents[2]
PHASE7 = ROOT / "phase7"


class Phase7ArtifactTests(unittest.TestCase):
    def test_baseline_reproduction_is_exact_and_holdout_is_sealed(self):
        phase6 = json.loads((ROOT / "phase6/c01_v1_frozen_baseline.json").read_text())
        replay = json.loads((PHASE7 / "_baseline_reproduction/c01_v1_frozen_baseline.json").read_text())
        self.assertEqual(phase6["corrected_phase6_result"], replay["corrected_phase6_result"])
        self.assertEqual(phase6["corrected_phase6_result"]["net_profit"], 117_590.5)
        self.assertEqual(phase6["corrected_phase6_result"]["trades"], 1_495)
        holdout = json.loads((PHASE7 / "FUTURE_HOLDOUT_FREEZE.json").read_text())
        self.assertFalse(holdout["protected_market_data_opened"])
        self.assertEqual(holdout["status"], "2026 MARKET HOLDOUT: UNTOUCHED")
        self.assertEqual(holdout["candidates"], [])

    def test_required_artifacts_and_checksums(self):
        required = {
            "PHASE7_INITIAL_AUDIT.md", "PHASE7_RESEARCH_CONTRACT.json", "PHASE7_FINAL_REPORT.md",
            "PHASE7_EXECUTIVE_SUMMARY.md", "phase7_experiment_registry.json", "c01_trade_anatomy.parquet",
            "c01_loss_taxonomy.json", "c01_winner_taxonomy.json", "c01_failure_graph.json",
            "c01_regime_analysis.json", "c01_interaction_analysis.json", "c01_predictive_filter_results.json",
            "c01_early_management_results.json", "c01_exit_analysis.json", "strategy_discovery_results.json",
            "strategy_failure_analysis.json", "strategy_complementarity.json", "strategy_tournament.json",
            "portfolio_results.json", "macro_event_analysis.json", "similar_day_analysis.json",
            "ml_predictive_analysis.json", "tcn_results.json", "risk_map_results.json", "tail_dependence.json",
            "cost_stress.json", "execution_stress.json", "walk_forward_results.json",
            "multiple_testing_results.json", "leakage_audit.md", "engine_invariants.md", "DATA_REQUEST.md",
            "FALSE_FRIENDS.md", "WHAT_WOULD_CHANGE_OUR_MIND.md", "FUTURE_HOLDOUT_FREEZE.json",
            "SHA256SUMS.txt",
        }
        self.assertFalse(sorted(name for name in required if not (PHASE7 / name).is_file()))
        for line in (PHASE7 / "SHA256SUMS.txt").read_text().splitlines():
            expected, relative = line.split("  ", 1)
            digest = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(digest, expected, relative)

    def test_registry_contract_and_budget_integrity(self):
        contract = json.loads((PHASE7 / "PHASE7_RESEARCH_CONTRACT.json").read_text())
        registry = json.loads((PHASE7 / "phase7_experiment_registry.json").read_text())
        self.assertEqual(registry["contract_id"], contract["contract_id"])
        self.assertEqual(registry["consumed"], len(registry["experiments"]))
        self.assertLessEqual(registry["consumed"], 150)
        self.assertTrue(registry["within_budget"])
        self.assertTrue(all(row["contract_id"] == contract["contract_id"] for row in registry["experiments"]))
        self.assertTrue(all(row["evaluation_range"].startswith("2024-2025") for row in registry["experiments"]))

    def test_forensic_dataset_has_exact_context_and_separated_outcomes(self):
        frame = pd.read_parquet(PHASE7 / "c01_trade_anatomy.parquet")
        self.assertEqual(len(frame), 1_966)
        self.assertEqual(int(frame.trade_executed.sum()), 1_495)
        required = {
            "opening_candle_open", "opening_candle_high", "opening_candle_low", "opening_candle_close",
            "overnight_open", "overnight_high_raw", "overnight_low_raw", "overnight_close", "prior_close",
            "time_to_mfe", "time_to_mae", "time_to_opening_range_reentry", "time_to_vwap_cross",
            "time_to_1r", "time_to_2r", "time_to_3r", "time_to_4r", "r_outcome", "outcome_class",
        }
        self.assertTrue(required.issubset(frame.columns))
        self.assertEqual(frame.opening_candle_open.notna().sum(), 1_966)
        self.assertEqual(frame.loc[frame.trade_executed, "time_to_mfe"].notna().sum(), 1_495)
        metadata = json.loads((PHASE7 / "feature_metadata.json").read_text())
        classes = {row["classification"] for row in metadata}
        self.assertTrue({"PRE_ENTRY", "ENTRY_TIME", "POST_ENTRY", "OUTCOME_ONLY"}.issubset(classes))

    def test_placebo_and_leak_detector_are_selection_ineligible(self):
        result = json.loads((PHASE7 / "c01_predictive_filter_results.json").read_text())
        leaked = result["controls"]["INTENTIONALLY_LEAKED_UNIT_TEST"]
        self.assertGreater(leaked["auc"], .99)
        self.assertTrue(leaked["pipeline_rejected"])
        self.assertFalse(leaked["selection_eligible"])
        shifted = result["controls"]["TIME_SHIFTED_FUTURE_FEATURES"]
        self.assertFalse(shifted["selection_eligible"])
        self.assertTrue(all(model["status"] in {"DESCRIPTIVE", "PROMISING"} for model in result["models"].values()))

    def test_final_statistics_have_required_resolution_and_block_sensitivity(self):
        result = json.loads((PHASE7 / "multiple_testing_results.json").read_text())
        self.assertEqual(result["bootstrap_samples"], 50_000)
        self.assertEqual(result["block_sensitivity"], [5, 10, 20, 60])
        for comparison in result["paired_comparisons"].values():
            self.assertEqual(set(comparison), {"5", "10", "20", "60"})
            self.assertTrue(all(item["samples"] == 50_000 for item in comparison.values()))


class Phase7ApiTests(unittest.TestCase):
    def test_summary_exposes_corrected_not_invalid_baseline(self):
        _phase7_summary.cache_clear()
        payload = _phase7_summary()
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["baseline"]["net_profit"], 117_590.5)
        self.assertEqual(payload["holdout"]["status"], "2026 MARKET HOLDOUT: UNTOUCHED")
        self.assertEqual(payload["classification"], "EXPLORATORY")
        self.assertLessEqual(payload["registry"]["consumed"], payload["registry"]["maximum"])

    def test_all_versioned_phase7_endpoints_are_ready(self):
        payloads = [
            phase7_c01_failures(), phase7_c01_winners(), phase7_c01_regimes(), phase7_c01_management(),
            phase7_strategies(), phase7_complementarity(), phase7_tournament(), phase7_experiments(), phase7_statistics(),
        ]
        self.assertTrue(all(payload["status"] == "ready" for payload in payloads))
        anatomy = phase7_c01_anatomy(3, True)
        self.assertEqual(anatomy["status"], "ready")
        self.assertEqual(len(anatomy["rows"]), 3)
        self.assertTrue(all(str(row["date"]) < "2026-01-01" for row in anatomy["rows"]))


if __name__ == "__main__":
    unittest.main()
