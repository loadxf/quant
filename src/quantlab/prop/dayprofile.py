"""Per-day precomputed arrays that power the vectorized Monte Carlo engine.

For each source trading day we store, per trade slot i (padded to the max
trades/day K), the equity points RELATIVE TO THE DAY OPEN:

    low_rel[d, i]   = C_{i-1} + mae_i      (adverse extreme of trade i)
    high_rel[d, i]  = C_{i-1} + mfe_i      (favorable extreme)
    close_rel[d, i] = C_i                  (running cumulative at close)

where C_i is the cumulative day PnL after trade i. Padding slots are
no-ops: low=+inf (never breaches), high=-inf (never ratchets), close
repeats the day's final cumulative.

The within-trade point order is high -> low -> close, identical to the
deterministic evaluator (see rules/trailing_dd.py) — the Monte Carlo
engine replays these arrays trade-step by trade-step, which is what
makes exact scalar<->vector equivalence possible.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from quantlab.errors import QuantLabError
from quantlab.schema.trade import DayBoundary, Trade, TradeLog


def trade_points(trade: Trade, base: float) -> tuple[float, float, float]:
    """(high, low, close) equity for one trade at cumulative base `base`.

    MAE/MFE-refined when present; trade-close fidelity otherwise
    (documented as optimistic for intraday-sensitive rules). The low/high
    are clamped to include the close: platforms sometimes export MAE/MFE
    that excludes fees or the final tick, so a net PnL below the recorded
    MAE (or above the MFE) must still count — equity provably passed
    through the close.
    """
    if trade.mae is not None and trade.mfe is not None:
        low = base + min(trade.mae, trade.pnl)
        high = base + max(trade.mfe, trade.pnl)
    else:
        low = base + min(0.0, trade.pnl)
        high = base + max(0.0, trade.pnl)
    return high, low, base + trade.pnl


@dataclass
class DayProfile:
    """Padded (D, K) per-trade arrays + per-day aggregates."""

    low_rel: np.ndarray  # (D, K)
    high_rel: np.ndarray  # (D, K)
    close_rel: np.ndarray  # (D, K)
    n_trades: np.ndarray  # (D,) int
    day_pnl: np.ndarray  # (D,)
    has_excursions: bool

    @property
    def n_days(self) -> int:
        return int(self.low_rel.shape[0])

    def scaled(self, factor: float) -> DayProfile:
        """PnL-scaled copy (position-sizing what-ifs). factor must be > 0;
        +/-inf padding survives scaling unchanged."""
        if factor == 1.0:
            return self
        return DayProfile(
            low_rel=self.low_rel * factor,
            high_rel=self.high_rel * factor,
            close_rel=self.close_rel * factor,
            n_trades=self.n_trades,
            day_pnl=self.day_pnl * factor,
            has_excursions=self.has_excursions,
        )

    @property
    def max_trades(self) -> int:
        return int(self.low_rel.shape[1])

    def gather(self, idx: np.ndarray) -> DayProfile:
        """Row-gathered copy along the day axis (bootstrap resamples,
        regime-conditioned subsets)."""
        return DayProfile(
            low_rel=self.low_rel[idx],
            high_rel=self.high_rel[idx],
            close_rel=self.close_rel[idx],
            n_trades=self.n_trades[idx],
            day_pnl=self.day_pnl[idx],
            has_excursions=self.has_excursions,
        )

    @classmethod
    def from_log(cls, log: TradeLog, boundary: DayBoundary, days: list | None = None) -> DayProfile:
        if days is None:
            days = log.daily_groups(boundary)
        if not days:
            raise QuantLabError("Trade log has no trading days")
        return cls.from_day_lists([trades for _, trades in days], log.has_excursions)

    @classmethod
    def from_day_lists(cls, day_lists: list[list[Trade]], has_excursions: bool) -> DayProfile:
        n_days = len(day_lists)
        k = max(len(trades) for trades in day_lists)
        low = np.full((n_days, k), np.inf)
        high = np.full((n_days, k), -np.inf)
        close = np.zeros((n_days, k))
        n_trades = np.zeros(n_days, dtype=np.int64)
        for d, trades in enumerate(day_lists):
            cum = 0.0
            for i, trade in enumerate(trades):
                h, lo, c = trade_points(trade, cum)
                high[d, i] = h
                low[d, i] = lo
                cum = c
                close[d, i] = cum
            n_trades[d] = len(trades)
            close[d, len(trades) :] = cum  # padding repeats the final cumulative
        return cls(
            low_rel=low,
            high_rel=high,
            close_rel=close,
            n_trades=n_trades,
            day_pnl=close[:, -1].copy(),
            has_excursions=has_excursions,
        )
