"""Shared rule primitives."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import overload

import numpy as np


@dataclass(frozen=True, slots=True)
class BreachEvent:
    rule: str
    date: dt.date
    day_index: int
    trade_index: int  # index within the day; -1 for day-close checks
    equity: float
    threshold: float
    detail: str


@overload
def breached(equity: float, threshold: float, inclusive: bool) -> bool: ...
@overload
def breached(equity: np.ndarray, threshold: float | np.ndarray, inclusive: bool) -> np.ndarray: ...
@overload
def breached(equity: float, threshold: np.ndarray, inclusive: bool) -> np.ndarray: ...
def breached(
    equity: float | np.ndarray, threshold: float | np.ndarray, inclusive: bool
) -> bool | np.ndarray:
    """Breach comparator: inclusive => touch fails (futures firms);
    exclusive => strictly below fails (FTMO wording).

    Serves both engines: scalars in the deterministic evaluator, arrays in
    the vectorized Monte Carlo (same semantics by construction)."""
    return equity <= threshold if inclusive else equity < threshold
