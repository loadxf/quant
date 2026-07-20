"""Deterministic replay of a real trade log against a firm's rules.

Produces a human-readable verdict: pass/fail, the exact breach event,
and a per-day timeline. The vectorized Monte Carlo engine implements the
same day-level semantics; a golden-equivalence test keeps them honest.

Fidelity: intraday checks use each trade's MAE/MFE when present,
otherwise trade-close granularity (documented as optimistic for
intraday-sensitive rules). Within a trade the point order is
high -> low -> close (see rules/trailing_dd.py).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from quantlab.errors import ConfigError
from quantlab.prop.config import (
    ConsistencySpec,
    ContractLimitSpec,
    DailyLossLimitSpec,
    FirmConfig,
    MinTradingDaysSpec,
    PhaseConfig,
    StaticMaxLossSpec,
    TimeLimitSpec,
    TrailingDrawdownSpec,
)
from quantlab.prop.dayprofile import trade_points
from quantlab.prop.rules import (
    BreachEvent,
    ConsistencyGate,
    DailyLossRule,
    MinTradingDaysGate,
    StaticMaxLossRule,
    TimeLimitGate,
    TrailingDrawdownRule,
)
from quantlab.prop.voltarget import CushionParams, EwmaSizer, VolSizingParams, cushion_weight
from quantlab.schema.trade import Trade, TradeLog

Outcome = Literal["passed", "breached", "expired", "incomplete", "survived"]


@dataclass
class EvaluationResult:
    firm: str
    phase: str
    outcome: Outcome
    passed: bool
    breach: BreachEvent | None
    pass_date: dt.date | None
    pass_day_index: int | None
    trading_days: int
    final_balance: float
    initial_balance: float
    effective_target: float | None
    best_day: float
    lockout_days: int
    fidelity: str  # "mae_mfe" | "trade_close"
    timeline: pd.DataFrame
    advisories: list[str] = field(default_factory=list)
    days_consumed: int = 0  # trading days used from the log (for phase chaining)


def evaluate(
    log: TradeLog,
    firm: FirmConfig,
    phase: str = "challenge",
    start_day: int = 0,
    sizing: VolSizingParams | None = None,
    cushion_clip: tuple[float, float] | None = None,
) -> EvaluationResult:
    """Replay `log` (from trading-day index `start_day`) against one phase.

    `sizing`: optional vol-targeted dynamic sizing — the same EwmaSizer
    recursion the Monte Carlo uses (golden equivalence by construction).
    `cushion_clip`: optional buffer-aware sizing — the same cushion_weight
    kernel the Monte Carlo uses."""
    phase_cfg = _find_phase(firm, phase)
    days = log.daily_groups(firm.day_boundary.to_boundary())[start_day:]
    return _evaluate_days(
        days, firm, phase_cfg, fidelity_from(log), sizing=sizing, cushion_clip=cushion_clip
    )


def evaluate_sequence(
    log: TradeLog,
    firm: FirmConfig,
    sizing: VolSizingParams | None = None,
    cushion_clip: tuple[float, float] | None = None,
) -> list[EvaluationResult]:
    """Chain phases over the log: each eval phase consumes trading days until
    it resolves; the funded phase replays whatever remains.

    `sizing` applies per phase with FRESH EWMA state (matching the Monte
    Carlo, which re-seeds each simulated phase); `cushion_clip` re-anchors
    per phase on that phase's own drawdown allowance."""
    all_days = log.daily_groups(firm.day_boundary.to_boundary())
    fidelity = fidelity_from(log)
    results: list[EvaluationResult] = []
    cursor = 0
    for phase_cfg in firm.phases:
        result = _evaluate_days(
            all_days[cursor:], firm, phase_cfg, fidelity, sizing=sizing, cushion_clip=cushion_clip
        )
        results.append(result)
        cursor += result.days_consumed
        if not result.passed:
            return results
    results.append(
        _evaluate_days(
            all_days[cursor:], firm, firm.funded, fidelity, sizing=sizing, cushion_clip=cushion_clip
        )
    )
    return results


def fidelity_from(log: TradeLog) -> str:
    return "mae_mfe" if log.has_excursions else "trade_close"


def _find_phase(firm: FirmConfig, name: str) -> PhaseConfig:
    if name in ("funded", firm.funded.name):
        return firm.funded
    for phase_cfg in firm.phases:
        if phase_cfg.name == name:
            return phase_cfg
    if name == "challenge" and firm.phases:
        return firm.phases[0]
    known = [p.name for p in firm.phases] + [firm.funded.name]
    raise ConfigError(f"Unknown phase {name!r} for {firm.name}; phases: {known}")


