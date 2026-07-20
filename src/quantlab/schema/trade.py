"""Canonical trade schema.

Every layer (ingestion, LEAN results, prop-firm engine, metrics, reporting)
consumes `Trade` / `TradeLog`. All datetimes are tz-aware UTC internally.
`pnl` is NET profit/loss in account currency (after commissions/fees).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from zoneinfo import ZoneInfo

import pandas as pd

from quantlab.errors import QuantLabError

UTC = dt.UTC


class Side(StrEnum):
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True, slots=True)
class Trade:
    entry_time: dt.datetime
    exit_time: dt.datetime
    symbol: str
    side: Side
    quantity: float  # contracts/shares, positive
    pnl: float  # NET P&L in account currency
    entry_price: float | None = None
    exit_price: float | None = None
    fees: float = 0.0  # informational; pnl is already net
    mae: float | None = None  # max adverse excursion in $, <= 0
    mfe: float | None = None  # max favorable excursion in $, >= 0

    def __post_init__(self) -> None:
        for name in ("entry_time", "exit_time"):
            value: dt.datetime = getattr(self, name)
            if value.tzinfo is None:
                raise QuantLabError(f"Trade.{name} must be tz-aware (got naive {value!r})")
            # Normalize to UTC so the "UTC internally" contract actually holds.
            object.__setattr__(self, name, value.astimezone(UTC))
        if self.exit_time < self.entry_time:
            raise QuantLabError(
                f"Trade exit_time {self.exit_time} precedes entry_time {self.entry_time}"
            )
        if self.quantity <= 0:
            raise QuantLabError(f"Trade.quantity must be positive (got {self.quantity})")
        if self.mae is not None and self.mae > 0:
            raise QuantLabError(f"Trade.mae must be <= 0 (got {self.mae})")
        if self.mfe is not None and self.mfe < 0:
            raise QuantLabError(f"Trade.mfe must be >= 0 (got {self.mfe})")


@dataclass(frozen=True, slots=True)
class DayBoundary:
    """Defines when one trading day ends and the next begins.

    Futures firms (Topstep/Apex/TPT) roll at 17:00 America/Chicago.
    FTMO's daily loss resets at midnight Prague (CE/CEST).
    """

    tz: str = "America/Chicago"
    cutoff_hour: int = 17  # 0 => midnight boundary

    def session_date(self, when: dt.datetime) -> dt.date:
        """Trading-day date a timestamp belongs to.

        With a 17:00 cutoff, 18:00 Monday belongs to Tuesday's session
        (shift forward by 24 - cutoff hours, then take the local date).
        """
        local = when.astimezone(ZoneInfo(self.tz))
        if self.cutoff_hour == 0:
            return local.date()
        shifted = local + dt.timedelta(hours=24 - self.cutoff_hour)
        return shifted.date()


FUTURES_DAY = DayBoundary("America/Chicago", 17)
FTMO_DAY = DayBoundary("Europe/Prague", 0)


@dataclass
class TradeLog:
    """An ordered (by exit_time) sequence of trades plus provenance metadata."""

    trades: list[Trade]
    account_currency: str = "USD"
    source: str = "csv"  # csv | lean-cloud | synthetic

    def __post_init__(self) -> None:
        self.trades = sorted(self.trades, key=lambda t: (t.exit_time, t.entry_time))

    def __len__(self) -> int:
        return len(self.trades)

    def __iter__(self) -> Iterable[Trade]:  # pragma: no cover - trivial
        return iter(self.trades)

    @property
    def has_excursions(self) -> bool:
        """True when every trade carries MAE/MFE (intraday-refined fidelity)."""
        return bool(self.trades) and all(
            t.mae is not None and t.mfe is not None for t in self.trades
        )

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "entry_time": [t.entry_time for t in self.trades],
                "exit_time": [t.exit_time for t in self.trades],
                "symbol": [t.symbol for t in self.trades],
                "side": [t.side.value for t in self.trades],
                "quantity": [t.quantity for t in self.trades],
                "pnl": [t.pnl for t in self.trades],
                "entry_price": [t.entry_price for t in self.trades],
                "exit_price": [t.exit_price for t in self.trades],
                "fees": [t.fees for t in self.trades],
                "mae": [t.mae for t in self.trades],
                "mfe": [t.mfe for t in self.trades],
            }
        )

    def daily_groups(
        self, boundary: DayBoundary = FUTURES_DAY
    ) -> list[tuple[dt.date, list[Trade]]]:
        """Group trades into trading days (by exit_time), in chronological order."""
        groups: dict[dt.date, list[Trade]] = {}
        for trade in self.trades:
            groups.setdefault(boundary.session_date(trade.exit_time), []).append(trade)
        return sorted(groups.items())

    def daily_pnl(
        self,
        boundary: DayBoundary = FUTURES_DAY,
        days: list[tuple[dt.date, list[Trade]]] | None = None,
    ) -> np.ndarray:
        """Per-trading-day net PnL, chronological — THE single definition
        of "a day's PnL" (clustering tests, sizing weights, and headline
        metrics must never disagree about this series). Pass `days` to
        reuse an existing daily_groups result."""
        import numpy as np

        if days is None:
            days = self.daily_groups(boundary)
        return np.array([sum(t.pnl for t in trades) for _, trades in days], dtype=float)

    def max_abs_quantity(self) -> float | None:
        """Largest absolute position in the log — the scaling-plan
        contracts->weight conversion base (None if no quantities)."""
        quantities = [abs(t.quantity) for t in self.trades if t.quantity]
        return max(quantities) if quantities else None
