"""Deflated performance statistics: PSR, DSR, MinTRL, MinBTL, haircut
Sharpe, and SQN.

The multiple-testing honesty layer. Sources (formulas verified against
the primary papers, July 2026):
- Bailey & Lopez de Prado, "The Sharpe Ratio Efficient Frontier",
  Journal of Risk 15(2), 2012 — PSR, MinTRL.
- Bailey & Lopez de Prado, "The Deflated Sharpe Ratio", Journal of
  Portfolio Management 40(5), 2014 — DSR / expected-max-Sharpe SR0.
- Bailey, Borwein, Lopez de Prado & Zhu, "Pseudo-Mathematics and
  Financial Charlatanism", Notices of the AMS 61(5), 2014 — MinBTL.
- Harvey & Liu, "Backtesting", Journal of Portfolio Management 42(1),
  2015 — Bonferroni haircut Sharpe (the only variant computable
  without the full cross-section of tried strategies).
- Van Tharp — SQN (System Quality Number), the retail-standard label
  for the t-statistic of mean trade PnL, conventionally capped at
  n=100 ("SQN 100").

All Sharpe ratios here are PER-TRADE (per-observation), never
annualized — Bailey & LdP's distributions are stated for the
per-period estimator. Kurtosis is RAW (normal = 3), not excess.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

EULER_MASCHERONI = 0.5772156649015329


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# Acklam's rational approximation for the inverse normal CDF
# (peter.acklam algorithm, |relative error| < 1.15e-9) — avoids a
# scipy dependency for the handful of quantiles needed here.
_A = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_B = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_C = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_D = (
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
)
_P_LOW = 0.02425


def _gser(a: float, x: float) -> float:
    """Series representation of the regularized lower incomplete gamma
    P(a, x) (Numerical Recipes 6.2), for x < a + 1."""
    gln = math.lgamma(a)
    ap = a
    total = 1.0 / a
    delt = total
    for _ in range(500):
        ap += 1.0
        delt *= x / ap
        total += delt
        if abs(delt) < abs(total) * 3e-12:
            break
    return total * math.exp(-x + a * math.log(x) - gln)


def _gcf(a: float, x: float) -> float:
    """Continued fraction for the regularized upper incomplete gamma
    Q(a, x) via modified Lentz (Numerical Recipes 6.2), for x >= a + 1."""
    gln = math.lgamma(a)
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b if b != 0 else 1.0 / tiny
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < 3e-12:
            break
    return math.exp(-x + a * math.log(x) - gln) * h


def gammq(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a, x) = 1 - P(a, x).

    Numerical Recipes 6.2 (series + modified-Lentz continued fraction),
    ~1e-10 accuracy — the chi-squared survival function without scipy,
    matching the precision standard of the Acklam ppf above."""
    if a <= 0.0:
        raise ValueError(f"gammq requires a > 0 (got {a})")
    if x < 0.0:
        raise ValueError(f"gammq requires x >= 0 (got {x})")
    if x == 0.0:
        return 1.0
    if x < a + 1.0:
        return 1.0 - _gser(a, x)
    return _gcf(a, x)


def chi2_sf(x: float, df: float) -> float:
    """Chi-squared survival function P(X > x) with df degrees of freedom."""
    return gammq(df / 2.0, x / 2.0)


def norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam)."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    if p < _P_LOW:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )
    if p > 1.0 - _P_LOW:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )
    q = p - 0.5
    r = q * q
    return ((((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]) * q) / (
        ((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0
    )


@dataclass(frozen=True, slots=True)
class DeflatedStats:
    n: int
    sr_per_trade: float
    skew: float
    kurtosis_raw: float
    psr: float  # P(true SR > 0), non-normality and sample-size adjusted
    min_trl: float | None  # trades needed to trust SR > 0 at 95% (None: SR <= 0)
    sqn: float  # t-stat of mean trade PnL (uncapped)
    sqn_capped: float  # Van Tharp convention: sqrt(min(n,100)) scaling
    n_trials: int
    # Multiple-testing outputs — only when n_trials > 1:
    sr0: float | None  # expected max SR under the null across n_trials
    dsr: float | None  # PSR evaluated against sr0
    minbtl_years: float | None  # min backtest length to support SR=1.0/yr claim
    haircut_sharpe: float | None  # Harvey-Liu Bonferroni-adjusted per-trade SR
    haircut_pct: float | None  # fraction of SR removed by the haircut


def _moments(pnls: np.ndarray) -> tuple[float, float, float, float]:
    """(mean, std_ddof1, skew, raw kurtosis) via population moment ratios
    (the estimator convention in Bailey & Lopez de Prado)."""
    mean = float(pnls.mean())
    # ptp==0: N identical values are exactly degenerate even when float
    # noise leaves std at ~1e-14 (the +/-inf convention must apply).
    std = 0.0 if np.ptp(pnls) == 0.0 else float(pnls.std(ddof=1))
    centered = pnls - mean
    m2 = float(np.mean(centered**2))
    if m2 == 0.0:
        return mean, std, 0.0, 3.0
    skew = float(np.mean(centered**3) / m2**1.5)
    kurt = float(np.mean(centered**4) / m2**2)
    return mean, std, skew, kurt


def _psr_denominator(sr: float, skew: float, kurt: float) -> float:
    inner = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2
    # Extreme skew/kurtosis with a large SR can push the variance
    # estimate negative (outside the approximation's domain) — floor it.
    return math.sqrt(max(inner, 1e-12))


def _degenerate_sr(mean: float) -> float:
    """Sharpe of a zero-variance series: +/-inf by the sign of the edge."""
    if mean > 0:
        return math.inf
    return -math.inf if mean < 0 else 0.0


def compute_psr(pnls: np.ndarray, sr_benchmark: float = 0.0) -> float:
    """Probabilistic Sharpe Ratio: P(true SR > sr_benchmark)."""
    n = pnls.size
    if n < 3:
        return 0.0
    _, std, skew, kurt = _moments(pnls)
    if std == 0.0:
        # Compare the degenerate SHARPE (+/-inf, not the dollar mean) to
        # the benchmark — mean vs sr_benchmark mixes units.
        return 1.0 if _degenerate_sr(float(pnls.mean())) > sr_benchmark else 0.0
    sr = float(pnls.mean()) / std
    z = (sr - sr_benchmark) * math.sqrt(n - 1) / _psr_denominator(sr, skew, kurt)
    return norm_cdf(z)


def compute_deflated(pnls: np.ndarray, n_trials: int = 1) -> DeflatedStats:
    """Full deflated-statistics block for one trade log.

    n_trials is the USER-DECLARED number of strategy variants tried
    before settling on this one — the honesty lever. With only one log
    the variance of trial Sharpes is unobservable; it is proxied by the
    SR estimator's own variance (1 - g3*SR + (g4-1)/4*SR^2)/(n-1)
    (documented assumption; understates deflation when the true trial
    spread was wider).
    """
    n = pnls.size
    if n < 3:
        raise ValueError(f"need >= 3 trades for deflated stats (got {n})")
    if n_trials < 1:
        raise ValueError(f"n_trials must be >= 1 (got {n_trials})")
    mean, std, skew, kurt = _moments(pnls)
    if std == 0.0:
        # Three-way degenerate values: an all-losing constant log is -inf,
        # not 0.0 (which would be indistinguishable from break-even).
        sr = sqn = _degenerate_sr(mean)
        psr = compute_psr(pnls)
        return DeflatedStats(
            n=n,
            sr_per_trade=sr,
            skew=skew,
            kurtosis_raw=kurt,
            psr=psr,
            min_trl=None,
            sqn=sqn,
            sqn_capped=sqn,
            n_trials=n_trials,
            sr0=None,
            dsr=None,
            minbtl_years=None,
            haircut_sharpe=None,
            haircut_pct=None,
        )
    sr = mean / std
    denom = _psr_denominator(sr, skew, kurt)
    # THE PSR implementation (compute_psr) — a second inline copy of the
    # formula here could drift from the public function.
    psr = compute_psr(pnls)

    # MinTRL (Bailey-LdP 2012): observations needed for PSR(0) >= 95%.
    z95 = norm_ppf(0.95)
    min_trl = 1.0 + denom**2 * (z95 / sr) ** 2 if sr > 0 else None

    # SQN: t-stat of mean trade PnL. Without per-trade initial risk the
    # R-multiple reduces to raw PnL (identical when risk is constant —
    # SQN is scale-invariant); Van Tharp caps the sqrt(n) factor at 100.
    sqn = mean / std * math.sqrt(n)
    sqn_capped = mean / std * math.sqrt(min(n, 100))

    sr0 = dsr = minbtl_years = haircut_sharpe = haircut_pct = None
    if n_trials > 1:
        var_sr = denom**2 / (n - 1)  # documented proxy for V[SR_trials]
        emax = (1.0 - EULER_MASCHERONI) * norm_ppf(1.0 - 1.0 / n_trials) + (
            EULER_MASCHERONI
        ) * norm_ppf(1.0 - 1.0 / (n_trials * math.e))
        sr0 = math.sqrt(var_sr) * emax
        dsr = compute_psr(pnls, sr_benchmark=sr0)
        # MinBTL (AMS 2014): years of backtest needed before an
        # ANNUALIZED Sharpe of 1.0 stops being explainable as the
        # expected maximum over n_trials random tries.
        minbtl_years = emax**2
        # Harvey-Liu Bonferroni haircut on the per-trade SR. Defined for a
        # POSITIVE candidate Sharpe only — abs(t) on a losing strategy would
        # sign-flip its "adjusted" edge to significantly positive.
        if sr > 0:
            t_stat = sr * math.sqrt(n)
            p_single = 2.0 * (1.0 - norm_cdf(t_stat))
            p_adj = min(p_single * n_trials, 1.0)
            z_adj = norm_ppf(1.0 - p_adj / 2.0)
            haircut_sharpe = max(z_adj, 0.0) / math.sqrt(n)
            haircut_pct = 1.0 - haircut_sharpe / sr

    return DeflatedStats(
        n=n,
        sr_per_trade=sr,
        skew=skew,
        kurtosis_raw=kurt,
        psr=psr,
        min_trl=min_trl,
        sqn=sqn,
        sqn_capped=sqn_capped,
        n_trials=n_trials,
        sr0=sr0,
        dsr=dsr,
        minbtl_years=minbtl_years,
        haircut_sharpe=haircut_sharpe,
        haircut_pct=haircut_pct,
    )
