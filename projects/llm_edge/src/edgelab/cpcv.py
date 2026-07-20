"""Combinatorially purged cross-validation, adapted (Lopez de Prado 2018, ch. 12).

The date range is cut into ``n_blocks`` contiguous blocks; every combination
of ``n_test`` blocks forms one path's test set. This adaptation SCORES an
already-computed self-financing return series inside each path's test blocks —
no model is re-fit per path (signals are pure functions of past data, enforced
by the engine's t+2 alignment), so the train/test estimation split of full
CPCV does not apply. What remains of purging/embargo in this setting is
boundary decontamination: ``purge_days`` observations are dropped on BOTH
sides of every test-block edge, which removes the rolling-lookback overlap an
embargo would otherwise handle. The output is the distribution of
out-of-sample Sharpe across the C(n_blocks, n_test) paths.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from .stats import sharpe_ratio


def cpcv_paths(dates: pd.DatetimeIndex, n_blocks: int = 8, n_test: int = 2) -> list[dict]:
    """Enumerate CPCV paths: each is {'test_mask': bool Series, 'blocks': (i, j)}."""
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
    """Distribution of out-of-sample Sharpe across CPCV test paths.

    ``strategy_returns`` must come from an engine whose signals only use past
    data. Each path scores the return series inside its test blocks, dropping
    ``purge_days`` at every block boundary to break rolling-window overlap.
    """
    r = strategy_returns.dropna()
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
        "n_paths": len(srs),
        "median_sr": float(srs.median()) if len(srs) else float("nan"),
        "q25_sr": float(srs.quantile(0.25)) if len(srs) else float("nan"),
        "min_sr": float(srs.min()) if len(srs) else float("nan"),
        "frac_positive": float((srs > 0).mean()) if len(srs) else float("nan"),
    }
