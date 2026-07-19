"""Shared fixtures: synthetic trade logs with controllable day structure."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from quantlab.schema.trade import Side, Trade, TradeLog

CT = ZoneInfo("America/Chicago")
BASE_DAY = dt.date(2026, 1, 5)  # a Monday


def _nth_weekday(n: int) -> dt.date:
    """n-th trading day (weekdays only) starting from BASE_DAY."""
    day = BASE_DAY
    remaining = n
    while remaining > 0:
        day += dt.timedelta(days=1)
        if day.weekday() < 5:
            remaining -= 1
    return day


def trades_from_daily(
    daily_pnls: Sequence[Sequence[float]],
    with_excursions: bool = False,
    symbol: str = "MNQ",
) -> TradeLog:
    """Build a TradeLog from per-day lists of trade PnLs.

    Trades land inside RTH (09:00 + k*30min CT) on consecutive weekdays,
    so futures session grouping maps day i -> daily_pnls[i] exactly.
    """
    trades: list[Trade] = []
    for day_index, pnls in enumerate(daily_pnls):
        date = _nth_weekday(day_index)
        for trade_index, pnl in enumerate(pnls):
            entry = dt.datetime.combine(date, dt.time(9, 0), tzinfo=CT) + dt.timedelta(
                minutes=30 * trade_index
            )
            trades.append(
                Trade(
                    entry_time=entry,
                    exit_time=entry + dt.timedelta(minutes=20),
                    symbol=symbol,
                    side=Side.LONG,
                    quantity=1,
                    pnl=float(pnl),
                    mae=min(float(pnl), 0.0) if with_excursions else None,
                    mfe=max(float(pnl), 0.0) if with_excursions else None,
                )
            )
    return TradeLog(trades=trades, source="synthetic")


def random_log(
    n_days: int = 120,
    trades_per_day: int = 4,
    mean: float = 15.0,
    std: float = 180.0,
    seed: int = 0,
    with_excursions: bool = False,
) -> TradeLog:
    rng = np.random.default_rng(seed)
    daily = [list(np.round(rng.normal(mean, std, size=trades_per_day), 2)) for _ in range(n_days)]
    return trades_from_daily(daily, with_excursions=with_excursions)


@pytest.fixture
def winner_log() -> TradeLog:
    return random_log(n_days=120, mean=40.0, std=150.0, seed=1)


@pytest.fixture
def loser_log() -> TradeLog:
    return random_log(n_days=120, mean=-40.0, std=150.0, seed=2)


@pytest.fixture
def marginal_log() -> TradeLog:
    return random_log(n_days=150, mean=5.0, std=200.0, seed=3)
