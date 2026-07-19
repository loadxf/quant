from __future__ import annotations

import numpy as np

from quantlab.prop.bootstrap import (
    IIDDayBootstrap,
    StationaryBlockBootstrap,
    default_block_length,
    make_bootstrapper,
)


class TestStationaryBlockBootstrap:
    def test_shape_bounds_and_determinism(self) -> None:
        sampler = StationaryBlockBootstrap()
        a = sampler.sample(100, 50, 30, np.random.default_rng(1))
        b = sampler.sample(100, 50, 30, np.random.default_rng(1))
        assert a.shape == (50, 30)
        assert a.min() >= 0 and a.max() < 100
        assert np.array_equal(a, b)

    def test_block_continuity_fraction(self) -> None:
        """Sequential continuations should appear at rate ~ 1 - 1/L."""
        length = 8
        sampler = StationaryBlockBootstrap(expected_block_len=length)
        idx = sampler.sample(500, 400, 200, np.random.default_rng(2))
        continues = (idx[:, 1:] == (idx[:, :-1] + 1) % 500).mean()
        assert abs(continues - (1 - 1 / length)) < 0.02

    def test_wraparound_is_valid(self) -> None:
        sampler = StationaryBlockBootstrap(expected_block_len=50)
        idx = sampler.sample(10, 20, 100, np.random.default_rng(3))
        assert idx.max() < 10  # long blocks wrap instead of overflowing

    def test_default_block_length(self) -> None:
        assert default_block_length(8) == 2
        assert default_block_length(125) == 5


class TestIIDAndFactory:
    def test_iid_uniform(self) -> None:
        idx = IIDDayBootstrap().sample(50, 1000, 100, np.random.default_rng(4))
        counts = np.bincount(idx.ravel(), minlength=50)
        assert counts.min() > 0.7 * counts.mean()  # roughly uniform

    def test_factory(self) -> None:
        assert isinstance(make_bootstrapper("stationary"), StationaryBlockBootstrap)
        assert isinstance(make_bootstrapper("iid_day"), IIDDayBootstrap)
        assert isinstance(make_bootstrapper("iid_trade"), IIDDayBootstrap)
