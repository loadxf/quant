"""Best-day consistency — a gate, never a breach.

Unified formula (covers both verified variants):
    required_total = max(profit_target, best_day / (pct/100))

- Topstep Combine (basis=profit_target, 50%): "Best Day / 0.50 = Total
  Profit Needed" once the best day exceeds 50% of the target.
- TPT Test (basis=total_profit, 50%): no day may be >= 50% of total net
  P/L, i.e. required total = 2x best day.
The current (incomplete) day's running total counts toward best_day: if
today's run-up is your outsized day, you cannot pass today on it.
"""

from __future__ import annotations

from quantlab.prop.config import ConsistencySpec


class ConsistencyGate:
    def __init__(self, spec: ConsistencySpec) -> None:
        self.spec = spec
        self.name = "consistency"

    def required_total(self, profit_target: float, best_day: float) -> float:
        if best_day <= 0:
            return profit_target
        raised = best_day / (self.spec.max_best_day_pct / 100.0)
        if self.spec.basis == "profit_target":
            # Only raises once the best day exceeds pct% of the target.
            limit = profit_target * self.spec.max_best_day_pct / 100.0
            return raised if best_day > limit else profit_target
        return max(profit_target, raised)

    def payout_eligible(self, best_day: float, total_profit: float) -> bool:
        """Funded-phase gating (effect=gate_payout): best day must stay
        under pct% of profit since the measurement window began."""
        if total_profit <= 0:
            return False
        return best_day / total_profit <= self.spec.max_best_day_pct / 100.0
