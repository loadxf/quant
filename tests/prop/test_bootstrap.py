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


class TestOptimalBlockLength:
    """Politis-White automatic block length (pass: M8)."""

    def test_iid_data_gets_short_blocks(self) -> None:
        from quantlab.prop.bootstrap import optimal_block_length

        rng = np.random.default_rng(1)
        iid = rng.standard_normal(400)
        assert 2 <= optimal_block_length(iid) <= 6

    def test_autocorrelated_data_gets_longer_blocks(self) -> None:
        from quantlab.prop.bootstrap import optimal_block_length

        rng = np.random.default_rng(2)
        ar = np.zeros(400)
        for i in range(1, 400):
            ar[i] = 0.85 * ar[i - 1] + rng.standard_normal()
        iid = rng.standard_normal(400)
        assert optimal_block_length(ar) > optimal_block_length(iid)

    def test_short_series_falls_back_to_heuristic(self) -> None:
        from quantlab.prop.bootstrap import default_block_length, optimal_block_length

        series = np.arange(10.0)
        assert optimal_block_length(series) == default_block_length(10)

    def test_constant_series_no_crash(self) -> None:
        from quantlab.prop.bootstrap import optimal_block_length

        assert optimal_block_length(np.full(100, 5.0)) >= 2
