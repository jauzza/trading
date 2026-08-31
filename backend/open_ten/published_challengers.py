from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, time
from pathlib import Path

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

from .analytics import stationary_bootstrap_mean
from .engine import ExecutionConfig, round_trip_cost_per_contract
from .models import Signal
from .phase5 import NY, ProtectedMarketDataGuard, _execute, _signal, _trade_metrics
from .research import NQ_FP, _bar, _condition_dates, _quality, _roll_dates


def _period(year: int) -> str:
    return "development" if year <= 2021 else "validation" if year <= 2023 else "historical_evaluation"


def run_published_challengers(root: Path = Path("data"), samples: int = 50_000) -> dict:
    guard = ProtectedMarketDataGuard(root); manifest = guard.manifest(); before = guard.checksums(manifest)
    dataset = manifest["datasets"][NQ_FP]; degraded, _ = _condition_dates(root)
    roll_dates = _roll_dates([Path(row["mapping_path"]) for row in dataset["partitions"]])
    schedule = mcal.get_calendar("NYSE").schedule("2018-01-01", "2025-12-31")
    prior_tail = pd.DataFrame(); prior_close = None; minute_history: dict[time, list[float]] = defaultdict(list)
    accepted = []; noise_trades = []; momentum_rows = []
    for partition in sorted(dataset["partitions"], key=lambda row: int(row["year"])):
        year = int(partition["year"])
        if year >= 2026: raise RuntimeError("protected partition rejected before market read")
        if year < 2018: continue
        current = guard.read_parquet(partition["path"])
        frame = pd.concat([prior_tail, current], ignore_index=True).sort_values("ts_ny") if len(prior_tail) else current
        for session_day, calendar_row in schedule[schedule.index.year == year].iterrows():
            day = session_day.date(); market_open = calendar_row.market_open.tz_convert("America/New_York"); market_close = calendar_row.market_close.tz_convert("America/New_York")
            rth_frame = frame[(frame.ts_ny >= market_open) & (frame.ts_ny < market_close)].copy()
            ok, _ = _quality(day, rth_frame, int((market_close-market_open).total_seconds()/60), degraded, roll_dates)
            if not ok: continue
            bars = [_bar(row) for row in rth_frame.itertuples(index=False)]; accepted.append(day)
            by_time = {bar.ts.time(): bar for bar in bars}
            if all(value in by_time for value in (time(9,30),time(9,59),time(15,0),time(15,29),time(15,30),time(15,55))):
                first = by_time[time(9,59)].close/by_time[time(9,30)].open-1
                penultimate = by_time[time(15,29)].close/by_time[time(15,0)].open-1
                final = by_time[time(15,55)].close/by_time[time(15,30)].open-1
                final_bars = [bar for bar in bars if time(15,30) <= bar.ts.time() <= time(15,55)]
                prior_half = [bar for bar in bars if time(15,0) <= bar.ts.time() <= time(15,29)]
                momentum_rows.append({"date": day, "year": year, "first30": first, "penultimate30": penultimate, "final30": final,
                                      "entry": by_time[time(15,30)].open, "exit": by_time[time(15,55)].close,
                                      "final_high": max(bar.high for bar in final_bars), "final_low": min(bar.low for bar in final_bars),
                                      "stop_long": min(bar.low for bar in prior_half), "stop_short": max(bar.high for bar in prior_half)})

            # Author-logic shadow: trailing 14 same-minute absolute moves, RTH VWAP, 30-minute decisions.
            cumulative_pv = cumulative_volume = 0.0; chosen = None
            for index, bar in enumerate(bars[:-1]):
                cumulative_pv += ((bar.high+bar.low+bar.close)/3)*bar.volume; cumulative_volume += bar.volume
                if bar.ts.minute not in (0,30) or bar.ts.time() < time(10,0) or bar.ts.time() > time(15,0): continue
                history = minute_history[bar.ts.time()][-14:]
                if len(history) < 14 or prior_close is None: continue
                sigma = float(np.mean(history)); upper = max(bars[0].open, prior_close)*(1+sigma); lower = min(bars[0].open, prior_close)*(1-sigma)
                vwap = cumulative_pv/cumulative_volume if cumulative_volume else bar.close
                side = "long" if bar.close > upper and bar.close > vwap else "short" if bar.close < lower and bar.close < vwap else None
                if side:
                    chosen = _signal("PUB_NOISE_VWAP_SHADOW", side, bars[index+1], lower if side == "long" else upper, "14-session noise band plus RTH VWAP")
                    if chosen: break
            if chosen:
                trade = _execute(chosen, bars, "NQ", 100_000+sum(t.net_pnl for t in noise_trades), "matched_EOD", "fixed1", f"PUB-NOISE:{day}")
                if trade: noise_trades.append(trade)
            for bar in bars: minute_history[bar.ts.time()].append(abs(bar.close/bars[0].open-1))
            prior_close = bars[-1].close
        cutoff = current.ts_ny.max()-pd.Timedelta(days=4); prior_tail = current[current.ts_ny >= cutoff].copy()

    momentum = pd.DataFrame(momentum_rows); development = momentum[momentum.year <= 2021]
    design = np.column_stack([np.ones(len(development)), development.first30, development.penultimate30])
    coefficients = np.linalg.lstsq(design, development.final30, rcond=None)[0]
    cost = round_trip_cost_per_contract("NQ", ExecutionConfig(fixed_contracts=1))
    for frame_name, frame_value in momentum.groupby(momentum.year.map(_period)):
        prediction = coefficients[0]+coefficients[1]*frame_value.first30+coefficients[2]*frame_value.penultimate30
        side = np.where(prediction >= 0, 1, -1)
        stop = np.where(side > 0, frame_value.stop_long, frame_value.stop_short)
        stop_hit = np.where(side > 0, frame_value.final_low <= stop, frame_value.final_high >= stop)
        reference_exit = np.where(stop_hit, stop, frame_value.exit)
        gross = side*(reference_exit-frame_value.entry)*20
        momentum.loc[frame_value.index, "shadow_net"] = gross-cost
        momentum.loc[frame_value.index, "prediction"] = prediction
    momentum_summary = {}
    for name in ("development","validation","historical_evaluation"):
        chosen = momentum[momentum.year.map(_period) == name]
        daily_r = chosen.shadow_net.to_numpy()/1000
        momentum_summary[name] = {"sessions": len(chosen), "net_profit": round(float(chosen.shadow_net.sum()),2),
            "mean_final30_return": round(float(chosen.final30.mean()),8), "prediction_correlation": round(float(np.corrcoef(chosen.prediction,chosen.final30)[0,1]),6),
            "bootstrap_vs_zero": stationary_bootstrap_mean(daily_r.tolist(), samples, 10, 6300+len(momentum_summary))}
    noise = _trade_metrics(noise_trades, accepted); noise.pop("session_r",None)
    result = {"schema_version":1,"selection_eligible":False,
              "noise_area_vwap_shadow":{"adaptation":"NQ continuous futures; opposite noise band stop; 15:55 exit; this stop adaptation was not source-complete and is not selection eligible","metrics":noise},
              "intraday_momentum_shadow":{"coefficients_from_development":[round(float(value),10) for value in coefficients],"periods":momentum_summary,
                                           "adaptation":"first and penultimate 30-minute returns predict final 26-minute executable window; prior-half-hour extreme stop; baseline NQ costs"},
              "mnq_falsification_paper":{"status":"shadow_only_not_reproduced","reason":"Exact GMM features, retraining cadence, stops, and session rules were not all source-complete."},
              "vvg_classifier":{"status":"implemented_as_lag_safe_descriptive_feature","location":"phase5-features.parquet:vvg_regime_score"},
              "raw_cache_immutable": before == guard.checksums(manifest)}
    (root/"research/phase5-published-challengers.json").write_text(json.dumps(result,indent=2,default=str))
    return result
