import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from open_ten.engine import (
    FEE_PRESETS, ExecutionConfig, FeeSchedule, break_even_win_rate,
    compound_losses, execute_signal, position_size, risk_per_contract,
    round_to_tick,
)
from open_ten.models import Bar, Signal

NY = ZoneInfo("America/New_York")
ZERO = ExecutionConfig(fixed_contracts=1, fee_schedule=FEE_PRESETS["zero"], slippage_ticks_per_side=0, spread_ticks_round_trip=0)


class EngineTests(unittest.TestCase):
    def signal(self, side="long", target_r=1):
        ts = datetime(2025, 1, 2, 10, 1, tzinfo=NY)
        stop = 95 if side == "long" else 105
        return Signal(ts, "fixture", "X", side, 100, stop, target_r, "fixture", ts)

    def execute(self, side, bar, config=ZERO, target_r=1):
        return execute_signal(self.signal(side, target_r), [bar], 100_000, "NQ", config, f"{side}-fixture")

    def test_nq_and_mnq_point_values(self):
        self.assertEqual(risk_per_contract(75, "NQ", ZERO), 1500)
        self.assertEqual(risk_per_contract(75, "MNQ", ZERO), 150)

    def test_contract_specific_default_fees(self):
        self.assertNotEqual(FEE_PRESETS["NQ"].per_side, FEE_PRESETS["MNQ"].per_side)

    def test_tick_rounding(self):
        self.assertEqual(round_to_tick(100.13), 100.25)
        self.assertEqual(round_to_tick(100.12), 100.0)
        self.assertEqual(round_to_tick(100.01, mode="up"), 100.25)

    def test_whole_contract_risk_and_margin_limits(self):
        config = ExecutionConfig(risk_fraction=.01, fee_schedule=FEE_PRESETS["zero"], slippage_ticks_per_side=0, spread_ticks_round_trip=0)
        self.assertEqual(position_size(100_000, 25, "NQ", config), 2)
        self.assertEqual(position_size(100_000, 75, "NQ", config), 0)
        margin = ExecutionConfig(fixed_contracts=4, max_contracts=10, margin_per_contract=30_000)
        self.assertEqual(position_size(100_000, 10, "NQ", margin), 3)

    def test_fixed_dollar_risk(self):
        config = ExecutionConfig(risk_dollars=500, fee_schedule=FEE_PRESETS["zero"], slippage_ticks_per_side=0, spread_ticks_round_trip=0)
        self.assertEqual(position_size(100_000, 10, "NQ", config), 2)

    def test_gross_to_net_reconciliation_long_winner(self):
        config = ExecutionConfig(fixed_contracts=1, fee_schedule=FeeSchedule(1, 2, 3, 4), slippage_ticks_per_side=1, spread_ticks_round_trip=1)
        trade = self.execute("long", Bar(self.signal().ts, 100, 106, 99, 105), config)
        self.assertEqual(trade.gross_pnl, 100)
        self.assertEqual(trade.spread_cost, 5)
        self.assertEqual(trade.slippage, 10)
        self.assertEqual(trade.fees, 20)
        self.assertEqual(trade.total_costs, 35)
        self.assertEqual(trade.net_pnl, 65)
        self.assertEqual(trade.gross_pnl - trade.total_costs, trade.net_pnl)

    def test_short_winner_and_directional_fills(self):
        config = ExecutionConfig(fixed_contracts=1, fee_schedule=FEE_PRESETS["zero"], slippage_ticks_per_side=1, spread_ticks_round_trip=0)
        trade = self.execute("short", Bar(self.signal("short").ts, 100, 101, 94, 95), config)
        self.assertEqual(trade.entry, 99.75)
        self.assertEqual(trade.exit, 95.25)
        self.assertEqual(trade.gross_pnl, 100)
        self.assertEqual(trade.slippage, 10)
        self.assertEqual(trade.net_pnl, 90)

    def test_long_and_short_losers(self):
        long_trade = self.execute("long", Bar(self.signal().ts, 100, 101, 94, 95), ZERO)
        short_trade = self.execute("short", Bar(self.signal("short").ts, 100, 106, 99, 105), ZERO)
        self.assertEqual(long_trade.net_pnl, -100)
        self.assertEqual(short_trade.net_pnl, -100)

    def test_multiple_contract_costs_scale(self):
        config = ExecutionConfig(fixed_contracts=3, fee_schedule=FeeSchedule(1, 0, 0, 0), slippage_ticks_per_side=1, spread_ticks_round_trip=1)
        trade = self.execute("long", Bar(self.signal().ts, 100, 106, 99, 105), config)
        self.assertEqual(trade.gross_pnl, 300)
        self.assertEqual(trade.total_costs, 51)
        self.assertEqual(trade.net_pnl, 249)

    def test_ambiguous_bar_adverse_first(self):
        trade = self.execute("long", Bar(self.signal().ts, 100, 106, 94, 101), ZERO)
        self.assertEqual(trade.outcome, "ambiguous_stop")
        self.assertLess(trade.net_pnl, 0)

    def test_gap_through_stop(self):
        trade = self.execute("long", Bar(self.signal().ts, 90, 92, 88, 91), ZERO, target_r=2)
        self.assertEqual(trade.reference_exit, 90)
        self.assertEqual(trade.exit, 90)
        self.assertEqual(trade.net_pnl, -200)

    def test_forced_session_exit(self):
        ts = self.signal().ts
        trade = execute_signal(self.signal(target_r=4), [Bar(ts, 100, 102, 98, 101), Bar(ts + timedelta(minutes=1), 101, 103, 100, 102)], 100_000, "NQ", ZERO, "session")
        self.assertEqual(trade.outcome, "session_exit")
        self.assertEqual(trade.reference_exit, 102)

    def test_stop_plus_time_exit_has_no_profit_target(self):
        ts = self.signal().ts
        no_target = self.signal(target_r=None)
        trade = execute_signal(no_target, [Bar(ts, 100, 150, 99, 140), Bar(ts + timedelta(minutes=1), 140, 180, 139, 175)], 100_000, "NQ", ZERO, "time-exit")
        self.assertIsNone(trade.target)
        self.assertEqual(trade.outcome, "session_exit")
        self.assertEqual(trade.reference_exit, 175)

    def test_break_even_and_ten_percent_math(self):
        self.assertAlmostEqual(break_even_win_rate(4), .20)
        self.assertGreater(break_even_win_rate(4, .05), .20)
        self.assertAlmostEqual(compound_losses(.10, 5), .40951, places=5)


if __name__ == "__main__":
    unittest.main()
