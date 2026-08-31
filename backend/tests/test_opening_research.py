import unittest
from pathlib import Path

import pandas as pd

from open_ten.opening_research import _account_replay, _concentration, _cost_stress


class OpeningResearchTests(unittest.TestCase):
    def frame(self):
        rows=[]
        for index,(gross,net) in enumerate(((500,479.9),(-300,-320.1),(900,879.9))):
            rows.append({"entry_ts":f"2024-01-{index+2:02d}T09:35:00-05:00","entry_date":pd.Timestamp(f"2024-01-{index+2:02d}").date(),"side":"long" if index!=1 else "short","gross_pnl":gross,"net_pnl":net,"total_costs":20.1,"realized_r":net/500,"reference_entry":100,"stop":75,"outcome":"target" if net>0 else "stop"})
        return pd.DataFrame(rows)

    def test_pure_cost_stress_preserves_population(self):
        frame=self.frame();result=_cost_stress(frame,set(frame.entry_date))
        self.assertEqual({row["trades"] for row in result["levels"]},{3})
        self.assertEqual([row["all_in_round_trip_cost"] for row in result["levels"]],[20.1,30.15,40.2,50.25,60.3,70.35,80.4])
        self.assertGreater(result["levels"][0]["net_profit"],result["levels"][-1]["net_profit"])

    def test_account_feasibility_separates_skips(self):
        result=_account_replay(self.frame(),"NQ",10_000,1)
        self.assertEqual(result["executed_trades"],0)
        self.assertEqual(result["skipped_trades"],3)
        self.assertEqual(result["net_profit"],0)

    def test_concentration_reports_gross_and_net_shares(self):
        result=_concentration(self.frame())["tests"]["best_1_trades"]
        self.assertGreater(result["share_of_net_profit"],result["share_of_gross_profit"])
        self.assertEqual(result["removed_trades"],1)

    def test_raw_target_four_reconciles_to_corrected_cache(self):
        root=Path("data/research")
        if not (root/"opening-candle-targets.parquet").exists():
            self.skipTest("derived opening-candle research not present")
        baseline=pd.read_parquet(root/"trades.parquet",filters=[[('run_variant','=','NQ:B_CANDLE_4R_fixed1')]])
        targets=pd.read_parquet(root/"opening-candle-targets.parquet")
        targets=targets[targets.target_r==4]
        self.assertEqual(len(baseline),len(targets))
        self.assertAlmostEqual(float(baseline.net_pnl.sum()),float(targets.net_pnl.sum()),places=6)


if __name__=="__main__": unittest.main()
