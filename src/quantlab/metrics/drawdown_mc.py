"""Trade-order permutation Monte Carlo for drawdown distributions.

The retail-standard method (Kevin Davey's "trades in a hat"): shuffle
the EXISTING trades' order without replacement, so every path has the
identical total PnL and only the sequencing varies — isolating path
risk. Standard outputs: median and 95th-percentile max drawdown, and
P(ruin) at a fixed starting capital (cumulative PnL touching -capital).

Caveat surfaced everywhere this is shown: permutation ASSUMES trades
are independent — it destroys win/loss streaks, understating drawdowns
for streaky strategies (check DecayPanel.runs). The prop-firm Monte
Carlo's stationary block bootstrap is the streak-preserving
counterpart; the report shows both, labeled.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from quantlab.errors import QuantLabError
from quantlab.schema.trade import TradeLog


@dataclass(frozen=True, slots=True)
class DrawdownMC:
    n_iter: int
    median_max_dd: float
    p95_max_dd: float
    ruin_capital: float | None
    p_ruin: float | None  # P(cumulative PnL <= -ruin_capital at any point)


def permutation_drawdown(
    log: TradeLog,
    n_iter: int = 5000,
    seed: int | None = 42,
    ruin_capital: float | None = None,
) -> DrawdownMC:
    if n_iter < 1:
        raise QuantLabError(f"n_iter must be >= 1 (got {n_iter})")
    if ruin_capital is not None and (not np.isfinite(ruin_capital) or ruin_capital <= 0):
        raise QuantLabError("ruin_capital must be finite and positive")
    pnls = np.array([t.pnl for t in log.trades], dtype=float)
    n = pnls.size
    if n < 2:
        return DrawdownMC(0, 0.0, 0.0, ruin_capital, None if ruin_capital is None else 0.0)
    rng = np.random.default_rng(seed)
    # Vectorized permutations (argsort of random keys), CHUNKED: one big
    # (n_iter, n) batch holds ~5 simultaneous arrays — ~2.5 GB for a
    # 10k-trade log — where 512-path chunks bound peak memory and, because
    # the generator stream is consumed in the same order, produce
    # bit-identical results for a given seed.
    chunk = max(1, min(512, 2_000_000 // n))
    max_dd_parts: list[np.ndarray] = []
    ruin_hits = 0
    for start in range(0, n_iter, chunk):
        rows = min(chunk, n_iter - start)
        order = np.argsort(rng.random((rows, n)), axis=1)
        equity = np.cumsum(pnls[order], axis=1)
        peaks = np.maximum.accumulate(np.maximum(equity, 0.0), axis=1)  # peak incl. start=0
        max_dd_parts.append(np.max(peaks - equity, axis=1))
        if ruin_capital is not None:
            ruin_hits += int(np.sum(np.min(equity, axis=1) <= -ruin_capital))
    max_dd = np.concatenate(max_dd_parts)
    p_ruin: float | None = None
    if ruin_capital is not None:
        p_ruin = ruin_hits / n_iter
    return DrawdownMC(
        n_iter=n_iter,
        median_max_dd=float(np.median(max_dd)),
        p95_max_dd=float(np.percentile(max_dd, 95)),
        ruin_capital=ruin_capital,
        p_ruin=p_ruin,
    )
