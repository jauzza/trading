from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import datetime, time, timedelta
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
    """Pivots carry the timestamp at which their right-hand bars make them legal."""
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
        if len(group) != 5 or any((group[i].ts - group[i-1].ts) != timedelta(minutes=1) for i in range(1, 5)):
            continue
        result.append(Bar(group[0].ts, group[0].open, max(x.high for x in group), min(x.low for x in group), group[-1].close, sum(x.volume for x in group)))
    return sorted(result, key=lambda b: b.ts)


def opening_candle(bars: list[Bar], start: time = time(9, 30)) -> Bar | None:
    minutes = [b for b in bars if b.ts.time() >= start][:5]
    if len(minutes) != 5 or minutes[0].ts.time() != start:
        return None
    if any((minutes[i].ts - minutes[i-1].ts) != timedelta(minutes=1) for i in range(1, 5)):
        return None
    return Bar(minutes[0].ts, minutes[0].open, max(b.high for b in minutes), min(b.low for b in minutes), minutes[-1].close, sum(b.volume for b in minutes))


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
    stop_mode: str = "confirmed_pivot"


def strategy_a(bars: list[Bar], config: StrategyAConfig = StrategyAConfig()) -> list[Signal]:
    """Causal sweep → displacement → retest using explicitly available stops."""
    at_anchor = next((i for i, b in enumerate(bars) if b.ts.time() == config.anchor_time), None)
    if at_anchor is None:
        return []
    level = bars[at_anchor].open
    pivots = confirmed_pivots(bars)
    state, swept_side, sweep_extreme, attempts = "seek_sweep", None, None, 0
    signals: list[Signal] = []
    for i in range(at_anchor, len(bars) - 1):
        bar, nxt = bars[i], bars[i + 1]
        if bar.ts.time() > config.latest_entry or attempts >= config.max_attempts:
            break
        if state == "seek_sweep":
            if bar.high >= level + config.min_sweep:
                state, swept_side, sweep_extreme = "seek_displacement", "up", bar.high
            elif bar.low <= level - config.min_sweep:
                state, swept_side, sweep_extreme = "seek_displacement", "down", bar.low
        elif state == "seek_displacement":
            body = abs(bar.close - bar.open)
            crossed = bar.close < level if swept_side == "up" else bar.close > level
            if crossed and body >= config.displacement_body:
                state = "seek_retest"
        elif state == "seek_retest":
            touched = bar.high >= level - config.retest_tolerance if swept_side == "up" else bar.low <= level + config.retest_tolerance
            rejected = bar.close <= level - config.confirmation if swept_side == "up" else bar.close >= level + config.confirmation
            if not (touched and rejected):
                continue
            side = "short" if swept_side == "up" else "long"
            if config.stop_mode == "confirmed_pivot":
                kind = "high" if side == "short" else "low"
                legal = [p for p in pivots if p["kind"] == kind and p["available_at"] <= bar.ts and p["pivot_ts"] >= bars[at_anchor].ts]
                if not legal:
                    continue
                chosen = legal[-1]
                stop = float(chosen["price"])
                stop_source = f"confirmed_{kind}"
            else:
                stop = float(sweep_extreme)
                stop_source = "sweep_extreme"
            stop = max(stop, bar.high) if side == "short" else min(stop, bar.low)
            if abs(nxt.open - stop) < 1:
                continue
            signals.append(Signal(
                nxt.ts, "10:00 level", config.variant, side, nxt.open, stop,
                config.target_r, "confirmed sweep, displacement and retest", nxt.ts,
                {"level": level, "sweep": str(swept_side), "stop_source": stop_source},
            ))
            attempts += 1
            state = "seek_sweep"
    return signals


def strategy_a_mechanical(bars: list[Bar], config: StrategyAConfig = StrategyAConfig(variant="A2", max_attempts=3)) -> list[Signal]:
    at_anchor = next((i for i, b in enumerate(bars) if b.ts.time() == config.anchor_time), None)
    if at_anchor is None:
        return []
    level, signals = bars[at_anchor].open, []
    for i in range(at_anchor + 1, len(bars) - 1):
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
        if abs(nxt.open - stop) < 1:
            continue
        signals.append(Signal(nxt.ts, "10:00 level", config.variant, side, nxt.open, stop, config.target_r, "mechanical level touch and closed rejection", nxt.ts, {"level": level, "attempt": len(signals) + 1}))
    return signals


@dataclass(frozen=True)
class StrategyBConfig:
    variant: str = "B1"
    target_r: float = 2.0
    require_body_agreement: bool = False
    require_slope: bool = False
    breakout_retest: bool = False
    stop_mode: str = "opposite_side"
    opening_time: time = time(9, 30)
    direction_mode: str = "close_vs_ema"
    ema_period: int = 12
    min_warmup_periods: int = 12
    random_seed: int = 1701
    ema_session: str = "full_overnight"


