from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, time
from pathlib import Path
from statistics import mean

import pandas as pd
import pandas_market_calendars as mcal

from .analytics import benjamini_hochberg, block_bootstrap, metrics
from .engine import ExecutionConfig, execute_signal
from .models import Bar, Signal, Trade
from .strategies import (
    StrategyAConfig, StrategyBConfig, first_candle_baseline, strategy_a,
    strategy_a_mechanical, strategy_b,
)

NQ_FP = "e0ae8898e1f56f76"
MNQ_FP = "a136a761bbf3d8a0"
ANCHORS = [time(9,45), time(9,50), time(9,55), time(10,0), time(10,5), time(10,10), time(10,15)]


def _bar(row) -> Bar:
    return Bar(row.ts_ny.to_pydatetime(), float(row.open), float(row.high), float(row.low), float(row.close), int(row.volume), int(row.instrument_id))


def _clone_signal(signal: Signal, *, variant: str, side: str | None = None, target_r: float | None = None) -> Signal:
    new_side = side or signal.side
    stop = signal.stop
    if side and side != signal.side:
        stop = signal.entry - (signal.stop - signal.entry)
    return Signal(signal.ts, signal.strategy, variant, new_side, signal.entry, stop, target_r or signal.target_r, signal.reason, signal.available_at, dict(signal.metadata))


def _quality(day: date, rth: pd.DataFrame, expected: int, degraded: set[date], roll_dates: set[date]) -> tuple[bool, dict]:
    times = set(rth.ts_ny.dt.time) if len(rth) else set()
    duplicate_count = int(rth.ts_ny.duplicated().sum()) if len(rth) else 0
    ranges = rth.high - rth.low if len(rth) else pd.Series(dtype=float)
    median_range = float(ranges.median()) if len(ranges) else 0
    suspicious = int(((ranges > max(50.0, median_range * 20))).sum()) if len(ranges) else 0
    missing = max(0, expected - int(rth.ts_ny.nunique()))
    checks = {
        "date": day.isoformat(), "bars": int(len(rth)), "expected": expected,
        "missing_minutes": missing, "duplicates": duplicate_count,
        "has_0930": time(9,30) in times, "has_0935": time(9,35) in times,
        "has_1000": time(10,0) in times, "suspicious_bars": suspicious,
        "degraded_condition": day in degraded, "roll_session": day in roll_dates,
        "legacy_feed": day < date(2017,5,21),
    }
    accepted = missing == 0 and duplicate_count == 0 and suspicious == 0 and checks["has_0930"] and checks["has_0935"] and checks["has_1000"] and day not in degraded and day not in roll_dates
    checks["accepted"] = accepted
    if not accepted:
        checks["reasons"] = [k for k,v in checks.items() if k in {"missing_minutes","duplicates","suspicious_bars"} and v] + [k for k in ("has_0930","has_0935","has_1000") if not checks[k]] + (["degraded_condition"] if day in degraded else []) + (["roll_session"] if day in roll_dates else [])
    return accepted, checks


def _roll_dates(mapping_files: list[Path]) -> set[date]:
    dates = set()
    for path in mapping_files:
        payload = json.loads(path.read_text())
        for mapping in payload.get("mappings", []):
            for interval in mapping.get("intervals", [])[1:]:
                dates.add(date.fromisoformat(interval["start_date"]))
    return dates


def _condition_dates(root: Path) -> tuple[set[date], list[dict]]:
    path = root / "conditions-2016-2025.json"
    if path.exists():
        rows = json.loads(path.read_text())
    else:
        from databento import Historical
        rows = Historical(os.environ["DATABENTO_API_KEY"]).metadata.get_dataset_condition("GLBX.MDP3", "2016-01-01", "2026-01-01")
        path.write_text(json.dumps(rows, indent=2))
    degraded = {date.fromisoformat(row["date"]) for row in rows if row.get("condition") != "available"}
    return degraded, rows


