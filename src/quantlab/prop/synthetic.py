"""Synthetic Bernoulli trade logs for risk-geometry exploration.

Library-grade simulation infrastructure (the statistical anchor tests
build on it) — kept out of the CLI layer.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import numpy as np

from quantlab.schema.trade import Side, Trade, TradeLog


@dataclass(frozen=True, slots=True)
class GeometrySpec:
    """Resolved synthetic geometry, including any EV-reconciliation shift."""

    win_size: float  # signed PnL of a winning trade (after shift)
    loss_size: float  # signed PnL of a losing trade (after shift)
    shift: float  # ev - implied EV of (win_rate, rr, risk); 0 when consistent

    @property
    def distorted(self) -> bool:
        """True when the requested EV materially reshapes the geometry
        (the shift exceeds 1% of the nominal risk)."""
        nominal_risk = abs(self.loss_size - self.shift)
        return nominal_risk > 0 and abs(self.shift) > 0.01 * nominal_risk


def resolve_geometry(win_rate: float, rr: float, risk: float, ev: float) -> GeometrySpec:
    implied = risk * (win_rate * rr - (1 - win_rate))
    shift = ev - implied
    return GeometrySpec(win_size=rr * risk + shift, loss_size=-risk + shift, shift=shift)


def synthetic_geometry_log(
    win_rate: float,
    rr: float,
    trades_per_day: int,
    risk: float,
    ev: float,
    days: int,
    seed: int,
) -> TradeLog:
    """Bernoulli strategy: win = +rr*risk + shift, loss = -risk + shift.

    The sample is built with EXACT win counts and demeaned so its realized
    per-trade mean equals `ev` exactly — bootstrapping resamples this log,
    so any sampling drift in a naive finite sample would otherwise swamp
    the geometry effect (a +7/trade accident compounds to thousands over a
    challenge horizon).

    When (win_rate, rr, risk) imply a different EV than requested, the
    shift changes the effective win/loss sizes — check
    resolve_geometry(...).distorted and surface it to the user.

    Trades carry NO MAE/MFE: intra-trade excursions of a synthetic
    bracket trade are unknown (a winner may draw down to nearly -risk
    before hitting its target), so results run at trade-close fidelity
    and the optimism warning stays visible.
    """
    rng = np.random.default_rng(seed)
    n_total = days * trades_per_day
    n_wins = round(win_rate * n_total)
    geometry = resolve_geometry(win_rate, rr, risk, ev)
    pnls = np.concatenate(
        [np.full(n_wins, geometry.win_size), np.full(n_total - n_wins, geometry.loss_size)]
    )
    pnls = rng.permutation(pnls)
    pnls += ev - pnls.mean()  # zero out the exact-count rounding residual
    ct = ZoneInfo("America/Chicago")
    date = dt.date(2026, 1, 5)
    trades: list[Trade] = []
    for day in range(days):
        while date.weekday() >= 5:
            date += dt.timedelta(days=1)
        for k in range(trades_per_day):
            pnl = float(pnls[day * trades_per_day + k])
            entry = dt.datetime.combine(date, dt.time(9, 0), tzinfo=ct) + dt.timedelta(
                minutes=15 * k
            )
            trades.append(
                Trade(
                    entry_time=entry,
                    exit_time=entry + dt.timedelta(minutes=10),
                    symbol="SYN",
                    side=Side.LONG,
                    quantity=1,
                    pnl=pnl,
                )
            )
        date += dt.timedelta(days=1)
    return TradeLog(trades=trades, source="synthetic")
