"""Statistics pins: limiting cases with known closed forms, self-consistency,
and golden regression values. Paper-exact worked-example pins are added after
Phase A verifies the formulas against the original sources (see
research/prior_art/multiple_testing.md).
"""

import numpy as np
import pandas as pd
import pytest
from edgelab.stats import (
    deflated_sharpe_ratio,
    expected_max_sharpe,
    newey_west_tstat,
    probabilistic_sharpe_ratio,
    reality_check_pvalue,
    sharpe_ratio,
    stationary_bootstrap_indices,
)
from scipy import stats as sps


def test_sharpe_known_value():
    r = pd.Series([0.01, -0.01] * 100)
    assert sharpe_ratio(r, annualize=False) == pytest.approx(0.0, abs=1e-12)
    r2 = pd.Series(np.full(252, 0.001) + np.tile([0.001, -0.001], 126))
    daily = r2.mean() / r2.std(ddof=1)
    assert sharpe_ratio(r2) == pytest.approx(daily * np.sqrt(252))


def test_psr_normal_zero_benchmark_closed_form():
    """For normal returns (skew 0, kurt 3): PSR = Phi(SR * sqrt(n-1) / sqrt(1 + SR^2/2))."""
    sr, n = 0.05, 1000
    expected = sps.norm.cdf(sr * np.sqrt(n - 1) / np.sqrt(1 + sr**2 / 2))
    assert probabilistic_sharpe_ratio(sr, n, 0.0, 3.0, 0.0) == pytest.approx(expected, rel=1e-12)


def test_psr_monotonic_in_sr_and_n():
    lo = probabilistic_sharpe_ratio(0.02, 500, 0.0, 3.0)
    hi = probabilistic_sharpe_ratio(0.08, 500, 0.0, 3.0)
    assert hi > lo
    short = probabilistic_sharpe_ratio(0.05, 100, 0.0, 3.0)
    long = probabilistic_sharpe_ratio(0.05, 2000, 0.0, 3.0)
    assert long > short


def test_negative_skew_fat_tails_reduce_psr():
    base = probabilistic_sharpe_ratio(0.05, 500, 0.0, 3.0)
    skewed = probabilistic_sharpe_ratio(0.05, 500, -1.0, 3.0)
    fat = probabilistic_sharpe_ratio(0.05, 500, 0.0, 8.0)
    assert skewed < base
    assert fat < base


def test_expected_max_sharpe_grows_with_trials():
    v = 0.01
    e10 = expected_max_sharpe(10, v)
    e1000 = expected_max_sharpe(1000, v)
    assert 0 < e10 < e1000
    # Sanity against direct simulation of E[max of N iid normals] * sqrt(V).
    rng = np.random.default_rng(0)
    sim = np.sqrt(v) * rng.standard_normal((20000, 100)).max(axis=1).mean()
    assert expected_max_sharpe(100, v) == pytest.approx(sim, rel=0.02)


def test_dsr_penalizes_many_trials():
    rng = np.random.default_rng(5)
    r = pd.Series(rng.normal(0.0008, 0.01, 1500))
    few = deflated_sharpe_ratio(r, n_trials=5, var_sr_trials=0.25)
    many = deflated_sharpe_ratio(r, n_trials=5000, var_sr_trials=0.25)
    assert many["dsr"] < few["dsr"]
    assert many["sr0_daily_benchmark"] > few["sr0_daily_benchmark"]


@pytest.mark.parametrize("trial_variance", [float("nan"), 0.0, -0.1])
def test_dsr_is_unavailable_when_multi_trial_dispersion_is_unestimable(trial_variance):
    rng = np.random.default_rng(51)
    returns = pd.Series(rng.normal(0.002, 0.01, 300))
    result = deflated_sharpe_ratio(returns, n_trials=100, var_sr_trials=trial_variance)
    assert np.isnan(result["sr0_daily_benchmark"])
    assert np.isnan(result["dsr"])


def test_newey_west_iid_matches_ols_t():
    rng = np.random.default_rng(9)
    r = pd.Series(rng.normal(0.001, 0.01, 5000))
    plain_t = r.mean() / (r.std(ddof=0) / np.sqrt(len(r)))
    nw = newey_west_tstat(r, lags=10)
    assert nw == pytest.approx(plain_t, rel=0.1)


def test_stationary_bootstrap_properties():
    rng = np.random.default_rng(1)
    idx = stationary_bootstrap_indices(5000, mean_block=20.0, rng=rng)
    assert idx.min() >= 0 and idx.max() < 5000
    steps = np.diff(idx)
    continuations = ((steps == 1) | (steps == 1 - 5000)).mean()
    assert continuations == pytest.approx(1 - 1 / 20.0, abs=0.02)


