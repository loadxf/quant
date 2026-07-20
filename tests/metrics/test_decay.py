"""Decay-panel tests: trend statistics pinned to hand-computed cases."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from quantlab.metrics.decay import (
    compute_decay,
    hac_slope,
    mann_kendall,
    rolling_expectancy,
    runs_test,
)
from tests.prop.conftest import day_trades, simple


class TestHacSlope:
    def test_exact_linear_trend_matches_polyfit(self) -> None:
        y = 5.0 - 0.03 * np.arange(200)
        assert hac_slope(y).slope == pytest.approx(np.polyfit(np.arange(200), y, 1)[0], abs=1e-12)

    def test_hac_se_geq_ols_on_autocorrelated_noise(self) -> None:
        rng = np.random.default_rng(11)
        e = np.zeros(400)
        for i in range(1, 400):  # AR(1), rho=0.7
            e[i] = 0.7 * e[i - 1] + rng.standard_normal()
        res = hac_slope(e)
        x = np.arange(400.0)
        x_c = x - x.mean()
        resid = (e - e.mean()) - res.slope * x_c
        ols_se = np.sqrt(np.sum(resid**2) / 398 / np.sum(x_c**2))
        assert res.se >= ols_se * 0.99  # HAC inflates se under positive AC

    def test_no_trend_high_p(self) -> None:
        rng = np.random.default_rng(5)
        assert hac_slope(rng.standard_normal(300)).p > 0.05


class TestMannKendall:
    def test_monotone_series_significant(self) -> None:
        res = mann_kendall(np.arange(50, dtype=float))
        assert res.z > 0 and res.p < 0.01

    def test_decreasing_negative_z(self) -> None:
        assert mann_kendall(-np.arange(50, dtype=float)).z < 0

    def test_constant_series_null(self) -> None:
        res = mann_kendall(np.full(40, 7.0))
        assert res.z == 0.0 and res.p == 1.0

    @given(st.integers(min_value=0, max_value=2**32 - 1))
    def test_p_in_unit_interval(self, seed: int) -> None:
        pnls = np.random.default_rng(seed).standard_normal(30)
        res = mann_kendall(pnls)
        assert 0.0 <= res.p <= 1.0 and not np.isnan(res.z)


class TestRunsTest:
    def test_alternation_positive_z(self) -> None:
        pnls = np.tile([100.0, -50.0], 30)  # WLWLWL... = max runs
        res = runs_test(pnls)
        assert res.z > 0 and res.p < 0.01

    def test_long_streaks_negative_z(self) -> None:
        pnls = np.concatenate([np.full(30, 100.0), np.full(30, -50.0)])  # 2 runs
        res = runs_test(pnls)
        assert res.runs == 2 and res.z < 0 and res.p < 0.01

    def test_hand_computed_small_case(self) -> None:
        # 12 wins, 12 losses, alternating -> runs=24.
        # E[r] = 1 + 2*12*12/24 = 13; Var = 2*144*(288-24)/(576*23) = 5.739...
        pnls = np.tile([1.0, -1.0], 12)
        res = runs_test(pnls)
        assert res.runs == 24
        assert res.z == pytest.approx((24 - 13) / np.sqrt(2 * 144 * 264 / (576 * 23)), abs=1e-9)

    def test_scratches_excluded(self) -> None:
        pnls = np.tile([100.0, 0.0, -50.0], 20)
        res = runs_test(pnls)
        assert res.n_wins == 20 and res.n_losses == 20


class TestRollingAndPanel:
    def test_rolling_window_shape(self) -> None:
        assert rolling_expectancy(np.arange(100.0), 30).size == 71
        assert rolling_expectancy(np.arange(10.0), 30).size == 0

    def test_decaying_log_flagged(self) -> None:
        # Strong early edge fading to nothing: +200 avg -> ~0 avg.
        rng = np.random.default_rng(3)
        days = []
        for i in range(120):
            mean = 200.0 * max(0.0, 1.0 - i / 60.0)
            days.append([simple(mean + 40 * rng.standard_normal())])
        panel = compute_decay(day_trades(days))
        assert panel.decayed
        assert panel.hac.slope < 0 and panel.hac.p < 0.05
        assert panel.second_half.expectancy < 0.5 * panel.first_half.expectancy

    def test_steady_log_not_flagged(self) -> None:
        rng = np.random.default_rng(4)
        days = [[simple(100 + 30 * rng.standard_normal())] for _ in range(120)]
        panel = compute_decay(day_trades(days))
        assert not panel.decayed

    def test_wfe_computed_when_oos_start_given(self) -> None:
        days = [[simple(100.0)]] * 40 + [[simple(60.0)]] * 40
        log = day_trades(days)
        oos_start = log.trades[40].entry_time
        panel = compute_decay(log, oos_start=oos_start)
        assert panel.wfe == pytest.approx(0.6, abs=1e-9)