def _execute_day(key: str, signals: list[Signal], rth_bars: list[Bar], symbol: str, states: dict, specs: dict, day: date) -> None:
    state = states[key]
    config, starting = specs[key]
    daily_pnl, last_exit = 0.0, None
    by_ts = {b.ts: b for b in rth_bars}
    for signal in sorted(signals, key=lambda s: s.ts):
        if last_exit and signal.ts <= last_exit:
            state["skipped_overlap"] += 1
            continue
        if daily_pnl <= -state["equity"] * config.daily_loss_fraction:
            state["daily_loss_stops"] += 1
            break
        future = [b for b in rth_bars if b.ts >= signal.ts and b.ts.time() <= time(15,55)]
        if not future:
            continue
        trade = execute_signal(signal, future, state["equity"], symbol, config, f"{symbol}-{key}-{day.isoformat()}-{len(state['trades'])+1}")
        if trade is None:
            state["sizing_skips"] += 1
            continue
        entry_bar = by_ts.get(signal.ts)
        if entry_bar and entry_bar.instrument_id is not None:
            trade.underlying = str(entry_bar.instrument_id)
        trade.synthetic = False
        state["trades"].append(trade)
        state["equity"] += trade.net_pnl
        daily_pnl += trade.net_pnl
        last_exit = trade.exit_ts


def _summary(key: str, state: dict, starting: float) -> dict:
    trades = state["trades"]
    overall = metrics(trades, starting)
    split = {}
    for name, years in {"discovery":range(2018,2022), "validation":range(2022,2024), "blind_test":range(2024,2026)}.items():
        selected = [t for t in trades if t.entry_ts.year in years]
        split[name] = metrics(selected, starting)
    by_side = {side: metrics([t for t in trades if t.side == side], starting) for side in ("long","short")}
    profits_by_day = defaultdict(float)
    for trade in trades:
        profits_by_day[trade.entry_ts.date().isoformat()] += trade.net_pnl
    positive_days = sorted((p for p in profits_by_day.values() if p > 0), reverse=True)
    top5_share = sum(positive_days[:5]) / sum(positive_days) if positive_days and sum(positive_days) else 0
    strongest_removed = sorted(trades, key=lambda t:t.net_pnl, reverse=True)[5:]
    return {
        "id": key, "metrics": overall, "splits": split, "by_side": by_side,
        "block_bootstrap_expectancy_r": block_bootstrap(trades, samples=1000, seed=1701),
        "top_5_days_share_of_gross_profit": round(top5_share,4),
        "after_best_5_removed": metrics(strongest_removed, starting),
        "sizing_skips": state["sizing_skips"], "overlap_skips": state["skipped_overlap"],
        "daily_loss_stops": state["daily_loss_stops"],
    }


