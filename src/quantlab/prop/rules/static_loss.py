"""Static max loss: fixed equity floor at initial_balance - amount.

FTMO 2-Step Max Loss: "the equity ... must not drop below 90% of the
initial account balance at any given time" — equity-based, intraday,
strictly-below comparator (inclusive=False by default in the spec).
"""

from __future__ import annotations

import datetime as dt

from quantlab.prop.config import StaticMaxLossSpec, resolved_amount
from quantlab.prop.rules.base import BreachEvent, breached


class StaticMaxLossRule:
    def __init__(
        self, spec: StaticMaxLossSpec, initial_balance: float, account_size: float
    ) -> None:
        self.spec = spec
        self.amount = resolved_amount(spec, account_size)
        self.floor = initial_balance - self.amount
        self.name = "static_max_loss"

    def check(
        self, equity: float, date: dt.date, day_index: int, trade_index: int
    ) -> BreachEvent | None:
        if breached(equity, self.floor, self.spec.inclusive):
            return BreachEvent(
                rule=self.name,
                date=date,
                day_index=day_index,
                trade_index=trade_index,
                equity=equity,
                threshold=self.floor,
                detail=f"equity {equity:,.2f} fell to static floor {self.floor:,.2f}",
            )
        return None
