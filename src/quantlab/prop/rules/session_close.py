"""Hard daily flatten deadline — Topstep: flat by 15:10 America/Chicago.

Verified 2026-08-13: all positions must be closed by 3:10 PM CT (or the
product's earlier close); the platform force-flattens at the deadline.
A trade log containing a position open at/after the deadline could not
have come from a compliant account, so the deterministic evaluator
treats it as a breach.

Anchoring: the deadline instant belongs to the ENTRY's trading session
(17:00 CT roll). A trade opened 18:00 CT belongs to the next session and
may legally be held overnight to the next morning; any position spanning
15:10 of its own session — including one entered in the prohibited
15:10-17:00 window — violates.

Ordering convention: equity-based breaches (which occur at unknowable
intraday times) resolve first for a given trade; the session-close check
runs only if the trade survived them, and BEFORE any pass check — a
violating trade can never deliver the pass. Deterministic, documented,
slightly pessimistic.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from quantlab.prop.config import SessionCloseSpec
from quantlab.prop.rules.base import BreachEvent
from quantlab.schema.trade import DayBoundary, Trade, TradeLog


class SessionCloseRule:
    def __init__(self, spec: SessionCloseSpec, boundary: DayBoundary) -> None:
        self.spec = spec
        self.boundary = boundary
        self.tzinfo = ZoneInfo(spec.tz)
        self.close_time = spec.close_time()
        self.name = "session_close"

    def deadline(self, trade: Trade) -> dt.datetime:
        """The hard-close instant of the trade's ENTRY session."""
        session = self.boundary.session_date(trade.entry_time)
        return dt.datetime.combine(session, self.close_time, tzinfo=self.tzinfo)

    def violation(
        self,
        trade: Trade,
        date: dt.date,
        day_index: int,
        trade_index: int,
        equity: float,
    ) -> BreachEvent | None:
        deadline = self.deadline(trade)
        if trade.exit_time >= deadline:
            local_close = deadline.strftime("%H:%M:%S %Z")
            return BreachEvent(
                rule=self.name,
                date=date,
                day_index=day_index,
                trade_index=trade_index,
                equity=equity,
                threshold=0.0,
                detail=(
                    f"position open at/after the {local_close} hard close of its "
                    f"{deadline.date()} session (entry {trade.entry_time.isoformat()}, "
                    f"exit {trade.exit_time.isoformat()})"
                ),
            )
        return None


def count_session_close_violations(
    log: TradeLog, spec: SessionCloseSpec, boundary: DayBoundary
) -> int:
    """Source-log screen for the day-granular Monte Carlo, which cannot
    see clock times: how many trades span their session's hard close."""
    rule = SessionCloseRule(spec, boundary)
    return sum(1 for trade in log.trades if trade.exit_time >= rule.deadline(trade))
