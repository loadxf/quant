"""Daily loss limit.

The line sits `width` below the day-open realized balance (the firm's
`day_boundary` supplies the reset instant: 17:00 CT futures roll, or
midnight Prague for FTMO — where the width is a fixed % of INITIAL
capital but the anchor re-bases every midnight and can move down with
the balance).

effect="fail": phase over (FTMO).
effect="lockout": flatten + no more trades this session, NOT a failure
(Topstep opt-in DLL, Apex EOD variant). The evaluator truncates the
day's PnL at exactly -width — a documented approximation.
"""

from __future__ import annotations

import datetime as dt

from quantlab.prop.config import DailyLossLimitSpec, resolved_amount
from quantlab.prop.rules.base import BreachEvent, breached


class DailyLossRule:
    def __init__(self, spec: DailyLossLimitSpec, account_size: float) -> None:
        self.spec = spec
        self.width = resolved_amount(spec, account_size)
        self.day_open: float = 0.0
        self.name = f"daily_loss_limit[{spec.effect}]"

    @property
    def level(self) -> float:
        return self.day_open - self.width

    def day_start(self, day_open_balance: float) -> None:
        self.day_open = day_open_balance

    def hit(self, equity: float) -> bool:
        return breached(equity, self.level, self.spec.inclusive)

    def breach_event(
        self, equity: float, date: dt.date, day_index: int, trade_index: int
    ) -> BreachEvent:
        return BreachEvent(
            rule=self.name,
            date=date,
            day_index=day_index,
            trade_index=trade_index,
            equity=equity,
            threshold=self.level,
            detail=f"equity {equity:,.2f} hit daily loss level {self.level:,.2f} "
            f"(day open {self.day_open:,.2f} - {self.width:,.0f})",
        )