def run_research(root: Path = Path("data")) -> dict:
    manifest = json.loads((root / "manifest.json").read_text())
    degraded, condition_rows = _condition_dates(root)
    schedule = mcal.get_calendar("NYSE").schedule("2016-01-01", "2025-12-31")
    specs: dict[str, tuple[ExecutionConfig,float]] = {}
    for symbol in ("NQ","MNQ"):
        for target in (1,1.5,2,3,4):
            specs[f"{symbol}:A1_{target}R"] = (ExecutionConfig(risk_fraction=.01),100_000)
            specs[f"{symbol}:A2_1x_{target}R"] = (ExecutionConfig(risk_fraction=.01),100_000)
            specs[f"{symbol}:B1_{target}R"] = (ExecutionConfig(risk_fraction=.01),100_000)
        for attempts in (1,2,3,5): specs[f"{symbol}:A2_{attempts}x_2R"]=(ExecutionConfig(risk_fraction=.01),100_000)
        for variant in ("B2_2R","B3_2R","B4_2R","B1_range_stop","B1_structure_stop","B0_2R","C3_confluence","C4_failed_reversal","C5_sequential","C6_no_overlap_B_priority","C7_causal_router","C8_conflict_filter","C9_inverse_B1"):
            specs[f"{symbol}:{variant}"]=(ExecutionConfig(risk_fraction=.01),100_000)
        specs[f"{symbol}:B1_4R_cost2x"]=(ExecutionConfig(risk_fraction=.01,commission_per_side=5.10,slippage_ticks_per_side=2,spread_ticks=2),100_000)
        specs[f"{symbol}:B1_4R_cost4x"]=(ExecutionConfig(risk_fraction=.01,commission_per_side=10.20,slippage_ticks_per_side=4,spread_ticks=4),100_000)
        specs[f"{symbol}:B1_4R_fixed1"]=(ExecutionConfig(risk_fraction=1.0,max_contracts=1),100_000)
        for anchor in ANCHORS: specs[f"{symbol}:P{anchor.strftime('%H%M')}"]=(ExecutionConfig(risk_fraction=.01),100_000)
        for risk in (.0025,.005,.01,.10):
            specs[f"{symbol}:A1_2R_risk{risk*100:g}"]=(ExecutionConfig(starting_balance=10_000,risk_fraction=risk,max_contracts=100),10_000)
            specs[f"{symbol}:A1_4R_risk{risk*100:g}"]=(ExecutionConfig(starting_balance=10_000,risk_fraction=risk,max_contracts=100),10_000)
            specs[f"{symbol}:B2_2R_risk{risk*100:g}"]=(ExecutionConfig(starting_balance=100_000,risk_fraction=risk,max_contracts=100),100_000)
    states={key:{"equity":starting,"trades":[],"sizing_skips":0,"skipped_overlap":0,"daily_loss_stops":0} for key,(_,starting) in specs.items()}
    quality_reports, accepted_counts, opening_history = {}, defaultdict(int), defaultdict(list)

    datasets = [("NQ",NQ_FP),("MNQ",MNQ_FP)]
    for symbol, fingerprint in datasets:
        entry = manifest["datasets"][fingerprint]
        roll_dates = _roll_dates([Path(p["mapping_path"]) for p in entry["partitions"]])
        symbol_quality=[]
        for part in entry["partitions"]:
            year=part["year"]
            print(f"Auditing and backtesting {symbol} {year}", flush=True)
            df=pd.read_parquet(part["path"]).sort_index()
            df=df.reset_index().rename(columns={df.index.name or "index":"ts_event"})
            if "ts_event" not in df.columns: df=df.rename(columns={df.columns[0]:"ts_event"})
            df["ts_ny"]=pd.to_datetime(df.ts_event,utc=True).dt.tz_convert("America/New_York")
            df["local_date"]=df.ts_ny.dt.date
            year_schedule=schedule[schedule.index.year==year]
            for session_day,row in year_schedule.iterrows():
                day=session_day.date() if hasattr(session_day,"date") else session_day
                if symbol=="MNQ" and day<date(2019,5,6): continue
                market_open=row.market_open.tz_convert("America/New_York")
                market_close=row.market_close.tz_convert("America/New_York")
                day_df=df[df.local_date==day]
                rth=day_df[(day_df.ts_ny>=market_open)&(day_df.ts_ny<market_close)].copy()
                expected=int((market_close-market_open).total_seconds()/60)
                accepted, report=_quality(day,rth,expected,degraded,roll_dates)
                symbol_quality.append(report)
                if not accepted: continue
                # Use 2018 onward as the clean core even when legacy sessions happen to pass.
                if symbol=="NQ" and day<date(2018,1,1): continue
                accepted_counts[symbol]+=1
                overnight=day_df[(day_df.ts_ny.dt.time<time(9,30))].copy()
                rth_bars=[_bar(row) for row in rth.itertuples(index=False)]
                overnight_bars=[_bar(row) for row in overnight.itertuples(index=False)]
                day_signals:dict[str,list[Signal]]={}
                for target in (1,1.5,2,3,4):
                    day_signals[f"A1_{target}R"]=strategy_a(rth_bars,StrategyAConfig(variant=f"A1_{target}R",target_r=target))
                    day_signals[f"A2_1x_{target}R"]=strategy_a_mechanical(rth_bars,StrategyAConfig(variant=f"A2_1x_{target}R",target_r=target,max_attempts=1))
                    day_signals[f"B1_{target}R"]=strategy_b(rth_bars,overnight_bars,StrategyBConfig(variant=f"B1_{target}R",target_r=target))
                for attempts in (1,2,3,5): day_signals[f"A2_{attempts}x_2R"]=strategy_a_mechanical(rth_bars,StrategyAConfig(variant=f"A2_{attempts}x_2R",target_r=2,max_attempts=attempts))
                day_signals["B2_2R"]=strategy_b(rth_bars,overnight_bars,StrategyBConfig(variant="B2_2R",target_r=2))
                if day_signals["B2_2R"]:
                    # B2 is a breakout interpretation; replace B1 default variant behavior.
                    day_signals["B2_2R"]=strategy_b(rth_bars,overnight_bars,StrategyBConfig(variant="B2",target_r=2))
                day_signals["B3_2R"]=strategy_b(rth_bars,overnight_bars,StrategyBConfig(variant="B3",target_r=2,breakout_retest=True))
                day_signals["B4_2R"]=strategy_b(rth_bars,overnight_bars,StrategyBConfig(variant="B4",target_r=2,require_body_agreement=True))
                day_signals["B1_range_stop"]=strategy_b(rth_bars,overnight_bars,StrategyBConfig(variant="B1",target_r=2,stop_mode="range_from_entry"))
                day_signals["B1_structure_stop"]=strategy_b(rth_bars,overnight_bars,StrategyBConfig(variant="B1",target_r=2,stop_mode="structure"))
                day_signals["B1_4R_cost2x"]=[_clone_signal(s,variant="B1_4R_cost2x",target_r=4) for s in day_signals["B1_4R"]]
                day_signals["B1_4R_cost4x"]=[_clone_signal(s,variant="B1_4R_cost4x",target_r=4) for s in day_signals["B1_4R"]]
                day_signals["B1_4R_fixed1"]=[_clone_signal(s,variant="B1_4R_fixed1",target_r=4) for s in day_signals["B1_4R"]]
                day_signals["B0_2R"]=first_candle_baseline(rth_bars,2)
                for anchor in ANCHORS:
                    name=f"P{anchor.strftime('%H%M')}"
                    day_signals[name]=strategy_a_mechanical(rth_bars,StrategyAConfig(variant=name,target_r=2,max_attempts=1,anchor_time=anchor))
                a=day_signals["A1_2R"]; b=day_signals["B1_2R"]
                day_signals["C3_confluence"]=[_clone_signal(s,variant="C3") for s in a if b and s.side==b[0].side]
                day_signals["C8_conflict_filter"]=list(day_signals["C3_confluence"])
                day_signals["C5_sequential"]=[*b,*a]
                day_signals["C6_no_overlap_B_priority"]=[*b,*a]
                day_signals["C9_inverse_B1"]=[_clone_signal(s,variant="C9",side="short" if s.side=="long" else "long") for s in b]
                # Failure reversal becomes observable only if B has already closed for a loss.
                failed=[]
                if b:
                    probe=execute_signal(b[0],[x for x in rth_bars if x.ts>=b[0].ts],100_000,symbol,ExecutionConfig(risk_fraction=.01),"probe")
                    if probe and probe.net_pnl<0:
                        failed=[_clone_signal(s,variant="C4") for s in a if s.side!=b[0].side and s.ts>probe.exit_ts]
                day_signals["C4_failed_reversal"]=failed
                first_range=next(iter(b),None)
                opening_range=float(first_range.metadata.get("opening_range",0)) if first_range else 0
                prior=opening_history[symbol][-20:]
                threshold=sorted(prior)[len(prior)//2] if prior else None
                day_signals["C7_causal_router"]=(day_signals["B2_2R"] if threshold is not None and opening_range<=threshold else a)
                if opening_range: opening_history[symbol].append(opening_range)
                for name,signals in day_signals.items():
                    key=f"{symbol}:{name}"
                    if key in specs: _execute_day(key,signals,rth_bars,symbol,states,specs,day)
                for risk in (.0025,.005,.01,.10):
                    _execute_day(f"{symbol}:A1_2R_risk{risk*100:g}",a,rth_bars,symbol,states,specs,day)
                    _execute_day(f"{symbol}:A1_4R_risk{risk*100:g}",day_signals["A1_4R"],rth_bars,symbol,states,specs,day)
                    _execute_day(f"{symbol}:B2_2R_risk{risk*100:g}",day_signals["B2_2R"],rth_bars,symbol,states,specs,day)
        quality_reports[symbol]=symbol_quality

    summaries={key:_summary(key,state,specs[key][1]) for key,state in states.items()}
    ranked=sorted(summaries.values(),key=lambda x:x["splits"]["blind_test"]["expectancy_r"],reverse=True)
    test_family=[x for x in summaries.values() if "risk" not in x["id"] and "fixed1" not in x["id"] and "cost" not in x["id"]]
    discoveries=benjamini_hochberg([x["block_bootstrap_expectancy_r"]["p_value"] for x in test_family],alpha=.05)
    for item,significant in zip(test_family,discoveries): item["fdr_significant_5pct"]=significant
    for item in summaries.values(): item.setdefault("fdr_significant_5pct",False)
    credible=[x for x in ranked if x["splits"]["validation"]["expectancy_r"]>0 and x["splits"]["blind_test"]["expectancy_r"]>0 and x["block_bootstrap_expectancy_r"]["low"]>0 and x["fdr_significant_5pct"] and x["metrics"]["trades"]>=100 and ":P" not in x["id"] and "risk" not in x["id"]]
    result={
        "generated_at":datetime.now().astimezone().isoformat(), "data_mode":"real_licensed",
        "research_window":{"core":"2018-2025","discovery":"2018-2021","validation":"2022-2023","blind_test":"2024-2025","reserved_holdout":"2026 YTD — not downloaded"},
        "manifest_fingerprints":[NQ_FP,MNQ_FP], "accepted_sessions":dict(accepted_counts),
        "quality":{symbol:{"total":len(rows),"accepted":sum(r["accepted"] for r in rows),"excluded":sum(not r["accepted"] for r in rows),"legacy":sum(r["legacy_feed"] for r in rows),"degraded":sum(r["degraded_condition"] for r in rows),"roll":sum(r["roll_session"] for r in rows),"sessions":rows} for symbol,rows in quality_reports.items()},
        "dataset_conditions":{"records":len(condition_rows),"degraded_dates":sorted(d.isoformat() for d in degraded)},
        "strategies":summaries, "ranked_by_blind_expectancy":[x["id"] for x in ranked],
        "credible_candidates":[x["id"] for x in credible],
        "conclusion":"CANDIDATES REQUIRE PAPER TRADING" if credible else "NO RELIABLE EDGE DETECTED",
    }
    derived=root/"research";derived.mkdir(parents=True,exist_ok=True)
    (derived/"results.json").write_text(json.dumps(result,indent=2,default=str))
    trade_rows=[]
    for key,state in states.items():
        trade_rows.extend([{"run_variant":key,**t.to_dict()} for t in state["trades"]])
    pd.DataFrame(trade_rows).to_parquet(derived/"trades.parquet",index=False,compression="zstd")
    pd.DataFrame([r for rows in quality_reports.values() for r in rows]).to_parquet(derived/"quality.parquet",index=False,compression="zstd")
    return result
