import unittest
from datetime import date

import numpy as np

from open_ten.analytics import benjamini_hochberg, chronological_splits, max_drawdown, paired_matrix_bootstrap
from open_ten.portfolio import PortfolioRisk
from open_ten.quality import audit_session, mapping_changes
from open_ten.research import _run_specs
from open_ten.synthetic import synthetic_session


class QualityStatisticsTests(unittest.TestCase):
    def test_missing_bar_detection(self):
        bars=synthetic_session(date(2025,3,3))
        report=audit_session(bars[:10]+bars[11:])
        self.assertEqual(report.missing_minutes,1)

    def test_required_opening_sequence(self):
        report=audit_session(synthetic_session(date(2025,3,3)))
        self.assertTrue(report.has_0930 and report.has_0935 and report.has_1000)
        self.assertTrue(report.accepted)

    def test_contract_roll_detection(self):
        bars=synthetic_session(date(2025,3,3))[:3]
        mutated=[type(b)(b.ts,b.open,b.high,b.low,b.close,b.volume,100 if i<2 else 200) for i,b in enumerate(bars)]
        self.assertEqual(len(mapping_changes(mutated)),1)

    def test_chronological_holdout_isolation(self):
        splits=chronological_splits(list(range(2016,2027)),legacy_excluded=True)
        self.assertEqual(splits["discovery"],[2018,2019,2020,2021])
        self.assertEqual(splits["reserved_holdout"],[2026])
        self.assertFalse(set(splits["blind_test"]) & set(splits["discovery"]))

    def test_max_drawdown(self):
        dd,duration=max_drawdown([100,110,88,90,120])
        self.assertAlmostEqual(dd,-.2)
        self.assertEqual(duration,2)

    def test_fdr_correction(self):
        self.assertEqual(benjamini_hochberg([.001,.02,.8,.7]),[True,True,False,False])

    def test_paired_bootstrap_is_aligned_reproducible_and_resolved(self):
        candidate=np.array([.2,-.1,.3,0,.1]*20)
        controls=np.column_stack([np.zeros(len(candidate)),candidate])
        first=paired_matrix_bootstrap(candidate,controls,samples=1000,mean_block=5,seed=7)
        second=paired_matrix_bootstrap(candidate,controls,samples=1000,mean_block=5,seed=7)
        self.assertEqual(first,second)
        self.assertGreater(first[0]["observed_mean_difference"],0)
        self.assertAlmostEqual(first[1]["observed_mean_difference"],0)
        self.assertEqual(first[0]["minimum_p_value"],round(1/1001,8))

    def test_shared_capital_and_daily_loss(self):
        p=PortfolioRisk(100_000,3000,1500)
        self.assertTrue(p.reserve(1000))
        self.assertFalse(p.reserve(600))
        p.close(1000,-3000)
        self.assertFalse(p.reserve(500))

    def test_research_sizing_uses_contract_specific_margin(self):
        specs=_run_specs()
        self.assertEqual(specs["NQ:B_EMA_FULL_4R_risk1"][0].margin_per_contract,22000)
        self.assertEqual(specs["MNQ:B_EMA_FULL_4R_risk1"][0].margin_per_contract,2200)


if __name__=="__main__": unittest.main()
