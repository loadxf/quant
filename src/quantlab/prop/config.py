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
    # gt=0: frac 0 divides by zero mid-evaluation; negative silently blocks
    # every pass. le=100: >100% of profit is not a consistency rule.
    max_best_day_pct: float = Field(50.0, gt=0, le=100)
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
    # Required and positive: a 0-contract default would fire the advisory
    # on every run and zero out Apex-style half-size scaling.
    max_contracts: float = Field(gt=0)
    micros_multiplier: float = 10.0  # micros allowed at Nx the mini limit


class ScalingTier(_RuleBase):
    min_balance: float
    max_contracts: float


class ScalingPlanSpec(_RuleBase):
    """Balance-tiered position-size caps, ENFORCED in simulation (M11).

    Exactly one form:
    - tiers: allowed contracts by balance tier, looked up at day start
      from the prior close (Topstep Scaling Plan convention: limits never
      increase mid-session).
    - half_until_safety_net: half the max contracts until the END-OF-DAY
      balance reaches the payout safety-net floor, then full size unlocks
      permanently — even if the balance later drops (Apex 4.0 PA).

    Simulation maps contracts to a PnL weight via base_contracts (the
    log's max observed position by default, `--base-contracts` to
    override): cap_weight = allowed / base — the same-fill linear-scaling
    assumption.
    """

    type: Literal["scaling_plan"] = "scaling_plan"
    tiers: list[ScalingTier] = Field(default_factory=list)
    half_until_safety_net: bool = False

    @model_validator(mode="after")
    def _one_form(self) -> ScalingPlanSpec:
        if bool(self.tiers) == self.half_until_safety_net:
            raise ConfigError("scaling_plan: set exactly one of `tiers` or `half_until_safety_net`")
        if self.tiers:
            mins = [t.min_balance for t in self.tiers]
            if mins != sorted(mins) or len(set(mins)) != len(mins):
                raise ConfigError("scaling_plan tiers must have strictly increasing min_balance")
            if any(t.max_contracts <= 0 for t in self.tiers):
                raise ConfigError("scaling_plan tiers need positive max_contracts")
        return self


RuleSpec = Annotated[
    TrailingDrawdownSpec
    | StaticMaxLossSpec
    | DailyLossLimitSpec
    | ConsistencySpec
    | MinTradingDaysSpec
    | TimeLimitSpec
    | ContractLimitSpec
    | ScalingPlanSpec,
    Field(discriminator="type"),
]


class DayBoundarySpec(_RuleBase):
    tz: str = "America/Chicago"
    cutoff_hour: int = 17

    @model_validator(mode="after")
    def _tz_exists(self) -> DayBoundarySpec:
        # A typo'd zone would otherwise crash mid-evaluation (session_date
        # constructs ZoneInfo per call) with no config context.
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(self.tz)
        except (KeyError, ValueError, ZoneInfoNotFoundError):
            raise ConfigError(f"day_boundary.tz {self.tz!r} is not a known IANA zone") from None
        if not 0 <= self.cutoff_hour <= 23:
            raise ConfigError(f"day_boundary.cutoff_hour must be 0-23 (got {self.cutoff_hour})")
        return self

    def to_boundary(self):  # -> quantlab.schema.trade.DayBoundary
        """Single conversion point so every engine groups sessions identically."""
        from quantlab.schema.trade import DayBoundary

        return DayBoundary(self.tz, self.cutoff_hour)


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
    monthly: float = 0.0  # recurring eval subscription (Topstep/TPT; exclusive with one_time)
    one_time: float = 0.0  # single eval fee (Apex 4.0, FTMO; exclusive with monthly)
    reset: float = 0.0  # discounted retry fee replacing the next month (0 = full-price retry)
    free_resets_per_cycle: int = 0  # informational; ignored by EV math (documented pessimistic)
    activation: float = 0.0  # funded activation / PA fee
    refundable_on_first_payout: bool = False  # FTMO 2-Step refunds the fee
    # Generic user-side overheads, off by default (presets stay 0 — e.g.
    # Topstep L1 data is free during the Combine and pro data fees only hit
    # Live Funded, outside the modeled funnel). Set via YAML or the
    # --extra-monthly / --per-payout-fee CLI knobs for platform/data
    # subscriptions and payout processing costs.
    extra_monthly: float = 0.0  # recurring overhead billed while trading (eval AND funded)
    per_payout: float = 0.0  # processing cost deducted from each payout
    # USER-SUPPLIED counterparty assumption (0-1): expected fraction of
    # payout value lost to denials/delays/firm failure. The tool has no
    # data on denial rates — this knob exists so users can price their
    # own trust level; presets stay 0 and output states the assumption.
    payout_haircut: float = 0.0

    @model_validator(mode="after")
    def _exclusive(self) -> FeeSchedule:
        if self.monthly > 0 and self.one_time > 0:
            raise ConfigError(
                "FeeSchedule: set either monthly (recurring subscription) or "
                "one_time (single eval fee), not both — the EV math would "
                "silently ignore the monthly fee."
            )
        if not 0.0 <= self.payout_haircut < 1.0:
            # Guard the YAML/direct-construction path too, not just the CLI
            # override: h >= 1 flips every payout negative, h < 0 inflates.
            raise ConfigError(
                f"FeeSchedule.payout_haircut must be in [0, 1) (got {self.payout_haircut})"
            )
        for name in ("monthly", "one_time", "reset", "activation", "extra_monthly", "per_payout"):
            if getattr(self, name) < 0:
                raise ConfigError(f"FeeSchedule.{name} must be >= 0 (got {getattr(self, name)})")
        return self


