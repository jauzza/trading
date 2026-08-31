from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal

Side = Literal["long", "short"]


@dataclass(frozen=True, slots=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    instrument_id: int | None = None

    def __post_init__(self) -> None:
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("invalid OHLC bar")


@dataclass(slots=True)
class Signal:
    ts: datetime
    strategy: str
    variant: str
    side: Side
    entry: float
    stop: float
    target_r: float | None
    reason: str
    available_at: datetime
    metadata: dict[str, float | str | bool] = field(default_factory=dict)


@dataclass(slots=True)
class Trade:
    id: str
    strategy: str
    variant: str
    side: Side
    signal_ts: datetime
    entry_ts: datetime
    exit_ts: datetime
    instrument: str
    underlying: str
    contracts: int
    entry: float
    stop: float
    target: float | None
    exit: float
    reference_entry: float
    reference_exit: float
    gross_pnl: float
    spread_cost: float
    commission: float
    exchange_fees: float
    clearing_fees: float
    regulatory_fees: float
    fees: float
    slippage: float
    total_costs: float
    net_pnl: float
    realized_r: float
    outcome: str
    reason: str
    mae_points: float = 0.0
    mfe_points: float = 0.0
    duration_minutes: float = 0.0
    synthetic: bool = True

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("signal_ts", "entry_ts", "exit_ts"):
            data[key] = data[key].isoformat()
        return data


@dataclass(slots=True)
class RejectedTrade:
    ts: datetime
    strategy: str
    reason: str
    requested_risk: float
    minimum_risk: float
    achieved_risk: float = 0.0
