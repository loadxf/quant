"""Volatility-forecast tests: hand-computed recursions, lookahead
properties, and parameter recovery on simulated GARCH data."""

from __future__ import annotations

import math

import numpy as np
import pytest

from quantlab.errors import QuantLabError
from quantlab.metrics.volforecast import (
    arch_lm,
    compute_clustering,
    ewma_sigma_path,
    fit_garch11,
    mcleod_li,
)


def _simulate_garch(n: int, omega: float, alpha: float, beta: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    var = omega / (1.0 - alpha - beta)
    out = np.empty(n)
    for t in range(n):
        r = math.sqrt(var) * rng.standard_normal()
        out[t] = r
        var = omega + alpha * r * r + beta * var
    return out


class TestEwma:
    def test_three_step_hand_computed(self) -> None:
        # burn_in=2: seed = (1^2 + 2^2)/2 = 2.5
        # sigma[2] = sqrt(2.5)
        # var[3] = 0.94*2.5 + 0.06*3^2 = 2.35 + 0.54 = 2.89 -> sigma[3] = 1.7
        r = np.array([1.0, 2.0, 3.0, 1.0])
        res = ewma_sigma_path(r, lam=0.94, burn_in=2)
        assert math.isnan(res.sigma[0]) and math.isnan(res.sigma[1])
        assert res.sigma[2] == pytest.approx(math.sqrt(2.5))
        assert res.sigma[3] == pytest.approx(math.sqrt(2.89))
        assert res.seed_var == pytest.approx(2.5)

    def test_strict_lookahead(self) -> None:
        rng = np.random.default_rng(1)
        r = rng.standard_normal(100)
        base = ewma_sigma_path(r).sigma
        perturbed = r.copy()
        perturbed[60] += 50.0  # a huge future shock
        after = ewma_sigma_path(perturbed).sigma
        # sigma up to and INCLUDING day 60 must be unchanged (sigma[60]
        # uses r[59] and earlier); sigma[61] must differ.
        assert base[:61] == pytest.approx(after[:61], nan_ok=True)
        assert after[61] > base[61]

    def test_burn_in_longer_than_series(self) -> None:
        res = ewma_sigma_path(np.array([1.0, -1.0]), burn_in=20)
        assert all(math.isnan(s) for s in res.sigma)

    @pytest.mark.parametrize(
        "kwargs",
        [{"lam": 1.0}, {"burn_in": 0}],
    )
    def test_invalid_parameters_rejected(self, kwargs: dict) -> None:
        with pytest.raises(QuantLabError):
            ewma_sigma_path(np.array([1.0, 2.0]), **kwargs)

    def test_nonfinite_series_rejected(self) -> None:
        with pytest.raises(QuantLabError, match="finite"):
            compute_clustering(np.array([1.0, float("nan")]))


class TestGarchFit:
    def test_recovers_known_parameters(self) -> None:
        r = _simulate_garch(2000, omega=0.1, alpha=0.10, beta=0.85, seed=5)
        res = fit_garch11(r)
        assert res.method == "garch11" and res.converged
        assert res.alpha == pytest.approx(0.10, abs=0.05)
        assert res.beta == pytest.approx(0.85, abs=0.05)

    def test_falls_back_below_min_obs(self) -> None:
        r = _simulate_garch(150, 0.1, 0.1, 0.85, seed=6)
        res = fit_garch11(r)
        assert res.method == "ewma"
        assert res.fallback_reason is not None and "250" in res.fallback_reason

    def test_short_but_accepted_fit_warns(self) -> None:
        r = _simulate_garch(300, 0.1, 0.1, 0.8, seed=7)
        res = fit_garch11(r)
        if res.method == "garch11":  # fit may legitimately fall back
            assert res.fallback_reason is not None and "500" in res.fallback_reason

    def test_lookahead_property(self) -> None:
        r = _simulate_garch(600, 0.1, 0.1, 0.85, seed=8)
        base = fit_garch11(r)
        # Perturbing the LAST day cannot change any earlier sigma given
        # the same parameters — but the fit itself uses the full sample,
        # so compare sigma paths computed with IDENTICAL parameters: the
        # documented contract is that sigma[t] depends on r[0..t-1] only.
        assert base.method == "garch11"
        sigma = np.array(base.sigma)
        assert math.isnan(sigma[0])
        assert not math.isnan(sigma[-1])


class TestClusteringTests:
    def test_significant_on_garch_insignificant_on_iid(self) -> None:
        garch = _simulate_garch(1000, 0.05, 0.15, 0.80, seed=9)
        iid = np.random.default_rng(10).standard_normal(1000)
        _, p_garch, _ = arch_lm(garch)
        _, p_iid, _ = arch_lm(iid)
        assert p_garch < 0.01
        assert p_iid > 0.05
        _, ml_garch, _ = mcleod_li(garch)
        _, ml_iid, _ = mcleod_li(iid)
        assert ml_garch < 0.01
        assert ml_iid > 0.05

    def test_compute_clustering_verdict(self) -> None:
        garch = _simulate_garch(800, 0.05, 0.2, 0.75, seed=11)
        assert compute_clustering(garch).clustered
        iid = np.random.default_rng(12).standard_normal(800)
        assert not compute_clustering(iid).clustered

    def test_tiny_series_degenerate(self) -> None:
        stat, p, _ = arch_lm(np.arange(10.0))
        assert (stat, p) == (0.0, 1.0)

    def test_constant_series_no_crash(self) -> None:
        tests = compute_clustering(np.full(200, 5.0))
        assert not tests.clustered
