import unittest

from fastapi import HTTPException

from open_ten.api import _phase5_overview, phase5_research_trades, research_session


class Phase5ApiTests(unittest.TestCase):
    def test_overview_uses_real_cached_result_and_guard_status(self):
        _phase5_overview.cache_clear()
        payload = _phase5_overview()
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["holdout_guard"]["status"], "UNTOUCHED")
        self.assertTrue(payload["raw_cache_immutable"])
        self.assertEqual(payload["candidate_dispositions"]["C01"]["evidence"], "robust_historical_candidate")
        self.assertIn("NQ:BASE_NONE:matched_4R:fixed1", payload["summaries"])
        self.assertEqual(len(payload["robustness"]["parameter_surface"]), 9)
        self.assertEqual(len(payload["supplemental"]["expanding_walk_forward"]), 4)
        self.assertLessEqual(len(payload["summaries"]["NQ:C01:matched_4R:fixed1"]["equity"]), 240)

    def test_phase5_trade_navigation_returns_cached_rows(self):
        payload = phase5_research_trades("NQ:C01:matched_4R:fixed1", 2)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(len(payload["trades"]), 2)
        self.assertTrue(all(row["run_key"] == "NQ:C01:matched_4R:fixed1" for row in payload["trades"]))

    def test_session_endpoint_rejects_protected_year_before_path_lookup(self):
        with self.assertRaises(HTTPException) as raised:
            research_session("2026-01-02", "NQ")
        self.assertEqual(raised.exception.status_code, 403)

    def test_c01_replay_uses_the_frozen_ema200_indicator(self):
        payload = research_session("2025-12-31", "NQ", "c01_ema200")
        self.assertEqual(payload["indicator_label"], "EMA200 · completed 15m RTH")
        self.assertTrue(payload["ema"])
        self.assertTrue(all(point["time"] <= payload["bars"][-1]["time"] for point in payload["ema"]))


if __name__ == "__main__":
    unittest.main()
