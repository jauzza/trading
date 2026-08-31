from __future__ import annotations

import math
import random
from collections import defaultdict
from statistics import mean, pstdev

from .models import Trade


def max_drawdown(equity: list[float]) -> tuple[float, int]:
    peak, worst, duration, current = equity[0], 0.0, 0, 0
    for value in equity:
        if value >= peak:
            peak, current = value, 0
        else:
            current += 1
            duration = max(duration, current)
            worst = min(worst, value / peak - 1)
    return worst, duration


def metrics(trades: list[Trade], starting_balance: float) -> dict:
    pnl = [t.net_pnl for t in trades]
    equity = [starting_balance]
    for value in pnl:
        equity.append(equity[-1] + value)
    wins = [v for v in pnl if v > 0]
    losses = [v for v in pnl if v < 0]
    dd, dd_duration = max_drawdown(equity)
    returns = [p / starting_balance for p in pnl]
    std = pstdev(returns) if len(returns) > 1 else 0
    downside = [r for r in returns if r < 0]
    downside_std = pstdev(downside) if len(downside) > 1 else 0
    by_year: dict[int, float] = defaultdict(float)
    for trade in trades:
        by_year[trade.entry_ts.year] += trade.net_pnl
    years = max(1/252, (trades[-1].exit_ts - trades[0].entry_ts).days / 365.25) if trades else 0
    annualized = (equity[-1]/starting_balance)**(1/years)-1 if years and equity[-1] > 0 else None
    def streak(winning: bool) -> int:
        best=current=0
        for value in pnl:
            if (value>0)==winning:
                current+=1;best=max(best,current)
            else: current=0
        return best
    avg_win=mean(wins) if wins else 0; avg_loss=mean(losses) if losses else 0
    loss_rate=len(losses)/len(pnl) if pnl else 0
    payoff=avg_win/abs(avg_loss) if avg_loss else 0
    ruin=((loss_rate/(1-loss_rate))**max(1,payoff)) if 0<loss_rate<.5 and payoff else (1.0 if loss_rate>=.5 and sum(pnl)<=0 else 0.0)
    return {
        "net_profit": round(sum(pnl), 2), "total_return": round(equity[-1]/starting_balance-1, 6),
        "annualized_return": round(annualized,6) if annualized is not None else None,
        "trades": len(trades), "win_rate": round(len(wins)/len(pnl), 4) if pnl else 0,
        "profit_factor": round(sum(wins)/abs(sum(losses)), 3) if losses else None,
        "gross_profit":round(sum(wins),2), "gross_loss":round(sum(losses),2),
        "average_win":round(avg_win,2), "average_loss":round(avg_loss,2),
        "expectancy": round(mean(pnl), 2) if pnl else 0,
        "expectancy_r": round(mean(t.realized_r for t in trades), 4) if trades else 0,
        "max_drawdown": round(dd, 6), "drawdown_duration_trades": dd_duration,
        "sharpe_trade": round(mean(returns)/std*math.sqrt(252), 3) if std else 0,
        "sortino_trade":round(mean(returns)/downside_std*math.sqrt(252),3) if downside_std else 0,
        "calmar":round(annualized/abs(dd),3) if annualized is not None and dd else 0,
        "fees": round(sum(t.fees for t in trades), 2), "slippage": round(sum(t.slippage for t in trades), 2),
        "average_duration_minutes":round(mean(t.duration_minutes for t in trades),1) if trades else 0,
        "average_mae_points":round(mean(t.mae_points for t in trades),2) if trades else 0,
        "average_mfe_points":round(mean(t.mfe_points for t in trades),2) if trades else 0,
        "max_consecutive_wins":streak(True), "max_consecutive_losses":streak(False),
        "risk_of_ruin_estimate":round(min(1,max(0,ruin)),6),
        "by_year": dict(sorted(by_year.items())), "equity": [round(x,2) for x in equity],
    }


def block_bootstrap(trades: list[Trade], samples: int = 500, block: int = 5, seed: int = 1701) -> dict:
    rng = random.Random(seed)
    values = [t.realized_r for t in trades]
    if not values:
        return {"low": 0, "median": 0, "high": 0, "p_value": 1.0}
    means = []
    for _ in range(samples):
        draw = []
        while len(draw) < len(values):
            start = rng.randrange(len(values))
            draw.extend(values[start:start+block] or values[:block])
        means.append(mean(draw[:len(values)]))
    means.sort()
    nonpositive = sum(value <= 0 for value in means)
    return {"low": round(means[int(samples*.025)],4), "median": round(means[samples//2],4), "high": round(means[int(samples*.975)],4), "p_value": round((nonpositive+1)/(samples+1),6)}


def chronological_splits(years: list[int], legacy_excluded: bool = True) -> dict[str, list[int]]:
    floor_year = 2018 if legacy_excluded else 2016
    clean = sorted(set(y for y in years if y >= floor_year))
    return {"discovery": [y for y in clean if y <= 2021], "validation": [y for y in clean if 2022 <= y <= 2023], "blind_test": [y for y in clean if 2024 <= y <= 2025], "reserved_holdout": [y for y in clean if y >= 2026]}


def benjamini_hochberg(p_values: list[float], alpha: float = .05) -> list[bool]:
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    cutoff = -1
    for rank, (_, p) in enumerate(indexed, 1):
        if p <= alpha * rank / len(p_values):
            cutoff = rank
    selected = {idx for idx, _ in indexed[:cutoff]} if cutoff > 0 else set()
    return [i in selected for i in range(len(p_values))]
