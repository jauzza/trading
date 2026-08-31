import unittest
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from open_ten.calendar import regular_session
from open_ten.features import Feature, features_available
from open_ten.models import Bar
from open_ten.research import _contexts
from open_ten.strategies import StrategyAConfig, aggregate_five_minute, confirmed_pivots, ema, strategy_a

NY=ZoneInfo("America/New_York")


def bar(ts,o,h,l,c): return Bar(ts,o,h,l,c,100)


class TimeStrategyTests(unittest.TestCase):
    def test_five_minute_boundaries(self):
        start=datetime(2025,3,3,9,30,tzinfo=NY)
        bars=[bar(start+timedelta(minutes=i),100+i,102+i,99+i,101+i) for i in range(10)]
        fives=aggregate_five_minute(bars)
        self.assertEqual([x.ts.time() for x in fives],[time(9,30),time(9,35)])
        self.assertEqual(fives[0].close,105)

    def test_0935_signal_availability_boundary(self):
        end=datetime(2025,3,3,9,34,tzinfo=NY)
        feature=Feature("opening_candle",1,end+timedelta(minutes=1))
        with self.assertRaises(ValueError): features_available([feature],end)
        self.assertEqual(features_available([feature],end+timedelta(minutes=1))["opening_candle"],1)

    def test_1000_level_and_next_event_entry(self):
        start=datetime(2025,3,3,9,58,tzinfo=NY)
        bars=[bar(start,100,101,99,100),bar(start+timedelta(minutes=1),100,101,99,100),bar(start+timedelta(minutes=2),100,106,99,105),bar(start+timedelta(minutes=3),105,105,98,99),bar(start+timedelta(minutes=4),99,101,98,99),bar(start+timedelta(minutes=5),99,100,97,98),bar(start+timedelta(minutes=6),98,99,96,97)]
        signals=strategy_a(bars,StrategyAConfig(min_sweep=4,displacement_body=3,retest_tolerance=1.5,confirmation=.5))
        self.assertEqual(len(signals),1)
        self.assertEqual(signals[0].metadata["level"],100)
        self.assertEqual(signals[0].ts,start+timedelta(minutes=5))
        self.assertEqual(signals[0].entry,bars[-2].open)

    def test_confirmed_pivot_timing(self):
        start=datetime(2025,3,3,10,0,tzinfo=NY)
        bars=[bar(start+timedelta(minutes=i),100,100+h,100-h,100) for i,h in enumerate([1,2,5,2,1])]
        pivot=next(p for p in confirmed_pivots(bars) if p["kind"]=="high")
        self.assertEqual(pivot["pivot_ts"],start+timedelta(minutes=2))
        self.assertEqual(pivot["available_at"],start+timedelta(minutes=4))

    def test_ema_warmup_is_causal(self):
        values=list(range(1,20))
        output=ema(values,12)
        self.assertEqual(len(output),len(values))
        self.assertEqual(output[:5],ema(values[:5],12))

    def test_dst_offsets(self):
        before=datetime(2025,3,7,9,30,tzinfo=NY)
        after=datetime(2025,3,10,9,30,tzinfo=NY)
        self.assertEqual(before.utcoffset(),timedelta(hours=-5))
        self.assertEqual(after.utcoffset(),timedelta(hours=-4))

    def test_holiday_and_early_close(self):
        self.assertIsNone(regular_session(date(2025,7,4)))
        self.assertEqual(regular_session(date(2025,11,28))[1].time(),time(13,0))

    def test_full_overnight_context_includes_sunday_for_monday(self):
        stamps=[datetime(2024,3,10,18,0,tzinfo=NY),datetime(2024,3,11,0,0,tzinfo=NY),datetime(2024,3,11,9,29,tzinfo=NY),datetime(2024,3,11,9,30,tzinfo=NY)]
        frame=pd.DataFrame({"ts_ny":pd.to_datetime(stamps),"open":[1]*4,"high":[2]*4,"low":[0]*4,"close":[1]*4,"volume":[1]*4,"instrument_id":[1]*4})
        context=_contexts(frame,date(2024,3,11),pd.Timestamp(stamps[-1]),[])
        self.assertEqual(len(context["full_overnight"]),3)
        self.assertEqual(context["full_overnight"][0].ts.weekday(),6)
        self.assertEqual(len(context["same_day"]),2)

    def test_full_overnight_boundary_is_dst_safe(self):
        sunday=datetime(2024,11,3,18,0,tzinfo=NY)
        monday=datetime(2024,11,4,9,30,tzinfo=NY)
        frame=pd.DataFrame({"ts_ny":pd.to_datetime([sunday,monday]),"open":[1,1],"high":[2,2],"low":[0,0],"close":[1,1],"volume":[1,1],"instrument_id":[1,1]})
        context=_contexts(frame,date(2024,11,4),pd.Timestamp(monday),[])
        self.assertEqual(context["full_overnight"][0].ts.hour,18)


if __name__=="__main__": unittest.main()
