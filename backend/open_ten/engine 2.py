from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from math import floor
from typing import Iterable, Literal

from .models import Bar, Signal, Trade


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    symbol: str
    point_value: float
    tick_size: float = 0.25
    launch_date: str = "1999-06-21"


INSTRUMENTS = {
    "NQ": InstrumentSpec("NQ", 20.0),
    "MNQ": InstrumentSpec("MNQ", 2.0, launch_date="2019-05-06"),
}


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    starting_balance: float = 100_000
    risk_fraction: float = 0.01
    commission_per_side: float = 2.55
    slippage_ticks_per_side: int = 1
    spread_ticks: int = 1
    max_contracts: int = 20
    daily_loss_fraction: float = 0.03
    ambiguous_bar: Literal["adverse_first", "favorable_first"] = "adverse_first"


def round_to_tick(price: float, tick: float = 0.25, mode: str = "nearest") -> float:
    value = Decimal(str(price)) / Decimal(str(tick))
    rounding = {"nearest": ROUND_HALF_UP, "up": ROUND_CEILING, "down": ROUND_FLOOR}[mode]
    return float(value.quantize(Decimal("1"), rounding=rounding) * Decimal(str(tick)))


def risk_per_contract(stop_points: float, symbol: str, config: ExecutionConfig) -> float:
    spec = INSTRUMENTS[symbol]
    friction = (2 * config.slippage_ticks_per_side + config.spread_ticks) * spec.tick_size * spec.point_value
    fees = 2 * config.commission_per_side
    return stop_points * spec.point_value + friction + fees


def position_size(equity: float, stop_points: float, symbol: str, config: ExecutionConfig) -> int:
    if equity <= 0 or stop_points <= 0:
        return 0
    allowed = equity * config.risk_fraction
    contracts = floor(allowed / risk_per_contract(stop_points, symbol, config))
    return max(0, min(contracts, config.max_contracts))


def break_even_win_rate(reward_r: float, round_trip_cost_r: float = 0.0) -> float:
    if reward_r <= 0:
        raise ValueError("reward must be positive")
    return (1 + round_trip_cost_r) / (reward_r + 1)


def compound_losses(risk_fraction: float, count: int) -> float:
    return 1 - (1 - risk_fraction) ** count


def execute_signal(
    signal: Signal,
    future_bars: Iterable[Bar],
    equity: float,
    symbol: str,
    config: ExecutionConfig,
    trade_id: str,
) -> Trade | None:
    spec = INSTRUMENTS[symbol]
    stop_points = abs(signal.entry - signal.stop)
    contracts = position_size(equity, stop_points, symbol, config)
    if contracts < 1:
        return None
    direction = 1 if signal.side == "long" else -1
    target = round_to_tick(signal.entry + direction * stop_points * signal.target_r)
    entry_slip = config.slippage_ticks_per_side * spec.tick_size * direction
    fill_entry = round_to_tick(signal.entry + entry_slip)
    exit_price = fill_entry
    exit_ts = signal.ts
    outcome = "session_exit"
    min_low, max_high = fill_entry, fill_entry
    for bar in future_bars:
        min_low, max_high = min(min_low, bar.low), max(max_high, bar.high)
        stop_hit = bar.low <= signal.stop if signal.side == "long" else bar.high >= signal.stop
        target_hit = bar.high >= target if signal.side == "long" else bar.low <= target
        if stop_hit and target_hit:
            stop_hit = config.ambiguous_bar == "adverse_first"
            target_hit = not stop_hit
            outcome = "ambiguous_stop" if stop_hit else "ambiguous_target"
        if stop_hit:
            gap_price = min(bar.open, signal.stop) if signal.side == "long" else max(bar.open, signal.stop)
            exit_price = round_to_tick(gap_price - direction * config.slippage_ticks_per_side * spec.tick_size)
            exit_ts, outcome = bar.ts, outcome if outcome.startswith("ambiguous") else "stop"
            break
        if target_hit:
            exit_price = round_to_tick(target - direction * config.slippage_ticks_per_side * spec.tick_size)
            exit_ts, outcome = bar.ts, outcome if outcome.startswith("ambiguous") else "target"
            break
        exit_price, exit_ts = bar.close, bar.ts
    gross = direction * (exit_price - fill_entry) * spec.point_value * contracts
    fees = 2 * config.commission_per_side * contracts
    slip = 2 * config.slippage_ticks_per_side * spec.tick_size * spec.point_value * contracts
    net = gross - fees
    initial_risk = stop_points * spec.point_value * contracts
    mae = fill_entry - min_low if signal.side == "long" else max_high - fill_entry
    mfe = max_high - fill_entry if signal.side == "long" else fill_entry - min_low
    return Trade(
        id=trade_id, strategy=signal.strategy, variant=signal.variant, side=signal.side,
        signal_ts=signal.ts, entry_ts=signal.ts, exit_ts=exit_ts, instrument=symbol,
        underlying=f"{symbol}.v.0", contracts=contracts, entry=fill_entry, stop=signal.stop,
        target=target, exit=exit_price, gross_pnl=round(gross, 2), fees=round(fees, 2),
        slippage=round(slip, 2), net_pnl=round(net, 2),
        realized_r=round(net / initial_risk, 4) if initial_risk else 0,
        outcome=outcome, reason=signal.reason, mae_points=round(max(0,mae),2),
        mfe_points=round(max(0,mfe),2), duration_minutes=max(0,(exit_ts-signal.ts).total_seconds()/60),
    )
