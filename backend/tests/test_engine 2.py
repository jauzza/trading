import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from open_ten.engine import ExecutionConfig, break_even_win_rate, compound_losses, execute_signal, position_size, risk_per_contract, round_to_tick
from open_ten.models import Bar, Signal

NY=ZoneInfo("America/New_York")


class EngineTests(unittest.TestCase):
    def test_nq_point_value(self):
        cfg=ExecutionConfig(commission_per_side=0,slippage_ticks_per_side=0,spread_ticks=0)
        self.assertEqual(risk_per_contract(75,"NQ",cfg),1500)

    def test_mnq_point_value(self):
        cfg=ExecutionConfig(commission_per_side=0,slippage_ticks_per_side=0,spread_ticks=0)
        self.assertEqual(risk_per_contract(75,"MNQ",cfg),150)

    def test_tick_rounding(self):
        self.assertEqual(round_to_tick(100.13),100.25)
        self.assertEqual(round_to_tick(100.12),100.0)
        self.assertEqual(round_to_tick(100.01,mode="up"),100.25)

    def test_whole_contract_size(self):
        cfg=ExecutionConfig(risk_fraction=.01,commission_per_side=0,slippage_ticks_per_side=0,spread_ticks=0)
        self.assertEqual(position_size(100_000,25,"NQ",cfg),2)
        self.assertIsInstance(position_size(100_000,25,"NQ",cfg),int)

    def test_reject_when_one_contract_exceeds_budget(self):
        cfg=ExecutionConfig(risk_fraction=.01,commission_per_side=0,slippage_ticks_per_side=0,spread_ticks=0)
        self.assertEqual(position_size(100_000,75,"NQ",cfg),0)

    def test_fees_and_slippage_in_practical_risk(self):
        cfg=ExecutionConfig(commission_per_side=2.55,slippage_ticks_per_side=1,spread_ticks=1)
        self.assertAlmostEqual(risk_per_contract(10,"NQ",cfg),220.10)

    def test_four_r_break_even(self):
        self.assertAlmostEqual(break_even_win_rate(4),.20)
        self.assertGreater(break_even_win_rate(4,.05),.20)

    def test_ten_percent_loss_math(self):
        self.assertAlmostEqual(compound_losses(.10,5),.40951,places=5)

    def test_ambiguous_bar_adverse_first(self):
        ts=datetime(2025,1,2,10,1,tzinfo=NY)
        signal=Signal(ts,"fixture","X","long",100,95,1,"fixture",ts)
        bar=Bar(ts,100,106,94,101)
        trade=execute_signal(signal,[bar],100_000,"MNQ",ExecutionConfig(risk_fraction=.01,commission_per_side=0,slippage_ticks_per_side=0,spread_ticks=0),"T1")
        self.assertIsNotNone(trade)
        self.assertEqual(trade.outcome,"ambiguous_stop")
        self.assertLess(trade.net_pnl,0)

    def test_gap_through_stop(self):
        ts=datetime(2025,1,2,10,1,tzinfo=NY)
        signal=Signal(ts,"fixture","X","long",100,95,2,"fixture",ts)
        bar=Bar(ts,90,92,88,91)
        trade=execute_signal(signal,[bar],100_000,"MNQ",ExecutionConfig(risk_fraction=.01,commission_per_side=0,slippage_ticks_per_side=0,spread_ticks=0),"T2")
        self.assertEqual(trade.exit,90)


if __name__=="__main__": unittest.main()
