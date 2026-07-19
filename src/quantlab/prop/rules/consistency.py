"""Best-day consistency — a gate, never a breach.

Unified raise formula:
    required_total = max(profit_target, best_day / (pct/100))

The basis controls the BOUNDARY semantics (verified official wording):
- basis=profit_target (Topstep Combine): "best day <= 50% of the profit
  target" is allowed — INCLUSIVE; exceeding it raises the required total
  to best_day/0.50, and hitting that raised total exactly passes.
- basis=total_profit (TPT Test / Apex-style payout gates): "no single day
  may account for 50% OR MORE of total" — STRICT: a best day exactly at
  pct% of the total still blocks the pass/payout.

The current (incomplete) day's running total counts toward best_day: if
today's run-up is your outsized day, you cannot pass today on it.
"""

from __future__ import annotations

from quantlab.prop.config import ConsistencySpec


class ConsistencyGate:
    def __init__(self, spec: ConsistencySpec) -> None:
        self.spec = spec
        self.name = "consistency"
        self.frac = spec.max_best_day_pct / 100.0

    def required_total(self, profit_target: float, best_day: float) -> float:
        if best_day <= 0:
            return profit_target
        raised = best_day / self.frac
        if self.spec.basis == "profit_target":
            # Only raises once the best day exceeds pct% of the target.
            return raised if best_day > self.frac * profit_target else profit_target
        return max(profit_target, raised)

    def pass_blocked(self, total_profit: float, best_day: float) -> bool:
        """Strict-boundary block for basis=total_profit: at a total exactly
        equal to best_day/frac, the "50% or more" wording still forbids
        the pass — required_total alone would allow it."""
        if self.spec.basis != "total_profit" or best_day <= 0:
            return False
        return best_day >= self.frac * total_profit

    def payout_eligible(self, best_day: float, total_profit: float) -> bool:
        """Funded-phase gating (effect=gate_payout): the best day must stay
        STRICTLY under pct% of profit since the measurement window began
        (Apex: "50% or more" makes the payout unavailable)."""
        if total_profit <= 0:
            return False
        return best_day < self.frac * total_profit
