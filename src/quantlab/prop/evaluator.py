"""Deterministic replay of a real trade log against a firm's rules.

Produces a human-readable verdict: pass/fail, the exact breach event,
and a per-day timeline. The vectorized Monte Carlo engine implements the
same day-level semantics; a golden-equivalence test keeps them honest.

Fidelity: intraday checks use each trade's MAE/MFE when present,
otherwise trade-close granularity (documented as optimistic for
intraday-sensitive rules). Within a trade the point order is high -> low ->
close, except MAE-only records, which replay entry -> low -> close.
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
    ScalingPlanSpec,
    SessionCloseSpec,
    StaticMaxLossSpec,
    TimeLimitSpec,
    TrailingDrawdownSpec,
)
from quantlab.prop.dayprofile import trade_low_first, trade_points
from quantlab.prop.exposure import (
    peak_contract_equivalents,
    scaling_base_contracts,
    scaling_contract_limit,
)
from quantlab.prop.payout import PAYOUT_FLOOR_MARGIN, PayoutParams, resolve_payout
from quantlab.prop.rules import (
    BreachEvent,
    ConsistencyGate,
    DailyLossRule,
    MinTradingDaysGate,
    SessionCloseRule,
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
    fidelity: str  # "mae_mfe" | "partial_mae_mfe" | "trade_close"
    timeline: pd.DataFrame
    advisories: list[str] = field(default_factory=list)
    days_consumed: int = 0  # trading days used from the log (for phase chaining)
    # Funded-phase payout replay (evaluate(..., with_payouts=True)):
    total_withdrawn: float = 0.0
    payout_count: int = 0
    first_payout_date: dt.date | None = None


def evaluate(
    log: TradeLog,
    firm: FirmConfig,
    phase: str = "challenge",
    sizing: VolSizingParams | None = None,
    cushion_clip: tuple[float, float] | None = None,
    with_payouts: bool = False,
    payout_path: str | None = None,
) -> EvaluationResult:
    """Replay the full `log` against one phase.

    `sizing`: optional vol-targeted dynamic sizing — the same EwmaSizer
    recursion the Monte Carlo uses (golden equivalence by construction).
    `cushion_clip`: optional buffer-aware sizing — the same cushion_weight
    kernel the Monte Carlo uses. Phase chaining (each phase consuming
    days) lives in evaluate_sequence.

    `with_payouts`: replay the FUNDED phase with the firm's payout
    machinery (same PayoutParams the Monte Carlo resolves — payout-day
    windows, MLL reset events, cap ladders). `payout_path` overrides the
    YAML's payout.path ("standard" | "consistency")."""
    phase_cfg = _find_phase(firm, phase)
    days = log.daily_groups(firm.day_boundary.to_boundary())
    payout = _payout_for(log, firm, phase_cfg, days, payout_path) if with_payouts else None
    return _evaluate_days(
        days,
        firm,
        phase_cfg,
        fidelity_from(log),
        has_overlaps=log.has_overlapping_trades,
        cross_session_trades=log.cross_session_trade_count(firm.day_boundary.to_boundary()),
        sizing=sizing,
        cushion_clip=cushion_clip,
        base_contracts=scaling_base_contracts(log, scaling_contract_limit(phase_cfg)),
        payout=payout,
    )


def _payout_for(
    log: TradeLog,
    firm: FirmConfig,
    phase_cfg: PhaseConfig,
    days: list[tuple[dt.date, list[Trade]]],
    payout_path: str | None,
) -> PayoutParams:
    """Resolve payout parameters exactly as the Monte Carlo does."""
    from quantlab.metrics.core import observed_sessions_per_week

    if phase_cfg.profit_target is not None:
        raise ConfigError("payout replay applies to the funded phase only")
    boundary = firm.day_boundary.to_boundary()
    gate_pcts = [
        spec.max_best_day_pct / 100.0
        for spec in phase_cfg.rules
        if isinstance(spec, ConsistencySpec) and spec.effect == "gate_payout"
    ]
    sessions_per_week = observed_sessions_per_week(log, boundary, days=days)
    return resolve_payout(
        firm,
        phase_cfg.resolved_initial(firm.account_size),
        gate_pcts,
        sessions_per_week,
        path_override=payout_path,
    )


