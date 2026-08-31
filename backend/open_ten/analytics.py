from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean, pstdev

import numpy as np

from .models import Trade


def max_drawdown(equity: list[float]) -> tuple[float, int]:
    if not equity:
        return 0.0, 0
    peak, worst, duration, current = equity[0], 0.0, 0, 0
    for value in equity:
        if value >= peak:
            peak, current = value, 0
        else:
            current += 1
            duration = max(duration, current)
            if peak:
                worst = min(worst, value / peak - 1)
    return worst, duration


def metrics(trades: list[Trade], starting_balance: float) -> dict:
    trades = sorted(trades, key=lambda trade: (trade.entry_ts, trade.id))
    pnl = [trade.net_pnl for trade in trades]
    equity = [starting_balance]
    for value in pnl:
        equity.append(equity[-1] + value)
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    dd, dd_duration = max_drawdown(equity)
    returns = [value / starting_balance for value in pnl]
    std = pstdev(returns) if len(returns) > 1 else 0
    downside = [value for value in returns if value < 0]
    downside_std = pstdev(downside) if len(downside) > 1 else 0
    by_year: dict[int, float] = defaultdict(float)
    by_month: dict[str, float] = defaultdict(float)
    for trade in trades:
        by_year[trade.entry_ts.year] += trade.net_pnl
        by_month[trade.entry_ts.strftime("%Y-%m")] += trade.net_pnl
    years = max(1 / 252, (trades[-1].exit_ts - trades[0].entry_ts).days / 365.25) if trades else 0
    annualized = (equity[-1] / starting_balance) ** (1 / years) - 1 if years and equity[-1] > 0 else None

    def streak(winning: bool) -> int:
        best = current = 0
        for value in pnl:
            if (value > 0) == winning:
                current += 1
                best = max(best, current)
            else:
                current = 0
        return best

    avg_win = mean(wins) if wins else 0
    avg_loss = mean(losses) if losses else 0
    gross_profit = sum(wins)
    sorted_positive = sorted(wins, reverse=True)
    return {
        "net_profit": round(sum(pnl), 2), "total_return": round(equity[-1] / starting_balance - 1, 6),
        "ending_equity": round(equity[-1], 2),
        "annualized_return": round(annualized, 6) if annualized is not None else None,
        "trades": len(trades), "win_rate": round(len(wins) / len(pnl), 4) if pnl else 0,
        "profit_factor": round(gross_profit / abs(sum(losses)), 3) if losses else None,
        "gross_profit": round(gross_profit, 2), "gross_loss": round(sum(losses), 2),
        "average_win": round(avg_win, 2), "average_loss": round(avg_loss, 2),
        "expectancy": round(mean(pnl), 2) if pnl else 0,
        "expectancy_r": round(mean(trade.realized_r for trade in trades), 4) if trades else 0,
        "max_drawdown": round(dd, 6), "drawdown_duration_trades": dd_duration,
        "sharpe_trade": round(mean(returns) / std * math.sqrt(252), 3) if std else 0,
        "sortino_trade": round(mean(returns) / downside_std * math.sqrt(252), 3) if downside_std else 0,
        "calmar": round(annualized / abs(dd), 3) if annualized is not None and dd else 0,
        "reference_gross_pnl": round(sum(trade.gross_pnl for trade in trades), 2),
        "spread_cost": round(sum(trade.spread_cost for trade in trades), 2),
        "fees": round(sum(trade.fees for trade in trades), 2),
        "commission": round(sum(trade.commission for trade in trades), 2),
        "exchange_fees": round(sum(trade.exchange_fees for trade in trades), 2),
        "clearing_fees": round(sum(trade.clearing_fees for trade in trades), 2),
        "regulatory_fees": round(sum(trade.regulatory_fees for trade in trades), 2),
        "slippage": round(sum(trade.slippage for trade in trades), 2),
        "total_costs": round(sum(trade.total_costs for trade in trades), 2),
        "average_duration_minutes": round(mean(trade.duration_minutes for trade in trades), 1) if trades else 0,
        "average_mae_points": round(mean(trade.mae_points for trade in trades), 2) if trades else 0,
        "average_mfe_points": round(mean(trade.mfe_points for trade in trades), 2) if trades else 0,
        "max_consecutive_wins": streak(True), "max_consecutive_losses": streak(False),
        "top_trade_share_of_gross_profit": round(sorted_positive[0] / gross_profit, 4) if sorted_positive and gross_profit else 0,
        "top_5_trades_share_of_gross_profit": round(sum(sorted_positive[:5]) / gross_profit, 4) if gross_profit else 0,
        "positive_years": sum(value > 0 for value in by_year.values()), "years_observed": len(by_year),
        "by_year": dict(sorted(by_year.items())), "by_month": dict(sorted(by_month.items())),
        "equity": [round(value, 2) for value in equity],
    }


