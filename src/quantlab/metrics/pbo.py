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
from dataclasses import dataclass, field

import numpy as np

from quantlab.errors import QuantLabError

DEFAULT_PARTITIONS = 16  # the paper's S; C(16,8) = 12,870 splits
MAX_COMBOS = 12_870  # evaluate all splits up to S=16; sample beyond


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


def _unrank_combination(rank: int, n: int, k: int) -> tuple[int, ...]:
    """The rank-th k-subset of range(n) in lexicographic order — the same
    order itertools.combinations enumerates (combinatorial number system)."""
    combo = []
    x = 0
    for slot in range(k):
        while True:
            with_x = math.comb(n - x - 1, k - slot - 1)
            if rank < with_x:
                combo.append(x)
                x += 1
                break
            rank -= with_x
            x += 1
    return tuple(combo)


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
    m = np.asarray(matrix, dtype=float)
    if m.ndim != 2 or m.shape[1] < 2:
        raise QuantLabError(
            f"PBO needs a (days x variants) matrix with >= 2 variant columns (got shape {m.shape})"
        )
    if not np.isfinite(m).all():
        raise QuantLabError("PBO matrix contains NaN/inf — variants must be aligned, no gaps")
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
    if combos_total > 2**63 - 1:
        # rng.choice cannot draw from a population beyond int64.
        raise QuantLabError(
            f"--partitions {s} yields {combos_total:.2e} splits — beyond the "
            "split sampler's range; use 66 or fewer partitions"
        )
    if combos_total <= MAX_COMBOS:
        combos = list(itertools.combinations(range(s), s // 2))
    else:
        # Sample WITHOUT materializing all C(S, S/2) tuples (--partitions 30
        # would need ~29 GB): draw lexicographic ranks, then unrank each.
        # Identical split sets to enumerate-then-index for any seed, since
        # itertools.combinations is lexicographic.
        rng = np.random.default_rng(seed)
        picks = rng.choice(combos_total, size=MAX_COMBOS, replace=False)
        combos = [_unrank_combination(int(r), s, s // 2) for r in sorted(picks)]
        warnings.append(
            f"evaluated {MAX_COMBOS} of {combos_total} splits (deterministic sample, seed {seed})"
        )
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
    if np.all(omega == 0.5):
        warnings.append(
            "the IS winner ties every variant OOS on every split — no selection "
            "differential exists (identical/duplicated variant columns?); "
            "PBO is uninformative here"
        )

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
        # Continuity correction (deliberate deviation from the paper's
        # P(omega <= 0.5)): an exact-median tie counts HALF an overfit
        # event, so all-identical variants report the pure-noise ~0.5
        # instead of a spurious 1.0 "SEVERE" (or 0.0 with strict <).
        pbo=float(np.mean(omega < 0.5) + 0.5 * np.mean(omega == 0.5)),
        p_oos_loss=float(np.mean(oos_mean[rows, selected] < 0)),
        logit_mean=float(np.mean(logit)),
        logit_quantiles={f"p{q}": float(np.percentile(logit, q)) for q in (5, 25, 50, 75, 95)},
        degradation_slope=float(slope),
        degradation_intercept=float(intercept),
        warnings=warnings,
    )


def _index_like(column, name: str) -> str | None:
    """Reason the first CSV column is an index/date, not a variant — or None.

    A silently-kept index column is catastrophic: a 0..n-1 ramp has per-day
    Sharpe ~1.7, wins every split IS and OOS, and drives PBO to 0.0
    ("selection looks meaningful") on pure noise."""
    if name in ("date", "datetime", "day", "time", "session", "index", "") or name.startswith(
        "unnamed"
    ):
        return f"named {name!r}"
    try:
        values = column.astype(float).to_numpy()
    except (TypeError, ValueError):
        # Not numeric: a variant column must be numeric — date strings and
        # labels alike are provenance, not PnL.
        return "non-numeric values"
    if np.all(values == np.floor(values)):
        ints = values.astype(np.int64)
        n = ints.size
        if np.array_equal(ints, np.arange(n)) or np.array_equal(ints, np.arange(1, n + 1)):
            return "a 0..n-1/1..n integer ramp (a saved DataFrame index)"
        if n > 1 and (np.diff(ints) > 0).all():
            if ((ints >= 19000101) & (ints <= 21001231)).all():
                return "increasing yyyymmdd-style dates"
            if ints[0] >= 10**9:
                return "increasing epoch-timestamp-like values"
    return None


def load_variant_matrix(path) -> tuple[np.ndarray, list[str], list[str]]:
    """CSV -> (days x variants) matrix, variant names, and loader notes.

    A leading index/date-like column is dropped WITH a note saying so —
    silently ingesting it as a variant flips the verdict on pure noise."""
    import pandas as pd

    try:
        frame = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        raise QuantLabError(f"{path}: empty CSV") from None
    except pd.errors.ParserError as exc:
        raise QuantLabError(f"{path}: not a readable CSV ({exc})") from None
    if frame.empty:
        raise QuantLabError(f"{path}: empty CSV")
    notes: list[str] = []
    first_name = str(frame.columns[0]).strip().lower()
    reason = _index_like(frame[frame.columns[0]], first_name)
    if reason is not None:
        notes.append(f"dropped leading column {str(frame.columns[0])!r}: {reason}")
        frame = frame.drop(columns=frame.columns[0])
    if frame.shape[1] == 0:
        raise QuantLabError(f"{path}: no variant columns left after dropping the index column")
    numeric = frame.apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        bad = [c for c in numeric.columns if numeric[c].isna().any()]
        raise QuantLabError(f"{path}: non-numeric or missing values in variant column(s) {bad[:5]}")
    return numeric.to_numpy(dtype=float), [str(c) for c in numeric.columns], notes