def _stable_random_side(day: datetime, seed: int) -> str:
    digest = hashlib.sha256(f"{day.date().isoformat()}:{seed}".encode()).digest()
    return "long" if random.Random(int.from_bytes(digest[:8])).random() >= .5 else "short"


def strategy_b(bars: list[Bar], warmup_bars: Iterable[Bar] = (), config: StrategyBConfig = StrategyBConfig()) -> list[Signal]:
    opening = opening_candle(bars, config.opening_time)
    if opening is None:
        return []
    context = sorted([*warmup_bars, *[b for b in bars if b.ts <= opening.ts + timedelta(minutes=4)]], key=lambda b: b.ts)
    fives = aggregate_five_minute(context)
    opening_five = next((b for b in fives if b.ts == opening.ts), None)
    if opening_five is None:
        return []
    idx = fives.index(opening_five)
    closes = [b.close for b in fives[:idx + 1]]
    e = ema(closes, config.ema_period)
    if len(e) < config.min_warmup_periods:
        return []
    mode = config.direction_mode
    if mode == "candle_body":
        if opening.close == opening.open:
            return []
        side = "long" if opening.close > opening.open else "short"
    elif mode == "always_long":
        side = "long"
    elif mode == "always_short":
        side = "short"
    elif mode == "random":
        side = _stable_random_side(opening.ts, config.random_seed)
    elif mode == "overnight_direction":
        warm = sorted(warmup_bars, key=lambda b: b.ts)
        if len(warm) < 2 or warm[-1].close == warm[0].open:
            return []
        side = "long" if warm[-1].close > warm[0].open else "short"
    elif mode == "ema_slope_only":
        if len(e) < 2 or e[-1] == e[-2]:
            return []
        side = "long" if e[-1] > e[-2] else "short"
    else:
        if opening.close == e[-1]:
            return []
        side = "long" if opening.close > e[-1] else "short"
        if mode == "inverted_ema":
            side = "short" if side == "long" else "long"
    slope_agrees = len(e) > 1 and ((e[-1] > e[-2]) == (side == "long"))
    body_agrees = (opening.close > opening.open) == (side == "long")
    if (config.require_body_agreement or mode == "ema_body_agreement") and not body_agrees:
        return []
    if config.require_slope and not slope_agrees:
        return []

    decision = (datetime.combine(opening.ts.date(), config.opening_time, opening.ts.tzinfo) + timedelta(minutes=5)).time()
    after = [b for b in bars if b.ts.time() >= decision]
    if not after:
        return []
    entry_bar = after[0]
    if config.variant in {"B2", "B3"}:
        threshold = opening.high if side == "long" else opening.low
        breakout_i = next((i for i, b in enumerate(after) if (b.high > threshold if side == "long" else b.low < threshold)), None)
        if breakout_i is None or breakout_i + 1 >= len(after):
            return []
        entry_bar = after[breakout_i + 1]
        if config.variant == "B3":
            candidates = after[breakout_i + 1:]
            retest = next((b for b in candidates if (b.low <= threshold <= b.close if side == "long" else b.high >= threshold >= b.close)), None)
            if retest is None or after.index(retest) + 1 >= len(after):
                return []
            entry_bar = after[after.index(retest) + 1]
    if config.stop_mode == "range_from_entry":
        opening_range = opening.high - opening.low
        stop = entry_bar.open - opening_range if side == "long" else entry_bar.open + opening_range
    elif config.stop_mode == "structure":
        available = [b for b in bars if b.ts < entry_bar.ts][-3:]
        if not available:
            return []
        stop = min(b.low for b in available) if side == "long" else max(b.high for b in available)
    else:
        stop = opening.low if side == "long" else opening.high
    return [Signal(
        entry_bar.ts, "First candle + EMA", config.variant, side, entry_bar.open, stop,
        config.target_r, f"{mode} using {config.ema_session} EMA context", entry_bar.ts,
        {"ema": round(e[-1], 2), "ema_slope": round(e[-1] - e[-2], 4) if len(e) > 1 else 0,
         "opening_range": round(opening.high - opening.low, 2), "body_agrees": body_agrees,
         "ema_session": config.ema_session, "direction_mode": mode,
         "opening_time": config.opening_time.strftime("%H:%M")},
    )]


def first_candle_baseline(bars: list[Bar], target_r: float = 2.0) -> list[Signal]:
    return strategy_b(bars, bars[:0], StrategyBConfig(variant="B0", target_r=target_r, direction_mode="candle_body", min_warmup_periods=1, ema_session="none"))
