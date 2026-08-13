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

import math
from datetime import time as dt_time
from typing import Annotated, Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

from quantlab.errors import ConfigError


class _RuleBase(BaseModel):
    model_config = {"extra": "forbid", "allow_inf_nan": False, "strict": True}


PositiveFloat = Annotated[float, Field(gt=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]


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
    amount: PositiveFloat | None = None
    pct: PositiveFloat | None = None  # percent of account size (FTMO-style)
    ratchet: Literal["eod", "intraday"] = "eod"
    threshold_cap: float | None = None  # absolute equity level; None = trails forever
    inclusive: bool = True  # breach on touch (<=) vs strictly below (<)


class StaticMaxLossSpec(_RuleBase):
    """Fixed floor at initial_balance - amount (FTMO 2-Step Max Loss)."""

    type: Literal["static_max_loss"] = "static_max_loss"
    amount: PositiveFloat | None = None
    pct: PositiveFloat | None = None
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
    amount: PositiveFloat | None = None
    pct: PositiveFloat | None = None  # percent of account size (FTMO: width fixed vs INITIAL)
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
    max_best_day_pct: Annotated[float, Field(gt=0, le=100)] = 50.0
    basis: Literal["profit_target", "total_profit"] = "total_profit"
    effect: Literal["raise_target", "gate_payout"] = "raise_target"


class MinTradingDaysSpec(_RuleBase):
    type: Literal["min_trading_days"] = "min_trading_days"
    days: NonNegativeInt = 1


class SessionCloseSpec(_RuleBase):
    """Hard daily flatten deadline (Topstep: flat by 15:10 America/Chicago).

    A position still open AT or AFTER `hard_close` local wall time of its
    ENTRY's trading session violates the rule. Entry-session anchoring
    matters: a trade opened 18:00 CT belongs to the NEXT session (17:00
    roll), so holding it to the next morning is legal; holding any
    position through 15:10 of its own session is not.

    Enforced by the deterministic evaluator (which sees timestamps). The
    day-granular Monte Carlo cannot see clock times; run_monte_carlo
    FAILS CLOSED on source logs containing violations — simulating them
    would overstate what the account allows. Pending-order cancellation
    by the deadline is unobservable from a closed-trade log (stated in
    the evaluator's advisories). No per-product exchange calendar is
    modeled — see `early_closes` for date-aware shortened sessions.
    """

    type: Literal["session_close"] = "session_close"
    tz: str = "America/Chicago"
    hard_close: str = "15:10:00"  # HH:MM[:SS] local wall time
    # Date-aware overrides for shortened sessions (exchange holidays):
    # ISO session date -> earlier local close, e.g. {"2026-11-27": "12:15:00"}.
    # The EARLIER of hard_close and the override applies. Symbol-specific
    # product closes are NOT modeled — configure the earliest applicable
    # close for the traded products, or split logs per product.
    early_closes: dict[str, str] = Field(default_factory=dict)

    @staticmethod
    def _parse_time(value: str, field_name: str) -> dt_time:
        parts = value.split(":")
        if len(parts) not in (2, 3):
            raise ConfigError(f"session_close.{field_name} must be HH:MM[:SS] (got {value!r})")
        try:
            hh, mm = int(parts[0]), int(parts[1])
            ss = int(parts[2]) if len(parts) == 3 else 0
        except ValueError:
            raise ConfigError(
                f"session_close.{field_name} must be numeric HH:MM[:SS] (got {value!r})"
            ) from None
        if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
            raise ConfigError(f"session_close.{field_name} out of range (got {value!r})")
        return dt_time(hh, mm, ss)

    @model_validator(mode="after")
    def _valid(self) -> SessionCloseSpec:
        try:
            ZoneInfo(self.tz)
        except (KeyError, ValueError, TypeError, ZoneInfoNotFoundError):
            raise ConfigError(f"session_close.tz {self.tz!r} is not a known IANA zone") from None
        self._parse_time(self.hard_close, "hard_close")
        import datetime as _dt

        for date_str, time_str in self.early_closes.items():
            try:
                _dt.date.fromisoformat(date_str)
            except ValueError:
                raise ConfigError(
                    f"session_close.early_closes key {date_str!r} is not an ISO date"
                ) from None
            self._parse_time(time_str, f"early_closes[{date_str}]")
        return self

    def close_time(self) -> dt_time:
        return self._parse_time(self.hard_close, "hard_close")

    def close_time_for(self, session_date: object) -> dt_time:
        """Effective close for a session date: the earlier of hard_close
        and any date-specific early close."""
        base = self.close_time()
        override = self.early_closes.get(str(session_date))
        if override is None:
            return base
        early = self._parse_time(override, f"early_closes[{session_date}]")
        return min(base, early)


class TimeLimitSpec(_RuleBase):
    """Hard calendar-day expiry for a phase (Apex 4.0: 30-day evals)."""

    type: Literal["time_limit"] = "time_limit"
    max_calendar_days: PositiveInt = 30


class ContractLimitSpec(_RuleBase):
    """Advisory position-size check on the source log (not enforced in MC)."""

    type: Literal["contract_limit"] = "contract_limit"
    # Required and positive: a 0-contract default would fire the advisory
    # on every run and zero out Apex-style half-size scaling.
    max_contracts: PositiveFloat
    micros_multiplier: PositiveFloat = 10.0  # micros allowed at Nx the mini limit


class ScalingTier(_RuleBase):
    min_balance: NonNegativeFloat
    max_contracts: PositiveFloat


class ScalingPlanSpec(_RuleBase):
    """Balance-tiered position-size caps, ENFORCED in simulation (M11).

    Exactly one form:
    - tiers: allowed contracts by balance tier, looked up at day start
      from the prior close (Topstep Scaling Plan convention: limits never
      increase mid-session).
    - half_until_safety_net: half the max contracts until the END-OF-DAY
      balance reaches the payout safety-net floor, then full size unlocks
      permanently — even if the balance later drops (Apex 4.0 PA).

    Simulation maps contracts to a PnL weight via base_contracts (the log's
    peak concurrent gross exposure in mini-equivalents by default;
    `--base-contracts` uses the same unit): cap_weight = allowed / base —
    the same-fill linear-scaling assumption.
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
            if mins[0] != 0:
                raise ConfigError("scaling_plan first tier must start at min_balance 0")
            if any(t.max_contracts <= 0 for t in self.tiers):
                raise ConfigError("scaling_plan tiers need positive max_contracts")
        return self


RuleSpec = Annotated[
    TrailingDrawdownSpec
    | StaticMaxLossSpec
    | DailyLossLimitSpec
    | ConsistencySpec
    | MinTradingDaysSpec
    | SessionCloseSpec
    | TimeLimitSpec
    | ContractLimitSpec
    | ScalingPlanSpec,
    Field(discriminator="type"),
]


class DayBoundarySpec(_RuleBase):
    tz: str = "America/Chicago"
    cutoff_hour: Annotated[int, Field(ge=0, le=23)] = 17

    @field_validator("tz")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, TypeError) as exc:
            raise ValueError(f"unknown timezone {value!r}") from exc
        return value

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
    name: Annotated[str, Field(min_length=1)]
    profit_target: PositiveFloat | None = None  # None => funded phase (no target)
    initial_balance: NonNegativeFloat | None = None  # None => account_size (Topstep XFA uses 0)
    rules: list[RuleSpec] = Field(default_factory=list)

    def resolved_initial(self, account_size: float) -> float:
        return self.initial_balance if self.initial_balance is not None else account_size


class QualifyingDays(_RuleBase):
    count: NonNegativeInt = 0
    min_daily_profit: NonNegativeFloat = 0.0


class Reactivations(_RuleBase):
    max: NonNegativeInt = 0
    fees: list[NonNegativeFloat] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fees_cover_reactivations(self) -> Reactivations:
        if len(self.fees) > self.max:
            raise ConfigError("reactivation fee entries cannot exceed the maximum reactivations")
        return self


class FeeSchedule(_RuleBase):
    monthly: NonNegativeFloat = 0.0  # recurring eval subscription
    one_time: NonNegativeFloat = 0.0  # single eval fee
    reset: NonNegativeFloat = 0.0  # discounted retry fee
    free_resets_per_cycle: NonNegativeInt = 0
    activation: NonNegativeFloat = 0.0
    refundable_on_first_payout: bool = False  # FTMO 2-Step refunds the fee
    # Generic user-side overheads, off by default (presets stay 0 — e.g.
    # Topstep L1 data is free during the Combine and pro data fees only hit
    # Live Funded, outside the modeled funnel). Set via YAML or the
    # --extra-monthly / --per-payout-fee CLI knobs for platform/data
    # subscriptions and payout processing costs.
    extra_monthly: NonNegativeFloat = 0.0
    per_payout: NonNegativeFloat = 0.0
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
            raise ConfigError(
                f"FeeSchedule.payout_haircut must be in [0, 1) (got {self.payout_haircut})"
            )
        for name in ("monthly", "one_time", "reset", "activation", "extra_monthly", "per_payout"):
            if getattr(self, name) < 0:
                raise ConfigError(f"FeeSchedule.{name} must be >= 0 (got {getattr(self, name)})")
        return self


class ConsistencyPathSpec(_RuleBase):
    """Topstep XFA Consistency payout path (chosen at activation, mutually
    exclusive with the Standard path): at least `min_days` active trading
    days in the payout window, positive window profit, and the largest
    positive day at MOST `max_best_day_pct` of the window total
    (INCLUSIVE — exactly 40% still qualifies). The window resets to $0
    after each payout request."""

    min_days: PositiveInt = 3
    min_trades_per_day: PositiveInt = 1  # a session counts once it has >= this many trades
    max_best_day_pct: Annotated[float, Field(gt=0, le=100)] = 40.0
    payout_cap_ladder: list[PositiveFloat] = Field(default_factory=list)


class PayoutPolicy(_RuleBase):
    profit_split: Annotated[float, Field(gt=0, le=1)] = 1.0  # trader's share
    min_payout: NonNegativeFloat = 0.0
    # Min calendar days between payout requests. Biweekly is the industry
    # norm, so it is the safe default for user YAMLs that omit the field;
    # set 0 explicitly for on-demand payout firms.
    period_days: NonNegativeInt = 14
    qualifying_days: QualifyingDays = Field(default_factory=QualifyingDays)
    payout_cap_ladder: list[PositiveFloat] = Field(default_factory=list)
    max_lifetime_payouts: PositiveInt | None = None
    payout_share_of_balance: Annotated[float, Field(gt=0, le=1)] | None = None
    safety_net_floor: NonNegativeFloat | None = None
    buffer_above_initial: NonNegativeFloat | None = None
    reactivations: Reactivations = Field(default_factory=Reactivations)
    # Payout path selected at activation: "standard" (qualifying days) or
    # "consistency" (window ratio). `consistency` holds the alternative
    # path's parameters; simulation can flip paths without editing YAML.
    path: Literal["standard", "consistency"] = "standard"
    consistency: ConsistencyPathSpec | None = None
    # Standard path: payouts after the first need positive profit since
    # the prior payout (Topstep XFA; the first payout is exempt).
    require_profit_since_prior_payout: bool = False
    # "Your Maximum Loss Limit (MLL) resets to $0 permanently" at each
    # payout approval (Topstep payout policy, verified 2026-08-13): the
    # trailing floor snaps to its threshold_cap as an EVENT, even when
    # ordinary trailing would leave it lower.
    mll_reset_on_payout: bool = False

    @model_validator(mode="after")
    def _split_fraction(self) -> PayoutPolicy:
        # The classic percent-vs-fraction typo (profit_split: 90) would
        # silently inflate every payout and EV figure 90x.
        if not 0.0 < self.profit_split <= 1.0:
            raise ConfigError(
                f"payout.profit_split must be a FRACTION in (0, 1] (got {self.profit_split})"
            )
        if self.path == "consistency" and self.consistency is None:
            raise ConfigError(
                "payout.path 'consistency' needs a payout.consistency block "
                "(min_days, max_best_day_pct, payout_cap_ladder)"
            )
        return self


class FirmConfig(_RuleBase):
    name: Annotated[str, Field(min_length=1)]
    display_name: str = ""
    firm: str = ""
    account_size: PositiveFloat
    day_boundary: DayBoundarySpec = Field(default_factory=DayBoundarySpec)
    phases: list[PhaseConfig] = Field(min_length=1)  # evaluation phases, in order
    funded: PhaseConfig
    fees: FeeSchedule = Field(default_factory=FeeSchedule)
    payout: PayoutPolicy = Field(default_factory=PayoutPolicy)
    # Named platform commission profile (metrics.fee_profiles). When set,
    # cost analyses labeled with this firm use the platform's published
    # round-turn fees instead of the generic retail contract defaults —
    # and fail loudly for symbols the profile does not price.
    fee_profile: str = ""
    verified_as_of: str = ""
    sources: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("sources")
    @classmethod
    def _safe_source_urls(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"source must be an absolute HTTP(S) URL (got {value!r})")
        return values

    @model_validator(mode="after")
    def _check(self) -> FirmConfig:
        if self.account_size <= 0:
            raise ConfigError(f"account_size must be positive (got {self.account_size})")
        for phase in self.phases:
            if phase.profit_target is None:
                raise ConfigError(f"evaluation phase {phase.name!r} needs a profit_target")
        if self.funded.profit_target is not None:
            raise ConfigError("funded phase must not define a profit_target")
        names = [phase.name for phase in self.phases]
        if len(names) != len(set(names)):
            raise ConfigError("evaluation phase names must be unique")
        if self.funded.name in names:
            raise ConfigError("funded phase name must differ from evaluation phase names")
        if self.fee_profile:
            from quantlab.metrics.fee_profiles import get_fee_profile

            get_fee_profile(self.fee_profile)  # unknown profile fails at load time
        singleton_rules = (
            ScalingPlanSpec,
            ContractLimitSpec,
            TimeLimitSpec,
            MinTradingDaysSpec,
            SessionCloseSpec,
        )
        for phase in [*self.phases, self.funded]:
            for rule_type in singleton_rules:
                if sum(isinstance(rule, rule_type) for rule in phase.rules) > 1:
                    rule_name = rule_type.model_fields["type"].default
                    raise ConfigError(f"phase {phase.name!r} has duplicate {rule_name} rules")
        return self


# Optional Daily Loss Limit values, verified against help.topstep.com
# article 10490293 (fetched 2026-08-13): chosen at checkout, fixed
# thereafter, LOCKOUT-only (flatten + no new trades until 5 PM CT;
# never an account failure).
TOPSTEP_DLL_AMOUNTS: dict[float, float] = {50_000: 1_000, 100_000: 2_000, 150_000: 3_000}


def with_optional_dll(firm: FirmConfig, amount: float | None = None) -> FirmConfig:
    """Copy of `firm` with the opt-in Daily Loss Limit added to every
    phase (lockout effect — a soft breach, not a failure).

    `amount` defaults to the official Topstep value for the account size;
    an unknown size requires an explicit amount.
    """
    if amount is None:
        amount = TOPSTEP_DLL_AMOUNTS.get(firm.account_size)
        if amount is None:
            raise ConfigError(
                f"no official DLL amount for account size {firm.account_size:g} — "
                "pass an explicit --dll-amount"
            )
    if not math.isfinite(amount) or amount <= 0:
        raise ConfigError(f"DLL amount must be finite and positive (got {amount})")
    for phase in [*firm.phases, firm.funded]:
        if any(isinstance(rule, DailyLossLimitSpec) for rule in phase.rules):
            raise ConfigError(
                f"phase {phase.name!r} already defines a daily_loss_limit — "
                "remove --dll or edit the firm YAML"
            )
    dll = DailyLossLimitSpec(amount=amount, effect="lockout")
    new_phases = [phase.model_copy(update={"rules": [*phase.rules, dll]}) for phase in firm.phases]
    new_funded = firm.funded.model_copy(update={"rules": [*firm.funded.rules, dll]})
    return firm.model_copy(update={"phases": new_phases, "funded": new_funded})


def with_promo_payout_caps(firm: FirmConfig) -> FirmConfig:
    """Copy of `firm` with DOUBLED payout caps on both paths — the
    June-2026 limited promotion for accounts purchased WITH the optional
    DLL. Never the primary result: the baseline is non-promotional."""
    payout = firm.payout
    updates: dict[str, object] = {}
    if payout.payout_cap_ladder:
        updates["payout_cap_ladder"] = [2 * cap for cap in payout.payout_cap_ladder]
    if payout.consistency is not None and payout.consistency.payout_cap_ladder:
        updates["consistency"] = payout.consistency.model_copy(
            update={"payout_cap_ladder": [2 * cap for cap in payout.consistency.payout_cap_ladder]}
        )
    if not updates:
        raise ConfigError("promotional caps need a payout_cap_ladder to double")
    return firm.model_copy(update={"payout": payout.model_copy(update=updates)})


def apply_topstep_options(
    firm: FirmConfig,
    dll: bool = False,
    dll_amount: float | None = None,
    promo_caps: bool = False,
) -> FirmConfig:
    """Compose the opt-in DLL and the promotional doubled caps.

    The promotion applies only to accounts purchased WITH the DLL, so
    promo_caps without dll is a configuration error. The no-DLL,
    non-promotional configuration remains the primary baseline.
    """
    if dll_amount is not None and not dll:
        raise ConfigError("--dll-amount requires --dll")
    if promo_caps and not dll:
        raise ConfigError(
            "promotional doubled caps apply only to accounts purchased with the "
            "optional DLL — add --dll (and keep the no-DLL baseline primary)"
        )
    if dll:
        firm = with_optional_dll(firm, dll_amount)
    if promo_caps:
        firm = with_promo_payout_caps(firm)
    return firm


def with_fee_overrides(
    firm: FirmConfig,
    extra_monthly: float = 0.0,
    per_payout: float = 0.0,
    payout_haircut: float = 0.0,
) -> FirmConfig:
    """Copy of `firm` with user-side overhead/assumption knobs applied."""
    values = (extra_monthly, per_payout, payout_haircut)
    if not all(math.isfinite(value) for value in values):
        raise ConfigError("fee overrides must be finite")
    if extra_monthly < 0 or per_payout < 0:
        raise ConfigError("--extra-monthly and --per-payout-fee must be >= 0")
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
    if not math.isfinite(account_size) or account_size <= 0:
        raise ConfigError(f"account_size must be finite and positive (got {account_size})")
    if spec.amount is not None and spec.pct is not None:
        raise ConfigError(f"{spec.type}: set either amount or pct, not both")
    if spec.amount is not None:
        return spec.amount
    if spec.pct is not None:
        return account_size * spec.pct / 100.0
    raise ConfigError(f"{spec.type}: one of amount or pct is required")
