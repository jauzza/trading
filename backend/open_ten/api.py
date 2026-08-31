from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .data import DataRequest, DataVault
from .engine import ExecutionConfig, compound_losses, break_even_win_rate, execute_signal
from .fred import fred_status
from .models import Bar
from .paper import PaperJournal
from .quality import audit_session
from .strategies import StrategyAConfig, StrategyBConfig, aggregate_five_minute, ema, strategy_a, strategy_b
from .synthetic import synthetic_session

app = FastAPI(title="OPEN / TEN Research API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
vault = DataVault(Path("data"))
paper = PaperJournal()


class EstimateBody(BaseModel):
    symbol: str = "NQ.v.0"
    start: str = "2018-01-01"
    end: str = "2026-01-01"


class PaperActivationBody(BaseModel):
    activated_at: str
    exit_method: str = "stop_and_1555"


class PaperEventBody(BaseModel):
    event_type: str
    session_ts: str
    payload: dict


@app.get("/api/health")
def health() -> dict:
    mode = "real_licensed" if Path("data/research/results.json").exists() else "synthetic"
    return {"status": "ready", "mode": mode, "live_trading": False}


def _without_equity(metrics: dict) -> dict:
    return {k:v for k,v in metrics.items() if k != "equity"}


@lru_cache(maxsize=1)
def _overview() -> dict:
    path=Path("data/research/results.json")
    if not path.exists():
        return {"status":"unavailable","data_mode":"synthetic"}
    import json
    result=json.loads(path.read_text())
    strategies={}
    for key,item in result["strategies"].items():
        metrics_payload=dict(item["metrics"])
        equity=metrics_payload.pop("equity",[])
        metrics_payload.pop("by_month",None)
        strategies[key]={
            "metrics":metrics_payload,"equity":equity,"periods":item["periods"],
            "anchored_periods":item["anchored_periods"],"after_best_5_removed":_without_equity(item["after_best_5_removed"]),
            "evidence":item["evidence"],"sizing_skips":item["sizing_skips"],
        }
    return {
        "status":"ready","data_mode":result["data_mode"],"generated_at":result["generated_at"],
        "conclusion":result["conclusion"],"research_window":result["research_window"],
        "accepted_sessions":result["accepted_sessions"],"quality":{k:{x:v[x] for x in ("total","accepted","excluded","legacy","degraded","roll")} for k,v in result["quality"].items()},
        "degraded_dates":result["dataset_conditions"]["degraded_dates"],"credible_candidates":result["credible_candidates"],
        "strategies":strategies,"statistics":result["statistics"],"execution_assumptions":result["execution_assumptions"],
        "session_definition":result["session_definition"],"frozen_candidate":result["frozen_candidate"],"fred":fred_status(),
        "before_after":{
            "before":{"variant":"NQ:B1_4R dynamic 1%","net_profit":508160,"total_return":5.0816,"max_drawdown":-.2575,"method":"spread omitted from P&L; same-day-only EMA; period equity leaked"},
            "after":{"variant":"NQ:B_EMA_FULL_4R_risk1","net_profit":result["strategies"]["NQ:B_EMA_FULL_4R_risk1"]["metrics"]["net_profit"],"total_return":result["strategies"]["NQ:B_EMA_FULL_4R_risk1"]["metrics"]["total_return"],"max_drawdown":result["strategies"]["NQ:B_EMA_FULL_4R_risk1"]["metrics"]["max_drawdown"],"method":"spread, slippage and contract fees applied; full overnight EMA; independent periods"},
        },
    }


@app.get("/api/research/overview")
def research_overview() -> dict:
    return _overview()


@lru_cache(maxsize=1)
def _opening_overview() -> dict:
    import json
    path=Path("data/research/opening-candle-results.json")
    if not path.exists():
        return {"status":"unavailable"}
    return {"status":"ready",**json.loads(path.read_text())}


@app.get("/api/research/opening")
def opening_research_overview() -> dict:
    return _opening_overview()


@lru_cache(maxsize=1)
def _phase4_overview() -> dict:
    import json
    path = Path("data/research/phase4-results.json")
    if not path.exists():
        return {"status": "unavailable"}
    return {"status": "ready", **json.loads(path.read_text())}


@app.get("/api/research/phase4")
def phase4_research_overview() -> dict:
    return _phase4_overview()


def _compact_phase5_summary(item: dict) -> dict:
    """Return dashboard-safe aggregates without the large per-session vectors."""
    payload = dict(item)
    payload.pop("session_r", None)
    equity = payload.get("equity", [])
    if len(equity) > 240:
        indices = sorted({round(index * (len(equity) - 1) / 239) for index in range(240)})
        payload["equity"] = [equity[index] for index in indices]
    periods = {}
    for name, period in payload.get("periods", {}).items():
        periods[name] = {key: value for key, value in period.items() if key not in {"session_r", "equity"}}
    payload["periods"] = periods
    for delay in payload.get("delay_stress", {}).values():
        delay.pop("session_r", None)
        delay.pop("equity", None)
    return payload


@lru_cache(maxsize=1)
def _phase5_overview() -> dict:
    import json
    path = Path("data/research/phase5-results.json")
    if not path.exists():
        return {"status": "unavailable"}
    result = json.loads(path.read_text())
    summaries = {
        key: _compact_phase5_summary(value)
        for key, value in result.get("summaries", {}).items()
    }
    good_bad_path = Path("data/research/phase5-good-bad-day.json")
    good_bad = json.loads(good_bad_path.read_text()) if good_bad_path.exists() else None
    challenger_path = Path("data/research/phase5-published-challengers.json")
    challengers = json.loads(challenger_path.read_text()) if challenger_path.exists() else None
    robustness_path = Path("data/research/phase5-c01-robustness.json")
    robustness = json.loads(robustness_path.read_text()) if robustness_path.exists() else None
    supplemental_path = Path("data/research/phase5-supplemental.json")
    supplemental = json.loads(supplemental_path.read_text()) if supplemental_path.exists() else None
    return {
        "status": "ready",
        "schema_version": result.get("schema_version"),
        "generated_at": result.get("generated_at"),
        "data_window": result.get("data_window"),
        "accepted_sessions": result.get("accepted_sessions"),
        "holdout_guard": result.get("holdout_guard"),
        "raw_cache_immutable": result.get("raw_cache", {}).get("immutable"),
        "candidate_dispositions": result.get("candidate_dispositions", {}),
        "summaries": summaries,
        "inference": result.get("inference", {}),
        "limitations": result.get("limitations", []),
        "good_bad_day": {
            "conclusion": good_bad.get("conclusion"),
            "proposed_filter": good_bad.get("proposed_filter"),
            "small_models": good_bad.get("small_models"),
        } if good_bad else None,
        "published_challengers": challengers,
        "robustness": robustness,
        "supplemental": {
            "c01": supplemental.get("run_audits", {}).get("NQ:C01:matched_4R:fixed1"),
            "expanding_walk_forward": supplemental.get("expanding_walk_forward", []),
            "selection_eligible": supplemental.get("selection_eligible"),
        } if supplemental else None,
    }


@app.get("/api/research/phase5")
def phase5_research_overview() -> dict:
    return _phase5_overview()


@app.get("/api/research/phase5/trades")
def phase5_research_trades(run_key: str = "NQ:C01:matched_4R:fixed1", limit: int = 200) -> dict:
    import pandas as pd
    path = Path("data/research/phase5-trades.parquet")
    if not path.exists():
        return {"status": "unavailable", "trades": []}
    frame = pd.read_parquet(path, filters=[[('run_key', '=', run_key)]])
    frame = frame.sort_values("entry_ts", ascending=False).head(min(max(limit, 1), 1000))
    rows = frame.astype(object).where(frame.notna(), None).to_dict(orient="records")
    return {"status": "ready", "run_key": run_key, "trades": rows}


@app.get("/api/research/phase5/features")
def phase5_research_features(strategy: str = "C01", limit: int = 5000) -> dict:
    import pandas as pd
    path = Path("data/research/phase5-features.parquet")
    if not path.exists():
        return {"status": "unavailable", "features": []}
    frame = pd.read_parquet(path, filters=[[('strategy', '=', strategy)]])
    frame = frame.head(min(max(limit, 1), 20_000))
    rows = frame.astype(object).where(frame.notna(), None).to_dict(orient="records")
    return {"status": "ready", "strategy": strategy, "features": rows}


def _phase7_json(name: str) -> dict:
    import json
    path = Path("phase7") / name
    if not path.exists():
        return {"status": "unavailable"}
    return {"status": "ready", **json.loads(path.read_text())}


@lru_cache(maxsize=1)
def _phase7_summary() -> dict:
    import json
    directory = Path("phase7")
    required = [
        "PHASE7_RESEARCH_CONTRACT.json", "c01_loss_taxonomy.json", "c01_winner_taxonomy.json",
        "c01_early_management_results.json", "tail_dependence.json", "cost_stress.json",
        "execution_stress.json", "phase7_experiment_registry.json", "FUTURE_HOLDOUT_FREEZE.json",
        "strategy_tournament.json", "multiple_testing_results.json",
    ]
    if any(not (directory / name).exists() for name in required):
        return {"status": "unavailable"}
    contract = json.loads((directory / required[0]).read_text())
    losses = json.loads((directory / required[1]).read_text())["labels"]
    winners = json.loads((directory / required[2]).read_text())["features"]
    management = json.loads((directory / required[3]).read_text())
    tail = json.loads((directory / required[4]).read_text())["C01_CAUSAL"]
    cost = json.loads((directory / required[5]).read_text())
    execution = json.loads((directory / required[6]).read_text())
    registry = json.loads((directory / required[7]).read_text())
    holdout = json.loads((directory / required[8]).read_text())
    tournament = json.loads((directory / required[9]).read_text())
    statistics = json.loads((directory / required[10]).read_text())
    baseline = json.loads(Path("phase6/c01_v1_frozen_baseline.json").read_text())["corrected_phase6_result"]
    best_management_name, best_management = max(management["rules"].items(), key=lambda item: item[1]["improvement"])
    return {
        "status": "ready", "schema_version": 1, "contract_id": contract["contract_id"],
        "data_boundary": contract["data_boundary"], "holdout": holdout,
        "baseline": {key: baseline[key] for key in ["accepted_sessions", "trades", "net_profit", "profit_factor", "win_rate", "max_drawdown", "positive_years", "net_after_best_trade", "net_after_best_5", "net_after_best_1pct", "median_trade", "by_year", "equity"]},
        "tail": tail, "cost_stress": cost["multipliers"], "execution_stress": execution,
        "losses": sorted(({"name": name, **value} for name, value in losses.items()), key=lambda row: row["count"], reverse=True),
        "winners": sorted(({"name": name, **value} for name, value in winners.items()), key=lambda row: row["lift_r"], reverse=True),
        "management": {"best_rule": best_management_name, "best": best_management, "rules": management["rules"]},
        "registry": {"consumed": registry["consumed"], "maximum": registry["maximum_configurations"], "remaining": registry["remaining"]},
        "tournament": tournament, "statistics": statistics,
        "classification": "EXPLORATORY", "verdict": "Historically profitable, but exceptional-trade dependence prevents holdout promotion.",
        "feature_legend": {"PRE_ENTRY": "known before order submission", "ENTRY_TIME": "known when order may be submitted", "POST_ENTRY": "known only after entry", "OUTCOME_ONLY": "descriptive hindsight only"},
        "research_brain": "research_brain/00_INDEX.md",
    }


@app.get("/api/research/phase7/summary")
def phase7_summary() -> dict:
    return _phase7_summary()


@app.get("/api/research/phase7/c01/anatomy")
def phase7_c01_anatomy(limit: int = 250, executed_only: bool = True) -> dict:
    import pandas as pd
    path = Path("phase7/c01_trade_anatomy.parquet")
    if not path.exists():
        return {"status": "unavailable", "rows": []}
    frame = pd.read_parquet(path)
    if executed_only:
        frame = frame[frame.trade_executed]
    columns = [name for name in ["date", "entry_ts_trade", "side", "r_outcome", "outcome_class", "path_shape", "risk_points", "time_to_mfe", "time_to_mae", "time_to_opening_range_reentry", "time_to_vwap_cross", "time_to_1r", "time_to_2r", "time_to_3r", "time_to_4r", "opening_range_atr", "overnight_alignment", "vwap_alignment", "key_level_room_r"] if name in frame]
    frame = frame.sort_values("date", ascending=False).head(min(max(limit, 1), 2000))
    return {"status": "ready", "rows": frame[columns].astype(object).where(frame[columns].notna(), None).to_dict(orient="records")}


@app.get("/api/research/phase7/c01/failures")
def phase7_c01_failures() -> dict:
    return _phase7_json("c01_loss_taxonomy.json")


@app.get("/api/research/phase7/c01/winners")
def phase7_c01_winners() -> dict:
    return _phase7_json("c01_winner_taxonomy.json")


@app.get("/api/research/phase7/c01/regimes")
def phase7_c01_regimes() -> dict:
    return _phase7_json("c01_regime_analysis.json")


@app.get("/api/research/phase7/c01/interactions")
def phase7_c01_interactions() -> dict:
    return _phase7_json("c01_interaction_analysis.json")


@app.get("/api/research/phase7/c01/management")
def phase7_c01_management() -> dict:
    return _phase7_json("c01_early_management_results.json")


@app.get("/api/research/phase7/strategies")
def phase7_strategies() -> dict:
    return _phase7_json("strategy_discovery_results.json")


@app.get("/api/research/phase7/complementarity")
def phase7_complementarity() -> dict:
    return _phase7_json("strategy_complementarity.json")


@app.get("/api/research/phase7/tournament")
def phase7_tournament() -> dict:
    return _phase7_json("strategy_tournament.json")


@app.get("/api/research/phase7/experiments")
def phase7_experiments() -> dict:
    return _phase7_json("phase7_experiment_registry.json")


@app.get("/api/research/phase7/statistics")
def phase7_statistics() -> dict:
    return _phase7_json("multiple_testing_results.json")


@app.get("/api/paper/status")
def paper_status() -> dict:
    return paper.status()


@app.post("/api/paper/activate")
def paper_activate(body: PaperActivationBody) -> dict:
    try:
        return paper.activate(body.activated_at, body.exit_method)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/paper/events")
def paper_append(body: PaperEventBody) -> dict:
    try:
        return paper.append(body.event_type, body.session_ts, body.payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/paper/events")
def paper_events(limit: int = 500) -> dict:
    return {"evidence_label": "Prospective paper", "historical_results_merged": False, "events": paper.events(limit)}


@app.get("/api/data/status")
def data_status() -> dict:
    import json
    path=Path("data/manifest.json")
    if not path.exists(): return {"status":"empty","datasets":[]}
    manifest=json.loads(path.read_text())
    return {"status":"cached","datasets":[{"fingerprint":fp,"symbol":d["request"]["symbol"],"partitions":len(d["partitions"]),"rows":sum(p["rows"] for p in d["partitions"]),"estimated_cost_usd":d["estimated_cost_usd"]} for fp,d in manifest["datasets"].items()]}


@app.get("/api/data/fred/status")
def data_fred_status() -> dict:
    return fred_status()


@app.get("/api/research/trades")
def research_trades(variant: str="NQ:B_EMA_FULL_4R_fixed1", limit: int=200) -> dict:
    import pandas as pd
    path=Path("data/research/trades.parquet")
    if not path.exists(): return {"status":"unavailable","trades":[]}
    frame=pd.read_parquet(path,filters=[[('run_variant','=',variant)]]).sort_values("entry_ts",ascending=False).head(min(limit,1000))
    return {"status":"ready","variant":variant,"trades":frame.astype(object).where(frame.notna(),None).to_dict(orient="records")}


@app.get("/api/research/session/{iso_day}")
def research_session(iso_day: str, symbol: str="NQ", indicator: str="overnight_ema12") -> dict:
    import json
    import pandas as pd
    day=date.fromisoformat(iso_day); symbol=symbol.upper()
    if day.year >= 2026:
        raise HTTPException(status_code=403, detail="protected market holdout rejected before cache inspection")
    fp={"NQ":"e0ae8898e1f56f76","MNQ":"a136a761bbf3d8a0"}.get(symbol)
    if not fp: raise HTTPException(status_code=400,detail="symbol must be NQ or MNQ")
    path=Path(f"data/raw/{fp}/year={day.year}/bars.parquet")
    if not path.exists(): raise HTTPException(status_code=404,detail="session not cached")
    frame=pd.read_parquet(path).reset_index()
    prior=Path(f"data/raw/{fp}/year={day.year-1}/bars.parquet")
    if prior.exists() and day.month==1 and day.day<=15:
        prior_frame=pd.read_parquet(prior).reset_index()
        frame=pd.concat([prior_frame.tail(20_000),frame],ignore_index=True)
    frame["ts_ny"]=pd.to_datetime(frame.ts_event,utc=True).dt.tz_convert("America/New_York")
    start=pd.Timestamp(datetime.combine(day-__import__('datetime').timedelta(days=1),__import__('datetime').time(18),tzinfo=ZoneInfo("America/New_York")))
    end=pd.Timestamp(datetime.combine(day,__import__('datetime').time(16),tzinfo=ZoneInfo("America/New_York")))
    session=frame[(frame.ts_ny>=start)&(frame.ts_ny<end)]
    rth=session[(session.ts_ny.dt.date==day)&(session.ts_ny.dt.time>=__import__('datetime').time(9,30))]
    bars=[{"time":int(row.ts_event.timestamp()),"open":row.open,"high":row.high,"low":row.low,"close":row.close,"volume":row.volume,"instrument_id":row.instrument_id} for row in rth.itertuples()]
    context=[Bar(row.ts_ny.to_pydatetime(),float(row.open),float(row.high),float(row.low),float(row.close),int(row.volume),int(row.instrument_id)) for row in session.itertuples()]
    if indicator == "c01_ema200":
        rth_history = frame[(frame.ts_ny < end) & (frame.ts_ny.dt.time >= __import__('datetime').time(9,30)) & (frame.ts_ny.dt.time < __import__('datetime').time(16,0))]
        fifteen_bars = []
        for _, group in rth_history.groupby(rth_history.ts_ny.dt.date, sort=True):
            rows = list(group.sort_values("ts_ny").itertuples(index=False))
            for index in range(0, len(rows), 15):
                block = rows[index:index + 15]
                if len(block) != 15:
                    continue
                fifteen_bars.append(Bar(block[0].ts_ny.to_pydatetime(), float(block[0].open), max(float(row.high) for row in block),
                                        min(float(row.low) for row in block), float(block[-1].close), sum(int(row.volume) for row in block)))
        values = ema([bar.close for bar in fifteen_bars], 200)
        ema_points = [{"time": int((bar.ts + __import__('datetime').timedelta(minutes=14)).timestamp()), "value": round(value, 3)}
                      for bar, value in zip(fifteen_bars, values) if bar.ts.date() == day]
        indicator_label = "EMA200 · completed 15m RTH"
    elif indicator == "none":
        ema_points = []; indicator_label = None
    else:
        fives=aggregate_five_minute(context);values=ema([bar.close for bar in fives],12)
        ema_points=[{"time":int((bar.ts+__import__('datetime').timedelta(minutes=4)).timestamp()),"value":round(value,3)} for bar,value in zip(fives,values) if bar.ts.date()==day and bar.ts.time()>=__import__('datetime').time(9,30)]
        indicator_label = "EMA12 · full overnight 5m"
    return {"status":"ready","data_mode":"real_licensed_cached_only","symbol":symbol,"date":iso_day,"bars":bars,"ema":ema_points,"indicator_label":indicator_label}


@app.post("/api/data/estimate")
def estimate(body: EstimateBody) -> dict:
    return vault.estimate(DataRequest(symbol=body.symbol, start=body.start, end=body.end))


@app.post("/api/data/download")
def download(body: EstimateBody, approved_fingerprint: str | None = None) -> dict:
    try:
        return vault.download(DataRequest(symbol=body.symbol, start=body.start, end=body.end), approved_fingerprint)
    except (PermissionError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/demo/session/{iso_day}")
def demo_session(iso_day: str) -> dict:
    bars = synthetic_session(date.fromisoformat(iso_day))
    a = strategy_a(bars, StrategyAConfig(target_r=2))
    b = strategy_b(bars, synthetic_session(date.fromisoformat(iso_day))[:60], StrategyBConfig())
    config = ExecutionConfig()
    trades = []
    for idx, signal in enumerate([*a, *b]):
        future = [bar for bar in bars if bar.ts >= signal.ts]
        trade = execute_signal(signal, future, 100_000, "NQ", config, f"SYN-{iso_day}-{idx+1:02d}")
        if trade:
            trades.append(trade.to_dict())
    return {"synthetic": True, "quality": audit_session(bars).to_dict(), "bars": [{"time": int(b.ts.timestamp()), "open":b.open,"high":b.high,"low":b.low,"close":b.close,"volume":b.volume} for b in bars], "signals": [s.metadata | {"time": int(s.ts.timestamp()), "side":s.side,"variant":s.variant,"entry":s.entry,"stop":s.stop} for s in [*a,*b]], "trades": trades}


@app.get("/api/math/audit")
def math_audit() -> dict:
    return {"five_losses_at_10pct": compound_losses(.10, 5), "breakeven_at_4r_before_costs": break_even_win_rate(4)}
