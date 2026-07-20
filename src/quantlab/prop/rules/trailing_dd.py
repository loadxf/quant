"""Trailing max drawdown — the load-bearing prop-firm rule.

Semantics (verified against official firm docs, 2026-07-19):
- The breach test is real-time intraday on equity INCLUDING unrealized
  P&L, regardless of ratchet mode ("If your Net P&L hits the limit at
  any point during the day, your account is liquidated" — Topstep;
  "touches or falls below ... at any time" — Apex; "at any time —
  through realized or unrealized losses" — TPT).
- ratchet="eod": the high-water mark advances only from end-of-day
  closing balances (intraday peaks do NOT raise the floor).
- ratchet="intraday": the high-water mark advances continuously from
  intraday peaks including open-position highs (MFE-aware).
- threshold = min(hwm - amount, threshold_cap): the floor freezes once
  it reaches the cap and never trails again.

Within-trade point ordering is unknowable from a trade log, so the
documented convention is high -> low -> close per trade: the favorable
excursion ratchets first (intraday mode), then the adverse excursion is
tested. This catches up-then-down moves inside a single trade and errs
slightly pessimistic.
"""

from __future__ import annotations

import datetime as dt

from quantlab.prop.config import TrailingDrawdownSpec, resolved_amount
from quantlab.prop.rules.base import BreachEvent, breached


class TrailingDrawdownRule:
    def __init__(
        self, spec: TrailingDrawdownSpec, initial_balance: float, account_size: float
    ) -> None:
        self.spec = spec
        self.amount = resolved_amount(spec, account_size)
        self.hwm = initial_balance
        self.name = f"trailing_drawdown[{spec.ratchet}]"

    @property
    def threshold(self) -> float:
        raw = self.hwm - self.amount
        if self.spec.threshold_cap is not None:
            return min(raw, self.spec.threshold_cap)
        return raw

    def observe_high(self, equity_high: float) -> None:
        """Intraday peak (MFE-refined). Only intraday ratchet advances here."""
        if self.spec.ratchet == "intraday":
            self.hwm = max(self.hwm, equity_high)

    def check(
        self, equity: float, date: dt.date, day_index: int, trade_index: int
    ) -> BreachEvent | None:
        if breached(equity, self.threshold, self.spec.inclusive):
            return BreachEvent(
                rule=self.name,
                date=date,
                day_index=day_index,
                trade_index=trade_index,
                equity=equity,
                threshold=self.threshold,
                detail=f"equity {equity:,.2f} hit trailing floor {self.threshold:,.2f} "
                f"(hwm {self.hwm:,.2f} - {self.amount:,.0f}"
                + (
                    f", capped at {self.spec.threshold_cap:,.0f})"
                    if self.spec.threshold_cap is not None
                    else ")"
                ),
            )
        return None

    def day_close(self, closing_balance: float) -> None:
        """EOD ratchet: the floor advances from closing balances only."""
        if self.spec.ratchet == "eod":
            self.hwm = max(self.hwm, closing_balance)
