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

    trailing: TrailingDrawdownRule | None = None
    static: StaticMaxLossRule | None = None
    daily: DailyLossRule | None = None
    dll_fails = False
    for spec in phase.rules:
        if isinstance(spec, TrailingDrawdownSpec):
            trailing = TrailingDrawdownRule(spec, initial, firm.account_size)
        elif isinstance(spec, StaticMaxLossSpec):
            static = StaticMaxLossRule(spec, initial, firm.account_size)
        elif isinstance(spec, DailyLossLimitSpec):
            daily = DailyLossRule(spec, firm.account_size)
            dll_fails = spec.effect == "fail"

    points = sorted(curve.points, key=lambda p: p.time)
    base = points[0].equity
    sessions: set = set()
    first_breach: EquityBreach | None = None
    dll_hits: list[EquityBreach] = []
    current_session = None
    day_open = initial
    last_balance = initial
    dll_hit_today = False

    for point in points:
        balance = initial + (point.equity - base)
        session = boundary.session_date(point.time)
        if session != current_session:
            if trailing is not None and current_session is not None:
                trailing.day_close(last_balance)
            current_session = session
            sessions.add(session)
            day_open = last_balance
            dll_hit_today = False
            if daily is not None:
                daily.day_start(day_open)

        day_index = len(sessions) - 1
        if trailing is not None and first_breach is None:
            trailing.observe_high(balance)
            event = trailing.check(balance, session, day_index, -1)
            if event is not None:
                first_breach = _to_breach(event, point.time)
        if static is not None and first_breach is None:
            event = static.check(balance, session, day_index, -1)
            if event is not None:
                first_breach = _to_breach(event, point.time)
        # Guarded on first_breach like the hard rules: a QC equity curve
        # runs to the end of the backtest, but the account is already
        # liquidated after a hard breach — later daily-loss crossings
        # would be phantom activity.
        if daily is not None and first_breach is None and not dll_hit_today and daily.hit(balance):
            dll_hit_today = True
            hit = EquityBreach(
                rule="daily_loss_limit",
                when=point.time.isoformat(),
                balance=balance,
                threshold=daily.level,
                detail=f"balance {balance:,.2f} crossed day floor {daily.level:,.2f} "
                f"(day open {day_open:,.2f})",
            )
            dll_hits.append(hit)
            if dll_fails and first_breach is None:
                first_breach = hit
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
    if not result.intraday_marks:
        result.warnings.append(
            "equity chart is ~daily-sampled: intra-session excursions between "
            "marks remain invisible — this check tightens the trade-log verdict "
            "but is still an optimistic bound"
        )
    if trailing is None and static is None and daily is None:
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

    frame = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in frame.columns}
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
