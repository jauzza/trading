from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Feature:
    name: str
    value: float
    available_at: datetime


def features_available(features: list[Feature], decision_at: datetime) -> dict[str, float]:
    illegal = [f.name for f in features if f.available_at > decision_at]
    if illegal:
        raise ValueError(f"lookahead features unavailable at decision: {', '.join(illegal)}")
    return {f.name: f.value for f in features}
