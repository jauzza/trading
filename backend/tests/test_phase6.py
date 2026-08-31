import unittest
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from open_ten.models import Bar
from open_ten.phase5 import c01_signals
from open_ten.phase6 import PRE_ENTRY_FEATURES, _c01_causal_signal


NY = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[2]
PHASE6 = ROOT / "phase6"


class Phase6CausalTimingTests(unittest.TestCase):
    def history(self):
        bars = []
        start = date(2024, 1, 2)
        for offset in range(10):
            day = start + timedelta(days=offset)
            for index in range(78):
                ts = datetime.combine(day, time(9, 30), NY) + timedelta(minutes=5 * index)
                bars.append(Bar(ts, 99.75, 100.25, 99.5, 100.0, 1000))
        return bars

    def rth(self):
        day = date(2024, 1, 16); start = datetime.combine(day, time(9, 30), NY); bars = []
        for index in range(390):
            if index < 15:
                open_, high, low, close, volume = 100, 101, 99, 100, 100
            elif index < 30:
                open_, high, low, close, volume = 100.5, 103, 100, 102.5, 200
            else:
                open_, high, low, close, volume = 102.5, 104, 102, 103, 100
            bars.append(Bar(start + timedelta(minutes=index), open_, high, low, close, volume))
        return bars

    def test_phase5_timestamp_bug_is_reproduced_and_phase6_is_causal(self):
        legacy = c01_signals(self.rth(), self.history())[0]
        corrected = _c01_causal_signal(self.rth(), self.history())
        self.assertEqual(legacy.ts.time(), time(9, 50))
        self.assertEqual(corrected.ts.time(), time(10, 0))
        self.assertEqual(corrected.available_at, corrected.ts)

    def test_causal_signal_is_deterministic(self):
        first = _c01_causal_signal(self.rth(), self.history())
        second = _c01_causal_signal(self.rth(), self.history())
        self.assertEqual((first.ts, first.side, first.entry, first.stop, first.metadata),
                         (second.ts, second.side, second.entry, second.stop, second.metadata))

    def test_post_entry_fields_cannot_enter_predictor_registry(self):
        prohibited = {f"return_r_{value}m" for value in (1, 2, 3, 5, 10, 15, 30, 60, 90, 120)} | {"net_pnl", "net_r", "win", "outcome", "event_after_entry"}
        self.assertFalse(prohibited.intersection(PRE_ENTRY_FEATURES))


class Phase6ArtifactRegressionTests(unittest.TestCase):
    def test_required_artifacts_exist_and_registry_is_bounded(self):
        required = {
            "phase6_engine_audit.md", "c01_v1_frozen_baseline.json",
            "phase6_research_registry.json", "phase6_leakage_audit.md",
            "c01_loss_taxonomy.json", "c01_winner_taxonomy.json",
            "c01_pattern_clusters.json", "c01_similar_day_results.json",
            "c01_pre_entry_predictors.json", "c01_post_entry_management.json",
            "c01_regime_analysis.json", "phase6_candidate_strategies.json",
            "phase6_strategy_results.json", "phase6_complementarity.json",
            "phase6_control_results.json", "phase6_statistical_report.md",
            "phase6_multiple_testing.json", "phase6_bootstrap_results.json",
            "phase6_tail_dependence.json", "PHASE6_FINAL_REPORT.md",
            "PHASE6_HOLDOUT_CANDIDATES.json",
        }
        self.assertFalse([name for name in required if not (PHASE6 / name).is_file()])
        registry = json.loads((PHASE6 / "phase6_research_registry.json").read_text())
        self.assertEqual(registry["consumed"], 56)
        self.assertLessEqual(registry["consumed"], registry["maximum_meaningful_configurations"])
        self.assertTrue(registry["within_budget"])

    def test_final_baseline_reconciles_to_causal_trade_ledger(self):
        baseline = json.loads((PHASE6 / "c01_v1_frozen_baseline.json").read_text())
        summary = baseline["corrected_phase6_result"]
        trades = pd.read_parquet(PHASE6 / "phase6_c01_trades.parquet")
        entry_times = pd.to_datetime(trades["entry_ts"], utc=True).dt.tz_convert(NY)
        self.assertEqual(len(trades), summary["trades"])
        self.assertAlmostEqual(float(trades["net_pnl"].sum()), summary["net_profit"], places=6)
        self.assertAlmostEqual(float(trades["total_costs"].sum()), summary["total_costs"], places=6)
        self.assertTrue((entry_times.dt.minute % 15 == 0).all())
        self.assertTrue(baseline["raw_cache_immutable"])
        self.assertFalse(baseline["protected_2026_market_data_opened"])
        self.assertEqual({part["year"] for part in baseline["data_partitions"]}, set(range(2018, 2026)))

    def test_final_inference_resolution_and_holdout_gate(self):
        bootstrap = json.loads((PHASE6 / "phase6_bootstrap_results.json").read_text())
        self.assertTrue(bootstrap)
        self.assertTrue(all(result["samples"] == 50_000 for result in bootstrap.values()))
        self.assertTrue(all(result["minimum_p_value"] == 1 / 50_000 for result in bootstrap.values()))
        holdout = json.loads((PHASE6 / "PHASE6_HOLDOUT_CANDIDATES.json").read_text())
        self.assertFalse(holdout["protected_holdout_opened"])
        self.assertEqual(holdout["candidates"], [])


if __name__ == "__main__":
    unittest.main()
