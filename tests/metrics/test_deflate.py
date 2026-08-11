"""Deflated-statistics tests: formulas pinned to published worked examples."""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from quantlab.metrics.contracts import resolve_contract
from quantlab.metrics.deflate import (
    EULER_MASCHERONI,
    compute_deflated,
    compute_psr,
    norm_cdf,
    norm_ppf,
)


def _unit_sample(n: int, sr: float, seed: int = 7) -> np.ndarray:
    """Sample with EXACT sample mean=sr and std(ddof=1)=1."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n)
    x = (x - x.mean()) / x.std(ddof=1)
    return x + sr


class TestNormalHelpers:
    def test_ppf_known_quantiles(self) -> None:
        assert norm_ppf(0.975) == pytest.approx(1.959964, abs=1e-6)
        assert norm_ppf(0.95) == pytest.approx(1.644854, abs=1e-6)
        assert norm_ppf(0.5) == 0.0
        assert norm_ppf(0.0) == -math.inf and norm_ppf(1.0) == math.inf

    @given(st.floats(min_value=1e-6, max_value=1 - 1e-6))
    def test_round_trip(self, p: float) -> None:
        assert norm_cdf(norm_ppf(p)) == pytest.approx(p, abs=1e-7)


class TestPsr:
    def test_matches_formula_from_independent_moments(self) -> None:
        pnls = _unit_sample(200, 0.15)
        n = pnls.size
        mean, std = pnls.mean(), pnls.std(ddof=1)
        sr = mean / std
        c = pnls - mean
        m2 = np.mean(c**2)
        g3 = np.mean(c**3) / m2**1.5
        g4 = np.mean(c**4) / m2**2
        expected = norm_cdf(sr * math.sqrt(n - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr**2))
        assert compute_psr(pnls) == pytest.approx(expected, abs=1e-12)

    def test_zero_edge_is_half(self) -> None:
        # Exact zero sample SR -> z = 0 -> PSR = 0.5.
        assert compute_psr(_unit_sample(100, 0.0)) == pytest.approx(0.5, abs=1e-9)


class TestMinTrl:
    def test_psr_at_min_trl_is_95pct(self) -> None:
        stats = compute_deflated(_unit_sample(150, 0.2))
        assert stats.min_trl is not None
        # By construction: SR * sqrt(MinTRL - 1) / denom == z_95.
        denom = math.sqrt(
            1
            - stats.skew * stats.sr_per_trade
            + (stats.kurtosis_raw - 1) / 4 * stats.sr_per_trade**2
        )
        z = stats.sr_per_trade * math.sqrt(stats.min_trl - 1) / denom
        assert z == pytest.approx(norm_ppf(0.95), abs=1e-9)


class TestMinBtl:
    def test_ams_worked_example(self) -> None:
        """Pseudo-Mathematics (AMS 2014): N=45 trials -> ~5 years needed
        to support an annualized Sharpe of 1."""
        stats = compute_deflated(_unit_sample(300, 0.2), n_trials=45)
        assert stats.minbtl_years == pytest.approx(5.0, abs=0.1)


class TestHaircutSharpe:
    def test_harvey_liu_worked_example(self) -> None:
        """Backtesting (JPM 2015) example: 240 monthly obs, annualized
        SR 0.75, 200 trials -> haircut in the ~55-60% band."""
        sr_monthly = 0.75 / math.sqrt(12)
        stats = compute_deflated(_unit_sample(240, sr_monthly, seed=3), n_trials=200)
        assert stats.haircut_pct is not None
        assert 0.55 <= stats.haircut_pct <= 0.60

    def test_insignificant_edge_haircut_to_zero(self) -> None:
        stats = compute_deflated(_unit_sample(50, 0.05), n_trials=1000)
        assert stats.haircut_sharpe == pytest.approx(0.0)


class TestDsr:
    def test_none_at_single_trial(self) -> None:
        stats = compute_deflated(_unit_sample(100, 0.3))
        assert stats.sr0 is None and stats.dsr is None and stats.minbtl_years is None

    def test_strictly_decreasing_in_trials(self) -> None:
        pnls = _unit_sample(150, 0.25)
        dsrs = [compute_deflated(pnls, n_trials=k).dsr for k in (2, 5, 20, 100)]
        assert all(d is not None for d in dsrs)
        assert all(a > b for a, b in itertools.pairwise(dsrs))

    def test_sr0_positive_and_grows(self) -> None:
        pnls = _unit_sample(150, 0.25)
        s5 = compute_deflated(pnls, n_trials=5).sr0
        s50 = compute_deflated(pnls, n_trials=50).sr0
        assert s5 is not None and s50 is not None and 0 < s5 < s50

    def test_expected_max_uses_euler_mascheroni(self) -> None:
        # Direct formula check for N=45 (the AMS example's inner term).
        n = 45
        emax = (1 - EULER_MASCHERONI) * norm_ppf(1 - 1 / n) + EULER_MASCHERONI * norm_ppf(
            1 - 1 / (n * math.e)
        )
        assert emax == pytest.approx(math.sqrt(5.0), abs=0.03)


class TestSqn:
    def test_equals_tstat_below_cap(self) -> None:
        pnls = _unit_sample(80, 0.2)
        stats = compute_deflated(pnls)
        t = pnls.mean() / pnls.std(ddof=1) * math.sqrt(80)
        assert stats.sqn == pytest.approx(t, abs=1e-12)
        assert stats.sqn_capped == pytest.approx(t, abs=1e-12)  # n < 100

    def test_cap_at_100(self) -> None:
        pnls = _unit_sample(400, 0.2)
        stats = compute_deflated(pnls)
        assert stats.sqn_capped == pytest.approx(0.2 * 10, abs=1e-9)  # sqrt(100)
        assert stats.sqn == pytest.approx(0.2 * 20, abs=1e-9)  # sqrt(400)


class TestContracts:
    @pytest.mark.parametrize(
        ("symbol", "root"),
        [
            ("MNQ", "MNQ"),
            ("MNQH26", "MNQ"),
            ("MES1!", "MES"),
            ("/ES", "ES"),
            ("ESZ5", "ES"),
            ("nq", "NQ"),
        ],
    )
    def test_resolution(self, symbol: str, root: str) -> None:
        spec = resolve_contract(symbol)
        assert spec is not None and spec.root == root

    def test_micro_never_matches_mini(self) -> None:
        assert resolve_contract("MES").tick_value == 1.25
        assert resolve_contract("ES").tick_value == 12.50

    def test_unknown_is_none(self) -> None:
        assert resolve_contract("CL") is None


class TestChi2:
    """gammq/chi2_sf anchors (M9): standard chi-squared critical values."""

    @pytest.mark.parametrize(
        ("x", "df", "p"),
        [
            (3.841, 1, 0.05),
            (11.0705, 5, 0.05),
            (18.307, 10, 0.05),
            (23.209, 10, 0.01),
            (0.0, 5, 1.0),
        ],
    )
    def test_critical_values(self, x: float, df: int, p: float) -> None:
        from quantlab.metrics.deflate import chi2_sf

        assert chi2_sf(x, df) == pytest.approx(p, abs=2e-4)

    def test_monotone_decreasing_in_x(self) -> None:
        from quantlab.metrics.deflate import chi2_sf

        values = [chi2_sf(x, 5) for x in (0.5, 2.0, 5.0, 12.0, 30.0)]
        assert all(a > b for a, b in itertools.pairwise(values))

    def test_domain_errors(self) -> None:
        from quantlab.metrics.deflate import gammq

        with pytest.raises(ValueError):
            gammq(0.0, 1.0)
        with pytest.raises(ValueError):
            gammq(1.0, -1.0)


class TestDegenerateZeroVariance:
    def test_constant_loser_reports_negative_infinity(self) -> None:
        """A log losing the same amount every trade must not look flat (F37)."""
        pnls = np.full(20, -50.0)
        stats = compute_deflated(pnls)
        assert stats.sr_per_trade == float("-inf")
        assert stats.sqn == float("-inf")
        assert stats.psr == 0.0

    def test_constant_winner_beats_any_finite_benchmark(self) -> None:
        """PSR of a zero-variance winner compares Sharpe, not dollars (F36)."""
        pnls = np.full(20, 0.5)  # mean $0.50 < any benchmark > 0.5 in the old units mixup
        assert compute_psr(pnls, sr_benchmark=2.0) == 1.0
        assert compute_psr(np.full(20, -0.5), sr_benchmark=-2.0) == 0.0

    def test_zero_mean_zero_variance_neutral(self) -> None:
        pnls = np.zeros(20)
        stats = compute_deflated(pnls)
        assert stats.sr_per_trade == 0.0 and stats.psr == 0.0