def evaluate_sequence(
    log: TradeLog,
    firm: FirmConfig,
    sizing: VolSizingParams | None = None,
    cushion_clip: tuple[float, float] | None = None,
    with_payouts: bool = False,
    payout_path: str | None = None,
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
            all_days[cursor:],
            firm,
            phase_cfg,
            fidelity,
            has_overlaps=log.has_overlapping_trades,
            cross_session_trades=log.cross_session_trade_count(firm.day_boundary.to_boundary()),
            sizing=sizing,
            cushion_clip=cushion_clip,
            base_contracts=scaling_base_contracts(log, scaling_contract_limit(phase_cfg)),
        )
        results.append(result)
        cursor += result.days_consumed
        if not result.passed:
            return results
    results.append(
        _evaluate_days(
            all_days[cursor:],
            firm,
            firm.funded,
            fidelity,
            has_overlaps=log.has_overlapping_trades,
            cross_session_trades=log.cross_session_trade_count(firm.day_boundary.to_boundary()),
            sizing=sizing,
            cushion_clip=cushion_clip,
            base_contracts=scaling_base_contracts(log, scaling_contract_limit(firm.funded)),
            payout=(
                _payout_for(log, firm, firm.funded, all_days[cursor:], payout_path)
                if with_payouts
                else None
            ),
        )
    )
    return results


