"""Per-day precomputed arrays that power the vectorized Monte Carlo engine.

For each source trading day we store, per trade slot i (padded to the max
trades/day K), the equity points RELATIVE TO THE DAY OPEN:

    low_rel[d, i]   = C_{i-1} + mae_i      (adverse extreme of trade i)
    high_rel[d, i]  = C_{i-1} + mfe_i      (favorable extreme)
    close_rel[d, i] = C_i                  (running cumulative at close)

where C_i is the cumulative day PnL after trade i. Padding slots are
no-ops: low=+inf (never breaches), high=-inf (never ratchets), close
repeats the day's final cumulative.

The within-trade point order is normally high -> low -> close. When an
export provides MAE but no MFE, however, inventing a pre-MAE favorable
extreme from the profitable close is wrong: the only defensible chronology
is entry -> MAE -> close. ``low_first`` records that distinction so both
engines replay the same evidence-backed path.
"""

from __future__ import annotations

import math
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
    close = base + trade.pnl
    # A missing excursion is not evidence that equity revisited the entry
    # level. Falling back to the close preserves genuine trade-close
    # fidelity instead of inventing a high->entry->close path for winners.
    low = base + min(trade.mae, trade.pnl) if trade.mae is not None else close
    high = base + max(trade.mfe, trade.pnl) if trade.mfe is not None else close
    return high, low, close


def trade_low_first(trade: Trade) -> bool:
    """Return whether the recorded path must visit its low before its high.

    MAE-only data proves an adverse point occurred and provides no favorable
    point before it. The close is therefore visited last. With both
    excursions present their ordering is unknowable, so high-first remains
    the conservative assumption for trailing-drawdown rules.
    """
    return trade.mae is not None and trade.mfe is None


@dataclass
class DayProfile:
    """Padded (D, K) per-trade arrays + per-day aggregates."""

    low_rel: np.ndarray  # (D, K)
    high_rel: np.ndarray  # (D, K)
    close_rel: np.ndarray  # (D, K)
    low_first: np.ndarray  # (D, K) bool; MAE-only trades visit low first
    n_trades: np.ndarray  # (D,) int
    day_pnl: np.ndarray  # (D,)
    has_excursions: bool
    excursion_fidelity: str = "close-only"

    @property
    def n_days(self) -> int:
        return int(self.low_rel.shape[0])

    def scaled(self, factor: float) -> DayProfile:
        """PnL-scaled copy (position-sizing what-ifs). factor must be > 0;
        +/-inf padding survives scaling unchanged."""
        if not math.isfinite(factor) or factor <= 0:
            raise QuantLabError(f"scale factor must be finite and positive (got {factor})")
        if factor == 1.0:
            return self
        return DayProfile(
            low_rel=self.low_rel * factor,
            high_rel=self.high_rel * factor,
            close_rel=self.close_rel * factor,
            low_first=self.low_first,
            n_trades=self.n_trades,
            day_pnl=self.day_pnl * factor,
            has_excursions=self.has_excursions,
            excursion_fidelity=self.excursion_fidelity,
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
            low_first=self.low_first[idx],
            n_trades=self.n_trades[idx],
            day_pnl=self.day_pnl[idx],
            has_excursions=self.has_excursions,
            excursion_fidelity=self.excursion_fidelity,
        )

    @classmethod
    def from_log(cls, log: TradeLog, boundary: DayBoundary, days: list | None = None) -> DayProfile:
        if days is None:
            days = log.daily_groups(boundary)
        if not days:
            raise QuantLabError("Trade log has no trading days")
        return cls.from_day_lists(
            [trades for _, trades in days],
            log.has_excursions,
            excursion_fidelity=log.excursion_fidelity,
        )

    @classmethod
    def from_day_lists(
        cls,
        day_lists: list[list[Trade]],
        has_excursions: bool,
        excursion_fidelity: str | None = None,
    ) -> DayProfile:
        if not day_lists or any(not trades for trades in day_lists):
            raise QuantLabError("DayProfile requires at least one trade in every source day")
        n_days = len(day_lists)
        k = max(len(trades) for trades in day_lists)
        low = np.full((n_days, k), np.inf)
        high = np.full((n_days, k), -np.inf)
        close = np.zeros((n_days, k))
        low_first = np.zeros((n_days, k), dtype=bool)
        n_trades = np.zeros(n_days, dtype=np.int64)
        for d, trades in enumerate(day_lists):
            cum = 0.0
            for i, trade in enumerate(trades):
                h, lo, c = trade_points(trade, cum)
                high[d, i] = h
                low[d, i] = lo
                cum = c
                close[d, i] = cum
                low_first[d, i] = trade_low_first(trade)
            n_trades[d] = len(trades)
            close[d, len(trades) :] = cum  # padding repeats the final cumulative
        return cls(
            low_rel=low,
            high_rel=high,
            close_rel=close,
            low_first=low_first,
            n_trades=n_trades,
            day_pnl=close[:, -1].copy(),
            has_excursions=has_excursions,
            excursion_fidelity=excursion_fidelity or ("full" if has_excursions else "close-only"),
        )
