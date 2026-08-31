from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PortfolioRisk:
    equity: float
    daily_loss_limit: float
    max_open_risk: float
    realized_today: float = 0
    open_risk: float = 0

    def reserve(self, requested: float) -> bool:
        if requested <= 0 or self.realized_today <= -self.daily_loss_limit:
            return False
        if self.open_risk + requested > self.max_open_risk:
            return False
        self.open_risk += requested
        return True

    def close(self, reserved: float, pnl: float) -> None:
        self.open_risk = max(0, self.open_risk - reserved)
        self.realized_today += pnl
