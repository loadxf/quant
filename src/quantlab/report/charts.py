"""Plotly figure builders for the HTML report.

Colors follow the validated reference palette (dataviz method): one blue
sequential ramp for magnitude/bands, the blue<->red diverging pair for
polarity (EV waterfall), single-hue marks elsewhere, recessive chrome.
One axis per chart; plotly's hover layer supplies tooltips.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import plotly.graph_objects as go

from quantlab.prop.outcomes import OUTCOME_BREACHED, EconomicsSummary, PhaseOutcome
from quantlab.schema.trade import FUTURES_DAY, DayBoundary, TradeLog

# Reference palette (light mode)
BLUE = "#2a78d6"
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"]
RED = "#e34948"
NEUTRAL = "#f0efec"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_MUTED = "#898781"
GRID = "#e1e0d9"

_LAYOUT = dict(
    template=None,
    paper_bgcolor=SURFACE,
    plot_bgcolor=SURFACE,
    font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif', color=INK, size=13),
    margin=dict(l=60, r=24, t=48, b=48),
    hovermode="x unified",
    showlegend=False,
)


def _base(title: str, xtitle: str, ytitle: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(title=dict(text=title, font=dict(size=15)), **_LAYOUT)
    fig.update_xaxes(title=xtitle, gridcolor=GRID, zeroline=False, color=INK_MUTED)
    fig.update_yaxes(title=ytitle, gridcolor=GRID, zeroline=False, color=INK_MUTED)
    return fig


def fig_equity_curve(log: TradeLog, starting_equity: float) -> go.Figure:
    equity = starting_equity + np.cumsum([t.pnl for t in log.trades])
    times = [t.exit_time for t in log.trades]
    fig = _base("Source equity curve (trade closes)", "", "equity ($)")
    fig.add_trace(
        go.Scatter(x=times, y=equity, mode="lines", line=dict(color=BLUE, width=2), name="equity")
    )
    return fig


def fig_fan(phase: PhaseOutcome, title: str) -> go.Figure:
    """Percentile bands (p5-p95) over sampled equity paths + faint spaghetti.

    Bands are computed over paths still alive at each step (resolved paths
    go NaN) — a documented survivorship framing; the fail histogram below
    carries the attrition story.
    """
    samples = phase.equity_samples
    # Trim to the last step where any sampled path is still alive (avoids
    # all-NaN percentile slices once every sample has resolved).
    alive_any = ~np.all(np.isnan(samples), axis=0)
    horizon = int(alive_any.nonzero()[0].max()) + 1 if alive_any.any() else 1
    samples = samples[:, :horizon]
    x = np.arange(1, horizon + 1)
    bands = {q: np.nanpercentile(samples, q, axis=0) for q in (5, 25, 50, 75, 95)}
    fig = _base(title, "trading day", "equity ($)")
    fill_pairs = [(5, 95, BLUE_RAMP[0]), (25, 75, BLUE_RAMP[1])]
    for lo, hi, color in fill_pairs:
        fig.add_trace(
            go.Scatter(
                x=np.concatenate([x, x[::-1]]),
                y=np.concatenate([bands[hi], bands[lo][::-1]]),
                fill="toself",
                fillcolor=color,
                line=dict(width=0),
                hoverinfo="skip",
                name=f"p{lo}-p{hi}",
                showlegend=False,
            )
        )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=bands[50],
            mode="lines",
            line=dict(color=BLUE_RAMP[4], width=2),
            name="median",
        )
    )
    for row in samples[:20]:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=row,
                mode="lines",
                line=dict(color=BLUE_RAMP[3], width=0.6),
                opacity=0.25,
                hoverinfo="skip",
                showlegend=False,
            )
        )
    fig.add_hline(y=phase.initial_balance, line=dict(color=INK_MUTED, width=1, dash="dot"))
    return fig


def fig_end_day_hist(phase: PhaseOutcome, title: str) -> go.Figure:
    fig = _base(title, "trading day resolved", "paths")
    breached_days = phase.end_day[phase.outcome == OUTCOME_BREACHED]
    passed_days = phase.end_day[phase.passed]
    if passed_days.size:
        fig.add_trace(
            go.Histogram(x=passed_days, name="passed", marker_color=BLUE, opacity=0.85, nbinsx=40)
        )
    if breached_days.size:
        fig.add_trace(
            go.Histogram(
                x=breached_days, name="breached", marker_color=RED, opacity=0.85, nbinsx=40
            )
        )
    fig.update_layout(barmode="overlay", showlegend=True, legend=dict(orientation="h"))
    return fig


def fig_payout_hist(received: np.ndarray) -> go.Figure:
    fig = _base("Net received per funded account", "total received ($)", "paths")
    fig.add_trace(go.Histogram(x=received, marker_color=BLUE, nbinsx=50))
    return fig


def fig_ev_waterfall(eco: EconomicsSummary) -> go.Figure:
    """Expected-value decomposition of a single attempt (diverging pair).

    Bars come from economics.ev_decomposition — the path-exact linear
    pieces of expected_net — so they SUM to the headline number exactly
    (re-deriving pass_prob * E[...] here would differ by Monte Carlo
    covariance and the total would not add up on screen)."""
    dec = eco.ev_decomposition
    if dec is None:
        # Every EconomicsSummary construction sets the field; a missing one
        # is a regression that must fail loudly, not render bars that
        # silently do not sum to the headline EV.
        raise ValueError("EconomicsSummary.ev_decomposition is missing")
    labels = ["eval fees", "payout value (x pass prob)", "activation (x pass prob)"]
    values: list[float | None] = [dec["eval_fees"], dec["payout_value"], dec["activation"]]
    if dec.get("overheads"):
        labels.append("funded overheads (x pass prob)")
        values.append(dec["overheads"])
    labels.append("net EV")
    values.append(None)
    fig = go.Figure(
        go.Waterfall(
            x=labels,
            y=values,
            measure=["relative"] * (len(labels) - 1) + ["total"],
            decreasing=dict(marker=dict(color=RED)),
            increasing=dict(marker=dict(color=BLUE)),
            totals=dict(marker=dict(color=NEUTRAL, line=dict(color=INK_MUTED, width=1))),
            connector=dict(line=dict(color=GRID, width=1)),
        )
    )
    fig.update_layout(title=dict(text="Expected value per attempt", font=dict(size=15)), **_LAYOUT)
    fig.update_yaxes(title="$", gridcolor=GRID, color=INK_MUTED)
    fig.update_xaxes(color=INK_MUTED)
    return fig


def fig_daily_pnl_hist(log: TradeLog, boundary: DayBoundary = FUTURES_DAY) -> go.Figure:
    daily = [sum(t.pnl for t in trades) for _, trades in log.daily_groups(boundary)]
    fig = _base("Daily PnL distribution", "day PnL ($)", "days")
    fig.add_trace(go.Histogram(x=daily, marker_color=BLUE, nbinsx=40))
    fig.add_vline(x=0, line=dict(color=INK_MUTED, width=1, dash="dot"))
    return fig


def fig_cost_sweep(stress: Any) -> go.Figure:
    """Expectancy (and MC pass prob when present) vs added round-turn cost."""
    grid = sorted(
        (p for p in stress.grid if not p.label.startswith("stop-stress")),
        key=lambda p: p.added_rt_per_contract,
    )
    added = [p.added_rt_per_contract for p in grid]
    fig = _base("Edge vs added cost per round turn", "added $/contract RT", "expectancy ($/trade)")
    fig.add_trace(
        go.Scatter(
            x=added,
            y=[p.expectancy for p in grid],
            mode="lines+markers",
            line=dict(color=BLUE, width=2),
            name="expectancy",
        )
    )
    fig.add_hline(y=0.0, line=dict(color=INK_MUTED, width=1, dash="dot"))
    mc_points = [p for p in grid if p.mc_pass_prob is not None]
    if mc_points:
        fig.add_trace(
            go.Scatter(
                x=[p.added_rt_per_contract for p in mc_points],
                y=[p.mc_pass_prob * 100 for p in mc_points],
                mode="lines+markers",
                line=dict(color=RED, width=2, dash="dash"),
                name="MC pass prob (%)",
                yaxis="y2",
            )
        )
        fig.update_layout(
            yaxis2=dict(
                title="MC pass prob (%)",
                overlaying="y",
                side="right",
                range=[0, 100],
                color=RED,
                showgrid=False,
            ),
            showlegend=True,
        )
    return fig


def fig_rolling_expectancy(panel: Any) -> go.Figure:
    """Rolling expectancy with the half-split marker."""
    fig = _base(
        f"Rolling expectancy ({panel.rolling_window}-trade window)",
        "trade #",
        "expectancy ($/trade)",
    )
    if panel.rolling:
        x = np.arange(panel.rolling_window - 1, panel.rolling_window - 1 + len(panel.rolling))
        fig.add_trace(
            go.Scatter(
                x=x, y=panel.rolling, mode="lines", line=dict(color=BLUE, width=2), name="rolling"
            )
        )
        half = panel.first_half.n
        fig.add_vline(x=half, line=dict(color=INK_MUTED, width=1, dash="dash"))
    fig.add_hline(y=0.0, line=dict(color=INK_MUTED, width=1, dash="dot"))
    return fig


def fig_drawdown_permutation(dd: Any) -> go.Figure:
    """Permutation max-DD estimates. Deliberately NOT overlaid with the
    prop MC's funded drawdowns: those cover a different horizon (252
    simulated days vs the log's n trades) and possibly different sizing,
    so a side-by-side would misread as pure streak risk."""
    fig = _base(
        "Permutation max drawdown (order-shuffle of the log's trades)", "", "max drawdown ($)"
    )
    labels = ["p50", "p95"]
    values = [dd.median_max_dd, dd.p95_max_dd]
    fig.add_trace(go.Bar(x=labels, y=values, marker_color=[BLUE_RAMP[2], BLUE_RAMP[4]]))
    return fig


def fig_vol_weights(vt: Any) -> go.Figure:
    """Vol-target counterfactual: applied weight path + forecast sigma."""
    fig = _base("Vol-target sizing path (counterfactual)", "trading day", "applied weight")
    x = np.arange(len(vt.weights))
    fig.add_trace(
        go.Scatter(x=x, y=vt.weights, mode="lines", line=dict(color=BLUE, width=2), name="weight")
    )
    fig.add_hline(y=1.0, line=dict(color=INK_MUTED, width=1, dash="dot"))
    sigma = np.array(vt.sigma, dtype=float)
    if np.isfinite(sigma).any():
        fig.add_trace(
            go.Scatter(
                x=x,
                y=sigma,
                mode="lines",
                line=dict(color=RED, width=1.5, dash="dash"),
                name="forecast sigma ($/day)",
                yaxis="y2",
            )
        )
        fig.update_layout(
            yaxis2=dict(
                title="forecast sigma ($/day)",
                overlaying="y",
                side="right",
                color=RED,
                showgrid=False,
            ),
            showlegend=True,
        )
    return fig


def fig_scale_frontier(fr: Any) -> go.Figure:
    """Scale frontier: EV (left axis) + pass prob / funded ruin (right)."""
    fig = _base("Scale frontier", "position-size multiple", "expected net ($)")
    scales = [p.scale for p in fr.points]
    fig.add_trace(
        go.Scatter(
            x=scales,
            y=[p.expected_net for p in fr.points],
            mode="lines+markers",
            line=dict(color=BLUE, width=2),
            name="expected net ($)",
        )
    )
    fig.add_hline(y=0.0, line=dict(color=INK_MUTED, width=1, dash="dot"))
    fig.add_trace(
        go.Scatter(
            x=scales,
            y=[p.pass_prob for p in fr.points],
            mode="lines+markers",
            line=dict(color=INK_MUTED, width=1.5, dash="dash"),
            name="pass prob",
            yaxis="y2",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=scales,
            y=[p.risk_of_ruin_funded for p in fr.points],
            mode="lines+markers",
            line=dict(color=RED, width=1.5, dash="dash"),
            name="funded ruin",
            yaxis="y2",
        )
    )
    fig.add_vline(x=fr.best_ev_scale, line=dict(color=BLUE, width=1, dash="dot"))
    fig.update_layout(
        yaxis2=dict(
            title="probability",
            overlaying="y",
            side="right",
            range=[0, 1],
            color=INK_MUTED,
            showgrid=False,
        ),
        showlegend=True,
    )
    return fig
