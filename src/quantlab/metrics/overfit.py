"""Overfit tells: named boolean flags with explanations.

Each flag is a red flag, not a proof — the report shows triggered flags
prominently and lists untriggered ones as passed checks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from quantlab.metrics.core import Metrics
from quantlab.metrics.decay import DecayPanel, compute_decay
from quantlab.schema.trade import TradeLog


@dataclass(frozen=True, slots=True)
class OverfitFlag:
    name: str
    triggered: bool
    explanation: str


def _smooth_curve(log: TradeLog, m: Metrics) -> OverfitFlag:
    pnls = np.array([t.pnl for t in log.trades])
    n = pnls.size
    triggered = False
    r2 = 0.0
    if n >= 10:
        equity = np.cumsum(pnls)
        x = np.arange(n, dtype=float)
        coeffs = np.polyfit(x, equity, 1)
        resid = equity - np.polyval(coeffs, x)
        ss_tot = float(((equity - equity.mean()) ** 2).sum())
        r2 = 1.0 - float((resid**2).sum()) / ss_tot if ss_tot > 0 else 1.0
        triggered = r2 > 0.98 and n < 200
    return OverfitFlag(
        "suspiciously_smooth_equity",
        triggered,
        f"equity-curve linearity R^2={r2:.3f} with {n} trades"
        + (
            " — real edges wobble; curves this clean at this sample size usually mean curve-fit"
            if triggered
            else ""
        ),
    )


def _zero_crossing(m: Metrics) -> OverfitFlag:
    lo, hi = m.expectancy_ci95
    triggered = lo < 0 < hi
    return OverfitFlag(
        "expectancy_ci_straddles_zero",
        triggered,
        f"95% CI of per-trade expectancy [{lo:.2f}, {hi:.2f}]"
        + (" — the edge is statistically indistinguishable from zero" if triggered else ""),
    )


def _top5_concentration(log: TradeLog, m: Metrics) -> OverfitFlag:
    pnls = np.array([t.pnl for t in log.trades])
    wins = np.sort(pnls[pnls > 0])
    top5 = float(wins[-5:].sum()) if wins.size else 0.0
    triggered = False
    detail = "top-5 winners vs net profit: n/a (net <= 0)"
    if m.net_profit > 0:
        share = top5 / m.net_profit
        triggered = share > 0.5
        detail = f"top-5 winners are {share:.0%} of net profit"
    return OverfitFlag(
        "top5_trade_concentration",
        triggered,
        detail + (" — the edge lives in a handful of outliers" if triggered else ""),
    )


def _breakeven_frontier(m: Metrics) -> OverfitFlag:
    if m.payoff_ratio in (0.0, float("inf")):
        distance = 1.0
    else:
        distance = abs(m.win_rate * (1 + m.payoff_ratio) - 1.0)
    triggered = distance < 0.02
    return OverfitFlag(
        "hugging_breakeven_frontier",
        triggered,
        f"win-rate/payoff distance from the breakeven frontier: {distance:.3f}"
        + (" — the strategy sits within noise of p*W=(1-p)*L" if triggered else ""),
    )


def _symbol_month_concentration(log: TradeLog, m: Metrics) -> OverfitFlag:
    triggered = False
    detail = "profit spread across symbol-months"
    if m.net_profit > 0 and len(log.trades) >= 20:
        buckets: dict[tuple[str, str], float] = {}
        for t in log.trades:
            key = (t.symbol, t.exit_time.strftime("%Y-%m"))
            buckets[key] = buckets.get(key, 0.0) + t.pnl
        if len(buckets) >= 3:
            best_key = max(buckets, key=lambda k: buckets[k])
            share = buckets[best_key] / m.net_profit
            triggered = share > 0.5
            detail = (
                f"largest symbol-month {best_key[0]} {best_key[1]} contributed "
                f"{share:.0%} of net profit"
            )
    return OverfitFlag(
        "single_symbol_month_dependency",
        triggered,
        detail + (" — one regime is carrying the whole edge" if triggered else ""),
    )


def _edge_decay(panel: DecayPanel) -> OverfitFlag:
    triggered = panel.decayed
    detail = (
        f"HAC trend slope {panel.hac.slope:+.3f}/trade (p={panel.hac.p:.3f}); "
        f"expectancy first half {panel.first_half.expectancy:.2f} -> "
        f"second half {panel.second_half.expectancy:.2f}"
    )
    return OverfitFlag(
        "edge_decaying_over_log",
        triggered,
        detail
        + (
            " — the edge is significantly weaker in the recent half; live results "
            "start where the log ENDS, not at its average"
            if triggered
            else ""
        ),
    )


def _mk_downtrend(panel: DecayPanel) -> OverfitFlag:
    triggered = panel.mk.z < 0 and panel.mk.p < 0.05
    return OverfitFlag(
        "mann_kendall_downtrend",
        triggered,
        f"Mann-Kendall z={panel.mk.z:.2f} (p={panel.mk.p:.3f})"
        + (" — non-parametric confirmation of a deteriorating trend" if triggered else ""),
    )


def _streak_dependence(panel: DecayPanel) -> OverfitFlag:
    triggered = panel.runs.z < 0 and panel.runs.p < 0.05
    return OverfitFlag(
        "streak_dependence",
        triggered,
        f"runs test z={panel.runs.z:.2f} (p={panel.runs.p:.3f}), "
        f"{panel.runs.runs} runs over {panel.runs.n_wins}W/{panel.runs.n_losses}L"
        + (
            " — wins/losses cluster; iid-based analyses (permutation drawdowns, "
            "iid bootstrap) are OPTIMISTIC — prefer the block-bootstrap results"
            if triggered
            else ""
        ),
    )


def overfit_flags(log: TradeLog, m: Metrics, decay: DecayPanel | None = None) -> list[OverfitFlag]:
    panel = decay if decay is not None else compute_decay(log)
    return [
        _smooth_curve(log, m),
        _zero_crossing(m),
        _top5_concentration(log, m),
        _breakeven_frontier(m),
        _symbol_month_concentration(log, m),
        _edge_decay(panel),
        _mk_downtrend(panel),
        _streak_dependence(panel),
    ]
