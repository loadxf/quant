"""Mark-to-market fidelity cross-check from a true equity curve.

A trade log only shows equity at fills (plus MAE/MFE when exported), so
the evaluator's intraday-sensitive checks are OPTIMISTIC between trade
points — the standing fidelity warning. A QuantConnect backtest also
ships the Strategy-Equity chart: genuine mark-to-market equity including
open-position P&L between fills. This module replays the SAME scalar
rule objects the deterministic evaluator uses (TrailingDrawdownRule,
StaticMaxLossRule, DailyLossRule — identical semantics by construction)
over those marks, so "would the real equity path have breached?" gets a
quantitative answer instead of a caveat.

Scope: equity-path rules only (trailing drawdown, static max loss,
daily loss). Trade-count rules (consistency, min days, time limits,
profit targets) need fills, which the trade-log evaluator already
handles at full fidelity. The curve's own resolution bounds the check:
daily-sampled charts still miss intra-bar excursions (reported).

Lockout caveat: a rule-free backtest keeps trading through a daily-loss
lockout the ruled account would have sat out. The locked remainder of
that session is ignored (phantom under the rules), but LATER sessions
replay the raw curve — the ruled account's balances would have diverged
at the lockout, so results after a locked session are indicative, not
exact (a warning says so).

Alignment convention: the curve's first mark is the backtest's starting
capital, mapped to the phase's initial balance — balance_t = initial +
(equity_t - equity_0). A session's opening balance is the prior
session's final mark (the engine's day-open convention).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from quantlab.errors import QuantLabError
from quantlab.prop.config import (
    DailyLossLimitSpec,
    FirmConfig,
    StaticMaxLossSpec,
    TrailingDrawdownSpec,
)
from quantlab.prop.rules.daily_loss import DailyLossRule
from quantlab.prop.rules.static_loss import StaticMaxLossRule
from quantlab.prop.rules.trailing_dd import TrailingDrawdownRule
from quantlab.schema.equity import EquityCurve


@dataclass(frozen=True, slots=True)
class EquityBreach:
    rule: str
    when: str  # ISO timestamp of the breaching mark
    balance: float
    threshold: float
    detail: str


@dataclass
class EquityCheckResult:
    phase: str
    n_marks: int
    n_sessions: int
    intraday_marks: bool  # more than one mark per session on average
    first_breach: EquityBreach | None = None
    daily_loss_hits: list[EquityBreach] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict:
        return dataclasses.asdict(self)


def check_equity_curve(
    curve: EquityCurve, firm: FirmConfig, phase_name: str | None = None
) -> EquityCheckResult:
    """Replay trailing/static/daily-loss rules over mark-to-market equity.

    Returns the first hard breach (trailing/static, or daily-loss when the
    firm fails rather than locks out) plus every daily-loss crossing."""
    if not curve.points:
        raise QuantLabError("equity curve has no points")
    phases = {p.name: p for p in firm.phases} | {firm.funded.name: firm.funded}
    name = phase_name or firm.phases[0].name
    if name not in phases:
        raise QuantLabError(f"unknown phase {name!r}: choose from {sorted(phases)}")
    phase = phases[name]
    initial = phase.resolved_initial(firm.account_size)
    boundary = firm.day_boundary.to_boundary()

    # Rule LISTS, exactly like the evaluator: a phase may carry several
    # rules of one type (two trailing floors, fail + lockout daily loss),
    # and every one must be replayed — keeping only the last silently
    # misses real breaches.
    trailing: list[TrailingDrawdownRule] = []
    static: list[StaticMaxLossRule] = []
    daily: list[tuple[DailyLossRule, bool]] = []  # (rule, fails_account)
    for spec in phase.rules:
        if isinstance(spec, TrailingDrawdownSpec):
            trailing.append(TrailingDrawdownRule(spec, initial, firm.account_size))
        elif isinstance(spec, StaticMaxLossSpec):
            static.append(StaticMaxLossRule(spec, initial, firm.account_size))
        elif isinstance(spec, DailyLossLimitSpec):
            daily.append((DailyLossRule(spec, firm.account_size), spec.effect == "fail"))

    points = sorted(curve.points, key=lambda p: p.time)
    base = points[0].equity
    sessions: set = set()
    first_breach: EquityBreach | None = None
    dll_hits: list[EquityBreach] = []
    current_session = None
    day_open = initial
    last_balance = initial
    dll_hit_today: set[int] = set()
    locked_today = False
    locked_sessions = 0

    for point in points:
        balance = initial + (point.equity - base)
        session = boundary.session_date(point.time)
        if session != current_session:
            if current_session is not None:
                for tr_rule in trailing:
                    tr_rule.day_close(last_balance)
            current_session = session
            sessions.add(session)
            day_open = last_balance
            dll_hit_today.clear()
            locked_today = False
            for dl_rule, _ in daily:
                dl_rule.day_start(day_open)

        day_index = len(sessions) - 1
        # After a hard breach the account is liquidated (later marks are
        # phantom); after a lockout the rest of THIS session is phantom —
        # the firm flattened the account at the lockout level, so equity
        # below it never happened under the rules.
        if first_breach is None and not locked_today:
            # First-hit resolution at the mark, matching the evaluator:
            # equity descends, so among all levels crossed the HIGHEST
            # fired first; a fail rule beats a lockout on exact ties.
            fail_hits: list[EquityBreach] = []
            for tr_rule in trailing:
                tr_rule.observe_high(balance)
                event = tr_rule.check(balance, session, day_index, -1)
                if event is not None:
                    fail_hits.append(_to_breach(event, point.time))
            for st_rule in static:
                event = st_rule.check(balance, session, day_index, -1)
                if event is not None:
                    fail_hits.append(_to_breach(event, point.time))
            lock_hits: list[EquityBreach] = []
            for k, (dl_rule, fails) in enumerate(daily):
                if k in dll_hit_today or not dl_rule.hit(balance):
                    continue
                dll_hit_today.add(k)
                hit = EquityBreach(
                    rule="daily_loss_limit",
                    when=point.time.isoformat(),
                    balance=balance,
                    threshold=dl_rule.level,
                    detail=(
                        f"balance {balance:,.2f} crossed day floor "
                        f"{dl_rule.level:,.2f} (day open {day_open:,.2f})"
                    ),
                )
                dll_hits.append(hit)
                (fail_hits if fails else lock_hits).append(hit)
            best_fail = max(fail_hits, key=lambda b: b.threshold, default=None)
            best_lock = max(lock_hits, key=lambda b: b.threshold, default=None)
            if best_fail is not None and (
                best_lock is None or best_fail.threshold >= best_lock.threshold
            ):
                first_breach = best_fail
            elif best_lock is not None:
                locked_today = True
                locked_sessions += 1
        last_balance = balance

    n_sessions = len(sessions)
    result = EquityCheckResult(
        phase=name,
        n_marks=len(points),
        n_sessions=n_sessions,
        intraday_marks=len(points) > 1.5 * max(n_sessions, 1),
        first_breach=first_breach,
        daily_loss_hits=dll_hits,
    )
    if locked_sessions:
        result.warnings.append(
            f"the curve kept trading through {locked_sessions} locked-out "
            "session(s) the ruled account would have sat out — rule state "
            "after those sessions is approximate; treat later results as "
            "indicative, not exact"
        )
    if not result.intraday_marks:
        result.warnings.append(
            "equity chart is ~daily-sampled: intra-session excursions between "
            "marks remain invisible — this check tightens the trade-log verdict "
            "but is still an optimistic bound"
        )
    if not trailing and not static and not daily:
        result.warnings.append(f"phase {name!r} has no equity-path rules to check")
    return result


def _to_breach(event, when) -> EquityBreach:
    return EquityBreach(
        rule=event.rule,
        when=when.isoformat(),
        balance=event.equity,
        threshold=event.threshold,
        detail=event.detail,
    )


def load_equity_csv(path) -> EquityCurve:
    """Read the datetime,equity CSV that `quant cloud results --chart` writes."""
    import pandas as pd

    try:
        frame = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        raise QuantLabError(f"{path}: file is empty") from None
    except pd.errors.ParserError as exc:
        raise QuantLabError(f"{path}: not a readable CSV ({exc})") from None
    cols: dict[str, str] = {}
    for c in frame.columns:  # first-wins on duplicate-normalizing headers
        cols.setdefault(str(c).lower().strip(), str(c))
    if "datetime" not in cols or "equity" not in cols:
        raise QuantLabError(
            f"{path}: expected datetime,equity columns (from `quant cloud results --chart`)"
        )
    stamps = pd.to_datetime(frame[cols["datetime"]], utc=True, errors="coerce")
    values = pd.to_numeric(frame[cols["equity"]], errors="coerce")
    keep = stamps.notna() & values.notna()
    if not keep.any():
        raise QuantLabError(f"{path}: no readable equity marks")
    series = pd.Series(values[keep].to_numpy(), index=pd.DatetimeIndex(stamps[keep]))
    return EquityCurve.from_series(series.sort_index())
