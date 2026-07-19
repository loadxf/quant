"""Equity curve derived from a trade log (stepwise at trade exits)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from quantlab.schema.trade import TradeLog


@dataclass(frozen=True, slots=True)
class EquityPoint:
    time: dt.datetime
    equity: float


@dataclass
class EquityCurve:
    points: list[EquityPoint]

    @classmethod
    def from_trades(cls, log: TradeLog, starting_equity: float) -> EquityCurve:
        equity = starting_equity
        points: list[EquityPoint] = []
        for trade in log.trades:
            equity += trade.pnl
            points.append(EquityPoint(trade.exit_time, equity))
        return cls(points)

    @classmethod
    def from_series(cls, series: pd.Series) -> EquityCurve:
        stamps = pd.DatetimeIndex(series.index)
        return cls(
            [
                EquityPoint(ts.to_pydatetime(), float(v))
                for ts, v in zip(stamps, series.to_numpy(), strict=True)
            ]
        )

    def to_series(self) -> pd.Series:
        if not self.points:
            return pd.Series(dtype=float)
        return pd.Series(
            [p.equity for p in self.points],
            index=pd.DatetimeIndex([p.time for p in self.points]),
            name="equity",
        )

    def daily(self) -> pd.Series:
        """End-of-day equity series (last observation per UTC calendar day)."""
        series = self.to_series()
        if series.empty:
            return series
        return series.resample("1D").last().dropna()
