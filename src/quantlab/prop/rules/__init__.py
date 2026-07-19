"""Scalar rule state machines shared by the deterministic evaluator.

The vectorized Monte Carlo engine (prop/montecarlo.py) re-implements the
same day-level semantics with numpy; a golden-equivalence test forces the
two to agree exactly.
"""

from quantlab.prop.rules.base import BreachEvent
from quantlab.prop.rules.consistency import ConsistencyGate
from quantlab.prop.rules.daily_loss import DailyLossRule
from quantlab.prop.rules.min_days import MinTradingDaysGate
from quantlab.prop.rules.static_loss import StaticMaxLossRule
from quantlab.prop.rules.time_limit import TimeLimitGate
from quantlab.prop.rules.trailing_dd import TrailingDrawdownRule

__all__ = [
    "BreachEvent",
    "ConsistencyGate",
    "DailyLossRule",
    "MinTradingDaysGate",
    "StaticMaxLossRule",
    "TimeLimitGate",
    "TrailingDrawdownRule",
]
