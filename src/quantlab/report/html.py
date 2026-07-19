"""Self-contained single-file HTML report (plotly.js inlined once)."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import numpy as np
import plotly.io as pio
from jinja2 import Environment

from quantlab import __version__
from quantlab.metrics.core import Metrics
from quantlab.metrics.scorecard import Verdict
from quantlab.prop.config import FirmConfig
from quantlab.prop.outcomes import MonteCarloReport
from quantlab.report import charts
from quantlab.report.format import money, pct
from quantlab.schema.trade import TradeLog

_money = money
_pct = pct


def _fig_html(fig, include_js: bool) -> str:
    return pio.to_html(
        fig,
        full_html=False,
        include_plotlyjs="inline" if include_js else False,
        default_height=380,
        config={"displayModeBar": False, "responsive": True},
    )


def _metric_rows(m: Metrics) -> list[tuple[str, str]]:
    return [
        ("Trades / trading days", f"{m.trade_count} / {m.trading_days}"),
        ("Net profit", _money(m.net_profit)),
        ("Win rate", _pct(m.win_rate)),
        ("Avg win / avg loss", f"{_money(m.avg_win)} / {_money(m.avg_loss)}"),
        ("Payoff ratio", f"{m.payoff_ratio:.2f}"),
        (
            "Expectancy (95% CI)",
            f"{_money(m.expectancy)}  [{_money(m.expectancy_ci95[0])}, "
            f"{_money(m.expectancy_ci95[1])}]",
        ),
        ("Profit factor", f"{m.profit_factor:.2f}"),
        ("Max drawdown", f"{_money(m.max_drawdown)} ({_pct(m.max_drawdown_pct)})"),
        ("Sharpe / Sortino (daily, ann.)", f"{m.sharpe:.2f} / {m.sortino:.2f}"),
        ("MAR", f"{m.mar:.2f}"),
        ("Longest losing streak", str(m.longest_losing_streak)),
        ("Best day share of net", _pct(m.best_day_share)),
    ]


def _prop_context(mc: MonteCarloReport, firm: FirmConfig) -> dict:
    """The SIMULATED FirmConfig is passed in — re-resolving by name would
    crash for user-YAML firms and could silently render a preset's rules."""
    eco = mc.economics
    challenge_rows: list[tuple[str, str]] = []
    for ph in mc.phases:
        challenge_rows.append((f"{ph.phase}: pass probability", _pct(float(np.mean(ph.passed)))))
        for rule, frac in ph.fail_breakdown().items():
            challenge_rows.append((f"— failed by {rule}", _pct(frac)))
    challenge_rows.append(("overall pass probability", _pct(eco.pass_prob)))
    challenge_rows.append(
        ("Wilson 95% CI", f"{_pct(eco.pass_prob_ci[0])} to {_pct(eco.pass_prob_ci[1])}")
    )
    if eco.time_to_pass_quantiles:
        q = eco.time_to_pass_quantiles
        challenge_rows.append(
            (
                "trading days to pass (p25/p50/p75)",
                f"{q['p25']:.0f} / {q['p50']:.0f} / {q['p75']:.0f}",
            )
        )

    funded_rows = [
        ("probability of >=1 payout", _pct(eco.p_payout)),
        ("risk of ruin (blown before any payout)", _pct(eco.risk_of_ruin_funded)),
    ]
    for rule, frac in mc.funded.fail_breakdown().items():
        funded_rows.append((f"— failed by {rule}", _pct(frac)))
    if eco.days_to_first_payout_quantiles:
        funded_rows.append(
            (
                "trading days to first payout (p50)",
                f"{eco.days_to_first_payout_quantiles['p50']:.0f}",
            )
        )

    econ_rows = [
        ("expected eval fees per attempt", _money(eco.expected_fees_per_attempt)),
        ("expected cost to get funded", _money(eco.expected_cost_to_funded)),
        ("expected payout value per funded account", _money(eco.expected_gross_payout)),
        ("expected net (single attempt)", _money(eco.expected_net)),
        ("P(net > 0)", _pct(eco.p_net_positive)),
        ("VaR 95% / CVaR 95%", f"{_money(eco.var_95)} / {_money(eco.cvar_95)}"),
    ]
    econ_rows += [
        (f"campaign EV, up to {k} attempt(s)", _money(ev)) for k, ev in eco.ev_with_resets.items()
    ]

    prop_charts = [
        _fig_html(
            charts.fig_fan(mc.phases[0], f"Challenge equity paths — {mc.phases[0].phase}"), False
        ),
        _fig_html(charts.fig_end_day_hist(mc.phases[0], "Challenge resolution days"), False),
        _fig_html(charts.fig_fan(mc.funded, "Funded equity paths"), False),
    ]
    if mc.funded.total_withdrawn is not None:
        received = mc.funded.total_withdrawn * firm.payout.profit_split
        prop_charts.append(_fig_html(charts.fig_payout_hist(received), False))
    prop_charts.append(_fig_html(charts.fig_ev_waterfall(eco, firm.fees.activation), False))

    rules_lines = [f"account size: {money(firm.account_size, decimals=0)}"]
    for phase_cfg in [*firm.phases, firm.funded]:
        rules_lines.append(f"\n[{phase_cfg.name}]")
        if phase_cfg.profit_target is not None:
            rules_lines.append(f"  profit target: {money(phase_cfg.profit_target, decimals=0)}")
        for spec in phase_cfg.rules:
            rules_lines.append(f"  {spec.model_dump(exclude_none=True)}")
    return {
        "firm_display": mc.firm_display,
        "firm_name": mc.firm_name,
        "verified_as_of": firm.verified_as_of,
        "sources": firm.sources,
        "rules_text": "\n".join(rules_lines),
        "sim_meta": (
            f"{mc.n_paths:,} paths, {mc.bootstrap} bootstrap, seed {mc.seed}, "
            f"challenge scale x{mc.scale_challenge:g}, funded scale x{mc.scale_funded:g}"
        ),
        "challenge_rows": challenge_rows,
        "funded_rows": funded_rows,
        "econ_rows": econ_rows,
        "charts": prop_charts,
    }


