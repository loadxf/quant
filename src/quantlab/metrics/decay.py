"""Edge-decay panel: is the strategy's edge deteriorating over the log?

Methods with citable provenance only:
- Split-sample (first half vs second half) comparison and rolling
  trade-count-window expectancy — walk-forward conventions per Pardo,
  "The Evaluation and Optimization of Trading Strategies" (Wiley).
- OLS slope of trade PnL on trade index with Newey-West HAC standard
  errors (lag = floor(4*(n/100)^(2/9)), the standard rule of thumb).
- Mann-Kendall non-parametric monotonic-trend test (tie-corrected
  normal approximation).
- Wald-Wolfowitz runs test on the win/loss sign sequence — flags
  serial dependence (streaks), which makes iid-based analyses
  optimistic and favors the block bootstrap.

Deliberately NOT implemented: fitting an exponential decay / half-life
to a single log. Decay-rate estimates are only identified
cross-sectionally (McLean & Pontiff 2016; Falck, Rej & Thesmar 2022);
from one realization a "half-life" is indistinguishable from an
ordinary drawdown, so the tool refuses to print one and offers
literature-anchored scenario haircuts instead (see costs.py).
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import numpy as np

from quantlab.metrics.deflate import norm_cdf
from quantlab.schema.trade import FUTURES_DAY, DayBoundary, TradeLog


@dataclass(frozen=True, slots=True)
class HalfStats:
    n: int
    expectancy: float
    profit_factor: float


@dataclass(frozen=True, slots=True)
class HacResult:
    slope: float  # $ per trade index step
    se: float
    t: float
    p: float  # two-sided
    lag: int


@dataclass(frozen=True, slots=True)
class MKResult:
    s: int
    z: float
    p: float  # two-sided


@dataclass(frozen=True, slots=True)
class RunsResult:
    n_wins: int
    n_losses: int
    runs: int
    z: float
    p: float  # two-sided; z < 0 => fewer runs than chance => streaky


@dataclass(frozen=True, slots=True)
class DecayPanel:
    first_half: HalfStats
    second_half: HalfStats
    rolling: list[float]  # rolling-window expectancy series
    rolling_window: int
    hac: HacResult
    mk: MKResult
    runs: RunsResult
    wfe: float | None  # walk-forward efficiency (OOS/IS expectancy ratio)
    decayed: bool


def rolling_expectancy(pnls: np.ndarray, window: int = 30) -> np.ndarray:
    """Trade-count rolling mean (trade windows beat calendar windows for
    frequency-varying discretionary logs)."""
    if pnls.size < window:
        return np.array([])
    kernel = np.ones(window) / window
    return np.convolve(pnls, kernel, mode="valid")


def hac_slope(pnls: np.ndarray) -> HacResult:
    """OLS of PnL on trade index with Newey-West HAC standard errors."""
    n = pnls.size
    if n < 8:
        return HacResult(0.0, 0.0, 0.0, 1.0, 0)
    x = np.arange(n, dtype=float)
    x_c = x - x.mean()
    y_c = pnls - pnls.mean()
    sxx = float(np.sum(x_c**2))
    slope = float(np.sum(x_c * y_c)) / sxx
    resid = y_c - slope * x_c
    lag = math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))
    lag = min(lag, n - 2)
    # Newey-West long-run variance of the score x_c * resid.
    score = x_c * resid
    gamma0 = float(np.sum(score**2))
    lrv = gamma0
    for k in range(1, lag + 1):
        w = 1.0 - k / (lag + 1.0)
        lrv += 2.0 * w * float(np.sum(score[k:] * score[:-k]))
    se = math.sqrt(max(lrv, 0.0)) / sxx
    if se == 0.0:
        return HacResult(slope, 0.0, 0.0, 1.0, lag)
    t = slope / se
    p = 2.0 * (1.0 - norm_cdf(abs(t)))
    return HacResult(slope, se, t, p, lag)


def mann_kendall(pnls: np.ndarray) -> MKResult:
    """Mann-Kendall monotonic trend test, tie-corrected normal approx."""
    n = pnls.size
    if n < 8:
        return MKResult(0, 0.0, 1.0)
    signs = np.sign(pnls[None, :] - pnls[:, None])
    s = int(np.triu(signs, k=1).sum())
    _, counts = np.unique(pnls, return_counts=True)
    tie_term = float(np.sum(counts * (counts - 1) * (2 * counts + 5)))
    var_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if var_s <= 0:
        return MKResult(s, 0.0, 1.0)
    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0
    p = 2.0 * (1.0 - norm_cdf(abs(z)))
    return MKResult(s, z, p)


def runs_test(pnls: np.ndarray) -> RunsResult:
    """Wald-Wolfowitz runs test on the win/loss sign sequence.

    z < 0 (fewer runs than chance) => streak dependence: block
    bootstrap results should be preferred over iid analyses.
    Zero-PnL trades (scratches) are excluded — they are neither wins
    nor losses in the sign sequence.
    """
    signs = np.sign(pnls)
    signs = signs[signs != 0]
    n1 = int(np.sum(signs > 0))
    n2 = int(np.sum(signs < 0))
    n = n1 + n2
    if n1 == 0 or n2 == 0 or n < 20:
        return RunsResult(n1, n2, 0, 0.0, 1.0)
    runs = int(1 + np.sum(signs[1:] != signs[:-1]))
    mean_r = 1.0 + 2.0 * n1 * n2 / n
    var_r = 2.0 * n1 * n2 * (2.0 * n1 * n2 - n) / (n**2 * (n - 1.0))
    if var_r <= 0:
        return RunsResult(n1, n2, runs, 0.0, 1.0)
    z = (runs - mean_r) / math.sqrt(var_r)
    p = 2.0 * (1.0 - norm_cdf(abs(z)))
    return RunsResult(n1, n2, runs, z, p)


def _half_stats(pnls: np.ndarray) -> HalfStats:
    wins = float(pnls[pnls > 0].sum())
    losses = float(-pnls[pnls < 0].sum())
    pf = wins / losses if losses > 0 else (float("inf") if wins > 0 else 0.0)
    return HalfStats(
        n=int(pnls.size), expectancy=float(pnls.mean()) if pnls.size else 0.0, profit_factor=pf
    )


def compute_decay(
    log: TradeLog,
    window: int = 30,
    oos_start: dt.datetime | None = None,
    boundary: DayBoundary = FUTURES_DAY,
) -> DecayPanel:
    """Full decay panel for one trade log.

    `oos_start`: optional user-declared out-of-sample boundary (e.g.
    "strategy went live here") for a walk-forward-efficiency ratio.
    """
    pnls = np.array([t.pnl for t in log.trades], dtype=float)
    n = pnls.size
    half = n // 2
    first, second = _half_stats(pnls[:half]), _half_stats(pnls[half:])

    wfe: float | None = None
    if oos_start is not None:
        is_mask = np.array([t.exit_time < oos_start for t in log.trades])
        is_pnls, oos_pnls = pnls[is_mask], pnls[~is_mask]
        if is_pnls.size >= 10 and oos_pnls.size >= 10 and is_pnls.mean() > 0:
            wfe = float(oos_pnls.mean() / is_pnls.mean())

    hac = hac_slope(pnls)
    mk = mann_kendall(pnls)
    runs = runs_test(pnls)
    decayed = (
        hac.slope < 0
        and hac.p < 0.05
        and first.expectancy > 0
        and second.expectancy < 0.5 * first.expectancy
    )
    return DecayPanel(
        first_half=first,
        second_half=second,
        rolling=[float(v) for v in rolling_expectancy(pnls, window)],
        rolling_window=window,
        hac=hac,
        mk=mk,
        runs=runs,
        wfe=wfe,
        decayed=decayed,
    )