def chronological_splits(years: list[int], legacy_excluded: bool = True) -> dict[str, list[int]]:
    floor_year = 2018 if legacy_excluded else 2016
    clean = sorted(set(year for year in years if year >= floor_year))
    evaluation = [year for year in clean if 2024 <= year <= 2025]
    return {
        "discovery": [year for year in clean if year <= 2021],
        "validation": [year for year in clean if 2022 <= year <= 2023],
        "historical_evaluation": evaluation,
        "blind_test": evaluation,  # compatibility alias; not an untouched holdout
        "reserved_holdout": [year for year in clean if year >= 2026],
    }


def adjusted_p_values(p_values: list[float], method: str = "bh") -> list[float]:
    if not p_values:
        return []
    count = len(p_values)
    harmonic = sum(1 / index for index in range(1, count + 1)) if method == "by" else 1.0
    ordered = sorted(enumerate(p_values), key=lambda item: item[1])
    adjusted = [1.0] * count
    running = 1.0
    for rank in range(count, 0, -1):
        original_index, value = ordered[rank - 1]
        running = min(running, value * count * harmonic / rank)
        adjusted[original_index] = min(1.0, running)
    return adjusted


def benjamini_hochberg(p_values: list[float], alpha: float = .05) -> list[bool]:
    return [value <= alpha for value in adjusted_p_values(p_values, "bh")]


def _stationary_indices(rng: np.random.Generator, samples: int, length: int, mean_block: float) -> np.ndarray:
    """Politis-Romano stationary bootstrap with circular continuation."""
    indices = np.empty((samples, length), dtype=np.int32)
    indices[:, 0] = rng.integers(0, length, size=samples)
    restart_probability = 1.0 / max(1.0, mean_block)
    for column in range(1, length):
        restart = rng.random(samples) < restart_probability
        indices[:, column] = np.where(restart, rng.integers(0, length, size=samples), (indices[:, column - 1] + 1) % length)
    return indices


def stationary_bootstrap_mean(values: list[float] | np.ndarray, samples: int = 50_000, mean_block: float = 10, seed: int = 1701) -> dict:
    array = np.asarray(values, dtype=float)
    if not len(array):
        return {"low": 0, "median": 0, "high": 0, "p_value": 1.0, "samples": samples, "minimum_p_value": round(1 / (samples + 1), 8)}
    rng = np.random.default_rng(seed)
    draws = []
    for offset in range(0, samples, 2_000):
        size = min(2_000, samples - offset)
        draws.append(array[_stationary_indices(rng, size, len(array), mean_block)].mean(axis=1))
    boot = np.concatenate(draws)
    low, median, high = np.quantile(boot, [.025, .5, .975])
    return {
        "low": round(float(low), 6), "median": round(float(median), 6), "high": round(float(high), 6),
        "p_value": round((int(np.sum(boot <= 0)) + 1) / (samples + 1), 8), "samples": samples,
        "mean_block_sessions": mean_block, "minimum_p_value": round(1 / (samples + 1), 8),
    }