def _evaluate_days(
    days: list[tuple[dt.date, list[Trade]]],
    firm: FirmConfig,
    phase_cfg: PhaseConfig,
    fidelity: str,
    sizing: VolSizingParams | None = None,
    cushion_clip: tuple[float, float] | None = None,
) -> EvaluationResult:
    initial = phase_cfg.resolved_initial(firm.account_size)
    account = firm.account_size
    is_funded = phase_cfg.profit_target is None
    target = phase_cfg.profit_target

    trailing: list[TrailingDrawdownRule] = []
    static: list[StaticMaxLossRule] = []
    daily_fail: list[DailyLossRule] = []
    daily_lockout: list[DailyLossRule] = []
    raise_gates: list[ConsistencyGate] = []
    min_days = MinTradingDaysGate(MinTradingDaysSpec(days=0))
    time_limit: TimeLimitGate | None = None
    advisories: list[str] = []
    max_contracts_spec: ContractLimitSpec | None = None

    for spec in phase_cfg.rules:
        if isinstance(spec, TrailingDrawdownSpec):
            trailing.append(TrailingDrawdownRule(spec, initial, account))
        elif isinstance(spec, StaticMaxLossSpec):
            static.append(StaticMaxLossRule(spec, initial, account))
        elif isinstance(spec, DailyLossLimitSpec):
            rule = DailyLossRule(spec, account)
            (daily_lockout if spec.effect == "lockout" else daily_fail).append(rule)
        elif isinstance(spec, ConsistencySpec):
            if spec.effect == "raise_target":
                raise_gates.append(ConsistencyGate(spec))
            # gate_payout consistency is applied by the economics layer.
        elif isinstance(spec, MinTradingDaysSpec):
            min_days = MinTradingDaysGate(spec)
        elif isinstance(spec, TimeLimitSpec):
            time_limit = TimeLimitGate(spec)
        elif isinstance(spec, ContractLimitSpec):
            max_contracts_spec = spec
        else:  # pragma: no cover - exhaustiveness guard for future rule types
            raise ConfigError(
                f"Rule type {type(spec).__name__} is not handled by the evaluator — "
                "add it here (and in montecarlo._resolve_rules) before use."
            )

    balance = initial
    sizer = EwmaSizer(sizing) if sizing is not None else None
    cushion: CushionParams | None = None
    if cushion_clip is not None:
        # Identical cushion_0 convention to the vectorized engine: the
        # distance from the starting balance to the tightest day-0 floor.
        floor_0 = float("-inf")
        for tr_rule in trailing:
            floor_0 = max(floor_0, tr_rule.threshold)
        for st_rule in static:
            floor_0 = max(floor_0, st_rule.floor)
        if floor_0 == float("-inf") or floor_0 >= initial:
            raise ConfigError(
                f"cushion sizing needs a trailing/static drawdown rule below the "
                f"initial balance in phase {phase_cfg.name!r}"
            )
        cushion = CushionParams(
            cushion_0=initial - floor_0, clip_lo=cushion_clip[0], clip_hi=cushion_clip[1]
        )
    best_day_completed = 0.0
    lockout_days = 0
    max_qty = 0.0
    rows: list[dict[str, object]] = []

    outcome: Outcome = "incomplete" if not is_funded else "survived"
    breach: BreachEvent | None = None
    pass_date: dt.date | None = None
    pass_day_index: int | None = None
    effective_target: float | None = target
    days_consumed = 0

    for day_index, (date, trades) in enumerate(days):
        if time_limit is not None and time_limit.expired(date):
            outcome = "expired"
            break
        # daily_groups never yields an empty day, so every consumed day is
        # also a trading day — one counter serves both.
        days_consumed += 1
        day_open = balance
        # Day weight from DAY-START information only (strict t-1 info) —
        # identical recursions/kernels to the vectorized engine.
        w = float(sizer.weight()) if sizer is not None else 1.0  # scalar engine
        if cushion is not None:
            floor_t = float("-inf")
            for tr_rule in trailing:
                floor_t = max(floor_t, tr_rule.threshold)
            for st_rule in static:
                floor_t = max(floor_t, st_rule.floor)
            w *= cushion_weight(balance - floor_t, cushion)
        for rule in (*daily_fail, *daily_lockout):
            rule.day_start(day_open)
        day_cum = 0.0
        locked = False
        day_resolved = False

        for trade_index, trade in enumerate(trades):
            # Linear same-fill scaling: w constant within the day, so
            # scaling each trade's pnl/mae/mfe equals the vector engine's
            # w * {high,low,close}_rel row multiply exactly. Quantity
            # scales too so the contract-limit advisory sees the EFFECTIVE
            # position (matching resize_log's counterfactual).
            eff = (
                trade
                if w == 1.0
                else dataclasses.replace(
                    trade,
                    pnl=trade.pnl * w,
                    quantity=trade.quantity * w,
                    mae=trade.mae * w if trade.mae is not None else None,
                    mfe=trade.mfe * w if trade.mfe is not None else None,
                )
            )
            max_qty = max(max_qty, eff.quantity)
            high, low, close = trade_points(eff, day_open + day_cum)

            for tr_rule in trailing:
                tr_rule.observe_high(high)

            # First-hit resolution at the adverse extreme: equity descends, so
            # among all levels hit, the HIGHEST fires first. Fail beats
            # lockout on exact ties (liquidation implies both trigger).
            fail_hits: list[tuple[float, BreachEvent]] = []
            for tr_rule in trailing:
                event = tr_rule.check(low, date, day_index, trade_index)
                if event:
                    fail_hits.append((event.threshold, event))
            for st_rule in static:
                event = st_rule.check(low, date, day_index, trade_index)
                if event:
                    fail_hits.append((event.threshold, event))
            for dl_rule in daily_fail:
                if dl_rule.hit(low):
                    fail_hits.append(
                        (dl_rule.level, dl_rule.breach_event(low, date, day_index, trade_index))
                    )
            lockout_hits = [rule for rule in daily_lockout if rule.hit(low)]

            best_fail = max(fail_hits, key=lambda pair: pair[0]) if fail_hits else None
            best_lock = max(lockout_hits, key=lambda rule: rule.level) if lockout_hits else None

            if best_fail and (best_lock is None or best_fail[0] >= best_lock.level):
                outcome, breach = "breached", best_fail[1]
                day_cum = min(day_cum, best_fail[0] - day_open)
                day_resolved = True
            elif best_lock is not None:
                locked = True
                lockout_days += 1
                day_cum = -best_lock.width  # equity flattened exactly at the level
            else:
                day_cum = close - day_open
                balance = day_open + day_cum
                # Up-then-down catch: intraday ratchet may have raised the
                # floor above this trade's close.
                for tr_rule in trailing:
                    event = tr_rule.check(balance, date, day_index, trade_index)
                    if event:
                        outcome, breach = "breached", event
                        day_resolved = True
                        break

            if day_resolved:
                break

            if not locked and not is_funded and target is not None:
                best_day_running = max(best_day_completed, day_cum)
                effective_target = target
                blocked = False
                for gate in raise_gates:
                    effective_target = max(
                        effective_target, gate.required_total(target, best_day_running)
                    )
                    blocked = blocked or gate.pass_blocked(balance - initial, best_day_running)
                if (
                    not blocked
                    and balance - initial >= effective_target
                    and min_days.satisfied(days_consumed)
                ):
                    outcome = "passed"
                    pass_date = date
                    pass_day_index = day_index
                    day_resolved = True
                    break

            if locked:
                break

        balance = day_open + day_cum
        best_day_completed = max(best_day_completed, day_cum)
        if sizer is not None:
            # Advance the forecast with the day's UNSCALED per-unit PnL.
            sizer.update(float(sum(t.pnl for t in trades)))
        for tr_rule in trailing:
            tr_rule.day_close(balance)

        rows.append(
            {
                "date": date,
                "day_pnl": day_cum,
                "balance": balance,
                "hwm": max((r.hwm for r in trailing), default=float("nan")),
                "trailing_floor": max((r.threshold for r in trailing), default=float("nan")),
                "locked": locked,
                "trades": len(trades),
            }
        )
        if day_resolved:
            break

    if max_contracts_spec is not None and max_qty > max_contracts_spec.max_contracts:
        advisories.append(
            f"max position {max_qty:g} exceeds the {max_contracts_spec.max_contracts:g}-contract "
            f"limit (micros typically allowed at {max_contracts_spec.micros_multiplier:g}x) — "
            "sizing is advisory only and not enforced in simulation"
        )

    return EvaluationResult(
        firm=firm.name,
        phase=phase_cfg.name,
        outcome=outcome,
        passed=outcome == "passed",
        breach=breach,
        pass_date=pass_date,
        pass_day_index=pass_day_index,
        trading_days=days_consumed,
        final_balance=balance if rows else initial,
        initial_balance=initial,
        effective_target=effective_target,
        best_day=best_day_completed,
        lockout_days=lockout_days,
        fidelity=fidelity,
        timeline=pd.DataFrame(rows),
        advisories=advisories,
        days_consumed=days_consumed,
    )
