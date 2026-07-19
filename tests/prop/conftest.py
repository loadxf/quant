"""Helpers for prop-engine tests: build firms + trade logs with exact excursions."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from zoneinfo import ZoneInfo

from quantlab.prop.config import FirmConfig, PhaseConfig
from quantlab.schema.trade import Side, Trade, TradeLog

CT = ZoneInfo("America/Chicago")
BASE_DAY = dt.date(2026, 1, 5)  # Monday


def make_firm(
    challenge_rules: Sequence[dict],
    target: float | None = 3_000,
    size: float = 50_000,
    funded_rules: Sequence[dict] = (),
    funded_initial: float | None = None,
    phases: Sequence[PhaseConfig] | None = None,
    day_boundary: dict | None = None,
) -> FirmConfig:
    if phases is None:
        assert target is not None
        phases = [PhaseConfig(name="challenge", profit_target=target, rules=list(challenge_rules))]
    return FirmConfig.model_validate(
        {
            "name": "testfirm",
            "account_size": size,
            "phases": [p if isinstance(p, dict) else p.model_dump() for p in phases],
            "funded": {
                "name": "funded",
                "initial_balance": funded_initial,
                "rules": list(funded_rules),
            },
            **({"day_boundary": day_boundary} if day_boundary else {}),
        }
    )


def day_trades(
    daily: Sequence[Sequence[tuple[float, float | None, float | None]]],
) -> TradeLog:
    """Build a log from per-day lists of (pnl, mae, mfe) tuples.

    Trades land at 09:00 + k*30min CT on consecutive weekdays.
    mae/mfe of None means no excursion data for that trade.
    """
    trades: list[Trade] = []
    date = BASE_DAY
    for day in daily:
        while date.weekday() >= 5:
            date += dt.timedelta(days=1)
        for k, (pnl, mae, mfe) in enumerate(day):
            entry = dt.datetime.combine(date, dt.time(9, 0), tzinfo=CT) + dt.timedelta(
                minutes=30 * k
            )
            trades.append(
                Trade(
                    entry_time=entry,
                    exit_time=entry + dt.timedelta(minutes=20),
                    symbol="MNQ",
                    side=Side.LONG,
                    quantity=1,
                    pnl=pnl,
                    mae=mae,
                    mfe=mfe,
                )
            )
        date += dt.timedelta(days=1)
    return TradeLog(trades=trades, source="synthetic")


def simple(pnl: float) -> tuple[float, float | None, float | None]:
    """Trade with excursions equal to its PnL extremes (no intraday noise)."""
    return (pnl, min(0.0, pnl), max(0.0, pnl))
