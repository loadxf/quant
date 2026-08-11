"""Probability of Backtest Overfitting via CSCV (opt-in, needs variant data).

Bailey, Borwein, Lopez de Prado & Zhu (2017), "The Probability of
Backtest Overfitting" (J. Computational Finance): split the days into S
even blocks; for every choice of S/2 blocks as in-sample, pick the
variant with the best IS Sharpe and find its RANK out-of-sample among
all variants. PBO is the fraction of splits where the IS winner lands
in the bottom half OOS — the probability that selecting "the best
backtest" selected noise. Pure-noise variant matrices give PBO ~ 0.5;
a genuine dominant strategy drives it toward 0.

This is the measured complement to the DSR's *declared* `--trials N`:
feed it the actual per-variant daily PnL (e.g. a QuantConnect parameter
sweep, one column per variant) and it quantifies the selection bias
directly. Combinatorially symmetric splits preserve the day ordering
inside blocks, so serial dependence within blocks is respected.
"""

from __future__ import annotations

import dataclasses
import itertools
import math
import random
from dataclasses import dataclass, field
from numbers import Integral

import numpy as np

from quantlab.errors import QuantLabError

DEFAULT_PARTITIONS = 16  # the paper's S; C(16,8) = 12,870 splits
MAX_COMBOS = 12_870  # evaluate all splits up to S=16; sample beyond


def _unrank_combination(n: int, k: int, rank: int) -> tuple[int, ...]:
    """Lexicographic combination at `rank`, without enumerating prior rows."""
    result: list[int] = []
    candidate = 0
    for position in range(k):
        remaining = k - position - 1
        while candidate < n:
            count = math.comb(n - candidate - 1, remaining)
            if rank < count:
                result.append(candidate)
                candidate += 1
                break
            rank -= count
            candidate += 1
    return tuple(result)


def _sample_ranks(total: int, count: int, seed: int) -> list[int]:
    """Floyd sampling uses O(count) memory even when `total` is enormous."""
    rng = random.Random(seed)
    selected: set[int] = set()
    for upper in range(total - count, total):
        pick = rng.randrange(upper + 1)
        selected.add(upper if pick in selected else pick)
    return sorted(selected)


@dataclass
class PboResult:
    n_variants: int
    n_days: int
    s_partitions: int
    combos_total: int
    combos_evaluated: int
    pbo: float  # P(IS winner ranks in the bottom half OOS)
    p_oos_loss: float  # P(IS winner's OOS mean < 0)
    logit_mean: float
    logit_quantiles: dict[str, float]
    degradation_slope: float  # OLS of OOS Sharpe on IS Sharpe (selected variant)
    degradation_intercept: float
    warnings: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict:
        return dataclasses.asdict(self)


