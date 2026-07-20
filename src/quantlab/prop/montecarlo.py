"""Vectorized Monte Carlo simulation of prop-firm accounts.

Paths are bootstrap-resampled sequences of source trading DAYS; each day
replays its trades step-by-step (padded per-trade arrays from
DayProfile), with every rule check vectorized across paths. The
semantics per trade are identical to the DeterministicEvaluator —
high -> low -> close, first-hit resolution by highest level, lockout
truncation at exactly -width, pass at trade close — which a golden
equivalence test enforces.

Calendar approximation: rule/payout windows quoted in calendar days
convert to trading days using the SOURCE LOG'S observed trading density
(sessions per week), so a Monday/Wednesday-only trader gets ~9 sessions
out of a 30-calendar-day limit, not 22. Dense weekday logs convert at
5/7 (Apex's 30-day expiry -> 22 trading days); fee months are 21 trading
days at that baseline, scaled by the same density (see economics.py).
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import numpy as np

from quantlab.errors import ConfigError, QuantLabError
from quantlab.prop.bootstrap import BootstrapName, make_bootstrapper, optimal_block_length
from quantlab.prop.config import (
    ConsistencySpec,
    ContractLimitSpec,
    DailyLossLimitSpec,
    FirmConfig,
    MinTradingDaysSpec,
    PhaseConfig,
    ScalingPlanSpec,
    StaticMaxLossSpec,
    TimeLimitSpec,
    TrailingDrawdownSpec,
    resolved_amount,
)
from quantlab.prop.dayprofile import DayProfile
from quantlab.prop.economics import summarize
from quantlab.prop.outcomes import (
    OUTCOME_ACTIVE,
    OUTCOME_BREACHED,
    OUTCOME_EXPIRED,
    OUTCOME_PASSED,
    OUTCOME_RETIRED,
    MonteCarloReport,
    PhaseOutcome,
)
from quantlab.prop.rules.base import breached
from quantlab.prop.voltarget import (
    CushionParams,
    EwmaSizer,
    VolSizingParams,
    auto_target_vol,
    cushion_weight,
)
from quantlab.schema.trade import TradeLog

MIN_DAYS_FOR_BLOCKS = 30
DEFAULT_SESSIONS_PER_WEEK = 5.0


def ensure_crn_seed(cfg: MCConfig) -> MCConfig:
    """A concrete seed for grid analyses (frontier, policies): common
    random numbers require one — default_rng(None) pulls fresh OS entropy
    per call, turning cell differences into resampling noise."""
    if cfg.seed is not None:
        return cfg
    import dataclasses as _dc

    return _dc.replace(cfg, seed=int(np.random.default_rng().integers(0, 2**31 - 1)))


# Keep withdrawn balances strictly above trailing floors so a payout can
# never itself trigger an inclusive-touch breach on the next bar.
PAYOUT_FLOOR_MARGIN = 0.01


def calendar_to_trading_days(
    calendar_days: int, sessions_per_week: float = DEFAULT_SESSIONS_PER_WEEK
) -> int:
    return max(1, math.ceil(calendar_days * sessions_per_week / 7))


def observed_sessions_per_week(log: TradeLog, boundary, days: list | None = None) -> float:
    """Trading density of the source log (sessions/week), capped at 7.

    Counts sessions over COMPLETE Mon-Sun weeks only (weeks whose full
    range lies inside the log's span). Partial edge weeks bias every
    simpler estimator: the raw endpoint ratio rates a Mon-Fri week at
    7.0/week (span excludes the weekend), while padding the span to
    whole weeks rates a full 22-session month at 4.4/week (a barely
    started final week fully counts in the denominator). Fewer than two
    complete weeks is too little cadence evidence — use the default.
    """
    if days is None:
        days = log.daily_groups(boundary)
    if len(days) < 2:
        return DEFAULT_SESSIONS_PER_WEEK
    first, last = days[0][0], days[-1][0]
    week_of_first = first - dt.timedelta(days=first.weekday())
    start = week_of_first if week_of_first == first else week_of_first + dt.timedelta(days=7)
    counts: dict[dt.date, int] = {}
    for session_date, _ in days:
        monday = session_date - dt.timedelta(days=session_date.weekday())
        counts[monday] = counts.get(monday, 0) + 1
    n_weeks = 0
    n_sessions = 0
    monday = start
    while monday + dt.timedelta(days=6) <= last:
        n_weeks += 1
        n_sessions += counts.get(monday, 0)  # vacation weeks count as 0
        monday += dt.timedelta(days=7)
    if n_weeks < 2 or n_sessions == 0:
        return DEFAULT_SESSIONS_PER_WEEK
    return min(7.0, n_sessions / n_weeks)


@dataclass
class MCConfig:
    n_paths: int = 10_000
    challenge_horizon_days: int = 120  # trading days per eval phase
    funded_horizon_days: int = 252
    bootstrap: BootstrapName = "stationary"
    block_len: int | None = None
    seed: int | None = None
    scale: float = 1.0
    challenge_scale: float | None = None  # per-phase sizing what-ifs
    funded_scale: float | None = None
    sample_paths_kept: int = 200
    # Scaling-plan cap conversion: the log's max observed |quantity| unless
    # overridden — "your log trades your full allowance" is the default
    # assumption, stated on output.
    base_contracts: float | None = None
    # Dynamic sizing (M9 vol_target, M11 cushion):
    # vol_target: weight_t = clip(target/sigma_t) from a per-path EWMA
    #   forecast of the strategy's per-unit day PnL.
    # cushion: weight_t = clip(cushion_t/cushion_0) from the live buffer
    #   above the trailing/static floor — the prop-native heuristic that
    #   de-risks toward the floor and re-risks as the buffer grows.
    sizing: str = "fixed"  # "fixed" | "vol_target" | "cushion"
    vol_lambda: float = 0.94  # RiskMetrics 1996 daily decay
    vol_target: float | None = None  # None -> median EWMA sigma of the profile
    vol_clip: tuple[float, float] = (0.5, 1.5)  # Moreira-Muir 1.5x cap
    cushion_clip: tuple[float, float] = (0.25, 1.5)
    # Funded-phase payout policy (M11): "asap" withdraws the maximum as
    # soon as eligible (the pre-M11 hardcoded behavior); "keep_buffer"
    # leaves `keep_buffer` dollars of cushion above the payout floor
    # working in the account. The trade-off is real and log-dependent:
    # the working buffer compounds (often higher long-run EV) but the
    # first payout lands later, so ruin-before-any-payout can RISE.
    payout_policy: str = "asap"  # "asap" | "keep_buffer"
    keep_buffer: float = 0.0
    # Extraction mode: once a path has banked its qualifying days for the
    # current payout cycle, multiply the day weight by this (0 < w <= 1)
    # until the payout lands — protect the banked cycle, then re-risk.
    # Definitional edge (deliberate): if the payout never becomes
    # eligible (e.g. a consistency gate that reduced size makes slower to
    # clear), the path STAYS at extract_weight — a well-defined policy
    # whose cost shows up honestly in the policies grid. Note the gate
    # interaction can self-reinforce: an Apex-style 50%-of-total gate
    # clears as profit_since grows, and extraction slows that growth,
    # so a dominant early day keeps the gate shut LONGER under
    # extraction. The grid prices exactly this.
    extract_weight: float | None = None


@dataclass
class _Trailing:
    amount: float
    intraday: bool
    cap: float  # +inf when uncapped
    inclusive: bool
    name: str


@dataclass
class _Barrier:  # static floors and daily-loss widths
    value: float  # static: absolute floor; daily: width below day open
    inclusive: bool
    name: str


@dataclass
class _ConsistencyRaise:
    frac: float
    strict: bool  # basis=total_profit: best day exactly at frac*total still blocks


@dataclass
class _PhaseRules:
    trailing: list[_Trailing]
    static: list[_Barrier]
    daily_fail: list[_Barrier]
    daily_lock: list[_Barrier]
    raises: list[_ConsistencyRaise]  # consistency (raise_target)
    payout_gate_pcts: list[float]  # consistency pct fractions (gate_payout)
    min_days: int
    time_limit_td: int | None
    rule_names: list[str]  # fail-code order: trailing, static, daily_fail
    scaling_tiers: list[tuple[float, float]] | None = None  # (min_balance, max_contracts) asc
    scaling_half_until_net: bool = False  # Apex: half size until safety-net unlock
    contract_limit: float | None = None  # full allowance (ContractLimitSpec)


def _resolve_rules(
    phase: PhaseConfig,
    firm: FirmConfig,
    initial: float,
    sessions_per_week: float = DEFAULT_SESSIONS_PER_WEEK,
) -> _PhaseRules:
    trailing: list[_Trailing] = []
    static: list[_Barrier] = []
    daily_fail: list[_Barrier] = []
    daily_lock: list[_Barrier] = []
    raises: list[_ConsistencyRaise] = []
    payout_gate_pcts: list[float] = []
    min_days = 0
    time_limit_td: int | None = None
    scaling_tiers: list[tuple[float, float]] | None = None
    scaling_half = False
    contract_limit: float | None = None
    for spec in phase.rules:
        if isinstance(spec, TrailingDrawdownSpec):
            trailing.append(
                _Trailing(
                    amount=resolved_amount(spec, firm.account_size),
                    intraday=spec.ratchet == "intraday",
                    cap=spec.threshold_cap if spec.threshold_cap is not None else np.inf,
                    inclusive=spec.inclusive,
                    name=f"trailing_drawdown[{spec.ratchet}]",
                )
            )
        elif isinstance(spec, StaticMaxLossSpec):
            static.append(
                _Barrier(
                    value=initial - resolved_amount(spec, firm.account_size),
                    inclusive=spec.inclusive,
                    name="static_max_loss",
                )
            )
        elif isinstance(spec, DailyLossLimitSpec):
            barrier = _Barrier(
                value=resolved_amount(spec, firm.account_size),
                inclusive=spec.inclusive,
                name=f"daily_loss_limit[{spec.effect}]",
            )
            (daily_lock if spec.effect == "lockout" else daily_fail).append(barrier)
        elif isinstance(spec, ConsistencySpec):
            frac = spec.max_best_day_pct / 100.0
            if spec.effect == "raise_target":
                raises.append(_ConsistencyRaise(frac=frac, strict=spec.basis == "total_profit"))
            else:
                payout_gate_pcts.append(frac)
        elif isinstance(spec, MinTradingDaysSpec):
            min_days = spec.days
        elif isinstance(spec, TimeLimitSpec):
            time_limit_td = calendar_to_trading_days(spec.max_calendar_days, sessions_per_week)
        elif isinstance(spec, ContractLimitSpec):
            contract_limit = spec.max_contracts  # full allowance; advisory sizing check
        elif isinstance(spec, ScalingPlanSpec):
            if spec.tiers:
                scaling_tiers = [(t.min_balance, t.max_contracts) for t in spec.tiers]
            else:
                scaling_half = True
        else:  # pragma: no cover - exhaustiveness guard for future rule types
            raise ConfigError(
                f"Rule type {type(spec).__name__} is not handled by the Monte Carlo "
                "engine — add it to _resolve_rules (and the evaluator) before use."
            )
    rule_names = (
        [t.name for t in trailing] + [s.name for s in static] + [d.name for d in daily_fail]
    )
    return _PhaseRules(
        trailing=trailing,
        static=static,
        daily_fail=daily_fail,
        daily_lock=daily_lock,
        raises=raises,
        payout_gate_pcts=payout_gate_pcts,
        min_days=min_days,
        time_limit_td=time_limit_td,
        rule_names=rule_names,
        scaling_tiers=scaling_tiers,
        scaling_half_until_net=scaling_half,
        contract_limit=contract_limit,
    )


@dataclass
class _PayoutParams:
    floor: float  # withdrawals never take balance below this
    share_of_balance: float | None
    ladder: np.ndarray  # per-payout caps; last entry repeats
    max_lifetime: int | None
    min_payout: float
    q_count: int
    q_min_profit: float
    period_td: int
    gate_pcts: list[float]
    keep_buffer: float = 0.0  # cushion left working above the payout floor


def _resolve_payout(
    firm: FirmConfig,
    initial: float,
    gate_pcts: list[float],
    sessions_per_week: float = DEFAULT_SESSIONS_PER_WEEK,
    keep_buffer: float = 0.0,
) -> _PayoutParams:
    p = firm.payout
    floor_candidates = [initial]
    if p.safety_net_floor is not None:
        floor_candidates.append(p.safety_net_floor)
    if p.buffer_above_initial is not None:
        floor_candidates.append(initial + p.buffer_above_initial)
    ladder = np.array(p.payout_cap_ladder or [np.inf], dtype=float)
    return _PayoutParams(
        floor=max(floor_candidates),
        share_of_balance=p.payout_share_of_balance,
        ladder=ladder,
        max_lifetime=p.max_lifetime_payouts,
        min_payout=max(p.min_payout, 1e-9),
        q_count=p.qualifying_days.count,
        q_min_profit=p.qualifying_days.min_daily_profit,
        period_td=(
            calendar_to_trading_days(p.period_days, sessions_per_week) if p.period_days else 0
        ),
        gate_pcts=gate_pcts,
        keep_buffer=keep_buffer,
    )


def _simulate_phase(
    profile: DayProfile,
    idx: np.ndarray,
    phase: PhaseConfig,
    firm: FirmConfig,
    payout: _PayoutParams | None,
    sample_paths: int,
    sessions_per_week: float = DEFAULT_SESSIONS_PER_WEEK,
    sizing: VolSizingParams | None = None,
    cushion_clip: tuple[float, float] | None = None,
    base_contracts: float | None = None,
    extract_weight: float | None = None,
) -> PhaseOutcome:
    n_paths, horizon = idx.shape
    initial = phase.resolved_initial(firm.account_size)
    rules = _resolve_rules(phase, firm, initial, sessions_per_week)
    target = phase.profit_target
    is_funded = target is None

    # Contract scaling plan (M11): allowed contracts -> a weight cap via
    # base_contracts (the log's max observed position unless overridden).
    tier_mins = tier_allowed = None
    half_cap_weight: float | None = None
    unlocked = None
    safety_net = None
    if rules.scaling_tiers is not None or rules.scaling_half_until_net:
        if base_contracts is None or base_contracts <= 0:
            raise QuantLabError(
                f"phase {phase.name!r} has a scaling plan but no usable base "
                "contract size — the log carries no positive quantities; pass "
                "--base-contracts"
            )
        if rules.scaling_tiers is not None:
            tier_mins = np.array([m for m, _ in rules.scaling_tiers])
            tier_allowed = np.array([c for _, c in rules.scaling_tiers])
        if rules.scaling_half_until_net:
            safety_net = firm.payout.safety_net_floor
            if safety_net is None:
                raise QuantLabError(
                    "scaling_plan.half_until_safety_net needs payout.safety_net_floor"
                )
            full_allowance = (
                rules.contract_limit if rules.contract_limit is not None else base_contracts
            )
            half_cap_weight = 0.5 * full_allowance / base_contracts
            unlocked = np.zeros(n_paths, dtype=bool)

    cushion: CushionParams | None = None
    if cushion_clip is not None:
        # cushion_0 = the phase's initial drawdown allowance: distance
        # from the starting balance to the tightest day-0 floor.
        floor_0 = -np.inf
        for tr in rules.trailing:
            floor_0 = max(floor_0, min(initial - tr.amount, tr.cap))
        for st in rules.static:
            floor_0 = max(floor_0, st.value)
        if not np.isfinite(floor_0) or floor_0 >= initial:
            raise QuantLabError(
                f"cushion sizing needs a trailing/static drawdown rule below the "
                f"initial balance in phase {phase.name!r}"
            )
        try:
            cushion = CushionParams(
                cushion_0=float(initial - floor_0),
                clip_lo=cushion_clip[0],
                clip_hi=cushion_clip[1],
            )
        except ValueError as exc:
            raise QuantLabError(str(exc)) from None

    balance = np.full(n_paths, float(initial))
    outcome = np.full(n_paths, OUTCOME_ACTIVE, dtype=np.int8)
    end_day = np.full(n_paths, horizon - 1, dtype=np.int32)
    fail_rule = np.full(n_paths, -1, dtype=np.int16)
    hwms = [np.full(n_paths, float(initial)) for _ in rules.trailing]
    best_day_completed = np.zeros(n_paths)
    peak = np.full(n_paths, float(initial))
    max_dd = np.zeros(n_paths)
    lockout_days = np.zeros(n_paths, dtype=np.int32)

    n_samples = min(sample_paths, n_paths)
    equity_samples = np.full((n_samples, horizon), np.nan)

    total_withdrawn = np.zeros(n_paths)
    payout_count = np.zeros(n_paths, dtype=np.int32)
    first_payout_day = np.full(n_paths, -1, dtype=np.int32)
    qual_days = np.zeros(n_paths, dtype=np.int32)
    days_since_payout = np.zeros(n_paths, dtype=np.int32)
    best_day_since = np.zeros(n_paths)
    profit_anchor = np.full(n_paths, float(initial))

    n_trades_arr = profile.n_trades
    low_rel, high_rel, close_rel = profile.low_rel, profile.high_rel, profile.close_rel
    # One shared sizing recursion serves both engines (see voltarget.py);
    # sizer.var is a (P,) array here and a float in the evaluator.
    sizer = EwmaSizer(sizing, n_paths=n_paths) if sizing is not None else None

    for t in range(horizon):
        alive = outcome == OUTCOME_ACTIVE
        if not alive.any():
            break
        if rules.time_limit_td is not None and t >= rules.time_limit_td:
            outcome[alive] = OUTCOME_EXPIRED
            end_day[alive] = t - 1
            break

        d = idx[:, t]
        day_n = n_trades_arr[d]
        day_open = balance.copy()
        locked = np.zeros(n_paths, dtype=bool)
        k_max = int(day_n[alive].max())
        # Day weight from DAY-START information only (strict t-1 info):
        # the EWMA forecast uses prior days' unscaled PnL; the cushion
        # weight uses the day-open balance vs the current floor. +/-inf
        # padding survives the positive multiply unchanged.
        w = sizer.weight() if sizer is not None else None
        if cushion is not None:
            floor_t = np.full(n_paths, -np.inf)
            for r, tr in enumerate(rules.trailing):
                floor_t = np.maximum(floor_t, np.minimum(hwms[r] - tr.amount, tr.cap))
            for st in rules.static:
                floor_t = np.maximum(floor_t, st.value)
            w_cushion = cushion_weight(balance - floor_t, cushion)
            w = w_cushion if w is None else w * w_cushion
        if extract_weight is not None and payout is not None and payout.q_count > 0:
            # Extraction: qualifying days banked for this cycle -> protect
            # them at reduced size until the payout lands (qual_days reset
            # on payout restores full size for the next cycle).
            w_extract = np.where(qual_days >= payout.q_count, extract_weight, 1.0)
            w = w_extract if w is None else w * w_extract
        # Scaling-plan cap LAST: no sizing mode may exceed the firm's
        # allowed size. Tier lookup uses the PRIOR-day close (= day_open;
        # Topstep: limits never increase mid-session); the Apex half-size
        # cap applies until the sticky safety-net unlock.
        if tier_mins is not None:
            assert tier_allowed is not None and base_contracts is not None
            tier_idx = np.maximum(np.searchsorted(tier_mins, balance, side="right") - 1, 0)
            cap_t = tier_allowed[tier_idx] / base_contracts
            # A cap never scales UP: fixed sizing stays at 1 even when the
            # tier would allow more contracts than the log ever used.
            w = np.minimum(np.ones(n_paths) if w is None else w, cap_t)
        if half_cap_weight is not None:
            assert unlocked is not None
            cap_t = np.where(unlocked, np.inf, half_cap_weight)
            w = np.minimum(np.ones(n_paths) if w is None else w, cap_t)

        for i in range(k_max):
            stepping = alive & ~locked & (i < day_n) & (outcome == OUTCOME_ACTIVE)
            if not stepping.any():
                break
            if w is None:
                high = day_open + high_rel[d, i]
                low = day_open + low_rel[d, i]
                close = day_open + close_rel[d, i]
            else:
                high = day_open + w * high_rel[d, i]
                low = day_open + w * low_rel[d, i]
                close = day_open + w * close_rel[d, i]

            for r, tr in enumerate(rules.trailing):
                if tr.intraday:
                    hwms[r] = np.where(stepping, np.maximum(hwms[r], high), hwms[r])

            # First-hit resolution: highest hit level wins; fail >= lockout.
            best_fail_level = np.full(n_paths, -np.inf)
            best_fail_code = np.full(n_paths, -1, dtype=np.int16)
            code = 0
            for r, tr in enumerate(rules.trailing):
                thr = np.minimum(hwms[r] - tr.amount, tr.cap)
                hit = stepping & breached(low, thr, tr.inclusive)
                better = hit & (thr > best_fail_level)
                best_fail_level = np.where(better, thr, best_fail_level)
                best_fail_code = np.where(better, code, best_fail_code)
                code += 1
            for st in rules.static:
                hit = stepping & breached(low, st.value, st.inclusive)
                better = hit & (st.value > best_fail_level)
                best_fail_level = np.where(better, st.value, best_fail_level)
                best_fail_code = np.where(better, code, best_fail_code)
                code += 1
            for dl in rules.daily_fail:
                level = day_open - dl.value
                hit = stepping & breached(low, level, dl.inclusive)
                better = hit & (level > best_fail_level)
                best_fail_level = np.where(better, level, best_fail_level)
                best_fail_code = np.where(better, code, best_fail_code)
                code += 1

            best_lock_level = np.full(n_paths, -np.inf)
            best_lock_width = np.zeros(n_paths)
            for dl in rules.daily_lock:
                level = day_open - dl.value
                hit = stepping & breached(low, level, dl.inclusive)
                better = hit & (level > best_lock_level)
                best_lock_level = np.where(better, level, best_lock_level)
                best_lock_width = np.where(better, dl.value, best_lock_width)

            fail_hit = best_fail_level > -np.inf
            lock_hit = best_lock_level > -np.inf
            fail_wins = fail_hit & (~lock_hit | (best_fail_level >= best_lock_level))
            newly_locked = lock_hit & ~fail_wins

            if fail_wins.any():
                outcome[fail_wins] = OUTCOME_BREACHED
                end_day[fail_wins] = t
                fail_rule[fail_wins] = best_fail_code[fail_wins]
                balance = np.where(fail_wins, np.minimum(balance, best_fail_level), balance)
            if newly_locked.any():
                locked |= newly_locked
                lockout_days[newly_locked] += 1
                balance = np.where(newly_locked, day_open - best_lock_width, balance)

            still = stepping & ~fail_wins & ~newly_locked
            balance = np.where(still, close, balance)

            # Up-then-down catch at close (intraday ratchet raised the floor
            # above this trade's close). Mathematically implied by the low
            # check, kept for exact scalar parity.
            for r, tr in enumerate(rules.trailing):
                thr = np.minimum(hwms[r] - tr.amount, tr.cap)
                hit = still & breached(balance, thr, tr.inclusive)
                if hit.any():
                    outcome[hit] = OUTCOME_BREACHED
                    end_day[hit] = t
                    fail_rule[hit] = r
                    still &= ~hit

            if not is_funded:
                assert target is not None
                day_close_so_far = close_rel[d, i] if w is None else w * close_rel[d, i]
                best_running = np.maximum(best_day_completed, day_close_so_far)
                eff_target = np.full(n_paths, float(target))
                blocked = np.zeros(n_paths, dtype=bool)
                for gate in rules.raises:
                    raised = np.where(
                        best_running > gate.frac * target, best_running / gate.frac, target
                    )
                    eff_target = np.maximum(eff_target, raised)
                    if gate.strict:
                        # "50% or more" wording: exact equality still blocks.
                        blocked |= (best_running > 0) & (
                            best_running >= gate.frac * (balance - initial)
                        )
                pass_hit = (
                    still & ~blocked & (balance - initial >= eff_target) & (t + 1 >= rules.min_days)
                )
                if pass_hit.any():
                    outcome[pass_hit] = OUTCOME_PASSED
                    end_day[pass_hit] = t

        # --- day close -----------------------------------------------------
        alive = outcome == OUTCOME_ACTIVE
        day_pnl = balance - day_open
        if sizer is not None:
            # Advance the forecast with the sampled day's UNSCALED per-unit
            # PnL — the strategy's own volatility, independent of the
            # weight that was applied to the account.
            sizer.update(profile.day_pnl[d])
        if unlocked is not None:
            # Apex: full size unlocks when the CLOSING balance reaches the
            # safety net, and stays unlocked even if it later drops. On
            # the intraday variants this deliberately diverges from the
            # trailing-floor freeze: the freeze keys on the intraday PEAK
            # (the threshold trails live PnL) while the unlock keys on
            # realized balance, per the firm's own rule texts — a path
            # whose high touches the net but closes below it gets a
            # frozen floor yet stays half-capped. Day-close balance is
            # the conservative realized-balance proxy at day granularity.
            unlocked = unlocked | (balance >= safety_net)
        for r, tr in enumerate(rules.trailing):
            if not tr.intraday:
                hwms[r] = np.where(alive, np.maximum(hwms[r], balance), hwms[r])
        best_day_completed = np.where(
            alive, np.maximum(best_day_completed, day_pnl), best_day_completed
        )
        peak = np.maximum(peak, balance)
        max_dd = np.maximum(max_dd, peak - balance)
        equity_samples[:, t] = np.where(
            (outcome[:n_samples] == OUTCOME_ACTIVE) | (end_day[:n_samples] == t),
            balance[:n_samples],
            np.nan,
        )

        if payout is not None:
            qual_days = np.where(alive & (day_pnl >= payout.q_min_profit), qual_days + 1, qual_days)
            days_since_payout = np.where(alive, days_since_payout + 1, days_since_payout)
            best_day_since = np.where(alive, np.maximum(best_day_since, day_pnl), best_day_since)
            profit_since = balance - profit_anchor
            eligible = (
                alive
                & (qual_days >= payout.q_count)
                & (days_since_payout >= max(payout.period_td, 1))
            )
            for frac in payout.gate_pcts:
                # Apex wording: a best day at "50% or more" blocks — strict.
                eligible &= (profit_since > 0) & (best_day_since < frac * profit_since)
            cap = payout.ladder[np.minimum(payout_count, len(payout.ladder) - 1)]
            # A withdrawal must never drop the balance to (or below) a live
            # trailing floor: the firm would liquidate the account on the
            # next tick. Bound the amount by every trailing threshold.
            floor_eff = np.full(n_paths, float(payout.floor))
            for r, tr in enumerate(rules.trailing):
                if np.isinf(tr.cap):
                    # Rebasing trail (FTMO 1-Step): the hwm drops with the
                    # withdrawal below, so the threshold moves down 1:1 with
                    # the amount — bounding by the PRE-withdrawal threshold
                    # would strand withdrawable profit. Only the post-rebase
                    # minimum (initial - width) constrains the amount.
                    floor_eff = np.maximum(
                        floor_eff, float(initial) - tr.amount + PAYOUT_FLOOR_MARGIN
                    )
                else:
                    thr = np.minimum(hwms[r] - tr.amount, tr.cap)
                    floor_eff = np.maximum(floor_eff, thr + PAYOUT_FLOOR_MARGIN)
            # keep_buffer policy: leave that much cushion WORKING above
            # the effective floor instead of withdrawing it.
            amount = np.minimum(balance - floor_eff - payout.keep_buffer, cap)
            if payout.share_of_balance is not None:
                amount = np.minimum(amount, payout.share_of_balance * balance)
            paying = eligible & (amount >= payout.min_payout)
            if paying.any():
                total_withdrawn = np.where(paying, total_withdrawn + amount, total_withdrawn)
                balance = np.where(paying, balance - amount, balance)
                # Withdrawal is not trading drawdown: shift the peak with it.
                peak = np.where(paying, peak - amount, peak)
                # Uncapped trails (FTMO 1-Step) reset on reward withdrawal —
                # approximate by lowering the hwm with the withdrawn amount.
                # Capped/locked floors (Topstep/Apex) never move down.
                for r, tr in enumerate(rules.trailing):
                    if np.isinf(tr.cap):
                        hwms[r] = np.where(
                            paying, np.maximum(hwms[r] - amount, float(initial)), hwms[r]
                        )
                first_payout_day = np.where(paying & (first_payout_day < 0), t, first_payout_day)
                payout_count = np.where(paying, payout_count + 1, payout_count)
                qual_days = np.where(paying, 0, qual_days)
                days_since_payout = np.where(paying, 0, days_since_payout)
                best_day_since = np.where(paying, 0.0, best_day_since)
                profit_anchor = np.where(paying, balance, profit_anchor)
                if payout.max_lifetime is not None:
                    retired = paying & (payout_count >= payout.max_lifetime)
                    if retired.any():
                        outcome[retired] = OUTCOME_RETIRED
                        end_day[retired] = t

    return PhaseOutcome(
        phase=phase.name,
        initial_balance=initial,
        horizon=horizon,
        outcome=outcome,
        end_day=end_day,
        fail_rule=fail_rule,
        rule_names=rules.rule_names,
        final_balance=balance,
        max_drawdown=max_dd,
        equity_samples=equity_samples,
        lockout_days=lockout_days,
        total_withdrawn=total_withdrawn if payout is not None else None,
        payout_count=payout_count if payout is not None else None,
        first_payout_day=first_payout_day if payout is not None else None,
    )


def _iid_trade_profile(
    log: TradeLog,
    boundary,
    rng: np.random.Generator,
    n_synth_days: int = 1000,
    days: list | None = None,
) -> DayProfile:
    if days is None:
        days = log.daily_groups(boundary)
    sizes = np.array([len(trades) for _, trades in days])
    all_trades = log.trades
    synth = []
    for _ in range(n_synth_days):
        n = int(sizes[rng.integers(len(sizes))])
        synth.append([all_trades[int(j)] for j in rng.integers(len(all_trades), size=n)])
    return DayProfile.from_day_lists(synth, log.has_excursions)


def run_monte_carlo(
    log: TradeLog, firm: FirmConfig, cfg: MCConfig | None = None
) -> MonteCarloReport:
    cfg = cfg or MCConfig()
    rng = np.random.default_rng(cfg.seed)
    boundary = firm.day_boundary.to_boundary()
    source_day_groups = log.daily_groups(boundary)  # single scan serves density + profile
    sessions_per_week = observed_sessions_per_week(log, boundary, days=source_day_groups)
    warnings: list[str] = []

    bootstrap_name: BootstrapName = cfg.bootstrap
    block_len_used = cfg.block_len  # resolved below only for the stationary scheme
    if bootstrap_name == "iid_trade":
        profile = _iid_trade_profile(log, boundary, rng, days=source_day_groups)
        sampler = make_bootstrapper("iid_day")
    else:
        profile = DayProfile.from_log(log, boundary, days=source_day_groups)
        if bootstrap_name == "stationary" and profile.n_days < MIN_DAYS_FOR_BLOCKS:
            warnings.append(
                f"only {profile.n_days} source trading days (<{MIN_DAYS_FOR_BLOCKS}): "
                "stationary block bootstrap degenerates — fell back to iid_day; "
                "treat results as low-confidence"
            )
            bootstrap_name = "iid_day"
        block_len_used = cfg.block_len
        if block_len_used is None and bootstrap_name == "stationary":
            # Politis-White automatic length from the day-PnL series'
            # actual autocorrelation (see bootstrap.optimal_block_length).
            block_len_used = optimal_block_length(profile.day_pnl)
        sampler = make_bootstrapper(bootstrap_name, block_len_used)

    if not profile.has_excursions:
        warnings.append(
            "trade log has no MAE/MFE columns: intraday-sensitive checks "
            "(intraday trailing, daily loss) run at trade-close fidelity and "
            "are OPTIMISTIC"
        )

    base_contracts = cfg.base_contracts
    if base_contracts is None:
        base_contracts = log.max_abs_quantity()
    return _run_from_profile(
        profile,
        firm,
        cfg,
        rng=rng,
        sampler=sampler,
        bootstrap_name=bootstrap_name,
        block_len_used=block_len_used,
        sessions_per_week=sessions_per_week,
        source_trades=len(log),
        warnings=warnings,
        base_contracts=base_contracts,
    )


def _firm_has_scaling(firm: FirmConfig) -> bool:
    return any(
        isinstance(spec, ScalingPlanSpec)
        for phase in [*firm.phases, firm.funded]
        for spec in phase.rules
    )


def _run_from_profile(
    profile: DayProfile,
    firm: FirmConfig,
    cfg: MCConfig,
    rng: np.random.Generator,
    sampler,
    bootstrap_name: str,
    block_len_used: int | None,
    sessions_per_week: float,
    source_trades: int,
    warnings: list[str],
    base_contracts: float | None = None,
) -> MonteCarloReport:
    """Simulation core once a DayProfile exists — run_monte_carlo's second
    half, split out so the sampling-uncertainty outer bootstrap can rerun
    the engine on row-gathered resamples of the profile without rescanning
    the trade log."""
    # The disclosure lives HERE (not in run_monte_carlo) so every entry
    # point that enforces a scaling plan with a log-derived base — regime
    # stress, the uncertainty band — carries it in its warnings. An
    # explicit cfg.base_contracts is a user-supplied fact, not an
    # assumption, so it draws no warning.
    if _firm_has_scaling(firm) and base_contracts is not None and cfg.base_contracts is None:
        warnings.append(
            f"scaling plan enforced assuming the log's max position "
            f"({base_contracts:g} contracts) IS the full allowance — pass "
            "--base-contracts if you traded below your limit"
        )
    challenge_scale = cfg.challenge_scale if cfg.challenge_scale is not None else cfg.scale
    funded_scale = cfg.funded_scale if cfg.funded_scale is not None else cfg.scale
    challenge_profile = profile.scaled(challenge_scale)
    funded_profile = profile.scaled(funded_scale)

    def _make_sizing(p: DayProfile) -> VolSizingParams | None:
        if cfg.sizing != "vol_target":
            if cfg.sizing not in ("fixed", "cushion"):
                raise QuantLabError(
                    f"unknown sizing mode {cfg.sizing!r}: choose fixed, vol_target, or cushion"
                )
            return None
        dp = p.day_pnl
        target = (
            cfg.vol_target
            if cfg.vol_target is not None
            else auto_target_vol(dp, lam=cfg.vol_lambda)
        )
        # Seed at target^2 so every path starts at weight exactly 1 and the
        # recursion takes over — seeding at the profile's unconditional RMS
        # would start every path systematically under-weighted whenever the
        # log is vol-clustered (RMS > median sigma), depressing the first
        # ~month of each phase below the documented median-weight-1 design.
        return VolSizingParams(
            lam=cfg.vol_lambda,
            target_vol=target,
            seed_var=target**2,
            clip_lo=cfg.vol_clip[0],
            clip_hi=cfg.vol_clip[1],
            burn_in=0,
        )

    challenge_sizing = _make_sizing(challenge_profile)
    funded_sizing = _make_sizing(funded_profile)
    cushion_clip = cfg.cushion_clip if cfg.sizing == "cushion" else None
    # A scale what-if means the trader runs scale x the log's positions,
    # so the scaling-plan conversion base scales WITH it: the firm caps
    # CONTRACTS, and effective contracts = phase_scale * weight * base.
    # Without this, `--scale 2` would quietly run twice the allowed size
    # through an enforced plan (and `--scale 0.5` would over-restrict).
    challenge_base = base_contracts * challenge_scale if base_contracts is not None else None
    funded_base = base_contracts * funded_scale if base_contracts is not None else None

    if cfg.payout_policy not in ("asap", "keep_buffer"):
        raise QuantLabError(
            f"unknown payout policy {cfg.payout_policy!r}: choose asap or keep_buffer"
        )
    keep_buffer = cfg.keep_buffer if cfg.payout_policy == "keep_buffer" else 0.0
    if keep_buffer < 0:
        raise QuantLabError(f"--keep-buffer must be >= 0 (got {keep_buffer})")
    if cfg.extract_weight is not None and not 0.0 < cfg.extract_weight <= 1.0:
        raise QuantLabError(
            f"--extract-weight must be in (0, 1] — extraction protects banked "
            f"qualifying days, it never levers up (got {cfg.extract_weight})"
        )

    if cfg.n_paths < 1:
        raise QuantLabError("n_paths must be >= 1")

    phase_outcomes: list[PhaseOutcome] = []
    for phase in firm.phases:
        idx = sampler.sample(profile.n_days, cfg.n_paths, cfg.challenge_horizon_days, rng)
        phase_outcomes.append(
            _simulate_phase(
                challenge_profile,
                idx,
                phase,
                firm,
                payout=None,
                sample_paths=cfg.sample_paths_kept,
                sessions_per_week=sessions_per_week,
                sizing=challenge_sizing,
                cushion_clip=cushion_clip,
                base_contracts=challenge_base,
            )
        )

    funded_gates = _resolve_rules(
        firm.funded, firm, firm.funded.resolved_initial(firm.account_size)
    ).payout_gate_pcts
    payout_params = _resolve_payout(
        firm,
        firm.funded.resolved_initial(firm.account_size),
        funded_gates,
        sessions_per_week,
        keep_buffer=keep_buffer,
    )
    idx = sampler.sample(profile.n_days, cfg.n_paths, cfg.funded_horizon_days, rng)
    funded_outcome = _simulate_phase(
        funded_profile,
        idx,
        firm.funded,
        firm,
        payout=payout_params,
        sample_paths=cfg.sample_paths_kept,
        sessions_per_week=sessions_per_week,
        sizing=funded_sizing,
        cushion_clip=cushion_clip,
        base_contracts=funded_base,
        extract_weight=cfg.extract_weight,
    )

    return summarize(
        firm=firm,
        phases=phase_outcomes,
        funded=funded_outcome,
        cfg=cfg,
        bootstrap_used=bootstrap_name,
        fidelity="mae_mfe" if profile.has_excursions else "trade_close",
        source_days=profile.n_days,
        source_trades=source_trades,
        scale_challenge=challenge_scale,
        scale_funded=funded_scale,
        warnings=warnings,
        sessions_per_week=sessions_per_week,
        block_len_used=block_len_used,
        base_contracts=base_contracts,
    )
