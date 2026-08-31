from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from math import floor
from typing import Iterable, Literal

from .models import Bar, Signal, Trade


@dataclass(frozen=True, slots=True)
class FeeSchedule:
    """Transparent per-side assumptions; users can replace every component."""

    commission: float
    exchange: float
    clearing: float
    regulatory: float
    label: str = "custom"

    @property
    def per_side(self) -> float:
        return self.commission + self.exchange + self.clearing + self.regulatory


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    symbol: str
    point_value: float
    tick_size: float = 0.25
    launch_date: str = "1999-06-21"
    assumed_margin: float = 0.0


INSTRUMENTS = {
    "NQ": InstrumentSpec("NQ", 20.0, assumed_margin=22_000),
    "MNQ": InstrumentSpec("MNQ", 2.0, launch_date="2019-05-06", assumed_margin=2_200),
}

# Research assumptions, not claims about a particular broker account.
FEE_PRESETS = {
    "NQ": FeeSchedule(.75, 1.25, .45, .10, "NQ research assumption"),
    "MNQ": FeeSchedule(.45, .35, .30, .10, "MNQ research assumption"),
    "zero": FeeSchedule(0, 0, 0, 0, "zero-cost test"),
}


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    starting_balance: float = 100_000
    risk_fraction: float = .01
    risk_dollars: float | None = None
    fixed_contracts: int | None = None
    fee_schedule: FeeSchedule | None = None
    fee_multiplier: float = 1.0
    slippage_ticks_per_side: int = 1
    spread_ticks_round_trip: float = 1.0
    max_contracts: int = 20
    margin_per_contract: float = 0.0
    daily_loss_fraction: float = .03
    ambiguous_bar: Literal["adverse_first", "favorable_first"] = "adverse_first"


def fees_for(symbol: str, config: ExecutionConfig) -> FeeSchedule:
    return config.fee_schedule or FEE_PRESETS[symbol]


def round_to_tick(price: float, tick: float = .25, mode: str = "nearest") -> float:
    value = Decimal(str(price)) / Decimal(str(tick))
    rounding = {"nearest": ROUND_HALF_UP, "up": ROUND_CEILING, "down": ROUND_FLOOR}[mode]
    return float(value.quantize(Decimal("1"), rounding=rounding) * Decimal(str(tick)))


def round_trip_cost_per_contract(symbol: str, config: ExecutionConfig) -> float:
    spec = INSTRUMENTS[symbol]
    fee = fees_for(symbol, config).per_side * 2 * config.fee_multiplier
    spread = config.spread_ticks_round_trip * spec.tick_size * spec.point_value
    slippage = 2 * config.slippage_ticks_per_side * spec.tick_size * spec.point_value
    return fee + spread + slippage


def risk_per_contract(stop_points: float, symbol: str, config: ExecutionConfig) -> float:
    return stop_points * INSTRUMENTS[symbol].point_value + round_trip_cost_per_contract(symbol, config)


