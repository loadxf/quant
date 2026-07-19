"""Shared rule primitives."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BreachEvent:
    rule: str
    date: dt.date
    day_index: int
    trade_index: int  # index within the day; -1 for day-close checks
    equity: float
    threshold: float
    detail: str


def breached(equity: float, threshold: float, inclusive: bool) -> bool:
    """Breach comparator: inclusive => touch fails (futures firms);
    exclusive => strictly below fails (FTMO wording)."""
    return equity <= threshold if inclusive else equity < threshold
