"""Volatility-targeted sizing: shared recursion + chronological
counterfactual.

Sizing rule (Moreira & Muir, JF 2017; Harvey et al., JPM 2018):
weight_t = clip(target_vol / forecast_vol_t, clip_lo, clip_hi), with the
EWMA/RiskMetrics forecast (lambda=0.94) and the target defaulting to the
trader's OWN median forecast vol so the median weight is 1 — the tool
never injects leverage a prop firm bars. Framing per the literature:
vol targeting is INSURANCE (tail/drawdown reduction, possibly -CAGR;
Cederburg et al. 2020 shows the return-enhancement claim fails
out-of-sample). Whether it improves PROP-FIRM survival under static
dollar limits is a per-log testable hypothesis, not a promise: it helps
only when the trader's losses cluster in high-forecast-vol periods.

`EwmaSizer` is the ONE implementation of the sizing recursion, shared by
the scalar evaluator and the vectorized Monte Carlo (the `breached()`
pattern) — golden equivalence by construction.

Counterfactual caveat (printed on every output): resizing a historical
log assumes the SAME FILLS at linearly scaled size — identical entries,
exits, and timing; ignores sub-contract granularity, margin, and the
psychology of trading larger. `fees` are left untouched because
`Trade.pnl` is already net: linear scaling scales embedded costs
proportionally, exactly the same-fill assumption.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

import numpy as np

from quantlab.metrics.volforecast import DEFAULT_LAMBDA, ewma_sigma_path
from quantlab.prop.config import FirmConfig
from quantlab.schema.trade import DayBoundary, TradeLog

SAME_FILL_CAVEAT = (
    "counterfactual assumes the same fills at linearly scaled size "
    "(identical entries/exits/timing; ignores sub-contract granularity, "
    "margin, and larger-size psychology)"
)


@dataclass(frozen=True, slots=True)
class VolSizingParams:
    lam: float
    target_vol: float
    seed_var: float
    clip_lo: float = 0.5
    clip_hi: float = 1.5
    burn_in: int = 0  # days at weight 1 before sizing activates
    band: float = 0.0  # no-trade band on |delta weight| (counterfactual only)


class EwmaSizer:
    """Broadcast-polymorphic EWMA sizing state: `var` is a float in the
    deterministic evaluator and a (P,) array in the Monte Carlo — the
    identical recursion serves both engines."""

    def __init__(self, params: VolSizingParams, n_paths: int | None = None) -> None:
        self.params = params
        self.day_index = 0
        self.var: float | np.ndarray
        if n_paths is None:
            self.var = float(params.seed_var)
        else:
            self.var = np.full(n_paths, float(params.seed_var))

    def weight(self) -> float | np.ndarray:
        p = self.params
        if self.day_index < p.burn_in:
            return 1.0 if isinstance(self.var, float) else np.ones_like(self.var)
        sigma = np.sqrt(np.maximum(self.var, 1e-300))
        raw = p.target_vol / sigma
        clipped = np.clip(raw, p.clip_lo, p.clip_hi)
        return float(clipped) if isinstance(self.var, float) else clipped

    def update(self, day_pnl_unscaled: float | np.ndarray) -> None:
        """Advance one day using the day's UNSCALED (per-unit-size) PnL —
        the strategy's own volatility, independent of the applied weight."""
        p = self.params
        self.var = p.lam * self.var + (1.0 - p.lam) * np.square(day_pnl_unscaled)
        if isinstance(day_pnl_unscaled, float | int):
            self.var = float(self.var)
        self.day_index += 1


def auto_target_vol(day_pnl: np.ndarray, lam: float = DEFAULT_LAMBDA, burn_in: int = 20) -> float:
    """Median of the log's own EWMA sigma path -> median weight 1 pre-clip."""
    sigma = np.array(ewma_sigma_path(day_pnl, lam=lam, burn_in=burn_in).sigma)
    valid = sigma[~np.isnan(sigma)]
    if valid.size == 0 or float(np.median(valid)) <= 0:
        fallback = float(np.sqrt(np.mean(np.square(day_pnl))))
        return max(fallback, 1e-12)
    return float(np.median(valid))


def resize_log(
    log: TradeLog, boundary: DayBoundary, params: VolSizingParams
) -> tuple[TradeLog, np.ndarray, np.ndarray]:
    """Chronological vol-targeted counterfactual of the source log.

    Returns (resized log, applied weight per day, forecast sigma per
    day). Strict t-1 information; burn-in days trade at weight 1; the
    no-trade band keeps the prior applied weight unless the target
    weight moved by more than `band`.
    """
    days = log.daily_groups(boundary)
    day_pnl = np.array([sum(t.pnl for t in trades) for _, trades in days], dtype=float)
    forecast = ewma_sigma_path(day_pnl, lam=params.lam, burn_in=params.burn_in)
    sigma = np.array(forecast.sigma)

    weights = np.ones(len(days))
    applied = 1.0
    for d in range(len(days)):
        if d < params.burn_in or np.isnan(sigma[d]) or sigma[d] <= 0:
            target_w = 1.0
        else:
            target_w = float(np.clip(params.target_vol / sigma[d], params.clip_lo, params.clip_hi))
        if abs(target_w - applied) > params.band:
            applied = target_w
        weights[d] = applied

    trades = []
    for d, (_, day_trades) in enumerate(days):
        w = weights[d]
        for t in day_trades:
            trades.append(
                dataclasses.replace(
                    t,
                    pnl=t.pnl * w,
                    quantity=t.quantity * w,
                    mae=t.mae * w if t.mae is not None else None,
                    mfe=t.mfe * w if t.mfe is not None else None,
                )
            )
    resized = TradeLog(trades=trades, account_currency=log.account_currency, source=log.source)
    return resized, weights, sigma


