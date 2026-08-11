"""Volatility forecasting and clustering tests for daily PnL series.

Estimator policy (research-grounded, see docs/research-notes.md):
- EWMA/RiskMetrics with lambda=0.94 — the J.P. Morgan RiskMetrics
  Technical Document (4th ed., 1996) daily convention, and the
  restricted IGARCH(1,1) special case. Half-life ~ 11 days. It is the
  ONLY estimator: GARCH(1,1) MLE is negatively biased and unstable at
  trade-log sample sizes (Hwang & Valls Pereira 2006 recommend ~500
  observations), so a fitter would be dead weight for this tool's
  60-250-day inputs.
- Clustering tests: Engle's (1982) ARCH-LM (T*R^2 ~ chi2(q)) and the
  McLeod-Li (1983) Ljung-Box portmanteau on squared demeaned PnL.

Lookahead discipline: every sigma[t] uses information through day t-1
ONLY. The EWMA seed comes from the first `burn_in` days and sigma is
NaN inside the burn-in (downstream sizing treats that as weight 1);
seeding from full-sample variance would leak the future.

Forecasts here are of the STRATEGY's daily PnL (per unit of size) —
no demeaning (RiskMetrics zero-mean convention; a full-sample mean is
lookahead, and skipping it inflates sigma slightly, which SHRINKS
sizing weights: the safe direction).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from quantlab.errors import QuantLabError
from quantlab.metrics.deflate import chi2_sf

DEFAULT_LAMBDA = 0.94  # RiskMetrics 1996 daily decay


def _validated_series(day_pnl: np.ndarray) -> np.ndarray:
    values = np.asarray(day_pnl, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise QuantLabError("daily PnL must be a finite one-dimensional array")
    return values


@dataclass(frozen=True, slots=True)
class VolForecastResult:
    lam: float  # EWMA decay
    n_days: int
    seed_var: float
    burn_in: int
    sigma: list[float]  # one-step-ahead sigma[t]; NaN inside burn-in


@dataclass(frozen=True, slots=True)
class ClusteringTests:
    n_days: int
    tested: bool  # False: too few days — a SKIPPED test, not a clean one
    arch_lm_stat: float
    arch_lm_p: float
    arch_lm_lags: int
    mcleod_li_stat: float
    mcleod_li_p: float
    mcleod_li_lags: int
    clustered: bool  # either test significant at 5% (False when untested)


def ewma_sigma_path(
    day_pnl: np.ndarray, lam: float = DEFAULT_LAMBDA, burn_in: int = 20
) -> VolForecastResult:
    """One-step-ahead EWMA sigma path: sigma2[t] = lam*sigma2[t-1] +
    (1-lam)*r[t-1]^2, seeded from the first `burn_in` days."""
    if not math.isfinite(lam) or not 0 < lam < 1:
        raise QuantLabError(f"lam must be in (0, 1) (got {lam})")
    if burn_in < 1:
        raise QuantLabError(f"burn_in must be >= 1 (got {burn_in})")
    r = _validated_series(day_pnl)
    n = r.size
    burn = min(burn_in, n)
    seed_var = float(np.mean(r[:burn] ** 2)) if burn > 0 else 0.0
    sigma = np.full(n, np.nan)
    var = seed_var
    for t in range(burn, n):
        if t == burn:
            sigma[t] = math.sqrt(max(var, 0.0))
        else:
            var = lam * var + (1.0 - lam) * r[t - 1] ** 2
            sigma[t] = math.sqrt(max(var, 0.0))
    return VolForecastResult(
        lam=lam,
        n_days=n,
        seed_var=seed_var,
        burn_in=burn,
        sigma=[float(s) for s in sigma],
    )


def arch_lm(day_pnl: np.ndarray, lags: int | None = None) -> tuple[float, float, int]:
    """Engle's (1982) ARCH-LM test: regress r^2 on a constant and q own
    lags; T*R^2 ~ chi2(q) under no-ARCH. Returns (stat, p, lags)."""
    r = _validated_series(day_pnl)
    n = r.size
    if lags is None:
        lags = 10 if n >= 100 else 5
    if lags < 1:
        raise QuantLabError(f"lags must be >= 1 (got {lags})")
    if n < max(30, lags + 10):
        return 0.0, 1.0, lags
    r2 = (r - r.mean()) ** 2
    y = r2[lags:]
    x = np.column_stack([np.ones(y.size)] + [r2[lags - k : n - k] for k in range(1, lags + 1)])
    coef, _, _, _ = np.linalg.lstsq(x, y, rcond=None)
    fitted = x @ coef
    ss_res = float(np.sum((y - fitted) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    stat = y.size * max(r_squared, 0.0)
    return stat, chi2_sf(stat, lags), lags


def mcleod_li(day_pnl: np.ndarray, lags: int | None = None) -> tuple[float, float, int]:
    """McLeod-Li (1983): Ljung-Box portmanteau on squared demeaned PnL.
    Returns (stat, p, lags)."""
    r = _validated_series(day_pnl)
    n = r.size
    if lags is None:
        lags = 10 if n >= 100 else 5
    if lags < 1:
        raise QuantLabError(f"lags must be >= 1 (got {lags})")
    if n < max(30, lags + 10):
        return 0.0, 1.0, lags
    s = (r - r.mean()) ** 2
    s = s - s.mean()
    denom = float(np.sum(s**2))
    if denom <= 0.0:
        return 0.0, 1.0, lags
    stat = 0.0
    for k in range(1, lags + 1):
        rho_k = float(np.sum(s[k:] * s[:-k])) / denom
        stat += rho_k**2 / (n - k)
    stat *= n * (n + 2.0)
    return stat, chi2_sf(stat, lags), lags


def compute_clustering(day_pnl: np.ndarray) -> ClusteringTests:
    n = int(_validated_series(day_pnl).size)
    lm_stat, lm_p, lm_lags = arch_lm(day_pnl)
    ml_stat, ml_p, ml_lags = mcleod_li(day_pnl)
    # A (0, 1) stub from a too-short series is a SKIPPED test — presenting
    # it as "no clustering" would steer short-log users away from the one
    # feature built for them. tested distinguishes the two.
    tested = n >= max(30, min(lm_lags, ml_lags) + 10)
    return ClusteringTests(
        n_days=n,
        tested=tested,
        arch_lm_stat=lm_stat,
        arch_lm_p=lm_p,
        arch_lm_lags=lm_lags,
        mcleod_li_stat=ml_stat,
        mcleod_li_p=ml_p,
        mcleod_li_lags=ml_lags,
        clustered=tested and (lm_p < 0.05 or ml_p < 0.05),
    )