def _reality_context(rc: Any) -> dict:
    costs = rc.costs
    d = rc.deflated
    cost_rows = [
        (
            p.label,
            money(p.added_rt_per_contract),
            money(p.expectancy),
            "inf" if p.profit_factor == float("inf") else f"{p.profit_factor:.2f}",
            pct(p.mc_pass_prob) if p.mc_pass_prob is not None else "-",
        )
        for p in costs.grid
    ]
    decay = rc.decay
    decay_rows = [
        ("First half expectancy", f"{money(decay.first_half.expectancy)} (n={decay.first_half.n})"),
        (
            "Second half expectancy",
            f"{money(decay.second_half.expectancy)} (n={decay.second_half.n})",
        ),
        ("HAC trend slope", f"{decay.hac.slope:+.3f}/trade (p={decay.hac.p:.3f})"),
        ("Mann-Kendall", f"z={decay.mk.z:.2f} (p={decay.mk.p:.3f})"),
        (
            "Runs test",
            f"z={decay.runs.z:.2f} (p={decay.runs.p:.3f}, "
            f"{decay.runs.n_wins}W/{decay.runs.n_losses}L)",
        ),
        ("Decayed", "YES" if decay.decayed else "no"),
    ]
    if decay.wfe is not None:
        decay_rows.insert(-1, ("Walk-forward efficiency", f"{decay.wfe:.2f} (>0.5 acceptable)"))
    stat_rows = [
        ("PSR — P(true Sharpe > 0)", pct(d.psr)),
        ("SQN (t-stat / Van Tharp capped)", f"{d.sqn:.2f} / {d.sqn_capped:.2f}"),
    ]
    if d.min_trl is not None:
        stat_rows.append(("MinTRL — trades to trust SR>0 at 95%", f"{d.min_trl:,.0f}"))
    if d.dsr is not None:
        stat_rows.append((f"DSR over {d.n_trials} declared trials", pct(d.dsr)))
    if d.minbtl_years is not None:
        stat_rows.append(("MinBTL — years to support SR=1/yr", f"{d.minbtl_years:.1f}"))
    if d.haircut_pct is not None:
        stat_rows.append(("Harvey-Liu Sharpe haircut", pct(d.haircut_pct)))
    dd = rc.drawdown
    dd_rows = [
        ("Permutation median max DD", money(dd.median_max_dd)),
        ("Permutation p95 max DD", money(dd.p95_max_dd)),
    ]
    if dd.p_ruin is not None:
        dd_rows.append((f"P(ruin at {money(dd.ruin_capital or 0)})", pct(dd.p_ruin)))
    haircut_rows = [
        (
            pct(h.haircut),
            h.label,
            money(h.expectancy),
            pct(h.mc_pass_prob) if h.mc_pass_prob is not None else "-",
        )
        for h in rc.haircuts
    ]
    survives = (
        f"edge survives up to {costs.survives_ticks_rt:.1f} ticks of added round-turn cost "
        f"(tick {money(costs.tick_value)}, {costs.tick_source})"
        if costs.survives_ticks_rt is not None
        else "no positive baseline edge to stress"
    )
    clustering_rows = []
    if rc.clustering is not None:
        cl = rc.clustering
        clustering_rows = [
            (f"ARCH-LM ({cl.arch_lm_lags} lags)", f"{cl.arch_lm_stat:.2f}", f"{cl.arch_lm_p:.4f}"),
            (
                f"McLeod-Li ({cl.mcleod_li_lags} lags)",
                f"{cl.mcleod_li_stat:.2f}",
                f"{cl.mcleod_li_p:.4f}",
            ),
            ("Verdict", "CLUSTERED" if cl.clustered else "no clustering", ""),
        ]
    voltarget_rows = []
    voltarget_note = None
    if rc.voltarget is not None:
        vt = rc.voltarget
        voltarget_rows = [
            ("Net PnL", money(vt.fixed["net"]), money(vt.targeted["net"])),
            (
                "Daily Sharpe (ann.)",
                f"{vt.fixed['daily_sharpe_ann']:.2f}",
                f"{vt.targeted['daily_sharpe_ann']:.2f}",
            ),
            ("Max drawdown", money(vt.fixed["max_drawdown"]), money(vt.targeted["max_drawdown"])),
            ("Worst month", money(vt.fixed["worst_month"]), money(vt.targeted["worst_month"])),
        ]
        if vt.mc_fixed is not None and vt.mc_targeted is not None:
            voltarget_rows += [
                ("MC pass prob", pct(vt.mc_fixed["pass_prob"]), pct(vt.mc_targeted["pass_prob"])),
                (
                    "MC risk of ruin",
                    pct(vt.mc_fixed["risk_of_ruin_funded"]),
                    pct(vt.mc_targeted["risk_of_ruin_funded"]),
                ),
            ]
        voltarget_note = (
            f"lambda={vt.lam:g}, clip [{vt.clip_lo:g}, {vt.clip_hi:g}], "
            f"avg weight {vt.avg_weight:.2f} — {vt.assumption}"
        )
    return {
        "cost_rows": cost_rows,
        "survives": survives,
        "decay_rows": decay_rows,
        "stat_rows": stat_rows,
        "dd_rows": dd_rows,
        "haircut_rows": haircut_rows,
        "clustering_rows": clustering_rows,
        "voltarget_rows": voltarget_rows,
        "voltarget_note": voltarget_note,
        "warnings": rc.warnings,
    }