def paired_stationary_bootstrap(candidate: list[float], control: list[float], samples: int = 50_000, mean_block: float = 10, seed: int = 1701) -> dict:
    if len(candidate) != len(control):
        raise ValueError("paired comparisons require session-aligned arrays")
    difference = np.asarray(candidate) - np.asarray(control)
    result = stationary_bootstrap_mean(difference, samples, mean_block, seed)
    result["observed_mean_difference"] = round(float(np.mean(difference)), 6) if len(difference) else 0
    return result


def paired_matrix_bootstrap(candidate: np.ndarray, controls: np.ndarray, samples: int = 50_000, mean_block: float = 10, seed: int = 1701) -> list[dict]:
    """Shared-resample paired intervals for many controls on identical sessions."""
    candidate = np.asarray(candidate, dtype=float)
    controls = np.asarray(controls, dtype=float)
    if controls.ndim != 2 or controls.shape[0] != len(candidate):
        raise ValueError("controls must be sessions × rules and aligned to candidate")
    differences = candidate[:, None] - controls
    rng = np.random.default_rng(seed)
    chunks = []
    for offset in range(0, samples, 500):
        size = min(500, samples - offset)
        chunks.append(differences[_stationary_indices(rng, size, len(candidate), mean_block)].mean(axis=1))
    boot = np.concatenate(chunks, axis=0)
    results = []
    for column in range(controls.shape[1]):
        values = boot[:, column]
        low, median, high = np.quantile(values, [.025, .5, .975])
        results.append({
            "observed_mean_difference": round(float(differences[:, column].mean()), 6),
            "low": round(float(low), 6), "median": round(float(median), 6), "high": round(float(high), 6),
            "p_value": round((int(np.sum(values <= 0)) + 1) / (samples + 1), 8),
            "samples": samples, "mean_block_sessions": mean_block,
            "minimum_p_value": round(1 / (samples + 1), 8),
        })
    return results


def reality_check(matrix: np.ndarray, benchmark: np.ndarray, samples: int = 50_000, mean_block: float = 10, seed: int = 1701) -> dict:
    """White reality check and studentized SPA-style maximum test on aligned sessions."""
    values = np.asarray(matrix, dtype=float) - np.asarray(benchmark, dtype=float)[:, None]
    if not values.size:
        return {"reality_check_p_value": 1.0, "spa_p_value": 1.0, "samples": samples}
    observed = values.mean(axis=0)
    centered = values - observed
    scale = values.std(axis=0, ddof=1) / math.sqrt(len(values))
    scale = np.where(scale > 1e-12, scale, np.inf)
    observed_max = float(np.max(observed))
    observed_studentized = float(np.max(observed / scale))
    rng = np.random.default_rng(seed)
    rc_exceed = spa_exceed = 0
    for offset in range(0, samples, 1_000):
        size = min(1_000, samples - offset)
        means = centered[_stationary_indices(rng, size, len(values), mean_block)].mean(axis=1)
        rc_exceed += int(np.sum(np.max(means, axis=1) >= observed_max))
        spa_exceed += int(np.sum(np.max(means / scale, axis=1) >= observed_studentized))
    return {
        "observed_best_mean_difference": round(observed_max, 6),
        "reality_check_p_value": round((rc_exceed + 1) / (samples + 1), 8),
        "spa_p_value": round((spa_exceed + 1) / (samples + 1), 8),
        "samples": samples, "mean_block_sessions": mean_block,
        "minimum_p_value": round(1 / (samples + 1), 8),
    }


def block_bootstrap(trades: list[Trade], samples: int = 50_000, block: int = 10, seed: int = 1701) -> dict:
    """Compatibility wrapper; inference now uses a stationary block bootstrap."""
    return stationary_bootstrap_mean([trade.realized_r for trade in trades], samples, block, seed)
