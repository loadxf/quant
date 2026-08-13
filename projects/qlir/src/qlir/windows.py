"""Half-open event-window primitives — the CANONICAL, unit-tested
implementations of the windows used by the QC timing-smoke notebook.

Round-4 defect: inclusive `.loc[a:b]` slicing counted the boundary bar
in BOTH the pre- and forward-volume sums, and at minute resolution a
"60-second" window could span two bars. Every window here is half-open
``(start, end]``: the bar whose stamp equals `start` is excluded, the
bar whose stamp equals `end` is included, and no bar can belong to both
a pre-window ending at b and a forward window starting at b.

The QC research notebook (projects/qlir/qc/qlir_timing_smoke.py) carries
a verbatim copy of these functions — it must stay paste-able standalone.
Any change here must be mirrored there.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def half_open_slice(series: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Values stamped in (start, end] — half-open on the left."""
    index = series.index
    lo = index.searchsorted(start, side="right")
    hi = index.searchsorted(end, side="right")
    return series.iloc[lo:hi]


def window_sum(series: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float:
    """Sum over (start, end] — e.g. volume in the 60 s before/after a
    boundary, with the boundary bar counted on exactly one side."""
    return float(half_open_slice(series, start, end).sum())


def last_at_or_before(series: pd.Series, when: pd.Timestamp) -> float | None:
    """Value of the last stamp <= when (None if none exists)."""
    position = series.index.searchsorted(when, side="right") - 1
    return float(series.iloc[position]) if position >= 0 else None


def logret_std(closes: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float:
    """Std of log returns over (start, end], using the last price at or
    before `start` as the base so the first in-window return is real."""
    window = half_open_slice(closes, start, end)
    base = last_at_or_before(closes, start)
    if base is None or len(window) < 1:
        return float("nan")
    prices = np.concatenate([[base], window.to_numpy(dtype="float64")])
    if len(prices) < 3:  # need >= 2 returns for a std
        return float("nan")
    return float(np.std(np.diff(np.log(prices)), ddof=1))