@dataclass
class VolTargetCounterfactual:
    lam: float
    target_vol: float
    clip_lo: float
    clip_hi: float
    band: float
    burn_in: int
    avg_weight: float
    weights: list[float]  # per trading day, chronological
    sigma: list[float]
    fixed: dict[str, float]
    targeted: dict[str, float]
    mc_fixed: dict[str, float] | None = None
    mc_targeted: dict[str, float] | None = None
    assumption: str = SAME_FILL_CAVEAT
    warnings: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict:
        return dataclasses.asdict(self)


def _log_stats(log: TradeLog, boundary: DayBoundary) -> dict[str, float]:
    days = log.daily_groups(boundary)
    day_pnl = np.array([sum(t.pnl for t in trades) for _, trades in days], dtype=float)
    equity = np.cumsum(day_pnl)
    peaks = np.maximum.accumulate(np.maximum(equity, 0.0))
    max_dd = float(np.max(peaks - equity)) if equity.size else 0.0
    std = float(day_pnl.std(ddof=1)) if day_pnl.size > 1 else 0.0
    sharpe = float(day_pnl.mean() / std * np.sqrt(252)) if std > 0 else 0.0
    months: dict[str, float] = {}
    for date, trades in days:
        key = f"{date.year}-{date.month:02d}"
        months[key] = months.get(key, 0.0) + sum(t.pnl for t in trades)
    worst_month = float(min(months.values())) if months else 0.0
    return {
        "net": float(day_pnl.sum()),
        "daily_sharpe_ann": sharpe,
        "max_drawdown": max_dd,
        "worst_month": worst_month,
    }


def compute_voltarget(
    log: TradeLog,
    firm: FirmConfig | None = None,
    mc_cfg=None,
    lam: float = DEFAULT_LAMBDA,
    clip: tuple[float, float] = (0.5, 1.5),
    band: float = 0.15,
    burn_in: int = 20,
) -> VolTargetCounterfactual:
    """Fixed-vs-vol-targeted comparison of the source log, with the full
    prop-firm Monte Carlo on both when a firm is given."""
    from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
    from quantlab.schema.trade import FUTURES_DAY

    boundary = firm.day_boundary.to_boundary() if firm is not None else FUTURES_DAY
    days = log.daily_groups(boundary)
    day_pnl = np.array([sum(t.pnl for t in trades) for _, trades in days], dtype=float)
    target = auto_target_vol(day_pnl, lam=lam, burn_in=burn_in)
    seed_var = float(np.mean(day_pnl[: min(burn_in, day_pnl.size)] ** 2))
    params = VolSizingParams(
        lam=lam,
        target_vol=target,
        seed_var=seed_var,
        clip_lo=clip[0],
        clip_hi=clip[1],
        burn_in=min(burn_in, len(days)),
        band=band,
    )
    resized, weights, sigma = resize_log(log, boundary, params)

    warnings: list[str] = []
    if len(days) < 60:
        warnings.append(
            f"only {len(days)} trading days — the EWMA forecast and this "
            "counterfactual are low-confidence below ~60 days"
        )

    mc_fixed = mc_targeted = None
    if firm is not None:
        cfg = mc_cfg or MCConfig(n_paths=2000, seed=42)
        rep_fixed = run_monte_carlo(log, firm, cfg)
        rep_targeted = run_monte_carlo(resized, firm, cfg)
        mc_fixed = {
            "pass_prob": rep_fixed.economics.pass_prob,
            "expected_net": rep_fixed.economics.expected_net,
            "risk_of_ruin_funded": rep_fixed.economics.risk_of_ruin_funded,
        }
        mc_targeted = {
            "pass_prob": rep_targeted.economics.pass_prob,
            "expected_net": rep_targeted.economics.expected_net,
            "risk_of_ruin_funded": rep_targeted.economics.risk_of_ruin_funded,
        }

    return VolTargetCounterfactual(
        lam=lam,
        target_vol=target,
        clip_lo=clip[0],
        clip_hi=clip[1],
        band=band,
        burn_in=params.burn_in,
        avg_weight=float(weights.mean()),
        weights=[float(w) for w in weights],
        sigma=[float(s) for s in sigma],
        fixed=_log_stats(log, boundary),
        targeted=_log_stats(resized, boundary),
        mc_fixed=mc_fixed,
        mc_targeted=mc_targeted,
        warnings=warnings,
    )
