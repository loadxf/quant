"""Equity curve derived from a trade log (stepwise at trade exits)."""

from __future__ import annotations

import datetime as dt
import math
import numbers
from dataclasses import dataclass

import pandas as pd

from quantlab.errors import QuantLabError


@dataclass(frozen=True, slots=True)
class EquityPoint:
    time: dt.datetime
    equity: float

    def __post_init__(self) -> None:
        if not isinstance(self.time, dt.datetime):
            raise QuantLabError(f"EquityPoint.time must be a datetime (got {self.time!r})")
        if self.time.tzinfo is None:
            raise QuantLabError("EquityPoint.time must be timezone-aware")
        if (
            not isinstance(self.equity, numbers.Real)
            or isinstance(self.equity, bool)
            or not math.isfinite(float(self.equity))
        ):
            raise QuantLabError(
                f"EquityPoint.equity must be a finite real number (got {self.equity!r})"
            )
        object.__setattr__(self, "time", self.time.astimezone(dt.UTC))
        object.__setattr__(self, "equity", float(self.equity))


@dataclass
class EquityCurve:
    points: list[EquityPoint]

    def __post_init__(self) -> None:
        self.points = sorted(self.points, key=lambda point: point.time)

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
        """End-of-day equity series: last observation per calendar day in the
        series' own timezone (UTC for curves built from canonical trades).

        Used for Sharpe/Sortino context only — prop-firm rules use the
        firm-specific `DayBoundary` session grouping instead.
        """
        series = self.to_series()
        if series.empty:
            return series
        return series.resample("1D").last().dropna()
