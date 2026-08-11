"""Resampling schemes over trading-day indices.

Default is the stationary block bootstrap (Politis & Romano 1994):
geometric block lengths with wrap-around, preserving the serial
dependence (streaks, volatility clustering) that prop-firm rules are
path-sensitive to. IID day resampling destroys autocorrelation and
systematically overstates pass probability for streaky strategies —
it is kept as an explicit comparison mode.
"""

from __future__ import annotations

import math
from typing import Literal, Protocol

import numpy as np

from quantlab.errors import QuantLabError

BootstrapName = Literal["stationary", "iid_day", "iid_trade"]


def _validate_shape(n_days: int, n_paths: int, horizon: int) -> None:
    if n_days < 1 or n_paths < 1 or horizon < 1:
        raise QuantLabError(
            "bootstrap dimensions must be positive "
            f"(days={n_days}, paths={n_paths}, horizon={horizon})"
        )


class Bootstrapper(Protocol):
    def sample(
        self, n_days: int, n_paths: int, horizon: int, rng: np.random.Generator
    ) -> np.ndarray:
        """(n_paths, horizon) int array of source-day indices."""
        ...


def default_block_length(n_days: int) -> int:
    if n_days < 1:
        raise QuantLabError(f"n_days must be positive (got {n_days})")
    return max(2, round(n_days ** (1 / 3)))


def optimal_block_length(series: np.ndarray) -> int:
    """Politis-White (2004) automatic block length for the stationary
    bootstrap, with the Patton-Politis-White (2009) correction —
    adapts the expected block length to the series' actual
    autocorrelation instead of the n^(1/3) rule of thumb.
    Cross-checked against the `arch` package's implementation.
    Falls back to the heuristic for short or degenerate series.
    """
    x = np.asarray(series, dtype=float)
    n = x.size
    if n < 30:
        return default_block_length(n)
    x = x - x.mean()
    kn = max(5, int(math.log10(n)))
    m_max = math.ceil(math.sqrt(n)) + kn
    acv = np.array([float(np.sum(x[: n - k] * x[k:])) / n for k in range(m_max + 1)])
    if acv[0] <= 0:
        return default_block_length(n)
    # Lag cutoff: twice the first lag after which K_N consecutive sample
    # autocorrelations are insignificant at the 2*sqrt(log10(n)/n) band.
    rho = np.abs(acv[1:] / acv[0])
    cv = 2.0 * math.sqrt(math.log10(n) / n)
    insignificant = rho < cv
    run_start = None
    for i in range(len(insignificant) - kn + 1):
        if insignificant[i : i + kn].all():
            run_start = i + 1  # lag index (1-based)
            break
    m = 2 * (run_start if run_start is not None else m_max)
    m = max(1, min(m, m_max))
    ks = np.arange(1, m + 1)
    lam = np.where(ks / m <= 0.5, 1.0, 2.0 * (1.0 - ks / m))  # flat-top window
    g = float(np.sum(2.0 * lam * ks * acv[1 : m + 1]))
    lr_acv = float(acv[0] + np.sum(2.0 * lam * acv[1 : m + 1]))
    d_sb = 2.0 * lr_acv**2
    if d_sb <= 0.0:
        return default_block_length(n)
    b = (2.0 * g**2 / d_sb) ** (1.0 / 3.0) * n ** (1.0 / 3.0)
    b = min(b, math.ceil(min(3.0 * math.sqrt(n), n / 3.0)))
    return max(2, round(b))


class StationaryBlockBootstrap:
    def __init__(self, expected_block_len: int | None = None) -> None:
        if expected_block_len is not None and expected_block_len < 1:
            # 1/L is the new-block probability: L <= 0 silently degenerates
            # every path into one circular run of the source days.
            raise QuantLabError(f"--block-len must be >= 1 (got {expected_block_len})")
        self.expected_block_len = expected_block_len

    def sample(
        self, n_days: int, n_paths: int, horizon: int, rng: np.random.Generator
    ) -> np.ndarray:
        _validate_shape(n_days, n_paths, horizon)
        length = (
            self.expected_block_len
            if self.expected_block_len is not None
            else default_block_length(n_days)
        )
        # Geometric block lengths: at each step, with prob 1/L start a new
        # block at a uniform position, else continue sequentially (wrapping).
        starts = rng.integers(0, n_days, size=(n_paths, horizon))
        new_block = rng.random(size=(n_paths, horizon)) < (1.0 / length)
        new_block[:, 0] = True
        idx = np.empty((n_paths, horizon), dtype=np.int64)
        idx[:, 0] = starts[:, 0]
        for t in range(1, horizon):
            idx[:, t] = np.where(new_block[:, t], starts[:, t], (idx[:, t - 1] + 1) % n_days)
        return idx


class IIDDayBootstrap:
    def sample(
        self, n_days: int, n_paths: int, horizon: int, rng: np.random.Generator
    ) -> np.ndarray:
        _validate_shape(n_days, n_paths, horizon)
        return rng.integers(0, n_days, size=(n_paths, horizon))


def make_bootstrapper(name: BootstrapName, block_len: int | None = None) -> Bootstrapper:
    if block_len is not None and block_len < 1:
        raise QuantLabError(f"block_len must be positive (got {block_len})")
    if name == "stationary":
        return StationaryBlockBootstrap(block_len)
    if name in ("iid_day", "iid_trade"):  # iid_trade resamples the *profile*, then IID days
        return IIDDayBootstrap()
    raise QuantLabError(
        f"Unknown bootstrap {name!r}: choose stationary, iid_day, or iid_trade. "
        "(A typo here must not silently fall back to IID sampling.)"
    )


MIN_DAYS_FOR_BLOCKS = 30


def resolve_sampler(
    requested: BootstrapName,
    day_pnl: np.ndarray,
    block_len: int | None = None,
) -> tuple[Bootstrapper, BootstrapName, int | None, bool]:
    """THE stationary-vs-iid fallback policy, in one place.

    Returns (sampler, resolved_name, block_len_used, fell_back). The
    stationary scheme degenerates below MIN_DAYS_FOR_BLOCKS source days
    and falls back to iid_day; block_len resolves to the Politis-White
    automatic length only for the stationary scheme. Callers own the
    user-facing warning phrasing (their tests pin the texts); `fell_back`
    tells them when one is due.
    """
    n_days = int(day_pnl.size)
    resolved: BootstrapName = requested
    fell_back = False
    if requested == "stationary" and n_days < MIN_DAYS_FOR_BLOCKS:
        resolved = "iid_day"
        fell_back = True
    block_len_used = block_len
    if resolved == "stationary" and block_len_used is None:
        block_len_used = optimal_block_length(day_pnl)
    return make_bootstrapper(resolved, block_len_used), resolved, block_len_used, fell_back
