import json
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from open_ten.algotrading_tournament import (
    ALL_IDS,
    _trade_record,
    noncausal_buy_dip_diagnostic,
    simulate_daily,
    verify_lock,
)


def daily_frame(rows):
    frame = pd.DataFrame(rows)
    defaults = {
        "volume": 1000, "minutes": 390, "roll_after": False,
        "sma5": np.nan, "sma200": np.nan, "ibs": .5,
        "highest10": np.nan, "avg_range25": np.nan,
        "rsi2": 50.0, "bb_mid": np.nan, "bb_lower": np.nan, "bb_upper": np.nan,
    }
    for key, value in defaults.items():
        if key not in frame:
            frame[key] = value
    return frame


class AlgotradingTournamentTests(unittest.TestCase):
    def test_frozen_spec_has_every_causal_candidate_and_untouched_holdout(self):
        payload = verify_lock(Path(".").resolve())
        self.assertEqual({row["candidate_id"] for row in payload["candidates"]}, set(ALL_IDS))
        self.assertEqual(payload["evidence_boundary"]["holdout_status"], "UNTOUCHED")
        self.assertEqual(payload["evidence_boundary"]["protected_market_boundary"], "2026-01-01")

    def test_reversal_uses_prior_completed_candles_gap_fill_and_same_day_exit(self):
        rows = [
            {"session_date": date(2024, 1, 2), "open_ts": pd.Timestamp("2024-01-02 09:30", tz="America/New_York"), "close_ts": pd.Timestamp("2024-01-02 15:59", tz="America/New_York"), "open": 100, "high": 110, "low": 95, "close": 108, "instrument_id": 1},
            {"session_date": date(2024, 1, 3), "open_ts": pd.Timestamp("2024-01-03 09:30", tz="America/New_York"), "close_ts": pd.Timestamp("2024-01-03 15:59", tz="America/New_York"), "open": 106, "high": 108, "low": 94, "close": 96, "instrument_id": 1},
            {"session_date": date(2024, 1, 4), "open_ts": pd.Timestamp("2024-01-04 09:30", tz="America/New_York"), "close_ts": pd.Timestamp("2024-01-04 15:59", tz="America/New_York"), "open": 109, "high": 112, "low": 107, "close": 111, "instrument_id": 1},
        ]
        records, diagnostics = simulate_daily(daily_frame(rows), "ALG01_DOWN_REVERSAL", "NQ")
        self.assertEqual(diagnostics["signals"], 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["entry_reference"], 109)
        self.assertEqual(records[0]["exit_reference"], 111)
        self.assertEqual(records[0]["outcome"], "session_close")

    def test_buy_dip_primary_is_causal_and_literal_lane_is_excluded(self):
        rows = [
            {"session_date": date(2024, 1, 2), "open_ts": pd.Timestamp("2024-01-02 09:30", tz="America/New_York"), "close_ts": pd.Timestamp("2024-01-02 15:59", tz="America/New_York"), "open": 100, "high": 110, "low": 90, "close": 92, "instrument_id": 1, "ibs": .1},
            {"session_date": date(2024, 1, 3), "open_ts": pd.Timestamp("2024-01-03 09:30", tz="America/New_York"), "close_ts": pd.Timestamp("2024-01-03 15:59", tz="America/New_York"), "open": 94, "high": 101, "low": 93, "close": 100, "instrument_id": 1, "ibs": .875},
        ]
        frame = daily_frame(rows)
        primary, _ = simulate_daily(frame, "ALG09_BUY_DIP_20", "NQ")
        literal = noncausal_buy_dip_diagnostic(frame, "NQ")
        self.assertEqual(primary[0]["entry_reference"], 94)
        self.assertEqual(primary[0]["exit_reference"], 100)
        self.assertTrue(primary[0]["valid_causal"])
        self.assertEqual(literal[0]["entry_reference"], 92)
        self.assertFalse(literal[0]["valid_causal"])

    def test_position_is_forced_flat_before_roll(self):
        rows = [
            {"session_date": date(2024, 1, 2), "open_ts": pd.Timestamp("2024-01-02 09:30", tz="America/New_York"), "close_ts": pd.Timestamp("2024-01-02 15:59", tz="America/New_York"), "open": 100, "high": 105, "low": 90, "close": 91, "instrument_id": 1, "ibs": .067, "highest10": 120, "avg_range25": 10},
            {"session_date": date(2024, 1, 3), "open_ts": pd.Timestamp("2024-01-03 09:30", tz="America/New_York"), "close_ts": pd.Timestamp("2024-01-03 15:59", tz="America/New_York"), "open": 92, "high": 96, "low": 90, "close": 95, "instrument_id": 1, "roll_after": True, "highest10": 120, "avg_range25": 10},
            {"session_date": date(2024, 1, 4), "open_ts": pd.Timestamp("2024-01-04 09:30", tz="America/New_York"), "close_ts": pd.Timestamp("2024-01-04 15:59", tz="America/New_York"), "open": 105, "high": 110, "low": 103, "close": 108, "instrument_id": 2, "highest10": 130, "avg_range25": 10},
        ]
        records, diagnostics = simulate_daily(daily_frame(rows), "ALG02_IBS_RANGE", "NQ")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["outcome"], "roll_exit")
        self.assertEqual(records[0]["exit_reference"], 95)
        self.assertEqual(diagnostics["roll_exits"], 1)

    def test_instrument_costs_are_separate_and_reconcile(self):
        ts = pd.Timestamp("2024-01-02 09:30", tz="America/New_York")
        nq = _trade_record("X", "NQ", "long", ts, ts, ts, 100, 101, "x", 1)
        mnq = _trade_record("X", "MNQ", "long", ts, ts, ts, 100, 101, "x", 1)
        self.assertNotEqual(nq["total_costs"], mnq["total_costs"])
        self.assertAlmostEqual(nq["net_pnl"], nq["gross_pnl"] - nq["total_costs"])
        self.assertAlmostEqual(mnq["net_pnl"], mnq["gross_pnl"] - mnq["total_costs"])

    def test_full_artifacts_are_corrected_and_holdout_safe(self):
        result = json.loads(Path("phase8/algotrading_tournament_results.json").read_text())
        self.assertEqual(result["holdout_guard"]["status"], "UNTOUCHED")
        self.assertFalse(result["holdout_guard"]["opened_2026_market_data"])
        self.assertEqual(result["inference"]["bootstrap_samples"], 50_000)
        self.assertEqual(result["proven_strategies"], [])
        for symbol in ("NQ", "MNQ"):
            for candidate_id in ALL_IDS:
                item = result["results"][f"{symbol}:{candidate_id}"]
                self.assertFalse(item["classification"]["proven"])
                self.assertEqual(item["summary"]["drawdown_method"], "worst of daily mark-to-market and intratrade MAE proxy")
        self.assertIn("same completed close used as the fill", result["noncausal_diagnostics"]["NQ:ALG09_BUY_DIP_20_LITERAL_NONCAUSAL"]["reason"])
        self.assertTrue(all("year=2026" not in path for paths in result["opened_partitions"].values() for path in paths))

    def test_trade_ledger_reconciles(self):
        frame = pd.read_parquet("phase8/algotrading_trades.parquet")
        error = (frame.gross_pnl - frame.total_costs - frame.net_pnl).abs().max()
        self.assertLessEqual(float(error), 1e-9)
        self.assertTrue(frame.valid_causal.all())


if __name__ == "__main__":
    unittest.main()