@pytest.mark.parametrize("args", [(0, 20.0), (10, 0.0), (10, float("nan"))])
def test_stationary_bootstrap_rejects_invalid_inputs(args):
    with pytest.raises(ValueError, match="positive"):
        stationary_bootstrap_indices(*args, rng=np.random.default_rng(1))


def test_reality_check_null_uniformish_and_power():
    rng = np.random.default_rng(2)
    null_panel = pd.DataFrame(rng.normal(0, 0.01, size=(750, 10)))
    p_null = reality_check_pvalue(null_panel, n_boot=300)["p_value"]
    assert p_null > 0.05  # no true effect: should not reject
    signal_panel = null_panel.copy()
    signal_panel[0] = rng.normal(0.002, 0.01, 750)  # one strong true effect
    p_sig = reality_check_pvalue(signal_panel, n_boot=300)["p_value"]
    assert p_sig < 0.05


def test_reality_check_uses_common_support_and_nonzero_pvalue():
    rng = np.random.default_rng(4)
    panel = pd.DataFrame(rng.normal(size=(100, 2)))
    panel.loc[:19, 1] = np.nan
    out = reality_check_pvalue(panel, n_boot=20, seed=2)
    assert out["n_obs"] == 80
    assert out["p_value"] >= 1 / 21
    assert out["statistic_name"] == "maximum_daily_sharpe"


def test_reality_check_rejects_invalid_bootstrap_count():
    with pytest.raises(ValueError, match="positive"):
        reality_check_pvalue(pd.DataFrame({"a": range(100)}), n_boot=0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n_boot": 4.0},
        {"n_boot": True},
        {"mean_block": True},
        {"seed": 1.5},
    ],
)
def test_reality_check_rejects_non_integer_or_boolean_controls(kwargs):
    with pytest.raises(ValueError, match="positive"):
        reality_check_pvalue(pd.DataFrame({"a": range(100)}), **kwargs)


@pytest.mark.parametrize("lags", [1.5, True])
def test_newey_west_rejects_non_integer_lags(lags):
    with pytest.raises(ValueError, match="lags"):
        newey_west_tstat(pd.Series(np.arange(20.0)), lags=lags)


def test_psr_pinned_to_sharpe_frontier_paper():
    """Bailey & Lopez de Prado, 'The Sharpe Ratio Efficient Frontier', sec. 3
    worked example (verified in research/prior_art/multiple_testing.md C6):
    2y monthly track record, annualized SR 1.59 -> monthly SR 1.59/sqrt(12).
    Normal moments: PSR(0) ~ 0.98; with skew -2.448, kurt 10.164: ~ 0.914;
    with 3 years: ~ 0.954."""
    m = 1.59 / np.sqrt(12)
    assert probabilistic_sharpe_ratio(m, 24, 0.0, 3.0, 0.0) == pytest.approx(0.982, abs=0.002)
    assert probabilistic_sharpe_ratio(m, 24, -2.448, 10.164, 0.0) == pytest.approx(0.914, abs=0.002)
    assert probabilistic_sharpe_ratio(m, 36, -2.448, 10.164, 0.0) == pytest.approx(0.954, abs=0.002)


def test_dsr_pinned_to_deflated_sharpe_paper():
    """Bailey & Lopez de Prado 2014 'The Deflated Sharpe Ratio' worked example
    (verified in multiple_testing.md C9): N=100, V=1/500 (daily units), T=1250,
    skew -3, kurt 10, annualized SR 2.5 (250 d/y) -> SR0 ~ 0.1132, DSR ~ 0.9004."""
    sr0 = expected_max_sharpe(100, 1.0 / 500.0)
    assert sr0 == pytest.approx(0.113176, abs=1e-4)
    sr_daily = 2.5 / np.sqrt(250)
    dsr = probabilistic_sharpe_ratio(sr_daily, 1250, -3.0, 10.0, sr0)
    assert dsr == pytest.approx(0.9004, abs=0.001)


def test_dsr_golden_regression():
    """Golden values frozen at harness build; guards silent formula drift."""
    rng = np.random.default_rng(42)
    r = pd.Series(rng.normal(0.0006, 0.012, 2000))
    out = deflated_sharpe_ratio(r, n_trials=1000, var_sr_trials=0.25)
    assert out["sr_daily"] == pytest.approx(-0.005124434, abs=1e-6)
    assert 0.0 <= out["dsr"] <= 1.0
