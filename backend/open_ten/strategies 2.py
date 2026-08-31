from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Iterable

from .models import Bar, Signal


def ema(values: list[float], period: int = 12) -> list[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(alpha * value + (1 - alpha) * out[-1])
    return out


def confirmed_pivots(bars: list[Bar], left: int = 2, right: int = 2) -> list[dict]:
    """Return pivots with the timestamp when each becomes legally observable."""
    pivots = []
    for i in range(left, len(bars) - right):
        window = bars[i-left:i+right+1]
        if bars[i].high == max(x.high for x in window):
            pivots.append({"kind": "high", "pivot_ts": bars[i].ts, "available_at": bars[i+right].ts, "price": bars[i].high})
        if bars[i].low == min(x.low for x in window):
            pivots.append({"kind": "low", "pivot_ts": bars[i].ts, "available_at": bars[i+right].ts, "price": bars[i].low})
    return pivots


def aggregate_five_minute(bars: list[Bar]) -> list[Bar]:
    groups: dict[tuple, list[Bar]] = {}
    for bar in bars:
        minute = bar.ts.minute - bar.ts.minute % 5
        key = (bar.ts.date(), bar.ts.hour, minute)
        groups.setdefault(key, []).append(bar)
    result = []
    for group in groups.values():
        group.sort(key=lambda b: b.ts)
        if len(group) != 5:
            continue
        result.append(Bar(group[0].ts, group[0].open, max(x.high for x in group), min(x.low for x in group), group[-1].close, sum(x.volume for x in group)))
    return sorted(result, key=lambda b: b.ts)


@dataclass(frozen=True)
class StrategyAConfig:
    variant: str = "A1"
    min_sweep: float = 4.0
    displacement_body: float = 3.0
    retest_tolerance: float = 1.5
    confirmation: float = 1.0
    target_r: float = 2.0
    latest_entry: time = time(11, 30)
    max_attempts: int = 1
    stop_buffer: float = 1.0
    anchor_time: time = time(10, 0)


def strategy_a(bars: list[Bar], config: StrategyAConfig = StrategyAConfig()) -> list[Signal]:
    """Causal sweep → displacement → retest state machine.

    Every transition uses the just-closed minute. Entry is the next bar's open,
    so no fill occurs at an unexecutable signal close.
    """
    at_ten = next((i for i, b in enumerate(bars) if b.ts.time() == config.anchor_time), None)
    if at_ten is None:
        return []
    level = bars[at_ten].open
    state, swept_side, structural, attempts = "seek_sweep", None, None, 0
    signals: list[Signal] = []
    for i in range(at_ten, len(bars) - 1):
        bar, nxt = bars[i], bars[i + 1]
        if bar.ts.time() > config.latest_entry or attempts >= config.max_attempts:
            break
        if state == "seek_sweep":
            if bar.high >= level + config.min_sweep:
                state, swept_side, structural = "seek_displacement", "up", bar.high
            elif bar.low <= level - config.min_sweep:
                state, swept_side, structural = "seek_displacement", "down", bar.low
        elif state == "seek_displacement":
            body = abs(bar.close - bar.open)
            crossed = bar.close < level if swept_side == "up" else bar.close > level
            if crossed and body >= config.displacement_body:
                state = "seek_retest"
        elif state == "seek_retest":
            touched = bar.high >= level - config.retest_tolerance if swept_side == "up" else bar.low <= level + config.retest_tolerance
            rejected = bar.close <= level - config.confirmation if swept_side == "up" else bar.close >= level + config.confirmation
            if touched and rejected:
                side = "short" if swept_side == "up" else "long"
                stop = max(float(structural), bar.high) if side == "short" else min(float(structural), bar.low)
                signals.append(Signal(nxt.ts, "10:00 level", config.variant, side, nxt.open, stop, config.target_r, "confirmed sweep, displacement and retest", nxt.ts, {"level": level, "sweep": swept_side}))
                attempts += 1
                state = "seek_sweep"
    return signals


def strategy_a_mechanical(bars: list[Bar], config: StrategyAConfig = StrategyAConfig(variant="A2", max_attempts=3)) -> list[Signal]:
    """Mechanical level touch and rejection; never shares A1's structure state."""
    at_ten = next((i for i, b in enumerate(bars) if b.ts.time() == config.anchor_time), None)
    if at_ten is None:
        return []
    level, signals = bars[at_ten].open, []
    for i in range(at_ten + 1, len(bars) - 1):
        bar, nxt = bars[i], bars[i + 1]
        if bar.ts.time() > config.latest_entry or len(signals) >= config.max_attempts:
            break
        touched = bar.low <= level + config.retest_tolerance and bar.high >= level - config.retest_tolerance
        long_reject = touched and bar.close >= level + config.confirmation and bar.close > bar.open
        short_reject = touched and bar.close <= level - config.confirmation and bar.close < bar.open
        if not long_reject and not short_reject:
            continue
        side = "long" if long_reject else "short"
        stop = bar.low - config.stop_buffer if side == "long" else bar.high + config.stop_buffer
        if abs(nxt.open - stop) < 1.0:
            continue
        signals.append(Signal(
            nxt.ts, "10:00 level", config.variant, side, nxt.open, stop,
            config.target_r, "mechanical level touch and closed rejection", nxt.ts,
            {"level": level, "attempt": len(signals) + 1},
        ))
    return signals


@dataclass(frozen=True)
class StrategyBConfig:
    variant: str = "B1"
    target_r: float = 2.0
    require_body_agreement: bool = False
    require_slope: bool = False
    breakout_retest: bool = False
    stop_mode: str = "opposite_side"


def strategy_b(bars: list[Bar], overnight_bars: Iterable[Bar] = (), config: StrategyBConfig = StrategyBConfig()) -> list[Signal]:
    all_bars = sorted([*overnight_bars, *bars], key=lambda b: b.ts)
    fives = aggregate_five_minute(all_bars)
    opening = next((b for b in fives if b.ts.time() == time(9, 30)), None)
    if opening is None:
        return []
    idx = fives.index(opening)
    closes = [b.close for b in fives[: idx + 1]]
    e = ema(closes, 12)
    if len(e) < 12 or opening.close == e[-1]:
        return []
    side = "long" if opening.close > e[-1] else "short"
    if config.require_body_agreement and ((opening.close > opening.open) != (side == "long")):
        return []
    if config.require_slope and len(e) > 1 and ((e[-1] > e[-2]) != (side == "long")):
        return []
    after = [b for b in bars if b.ts.time() >= time(9, 35)]
    if not after:
        return []
    entry_bar = after[0]
    if config.variant in {"B2", "B3"}:
        threshold = opening.high if side == "long" else opening.low
        breakout_i = next((i for i, b in enumerate(after) if b.high > threshold if side == "long"), None) if side == "long" else next((i for i, b in enumerate(after) if b.low < threshold), None)
        if breakout_i is None or breakout_i + 1 >= len(after):
            return []
        entry_bar = after[breakout_i + 1]
        if config.variant == "B3":
            retest = next((b for b in after[breakout_i + 1:] if b.low <= threshold <= b.close) if side == "long" else (b for b in after[breakout_i + 1:] if b.high >= threshold >= b.close), None)
            if retest is None:
                return []
            ri = after.index(retest)
            if ri + 1 >= len(after):
                return []
            entry_bar = after[ri + 1]
    if config.stop_mode == "range_from_entry":
        opening_range = opening.high - opening.low
        stop = entry_bar.open - opening_range if side == "long" else entry_bar.open + opening_range
    elif config.stop_mode == "structure":
        available = [b for b in bars if b.ts < entry_bar.ts][-3:]
        stop = min(b.low for b in available) if side == "long" else max(b.high for b in available)
    else:
        stop = opening.low if side == "long" else opening.high
    return [Signal(entry_bar.ts, "5m + EMA", config.variant, side, entry_bar.open, stop, config.target_r, "completed 09:30 candle relative to 12 EMA", entry_bar.ts, {"ema": round(e[-1], 2), "opening_range": round(opening.high-opening.low, 2)})]


def first_candle_baseline(bars: list[Bar], target_r: float = 2.0) -> list[Signal]:
    opening_bars = [b for b in bars if time(9, 30) <= b.ts.time() < time(9, 35)]
    after = next((b for b in bars if b.ts.time() >= time(9, 35)), None)
    if len(opening_bars) != 5 or after is None:
        return []
    opening = Bar(opening_bars[0].ts, opening_bars[0].open, max(b.high for b in opening_bars), min(b.low for b in opening_bars), opening_bars[-1].close)
    if opening.close == opening.open:
        return []
    side = "long" if opening.close > opening.open else "short"
    stop = opening.low if side == "long" else opening.high
    return [Signal(after.ts, "First-candle control", "B0", side, after.open, stop, target_r, "first candle body direction without EMA", after.ts, {"opening_range": opening.high-opening.low})]
