"""Combinatorial subperiod-stability analysis.

The date range is cut into ``n_blocks`` contiguous blocks; every combination
of ``n_test`` blocks forms one path's test set. This adaptation SCORES an
already-computed self-financing return series inside each path's test blocks —
no model is re-fit per path, so the train/test estimation split of full CPCV
does not apply. What remains of purging/embargo in this setting is
boundary decontamination: ``purge_days`` observations are dropped on BOTH
sides of every test-block edge, which removes the rolling-lookback overlap an
embargo would otherwise handle. The output is a descriptive distribution of
Sharpe across C(n_blocks, n_test) subperiod selections, not independent OOS evidence.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from .stats import sharpe_ratio


def cpcv_paths(dates: pd.DatetimeIndex, n_blocks: int = 8, n_test: int = 2) -> list[dict]:
    """Enumerate combinatorial subperiod masks (legacy public name)."""
    if not dates.is_unique or not dates.is_monotonic_increasing:
        raise ValueError("stability-analysis dates must be unique and increasing")
    if n_blocks < 2 or n_blocks > len(dates):
        raise ValueError("n_blocks must be between 2 and the number of observations")
    if n_test < 1 or n_test >= n_blocks:
        raise ValueError("n_test must be in [1, n_blocks)")
    blocks = np.array_split(np.arange(len(dates)), n_blocks)
    paths = []
    for combo in combinations(range(n_blocks), n_test):
        mask = np.zeros(len(dates), dtype=bool)
        for b in combo:
            mask[blocks[b]] = True
        paths.append({"test_mask": pd.Series(mask, index=dates), "blocks": combo})
    return paths


def cpcv_sharpe_distribution(
    strategy_returns: pd.Series,
    n_blocks: int = 8,
    n_test: int = 2,
    purge_days: int = 5,
) -> dict:
    """Distribution of Sharpe across combinatorial subperiod selections.

    ``strategy_returns`` must come from an engine whose signals only use past
    data. Each selection scores the return series inside its chosen blocks, dropping
    ``purge_days`` at every block boundary to break rolling-window overlap.
    This diagnoses temporal stability; it does not create OOS returns because
    no model is fitted independently for each selection.
    """
    if purge_days < 0:
        raise ValueError("purge_days must be non-negative")
    r = strategy_returns.dropna()
    if not np.isfinite(r.to_numpy(dtype=float)).all():
        raise ValueError("strategy returns contain infinite values")
    paths = cpcv_paths(r.index, n_blocks=n_blocks, n_test=n_test)
    srs = []
    for path in paths:
        mask = path["test_mask"].to_numpy().copy()
        edges = np.flatnonzero(np.diff(mask.astype(int)) != 0) + 1
        for edge in edges:
            mask[max(0, edge - purge_days) : min(len(mask), edge + purge_days)] = False
        test_r = r[mask]
        if len(test_r) > 60:
            srs.append(sharpe_ratio(test_r))
    srs = pd.Series(srs, dtype=float).dropna()
    return {
        "interpretation": "combinatorial_subperiod_stability_not_oos",
        "n_paths": len(srs),
        "median_sr": float(srs.median()) if len(srs) else float("nan"),
        "q25_sr": float(srs.quantile(0.25)) if len(srs) else float("nan"),
        "min_sr": float(srs.min()) if len(srs) else float("nan"),
        "frac_positive": float((srs > 0).mean()) if len(srs) else float("nan"),
    }
