"""Plotly figure builders for the HTML report.

Colors follow the validated reference palette (dataviz method): one blue
sequential ramp for magnitude/bands, the blue<->red diverging pair for
polarity (EV waterfall), single-hue marks elsewhere, recessive chrome.
One axis per chart; plotly's hover layer supplies tooltips.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from quantlab.prop.outcomes import OUTCOME_BREACHED, EconomicsSummary, PhaseOutcome
from quantlab.schema.trade import TradeLog

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
    fig = _base("Payouts received per funded account (after split)", "total received ($)", "paths")
    fig.add_trace(go.Histogram(x=received, marker_color=BLUE, nbinsx=50))
    return fig


def fig_ev_waterfall(eco: EconomicsSummary, activation: float) -> go.Figure:
    """Expected-value decomposition of a single attempt (diverging pair)."""
    fees = -eco.expected_fees_per_attempt
    act = -eco.pass_prob * activation
    gross = eco.pass_prob * eco.expected_gross_payout
    fig = go.Figure(
        go.Waterfall(
            x=["eval fees", "activation (x pass prob)", "payout value (x pass prob)", "net EV"],
            y=[fees, act, gross, None],
            measure=["relative", "relative", "relative", "total"],
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


def fig_daily_pnl_hist(log: TradeLog) -> go.Figure:
    daily = [sum(t.pnl for t in trades) for _, trades in log.daily_groups()]
    fig = _base("Daily PnL distribution", "day PnL ($)", "days")
    fig.add_trace(go.Histogram(x=daily, marker_color=BLUE, nbinsx=40))
    fig.add_vline(x=0, line=dict(color=INK_MUTED, width=1, dash="dot"))
    return fig