class PayoutPolicy(_RuleBase):
    profit_split: float = 1.0  # trader's share
    min_payout: float = 0.0
    # Min calendar days between payout requests. Biweekly is the industry
    # norm, so it is the safe default for user YAMLs that omit the field;
    # set 0 explicitly for on-demand payout firms.
    period_days: int = 14
    qualifying_days: QualifyingDays = Field(default_factory=QualifyingDays)
    payout_cap_ladder: list[float] = Field(default_factory=list)  # per-payout caps, indexed
    max_lifetime_payouts: int | None = None  # Apex 4.0: 6, then the PA closes
    payout_share_of_balance: float | None = None  # Topstep: request up to 50% of balance
    safety_net_floor: float | None = None  # balance must stay >= after payout (Apex)
    buffer_above_initial: float | None = None  # TPT: withdraw only above initial + DD
    reactivations: Reactivations = Field(default_factory=Reactivations)

    @model_validator(mode="after")
    def _split_fraction(self) -> PayoutPolicy:
        # The classic percent-vs-fraction typo (profit_split: 90) would
        # silently inflate every payout and EV figure 90x.
        if not 0.0 < self.profit_split <= 1.0:
            raise ConfigError(
                f"payout.profit_split must be a FRACTION in (0, 1] (got {self.profit_split})"
            )
        return self


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
        if self.account_size <= 0:
            raise ConfigError(f"account_size must be positive (got {self.account_size})")
        for phase in self.phases:
            if phase.profit_target is None:
                raise ConfigError(f"evaluation phase {phase.name!r} needs a profit_target")
        if self.funded.profit_target is not None:
            raise ConfigError("funded phase must not define a profit_target")
        return self


def with_fee_overrides(
    firm: FirmConfig,
    extra_monthly: float = 0.0,
    per_payout: float = 0.0,
    payout_haircut: float = 0.0,
) -> FirmConfig:
    """Copy of `firm` with user-side overhead/assumption knobs applied."""
    if not 0.0 <= payout_haircut < 1.0:
        raise ConfigError(f"--payout-haircut must be in [0, 1) (got {payout_haircut})")
    if extra_monthly <= 0 and per_payout <= 0 and payout_haircut <= 0:
        return firm
    updates: dict[str, float] = {}
    if extra_monthly > 0:
        updates["extra_monthly"] = extra_monthly
    if per_payout > 0:
        updates["per_payout"] = per_payout
    if payout_haircut > 0:
        updates["payout_haircut"] = payout_haircut
    return firm.model_copy(update={"fees": firm.fees.model_copy(update=updates)})


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