def build_html_report(
    log: TradeLog,
    metrics: Metrics,
    verdict: Verdict,
    out_path: Path,
    mc: MonteCarloReport | None = None,
    firm: FirmConfig | None = None,
    reality=None,
    title: str = "Strategy report",
) -> Path:
    if (mc is None) != (firm is None):
        raise ValueError("mc and firm must be provided together")
    template_text = (
        resources.files("quantlab.report") / "templates" / "report.html.j2"
    ).read_text()
    template = Environment(autoescape=True).from_string(template_text)

    fidelity_note = (
        "MAE/MFE-refined intraday checks"
        if log.has_excursions
        else "trade-close only — intraday-sensitive prop rules are OPTIMISTIC"
    )
    warnings = list(mc.warnings) if mc else []

    strategy_charts = [
        _fig_html(charts.fig_equity_curve(log, metrics.starting_equity), include_js=True),
        _fig_html(charts.fig_daily_pnl_hist(log), include_js=False),
    ]

    html = template.render(
        title=title,
        subtitle=(
            f"{metrics.trade_count} trades over {metrics.trading_days} trading days "
            f"(source: {log.source}, currency {log.account_currency})"
        ),
        fidelity_note=fidelity_note,
        warnings=warnings,
        verdict=verdict,
        metric_rows=_metric_rows(metrics),
        strategy_charts=strategy_charts,
        prop=_prop_context(mc, firm) if mc and firm else None,
        reality=_reality_context(reality) if reality is not None else None,
        reality_charts=(
            [
                _fig_html(charts.fig_cost_sweep(reality.costs), include_js=False),
                _fig_html(charts.fig_rolling_expectancy(reality.decay), include_js=False),
                _fig_html(charts.fig_drawdown_permutation(reality.drawdown), include_js=False),
            ]
            + (
                [_fig_html(charts.fig_vol_weights(reality.voltarget), include_js=False)]
                if reality.voltarget is not None
                else []
            )
            if reality is not None
            else []
        ),
        version=__version__,
        reproducibility=(
            f"seed {mc.seed}, {mc.n_paths:,} paths, {mc.bootstrap} bootstrap"
            if mc
            else "no simulation in this report"
        ),
    )
    out_path.write_text(html)
    return out_path
