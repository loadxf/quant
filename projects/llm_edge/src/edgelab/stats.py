"""Statistics for the pre-registered gates (protocol.md section 6).

Formula sources (verified in Phase A topic multiple_testing, see
research/prior_art/multiple_testing.md):
- Probabilistic / Deflated Sharpe Ratio: Bailey & Lopez de Prado (2014),
  "The Deflated Sharpe Ratio". All SR inputs to PSR/DSR are PER-PERIOD
  (daily here), not annualized; kurtosis is raw (normal = 3).
- Reality-Check-style bootstrap: White (2000) with the Politis-Romano (1994)
  stationary bootstrap.
- Newey-West HAC t-statistic on the mean daily return.
"""

from __future__ import annotations

from numbers import Integral, Real

import numpy as np
import pandas as pd
from scipy import stats as sps

EULER_GAMMA = 0.5772156649015329
TRADING_DAYS = 252


def sharpe_ratio(returns: pd.Series, annualize: bool = True) -> float:
    r = pd.Series(returns).dropna()
    if not np.isfinite(r.to_numpy(dtype=float)).all():
        raise ValueError("returns contain infinite values")
    if len(r) < 3 or r.std(ddof=1) == 0:
        return float("nan")
    sr = r.mean() / r.std(ddof=1)
    return float(sr * np.sqrt(TRADING_DAYS)) if annualize else float(sr)


def newey_west_tstat(returns: pd.Series, lags: int = 10) -> float:
    """t-stat of the mean daily return with a Newey-West (Bartlett) HAC variance."""
    r = pd.Series(returns).dropna().to_numpy(dtype=float)
    if (
        not isinstance(lags, Integral)
        or isinstance(lags, bool)
        or lags < 0
        or not np.isfinite(r).all()
    ):
        raise ValueError("lags must be non-negative and returns finite")
    lags = int(lags)
    n = len(r)
    if n < lags + 2:
        return float("nan")
    e = r - r.mean()
    gamma0 = float(e @ e) / n
    variance = gamma0
    for lag in range(1, lags + 1):
        gamma = float(e[lag:] @ e[:-lag]) / n
        variance += 2.0 * (1.0 - lag / (lags + 1.0)) * gamma
    se_mean = np.sqrt(variance / n)
    return float(r.mean() / se_mean) if se_mean > 0 else float("nan")


def probabilistic_sharpe_ratio(
    sr_hat: float, n: int, skew: float, kurt: float, sr_star: float = 0.0
) -> float:
    """PSR = Phi( (SR - SR*) sqrt(n-1) / sqrt(1 - g3*SR + (g4-1)/4 * SR^2) ).

    ``sr_hat`` and ``sr_star`` are per-period (NOT annualized); ``kurt`` is raw
    kurtosis (3 for a normal distribution).
    """
    denom_sq = 1.0 - skew * sr_hat + (kurt - 1.0) / 4.0 * sr_hat**2
    if denom_sq <= 0 or n < 2:
        return float("nan")
    z = (sr_hat - sr_star) * np.sqrt(n - 1.0) / np.sqrt(denom_sq)
    return float(sps.norm.cdf(z))


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """E[max SR] over N independent trials whose SRs have variance var_sr
    (per-period units), under the null of zero true SR:
    SR0 = sqrt(V) * ( (1-gamma) * Phi^-1(1 - 1/N) + gamma * Phi^-1(1 - 1/(N e)) ).
    """
    if not isinstance(n_trials, Integral) or isinstance(n_trials, bool) or n_trials < 1:
        raise ValueError("n_trials must be a positive integer")
    n_trials = int(n_trials)
    if n_trials < 2:
        return 0.0
    if not np.isfinite(var_sr) or var_sr <= 0:
        return float("nan")
    return float(
        np.sqrt(var_sr)
        * (
            (1.0 - EULER_GAMMA) * sps.norm.ppf(1.0 - 1.0 / n_trials)
            + EULER_GAMMA * sps.norm.ppf(1.0 - 1.0 / (n_trials * np.e))
        )
    )