def position_size(equity: float, stop_points: float, symbol: str, config: ExecutionConfig) -> int:
    if equity <= 0 or stop_points <= 0:
        return 0
    per_contract = risk_per_contract(stop_points, symbol, config)
    if config.fixed_contracts is not None:
        contracts = max(0, config.fixed_contracts)
    else:
        allowed = config.risk_dollars if config.risk_dollars is not None else equity * config.risk_fraction
        contracts = floor(allowed / per_contract)
    contracts = min(contracts, config.max_contracts)
    if config.margin_per_contract > 0:
        contracts = min(contracts, floor(equity / config.margin_per_contract))
    return max(0, contracts)


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
    """Execute against OHLC bars with explicit, reconcilable transaction costs."""
    spec = INSTRUMENTS[symbol]
    reference_entry = round_to_tick(signal.entry, spec.tick_size)
    stop = round_to_tick(signal.stop, spec.tick_size, "down" if signal.side == "long" else "up")
    stop_points = abs(reference_entry - stop)
    contracts = position_size(equity, stop_points, symbol, config)
    if contracts < 1:
        return None
    direction = 1 if signal.side == "long" else -1
    target = None if signal.target_r is None else round_to_tick(reference_entry + direction * stop_points * signal.target_r, spec.tick_size)
    entry = round_to_tick(reference_entry + direction * config.slippage_ticks_per_side * spec.tick_size, spec.tick_size)
    reference_exit = reference_entry
    exit_ts = signal.ts
    outcome = "session_exit"
    min_low, max_high = reference_entry, reference_entry
    for bar in future_bars:
        min_low, max_high = min(min_low, bar.low), max(max_high, bar.high)
        stop_hit = bar.low <= stop if signal.side == "long" else bar.high >= stop
        target_hit = False if target is None else (bar.high >= target if signal.side == "long" else bar.low <= target)
        if stop_hit and target_hit:
            stop_hit = config.ambiguous_bar == "adverse_first"
            target_hit = not stop_hit
            outcome = "ambiguous_stop" if stop_hit else "ambiguous_target"
        if stop_hit:
            reference_exit = min(bar.open, stop) if signal.side == "long" else max(bar.open, stop)
            reference_exit = round_to_tick(reference_exit, spec.tick_size)
            exit_ts = bar.ts
            outcome = outcome if outcome.startswith("ambiguous") else "stop"
            break
        if target_hit:
            reference_exit = target
            exit_ts = bar.ts
            outcome = outcome if outcome.startswith("ambiguous") else "target"
            break
        reference_exit, exit_ts = round_to_tick(bar.close, spec.tick_size), bar.ts
    exit_price = round_to_tick(reference_exit - direction * config.slippage_ticks_per_side * spec.tick_size, spec.tick_size)

    reference_gross = direction * (reference_exit - reference_entry) * spec.point_value * contracts
    actual_gross = direction * (exit_price - entry) * spec.point_value * contracts
    slippage = max(0.0, reference_gross - actual_gross)
    spread = config.spread_ticks_round_trip * spec.tick_size * spec.point_value * contracts
    schedule = fees_for(symbol, config)
    multiplier = 2 * contracts * config.fee_multiplier
    commission = schedule.commission * multiplier
    exchange = schedule.exchange * multiplier
    clearing = schedule.clearing * multiplier
    regulatory = schedule.regulatory * multiplier
    fees = commission + exchange + clearing + regulatory
    total_costs = spread + slippage + fees
    net = reference_gross - total_costs
    initial_risk = stop_points * spec.point_value * contracts
    mae = reference_entry - min_low if signal.side == "long" else max_high - reference_entry
    mfe = max_high - reference_entry if signal.side == "long" else reference_entry - min_low
    return Trade(
        id=trade_id, strategy=signal.strategy, variant=signal.variant, side=signal.side,
        signal_ts=signal.ts, entry_ts=signal.ts, exit_ts=exit_ts, instrument=symbol,
        underlying=f"{symbol}.v.0", contracts=contracts, entry=entry, stop=stop,
        target=target, exit=exit_price, reference_entry=reference_entry,
        reference_exit=reference_exit, gross_pnl=round(reference_gross, 2),
        spread_cost=round(spread, 2), commission=round(commission, 2),
        exchange_fees=round(exchange, 2), clearing_fees=round(clearing, 2),
        regulatory_fees=round(regulatory, 2), fees=round(fees, 2),
        slippage=round(slippage, 2), total_costs=round(total_costs, 2),
        net_pnl=round(net, 2), realized_r=round(net / initial_risk, 4) if initial_risk else 0,
        outcome=outcome, reason=signal.reason, mae_points=round(max(0, mae), 2),
        mfe_points=round(max(0, mfe), 2),
        duration_minutes=max(0, (exit_ts - signal.ts).total_seconds() / 60),
    )