def fidelity_from(log: TradeLog) -> str:
    return {
        "full": "mae_mfe",
        "partial": "partial_mae_mfe",
        "close-only": "trade_close",
    }[log.excursion_fidelity]


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
    has_overlaps: bool = False,
    cross_session_trades: int = 0,
    sizing: VolSizingParams | None = None,
    cushion_clip: tuple[float, float] | None = None,
    base_contracts: float | None = None,
    payout: PayoutParams | None = None,
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
    session_rules: list[SessionCloseRule] = []
    min_days = MinTradingDaysGate(MinTradingDaysSpec(days=0))
    time_limit: TimeLimitGate | None = None
    advisories: list[str] = []
    if has_overlaps:
        advisories.append(
            "trade intervals overlap: per-trade MAE/MFE cannot reconstruct the concurrent "
            "portfolio equity path, so intraday breach chronology is approximate; verify "
            "against a mark-to-market equity chart"
        )
    if cross_session_trades:
        advisories.append(
            f"{cross_session_trades} trade(s) cross the firm's daily reset: whole-trade PnL "
            "and excursions are assigned to the exit session, so daily-rule chronology and "
            "qualifying days are approximate; verify against mark-to-market equity data"
        )
    max_contracts_spec: ContractLimitSpec | None = None
    scaling_spec: ScalingPlanSpec | None = None

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
        elif isinstance(spec, SessionCloseSpec):
            session_rules.append(SessionCloseRule(spec, firm.day_boundary.to_boundary()))
            advisories.append(
                "session_close verifies POSITIONS only: pending-order cancellation "
                f"by the {spec.hard_close} {spec.tz} deadline is unobservable in a "
                "closed-trade log"
            )
        elif isinstance(spec, TimeLimitSpec):
            time_limit = TimeLimitGate(spec)
        elif isinstance(spec, ContractLimitSpec):
            max_contracts_spec = spec
        elif isinstance(spec, ScalingPlanSpec):
            scaling_spec = spec
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
    # Scaling plan (M11): identical semantics to the vectorized engine —
    # tier lookup on the prior close, Apex half-size until the sticky
    # safety-net unlock, caps never scale a weight UP.
    scaling_tiers: list[tuple[float, float]] | None = None
    half_cap_weight: float | None = None
    safety_net: float | None = None
    unlocked = False
    capped_days = 0
    if scaling_spec is not None:
        if base_contracts is None or base_contracts <= 0:
            raise ConfigError(
                f"phase {phase_cfg.name!r} has a scaling plan but the log carries no "
                "positive quantities — cannot derive the base contract size"
            )
        if scaling_spec.tiers:
            scaling_tiers = [(t.min_balance, t.max_contracts) for t in scaling_spec.tiers]
        if scaling_spec.half_until_safety_net:
            safety_net = firm.payout.safety_net_floor
            if safety_net is None:
                raise ConfigError(
                    "scaling_plan.half_until_safety_net needs payout.safety_net_floor"
                )
            full_allowance = (
                max_contracts_spec.max_contracts if max_contracts_spec else base_contracts
            )
            half_cap_weight = 0.5 * full_allowance / base_contracts
    best_day_completed = 0.0
    lockout_days = 0
    source_trades = [trade for _, trades in days for trade in trades]
    rows: list[dict[str, object]] = []

    # Funded-phase payout replay state (mirrors the Monte Carlo exactly).
    qual_days = 0
    days_since_payout = 0
    best_day_since = 0.0
    profit_anchor = initial
    payout_count = 0
    total_withdrawn = 0.0
    first_payout_date: dt.date | None = None

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
        cap_t = float("inf")
        if scaling_tiers is not None:
            assert base_contracts is not None
            allowed = scaling_tiers[0][1]
            for min_balance, max_contracts in scaling_tiers:
                if balance >= min_balance:
                    allowed = max_contracts
            cap_t = allowed / base_contracts
        if half_cap_weight is not None and not unlocked:
            cap_t = min(cap_t, half_cap_weight)
        if cap_t < w:
            w = cap_t
            capped_days += 1
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
            high, low, close = trade_points(eff, day_open + day_cum)
            low_first = trade_low_first(eff)

            if not low_first:
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
                # An MAE-only trade reaches its recorded close/high only after
                # surviving the adverse point. Ratcheting beforehand creates
                # a false trailing breach for profitable trades.
                if low_first:
                    for tr_rule in trailing:
                        tr_rule.observe_high(high)
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

            # Session-close check: only for trades that survived the equity
            # rules, and BEFORE the pass check — a position open at/after
            # the hard close can never deliver the pass (its recorded exit
            # could not have happened on a compliant account).
            if session_rules and not locked:
                sc_event = None
                for sc_rule in session_rules:
                    sc_event = sc_rule.violation(trade, date, day_index, trade_index, balance)
                    if sc_event is not None:
                        break
                if sc_event is not None:
                    outcome, breach = "breached", sc_event
                    day_resolved = True
                    break

            if locked:
                break

        balance = day_open + day_cum
        best_day_completed = max(best_day_completed, day_cum)
        # Pass adjudication happens on COMPLETED-SESSION state only (below,
        # at day close): Topstep locks each day's value at 3:10 PM CT
        # ("that day's value locks into your trading history"), so touching
        # the target intraday and giving it back the same session is NOT a
        # pass. An intraday breach still fails immediately (real-time MLL).
        if sizer is not None:
            # Advance the forecast with the day's UNSCALED per-unit PnL.
            sizer.update(float(sum(t.pnl for t in trades)))
        if safety_net is not None and balance >= safety_net:
            # Sticky: full size persists even if balance drops. Keys on
            # the CLOSING (realized) balance even for intraday-ratchet
            # firms, matching the vector engine — see the divergence
            # note on the unlock in montecarlo._simulate_phase.
            unlocked = True
        for tr_rule in trailing:
            tr_rule.day_close(balance)

        # EOD pass adjudication (evaluation phases): target and the
        # consistency raise are tested against the session-CLOSE balance
        # and the LOCKED best day. A DLL-locked day still adjudicates —
        # the lockout is a soft breach, the session still closes.
        if not is_funded and target is not None and not day_resolved:
            effective_target = target
            blocked = False
            for gate in raise_gates:
                effective_target = max(
                    effective_target, gate.required_total(target, best_day_completed)
                )
                blocked = blocked or gate.pass_blocked(balance - initial, best_day_completed)
            if (
                not blocked
                and balance - initial >= effective_target
                and min_days.satisfied(days_consumed)
            ):
                outcome = "passed"
                pass_date = date
                pass_day_index = day_index
                day_resolved = True

        # Payout replay AFTER the EOD ratchet (matching the Monte Carlo:
        # the floor advances from the pre-withdrawal closing balance).
        payout_amount = 0.0
        if payout is not None and not day_resolved:
            if day_cum >= payout.q_min_profit:
                qual_days += 1
            days_since_payout += 1
            best_day_since = max(best_day_since, day_cum)
            profit_since = balance - profit_anchor
            if payout.path == "consistency":
                # Active days == sessions (daily_groups never yields an
                # empty day); best positive day at MOST c_frac of the
                # window total — INCLUSIVE (exactly 40% still qualifies).
                eligible = (
                    days_since_payout >= max(payout.c_min_days, payout.period_td, 1)
                    and profit_since > 0
                    and best_day_since <= payout.c_frac * profit_since
                )
            else:
                eligible = qual_days >= payout.q_count and days_since_payout >= max(
                    payout.period_td, 1
                )
                if payout.require_profit_since and payout_count > 0:
                    # At least $0.01 since the prior payout (Topstep
                    # payout policy) — not merely floating-point > 0.
                    eligible = eligible and profit_since >= 0.01
            for frac in payout.gate_pcts:
                # Apex wording: a best day at "50% or more" blocks — strict.
                eligible = eligible and profit_since > 0 and best_day_since < frac * profit_since
            if eligible:
                cap = float(payout.ladder[min(payout_count, len(payout.ladder) - 1)])
                floor_eff = payout.floor
                for tr_rule in trailing:
                    cap_level = tr_rule.spec.threshold_cap
                    if cap_level is None:
                        floor_eff = max(floor_eff, initial - tr_rule.amount + PAYOUT_FLOOR_MARGIN)
                    else:
                        floor_eff = max(floor_eff, tr_rule.threshold + PAYOUT_FLOOR_MARGIN)
                        if payout.mll_reset_on_payout:
                            floor_eff = max(floor_eff, cap_level + PAYOUT_FLOOR_MARGIN)
                amount = min(balance - floor_eff - payout.keep_buffer, cap)
                if payout.share_of_balance is not None:
                    amount = min(amount, payout.share_of_balance * balance)
                if amount >= payout.min_payout:
                    payout_amount = amount
                    total_withdrawn += amount
                    balance -= amount
                    for tr_rule in trailing:
                        cap_level = tr_rule.spec.threshold_cap
                        if cap_level is None:
                            # Rebasing trail (FTMO 1-Step): hwm drops with
                            # the withdrawal, floored at initial.
                            tr_rule.hwm = max(tr_rule.hwm - amount, initial)
                        elif payout.mll_reset_on_payout:
                            # "Your Maximum Loss Limit (MLL) resets to $0
                            # permanently" — the floor snaps to its cap as
                            # an EVENT at payout approval.
                            tr_rule.hwm = max(tr_rule.hwm, cap_level + tr_rule.amount)
                    if first_payout_date is None:
                        first_payout_date = date
                    payout_count += 1
                    qual_days = 0
                    days_since_payout = 0
                    best_day_since = 0.0
                    profit_anchor = balance
                    if payout.max_lifetime is not None and payout_count >= payout.max_lifetime:
                        advisories.append(
                            f"retired after {payout_count} payouts (lifetime cap); replay stopped"
                        )
                        day_resolved = True

        row: dict[str, object] = {
            "date": date,
            "day_pnl": day_cum,
            "balance": balance,
            "hwm": max((r.hwm for r in trailing), default=float("nan")),
            "trailing_floor": max((r.threshold for r in trailing), default=float("nan")),
            "locked": locked,
            "trades": len(trades),
        }
        if payout is not None:
            row["payout"] = payout_amount
        rows.append(row)
        if day_resolved:
            break

    peak_contracts = (
        peak_contract_equivalents(source_trades, max_contracts_spec)
        if max_contracts_spec is not None
        else 0.0
    )
    if max_contracts_spec is not None and peak_contracts > max_contracts_spec.max_contracts:
        advisories.append(
            f"source-log peak concurrent gross exposure {peak_contracts:g} "
            "mini-equivalents exceeds the "
            f"{max_contracts_spec.max_contracts:g}-contract limit (micros converted at "
            f"{max_contracts_spec.micros_multiplier:g}:1) — "
            "sizing is advisory only and not enforced in simulation"
        )
    if scaling_spec is not None and capped_days:
        advisories.append(
            f"scaling plan capped position size on {capped_days} day(s) "
            f"(base {base_contracts:g} mini-equivalents = peak concurrent gross "
            "source-log exposure; "
            "same-fill linear scaling)"
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
        total_withdrawn=total_withdrawn,
        payout_count=payout_count,
        first_payout_date=first_payout_date,
    )
