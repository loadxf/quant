"""Minimum trading days pass-gate (a day counts once it has >= 1 trade)."""

from __future__ import annotations

from quantlab.prop.config import MinTradingDaysSpec


class MinTradingDaysGate:
    def __init__(self, spec: MinTradingDaysSpec) -> None:
        self.spec = spec
        self.name = "min_trading_days"

    def satisfied(self, trading_days_so_far: int) -> bool:
        return trading_days_so_far >= self.spec.days
