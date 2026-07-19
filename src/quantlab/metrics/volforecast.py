"""Volatility forecasting and clustering tests for daily PnL series.

Estimator policy (research-grounded, see docs/research-notes.md):
- EWMA/RiskMetrics with lambda=0.94 is the DEFAULT — the J.P. Morgan
  RiskMetrics Technical Document (4th ed., 1996) daily convention, and
  the restricted IGARCH(1,1) special case. Half-life ~ 11 days.
- GARCH(1,1) (Bollerslev 1986) is offered only for logs >= 250 days:
  MLE is negatively biased and unstable in small samples, with ~500
  observations the recommended floor (Hwang & Valls Pereira, European
  Journal of Finance, 2006). Estimation uses variance targeting
  (Engle & Mezrich 1996): omega = uncond_var*(1 - alpha - beta), so
  only (alpha, beta) are optimized (hand-rolled Nelder-Mead), with
  automatic fallback to EWMA on non-convergence or alpha+beta >= 1.
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

from quantlab.metrics.deflate import chi2_sf

DEFAULT_LAMBDA = 0.94  # RiskMetrics 1996 daily decay
GARCH_MIN_OBS = 250  # hard floor; < 500 still warns (Hwang & Valls Pereira 2006)
GARCH_STABLE_OBS = 500


@dataclass(frozen=True, slots=True)
class VolForecastResult:
    method: str  # "ewma" | "garch11"
    lam: float | None  # EWMA decay (None for garch11)
    omega: float | None
    alpha: float | None
    beta: float | None
    converged: bool
    fallback_reason: str | None
    n_days: int
    seed_var: float
    burn_in: int
    sigma: list[float]  # one-step-ahead sigma[t]; NaN inside burn-in


@dataclass(frozen=True, slots=True)
class ClusteringTests:
    n_days: int
    arch_lm_stat: float
    arch_lm_p: float
    arch_lm_lags: int
    mcleod_li_stat: float
    mcleod_li_p: float
    mcleod_li_lags: int
    clustered: bool  # either test significant at 5%


def ewma_sigma_path(
    day_pnl: np.ndarray, lam: float = DEFAULT_LAMBDA, burn_in: int = 20
) -> VolForecastResult:
    """One-step-ahead EWMA sigma path: sigma2[t] = lam*sigma2[t-1] +
    (1-lam)*r[t-1]^2, seeded from the first `burn_in` days."""
    r = np.asarray(day_pnl, dtype=float)
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
        method="ewma",
        lam=lam,
        omega=None,
        alpha=None,
        beta=None,
        converged=True,
        fallback_reason=None,
        n_days=n,
        seed_var=seed_var,
        burn_in=burn,
        sigma=[float(s) for s in sigma],
    )


def _garch_nll(r2: np.ndarray, uncond: float, alpha: float, beta: float) -> float:
    """Gaussian negative log-likelihood of GARCH(1,1) under variance
    targeting; r2 = squared (zero-mean) returns."""
    omega = uncond * (1.0 - alpha - beta)
    if omega <= 0.0 or alpha < 0.0 or beta < 0.0 or alpha + beta >= 1.0:
        return math.inf
    var = uncond
    nll = 0.0
    for t in range(r2.size):
        if t > 0:
            var = omega + alpha * r2[t - 1] + beta * var
        if var <= 0.0:
            return math.inf
        nll += math.log(var) + r2[t] / var
    return 0.5 * nll


def _nelder_mead(
    fn, x0: np.ndarray, step: float = 0.05, tol: float = 1e-7, max_iter: int = 400
) -> tuple[np.ndarray, float, bool]:
    """Minimal 2D Nelder-Mead (reflection/expansion/contraction/shrink)."""
    dim = x0.size
    simplex = [x0.copy()]
    for i in range(dim):
        v = x0.copy()
        v[i] += step
        simplex.append(v)
    values = [fn(v) for v in simplex]
    for _ in range(max_iter):
        order = np.argsort(values)
        simplex = [simplex[i] for i in order]
        values = [values[i] for i in order]
        if abs(values[-1] - values[0]) < tol:
            return simplex[0], values[0], True
        centroid = np.mean(simplex[:-1], axis=0)
        reflected = centroid + (centroid - simplex[-1])
        fr = fn(reflected)
        if fr < values[0]:
            expanded = centroid + 2.0 * (centroid - simplex[-1])
            fe = fn(expanded)
            simplex[-1], values[-1] = (expanded, fe) if fe < fr else (reflected, fr)
        elif fr < values[-2]:
            simplex[-1], values[-1] = reflected, fr
        else:
            contracted = centroid + 0.5 * (simplex[-1] - centroid)
            fc = fn(contracted)
            if fc < values[-1]:
                simplex[-1], values[-1] = contracted, fc
            else:
                for i in range(1, dim + 1):
                    simplex[i] = simplex[0] + 0.5 * (simplex[i] - simplex[0])
                    values[i] = fn(simplex[i])
    return simplex[0], values[0], False


def fit_garch11(
    day_pnl: np.ndarray, min_obs: int = GARCH_MIN_OBS, burn_in: int = 20
) -> VolForecastResult:
    """Variance-targeted GARCH(1,1) fit; falls back to EWMA whenever the
    fit is unreliable (small sample, non-convergence, IGARCH boundary)."""
    r = np.asarray(day_pnl, dtype=float)
    n = r.size
    if n < min_obs:
        ewma = ewma_sigma_path(r, burn_in=burn_in)
        return VolForecastResult(
            **{
                **_asdict(ewma),
                "fallback_reason": f"{n} days < {min_obs} minimum for GARCH MLE "
                "(Hwang & Valls Pereira 2006)",
            }
        )
    r2 = r**2
    uncond = float(np.mean(r2))
    if uncond <= 0.0:
        ewma = ewma_sigma_path(r, burn_in=burn_in)
        return VolForecastResult(
            **{**_asdict(ewma), "fallback_reason": "degenerate (zero-variance) series"}
        )
    best, _nll, converged = _nelder_mead(
        lambda x: _garch_nll(r2, uncond, float(x[0]), float(x[1])),
        np.array([0.08, 0.88]),
    )
    alpha, beta = float(best[0]), float(best[1])
    if not converged or alpha < 0 or beta < 0 or alpha + beta >= 1.0:
        ewma = ewma_sigma_path(r, burn_in=burn_in)
        reason = "optimizer did not converge" if not converged else "alpha+beta >= 1 (IGARCH)"
        return VolForecastResult(**{**_asdict(ewma), "fallback_reason": reason})
    omega = uncond * (1.0 - alpha - beta)
    # One-step-ahead sigma path: recursion runs from t=1 with the
    # unconditional variance as var[0]; values only surface after the
    # burn-in (strict t-1 information throughout).
    sigma = np.full(n, np.nan)
    var = uncond
    for t in range(1, n):
        var = omega + alpha * r2[t - 1] + beta * var
        if t >= burn_in:
            sigma[t] = math.sqrt(max(var, 0.0))
    return VolForecastResult(
        method="garch11",
        lam=None,
        omega=omega,
        alpha=alpha,
        beta=beta,
        converged=True,
        fallback_reason=None
        if n >= GARCH_STABLE_OBS
        else (
            f"fit accepted but {n} days < {GARCH_STABLE_OBS} recommended "
            "(Hwang & Valls Pereira 2006) — treat parameters as noisy"
        ),
        n_days=n,
        seed_var=uncond,
        burn_in=burn_in,
        sigma=[float(s) for s in sigma],
    )


def _asdict(result: VolForecastResult) -> dict:
    import dataclasses

    return dataclasses.asdict(result)


def arch_lm(day_pnl: np.ndarray, lags: int | None = None) -> tuple[float, float, int]:
    """Engle's (1982) ARCH-LM test: regress r^2 on a constant and q own
    lags; T*R^2 ~ chi2(q) under no-ARCH. Returns (stat, p, lags)."""
    r = np.asarray(day_pnl, dtype=float)
    n = r.size
    if lags is None:
        lags = 10 if n >= 100 else 5
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
    r = np.asarray(day_pnl, dtype=float)
    n = r.size
    if lags is None:
        lags = 10 if n >= 100 else 5
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
    lm_stat, lm_p, lm_lags = arch_lm(day_pnl)
    ml_stat, ml_p, ml_lags = mcleod_li(day_pnl)
    return ClusteringTests(
        n_days=int(np.asarray(day_pnl).size),
        arch_lm_stat=lm_stat,
        arch_lm_p=lm_p,
        arch_lm_lags=lm_lags,
        mcleod_li_stat=ml_stat,
        mcleod_li_p=ml_p,
        mcleod_li_lags=ml_lags,
        clustered=lm_p < 0.05 or ml_p < 0.05,
    )
