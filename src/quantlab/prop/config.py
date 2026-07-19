"""Firm configuration models.

A `FirmConfig` describes one prop-firm account as a structured product:
an ordered list of evaluation phases (FTMO 2-Step has two; futures firms
one), a funded phase, fee schedule, and payout policy. Rule parameters
are written in YAML as absolute dollars (`amount`) or percent of account
size (`pct`) — `resolved_amount()` collapses them at load time.

Semantics encoded here were verified against official firm sources on
2026-07-19 (see the preset YAML comments for per-parameter citations).
Firms change rules constantly — re-verify before trusting EV outputs.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from quantlab.errors import ConfigError


class _RuleBase(BaseModel):
    model_config = {"extra": "forbid"}


class TrailingDrawdownSpec(_RuleBase):
    """Trailing max drawdown.

    Breach test is ALWAYS real-time intraday on equity including
    unrealized P&L (MAE-aware). `ratchet` controls only how the
    high-water mark advances:
      - "eod": from end-of-day closing balance only (Topstep MLL, TPT
        Test, Apex EOD variant, FTMO 1-Step ML)
      - "intraday": continuously, including unrealized peaks via MFE
        (Apex Intraday variant, TPT PRO)
    `threshold_cap` freezes the floor: threshold = min(hwm - amount, cap).
    Topstep caps at starting balance; TPT at initial; Apex evals at
    initial + profit target (i.e. effectively trails the whole eval);
    Apex PAs at start + $100.
    """

    type: Literal["trailing_drawdown"] = "trailing_drawdown"
    amount: float | None = None
    pct: float | None = None  # percent of account size (FTMO-style)
    ratchet: Literal["eod", "intraday"] = "eod"
    threshold_cap: float | None = None  # absolute equity level; None = trails forever
    inclusive: bool = True  # breach on touch (<=) vs strictly below (<)


class StaticMaxLossSpec(_RuleBase):
    """Fixed floor at initial_balance - amount (FTMO 2-Step Max Loss)."""

    type: Literal["static_max_loss"] = "static_max_loss"
    amount: float | None = None
    pct: float | None = None
    inclusive: bool = False  # FTMO: violated when equity drops BELOW the limit


class DailyLossLimitSpec(_RuleBase):
    """Daily loss limit, breached on intraday equity.

    `anchor` documents what the line is measured from — in this
    day-granular model both variants resolve to the day-open realized
    balance (the firm-specific `day_boundary` supplies the reset time:
    17:00 CT for futures firms, midnight Prague for FTMO).
    `effect="fail"` ends the phase (FTMO); `effect="lockout"` flattens
    and locks the rest of the session without failing (Topstep opt-in,
    Apex EOD variant) — the day's PnL truncates at exactly -width, a
    documented approximation.
    """

    type: Literal["daily_loss_limit"] = "daily_loss_limit"
    amount: float | None = None
    pct: float | None = None  # percent of account size (FTMO: width fixed vs INITIAL)
    anchor: Literal["day_open_balance", "prev_midnight_balance"] = "day_open_balance"
    effect: Literal["fail", "lockout"] = "fail"
    inclusive: bool = True


class ConsistencySpec(_RuleBase):
    """Best-day consistency rule — never a breach.

    Pass/payout requirement collapses to:
        total_profit >= max(profit_target, best_day / (pct/100))
    - basis="profit_target" (Topstep Combine: best day <= 50% of target,
      exceeding raises the required total to best_day/0.50)
    - basis="total_profit" (TPT Test: best day < 50% of total net P/L,
      i.e. required total becomes 2x best day; Apex PA / Topstep XFA /
      FTMO 1-Step payout gating)
    effect="raise_target" applies to evaluation passing;
    effect="gate_payout" applies to funded-phase payout eligibility.
    """

    type: Literal["consistency"] = "consistency"
    max_best_day_pct: float = 50.0
    basis: Literal["profit_target", "total_profit"] = "total_profit"
    effect: Literal["raise_target", "gate_payout"] = "raise_target"


class MinTradingDaysSpec(_RuleBase):
    type: Literal["min_trading_days"] = "min_trading_days"
    days: int = 1


class TimeLimitSpec(_RuleBase):
    """Hard calendar-day expiry for a phase (Apex 4.0: 30-day evals)."""

    type: Literal["time_limit"] = "time_limit"
    max_calendar_days: int = 30


class ContractLimitSpec(_RuleBase):
    """Advisory position-size check on the source log (not enforced in MC)."""

    type: Literal["contract_limit"] = "contract_limit"
    max_contracts: float = 0
    micros_multiplier: float = 10.0  # micros allowed at Nx the mini limit


RuleSpec = Annotated[
    TrailingDrawdownSpec
    | StaticMaxLossSpec
    | DailyLossLimitSpec
    | ConsistencySpec
    | MinTradingDaysSpec
    | TimeLimitSpec
    | ContractLimitSpec,
    Field(discriminator="type"),
]


class DayBoundarySpec(_RuleBase):
    tz: str = "America/Chicago"
    cutoff_hour: int = 17


class PhaseConfig(_RuleBase):
    name: str
    profit_target: float | None = None  # None => funded phase (no target)
    initial_balance: float | None = None  # None => account_size (Topstep XFA uses 0)
    rules: list[RuleSpec] = Field(default_factory=list)

    def resolved_initial(self, account_size: float) -> float:
        return self.initial_balance if self.initial_balance is not None else account_size


class QualifyingDays(_RuleBase):
    count: int = 0
    min_daily_profit: float = 0.0


class Reactivations(_RuleBase):
    max: int = 0
    fees: list[float] = Field(default_factory=list)


class FeeSchedule(_RuleBase):
    monthly: float = 0.0  # recurring eval subscription (Topstep/TPT/FTMO=one_time instead)
    one_time: float = 0.0  # single eval fee (Apex 4.0, FTMO)
    reset: float = 0.0
    free_resets_per_cycle: int = 0
    activation: float = 0.0  # funded activation / PA fee
    refundable_on_first_payout: bool = False  # FTMO 2-Step refunds the fee


class PayoutPolicy(_RuleBase):
    profit_split: float = 1.0  # trader's share
    min_payout: float = 0.0
    period_days: int = 14  # min days between payout requests / windows
    qualifying_days: QualifyingDays = Field(default_factory=QualifyingDays)
    payout_cap_ladder: list[float] = Field(default_factory=list)  # per-payout caps, indexed
    max_lifetime_payouts: int | None = None  # Apex 4.0: 6, then the PA closes
    payout_share_of_balance: float | None = None  # Topstep: request up to 50% of balance
    safety_net_floor: float | None = None  # balance must stay >= after payout (Apex)
    buffer_above_initial: float | None = None  # TPT: withdraw only above initial + DD
    reactivations: Reactivations = Field(default_factory=Reactivations)


class FirmConfig(_RuleBase):
    name: str
    display_name: str = ""
    firm: str = ""
    account_size: float
    day_boundary: DayBoundarySpec = Field(default_factory=DayBoundarySpec)
    phases: list[PhaseConfig] = Field(min_length=1)  # evaluation phases, in order
    funded: PhaseConfig
    fees: FeeSchedule = Field(default_factory=FeeSchedule)
    payout: PayoutPolicy = Field(default_factory=PayoutPolicy)
    verified_as_of: str = ""
    sources: list[str] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def _check(self) -> FirmConfig:
        for phase in self.phases:
            if phase.profit_target is None:
                raise ConfigError(f"evaluation phase {phase.name!r} needs a profit_target")
        if self.funded.profit_target is not None:
            raise ConfigError("funded phase must not define a profit_target")
        return self


def resolved_amount(
    spec: TrailingDrawdownSpec | StaticMaxLossSpec | DailyLossLimitSpec,
    account_size: float,
) -> float:
    """Collapse amount/pct into absolute dollars (pct is % of account size)."""
    if spec.amount is not None and spec.pct is not None:
        raise ConfigError(f"{spec.type}: set either amount or pct, not both")
    if spec.amount is not None:
        return spec.amount
    if spec.pct is not None:
        return account_size * spec.pct / 100.0
    raise ConfigError(f"{spec.type}: one of amount or pct is required")
