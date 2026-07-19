"""Resampling schemes over trading-day indices.

Default is the stationary block bootstrap (Politis & Romano 1994):
geometric block lengths with wrap-around, preserving the serial
dependence (streaks, volatility clustering) that prop-firm rules are
path-sensitive to. IID day resampling destroys autocorrelation and
systematically overstates pass probability for streaky strategies —
it is kept as an explicit comparison mode.
"""

from __future__ import annotations

from typing import Literal, Protocol

import numpy as np

BootstrapName = Literal["stationary", "iid_day", "iid_trade"]


class Bootstrapper(Protocol):
    def sample(
        self, n_days: int, n_paths: int, horizon: int, rng: np.random.Generator
    ) -> np.ndarray:
        """(n_paths, horizon) int array of source-day indices."""
        ...


def default_block_length(n_days: int) -> int:
    return max(2, round(n_days ** (1 / 3)))


class StationaryBlockBootstrap:
    def __init__(self, expected_block_len: int | None = None) -> None:
        self.expected_block_len = expected_block_len

    def sample(
        self, n_days: int, n_paths: int, horizon: int, rng: np.random.Generator
    ) -> np.ndarray:
        length = self.expected_block_len or default_block_length(n_days)
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
        return rng.integers(0, n_days, size=(n_paths, horizon))


def make_bootstrapper(name: BootstrapName, block_len: int | None = None) -> Bootstrapper:
    if name == "stationary":
        return StationaryBlockBootstrap(block_len)
    return IIDDayBootstrap()  # iid_trade resamples the *profile*, then IID days