def deflated_sharpe_ratio(returns: pd.Series, n_trials: int, var_sr_trials: float) -> dict:
    """DSR = PSR evaluated at the expected-max-SR benchmark.

    ``var_sr_trials`` is the variance of ANNUALIZED net SRs across all ledger
    trials (as recorded); it is converted to per-period units here.
    """
    r = pd.Series(returns).dropna()
    sr_daily = sharpe_ratio(r, annualize=False)
    var_daily = var_sr_trials / TRADING_DAYS
    sr0 = expected_max_sharpe(n_trials, var_daily)
    dsr = probabilistic_sharpe_ratio(
        sr_daily, len(r), float(sps.skew(r)), float(sps.kurtosis(r, fisher=False)), sr0
    )
    return {
        "sr_annualized": sharpe_ratio(r),
        "sr_daily": sr_daily,
        "n_obs": len(r),
        "n_trials": int(n_trials),
        "var_sr_trials_annualized": float(var_sr_trials),
        "sr0_daily_benchmark": sr0,
        "dsr": dsr,
    }


def stationary_bootstrap_indices(n: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    """Politis-Romano stationary bootstrap index sequence of length n:
    geometric block lengths with mean ``mean_block``, wrapping circularly."""
    if (
        not isinstance(n, Integral)
        or isinstance(n, bool)
        or n < 1
        or not isinstance(mean_block, Real)
        or isinstance(mean_block, bool)
        or not np.isfinite(mean_block)
        or mean_block <= 0
    ):
        raise ValueError("n and mean_block must be positive")
    n = int(n)
    p = min(1.0, 1.0 / mean_block)
    idx = np.empty(n, dtype=int)
    t = rng.integers(0, n)
    for i in range(n):
        idx[i] = t
        if rng.random() < p:
            t = rng.integers(0, n)
        else:
            t = (t + 1) % n
    return idx


def reality_check_pvalue(
    candidate_returns: pd.DataFrame,
    n_boot: int = 1000,
    mean_block: float = 20.0,
    seed: int = 7,
) -> dict:
    """White (2000)-style Reality Check on a family of candidate return series.

    H0: the best candidate has zero expected return. The pre-registered
    statistic is the maximum daily Sharpe across candidates. Bootstrap:
    stationary bootstrap of the recentered panel.
    """
    if (
        not isinstance(n_boot, Integral)
        or isinstance(n_boot, bool)
        or n_boot < 1
        or not isinstance(mean_block, Real)
        or isinstance(mean_block, bool)
        or not np.isfinite(mean_block)
        or mean_block <= 0
        or not isinstance(seed, Integral)
        or isinstance(seed, bool)
    ):
        raise ValueError("n_boot and mean_block must be positive")
    n_boot = int(n_boot)
    seed = int(seed)
    if candidate_returns.shape[1] < 1:
        raise ValueError("candidate return panel needs at least one column")
    # Common support prevents short histories from acquiring synthetic
    # zero-return observations that improve their apparent risk profile.
    panel = candidate_returns.dropna(how="any")
    filled = panel.to_numpy(dtype=float)
    if not np.isfinite(filled).all():
        raise ValueError("candidate returns contain infinite values")
    n = filled.shape[0]
    if n < 60:
        return {"p_value": float("nan"), "n_obs": n}
    means = filled.mean(axis=0)
    standard_deviations = filled.std(axis=0, ddof=1)
    observed = np.divide(
        means,
        standard_deviations,
        out=np.full_like(means, -np.inf),
        where=standard_deviations > 0,
    )
    stat = observed.max()
    if not np.isfinite(stat):
        return {"p_value": float("nan"), "n_obs": n}
    centered = filled - means
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(n_boot):
        idx = stationary_bootstrap_indices(n, mean_block, rng)
        sample = centered[idx]
        boot_means = sample.mean(axis=0)
        boot_std = sample.std(axis=0, ddof=1)
        boot_sharpes = np.divide(
            boot_means,
            boot_std,
            out=np.full_like(boot_means, -np.inf),
            where=boot_std > 0,
        )
        if boot_sharpes.max() >= stat:
            exceed += 1
    return {
        "p_value": (exceed + 1) / (n_boot + 1),
        "statistic": float(stat),
        "statistic_name": "maximum_daily_sharpe",
        "n_candidates": filled.shape[1],
        "n_obs": n,
        "n_boot": n_boot,
    }
