"""Calendar time limit fail-gate (Apex 4.0: 30-day one-time evals)."""

from __future__ import annotations

import datetime as dt

from quantlab.prop.config import TimeLimitSpec


class TimeLimitGate:
    def __init__(self, spec: TimeLimitSpec) -> None:
        self.spec = spec
        self.name = "time_limit"
        self.start: dt.date | None = None

    def expired(self, date: dt.date) -> bool:
        """True when `date` falls outside the allowed window. Day 1 is the
        first trading day, so a 30-day limit allows dates start..start+29."""
        if self.start is None:
            self.start = date
        return (date - self.start).days >= self.spec.max_calendar_days
