from __future__ import annotations

import math
import random
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import Bar

NY = ZoneInfo("America/New_York")


def synthetic_session(day: date, seed: int = 17) -> list[Bar]:
    """Deterministic, visibly synthetic minute data for product demonstration."""
    rng = random.Random(seed + day.toordinal())
    start = datetime.combine(day, time(8, 30), NY)
    price = 14500 + (day.toordinal() % 420) * 4.7
    bars: list[Bar] = []
    for i in range(450):
        ts = start + timedelta(minutes=i)
        wave = math.sin(i / 19) * 0.8 + math.sin(i / 53) * 0.35
        shock = rng.gauss(0, 2.0 if i < 90 else 1.45)
        drift = ((day.toordinal() % 7) - 3) * 0.025
        close = price + wave + shock + drift
        high = max(price, close) + abs(rng.gauss(0, 0.9))
        low = min(price, close) - abs(rng.gauss(0, 0.9))
        bars.append(Bar(ts, round(price, 2), round(high, 2), round(low, 2), round(close, 2), int(600 + abs(rng.gauss(0, 420)))))
        price = close
    return bars