def _sharpe(sums: np.ndarray, sumsq: np.ndarray, n: int) -> np.ndarray:
    """Per-day Sharpe from pooled sums/sums-of-squares; degenerate
    (zero-variance) variants rank by sign of the mean at +/-inf."""
    mean = sums / n
    var = (sumsq - n * mean**2) / (n - 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        sr = mean / np.sqrt(np.maximum(var, 0.0))
    degenerate = ~np.isfinite(sr)
    return np.where(degenerate, np.where(mean > 0, np.inf, -np.inf), sr)


def compute_pbo(
    matrix: np.ndarray, partitions: int = DEFAULT_PARTITIONS, seed: int = 0
) -> PboResult:
    """CSCV over a (days x variants) daily-PnL matrix."""
    if not isinstance(partitions, Integral) or isinstance(partitions, bool):
        raise QuantLabError(f"--partitions must be an even integer >= 4 (got {partitions})")
    partitions = int(partitions)
    m = np.asarray(matrix, dtype=float)
    if m.ndim != 2 or m.shape[1] < 2:
        raise QuantLabError(
            f"PBO needs a (days x variants) matrix with >= 2 variant columns (got shape {m.shape})"
        )
    if not np.isfinite(m).all():
        raise QuantLabError("PBO matrix contains NaN/inf — variants must be aligned, no gaps")
    if m.shape[0] < 2:
        raise QuantLabError("PBO matrix needs at least two daily observations")
    if not np.any(m.std(axis=0, ddof=1) > 0):
        raise QuantLabError(
            "PBO is unavailable: every variant has zero return variance"
        )
    if np.unique(m, axis=1).shape[1] < 2:
        raise QuantLabError(
            "PBO is unavailable: the matrix has fewer than two distinct variant paths"
        )
    if partitions < 4 or partitions % 2:
        raise QuantLabError(f"--partitions must be an even number >= 4 (got {partitions})")
    t, n_variants = m.shape
    if t < 2 * partitions:
        raise QuantLabError(
            f"{t} days cannot fill {partitions} blocks of >= 2 days — "
            "use fewer --partitions or a longer sample"
        )
    s = partitions
    warnings: list[str] = []
    if n_variants < 5:
        warnings.append(
            f"only {n_variants} variants: PBO ranks are coarse (granularity 1/{n_variants + 1})"
        )

    # Trim the tail remainder so blocks are exactly even (paper convention).
    block_days = t // s
    used = block_days * s
    if used < t:
        warnings.append(f"dropped the last {t - used} days to fit {s} even blocks")
    blocks = m[:used].reshape(s, block_days, n_variants)
    block_sums = blocks.sum(axis=1)  # (S, N)
    block_sumsq = (blocks**2).sum(axis=1)

    combos_total = math.comb(s, s // 2)
    if combos_total > MAX_COMBOS:
        combos = [
            _unrank_combination(s, s // 2, rank)
            for rank in _sample_ranks(combos_total, MAX_COMBOS, seed)
        ]
        warnings.append(
            f"evaluated {MAX_COMBOS} of {combos_total} splits (deterministic sample, seed {seed})"
        )
    else:
        combos = list(itertools.combinations(range(s), s // 2))
    mask = np.zeros((len(combos), s), dtype=bool)
    for row, combo in enumerate(combos):
        mask[row, list(combo)] = True

    half_days = block_days * (s // 2)
    is_sr = _sharpe(mask @ block_sums, mask @ block_sumsq, half_days)  # (C, N)
    oos_sr = _sharpe((~mask) @ block_sums, (~mask) @ block_sumsq, half_days)
    oos_mean = ((~mask) @ block_sums) / half_days

    selected = np.argmax(is_sr, axis=1)  # (C,)
    rows = np.arange(len(combos))
    sel_oos = oos_sr[rows, selected]
    # Rank of the selected variant OOS (1 = worst, N = best), ties averaged.
    rank = (oos_sr < sel_oos[:, None]).sum(axis=1) + 0.5 * (
        (oos_sr == sel_oos[:, None]).sum(axis=1) + 1
    )
    omega = rank / (n_variants + 1)
    logit = np.log(omega / (1.0 - omega))

    finite = np.isfinite(is_sr[rows, selected]) & np.isfinite(sel_oos)
    if finite.sum() >= 2:
        slope, intercept = np.polyfit(is_sr[rows, selected][finite], sel_oos[finite], 1)
    else:
        slope = intercept = float("nan")

    return PboResult(
        n_variants=n_variants,
        n_days=used,
        s_partitions=s,
        combos_total=combos_total,
        combos_evaluated=len(combos),
        pbo=float(np.mean(omega <= 0.5)),
        p_oos_loss=float(np.mean(oos_mean[rows, selected] < 0)),
        logit_mean=float(np.mean(logit)),
        logit_quantiles={f"p{q}": float(np.percentile(logit, q)) for q in (5, 25, 50, 75, 95)},
        degradation_slope=float(slope),
        degradation_intercept=float(intercept),
        warnings=warnings,
    )


def load_variant_matrix(path) -> tuple[np.ndarray, list[str]]:
    """CSV -> (days x variants) matrix + variant names. A leading date-like
    column (unparseable as float, or named date/datetime/day) is dropped."""
    import pandas as pd

    frame = pd.read_csv(path)
    if frame.empty:
        raise QuantLabError(f"{path}: empty CSV")
    first = str(frame.columns[0]).strip().lower()
    if first in ("date", "datetime", "day", "time", "session"):
        frame = frame.drop(columns=frame.columns[0])
    else:
        try:
            frame[frame.columns[0]].astype(float)
        except (TypeError, ValueError):
            frame = frame.drop(columns=frame.columns[0])
    numeric = frame.apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        bad = [c for c in numeric.columns if numeric[c].isna().any()]
        raise QuantLabError(f"{path}: non-numeric or missing values in variant column(s) {bad[:5]}")
    return numeric.to_numpy(dtype=float), [str(c) for c in numeric.columns]
