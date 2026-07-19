"""Rich terminal rendering of a MonteCarloReport."""

from __future__ import annotations

from typing import Any

import numpy as np
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from quantlab.prop.outcomes import OUTCOME_ACTIVE, MonteCarloReport
from quantlab.report.format import money, pct


def _money(value: float) -> str:
    return money(value, decimals=0)


_pct = pct


def render_report(report: MonteCarloReport, console: Console) -> None:
    eco = report.economics
    header = (
        f"[bold]{report.firm_display}[/bold] — {report.n_paths:,} paths, "
        f"{report.bootstrap} bootstrap, seed {report.seed}, "
        f"source {report.source_trades} trades / {report.source_days} days, "
        f"fidelity {report.fidelity}"
    )
    console.print(Panel.fit(header))

    for warning in report.warnings:
        console.print(f"[yellow]warning:[/yellow] {warning}")

    table = Table(title="Challenge")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for ph in report.phases:
        p = float(np.mean(ph.passed))
        table.add_row(f"{ph.phase}: pass probability", _pct(p))
        for rule, frac in ph.fail_breakdown().items():
            table.add_row(f"  failed by {rule}", _pct(frac))
    table.add_row("overall pass probability", _pct(eco.pass_prob))
    table.add_row("  Wilson 95% CI", f"{_pct(eco.pass_prob_ci[0])} to {_pct(eco.pass_prob_ci[1])}")
    if eco.time_to_pass_quantiles:
        q = eco.time_to_pass_quantiles
        table.add_row(
            "trading days to pass (p25/p50/p75)",
            f"{q['p25']:.0f} / {q['p50']:.0f} / {q['p75']:.0f}",
        )
    console.print(table)

    funded = Table(title="Funded phase")
    funded.add_column("Metric")
    funded.add_column("Value", justify="right")
    funded.add_row(
        "survives horizon", _pct(float(np.mean(report.funded.outcome == OUTCOME_ACTIVE)))
    )
    funded.add_row("probability of >=1 payout", _pct(eco.p_payout))
    funded.add_row("risk of ruin (blown before any payout)", _pct(eco.risk_of_ruin_funded))
    for rule, frac in report.funded.fail_breakdown().items():
        funded.add_row(f"  failed by {rule}", _pct(frac))
    if eco.payout_quantiles:
        q = eco.payout_quantiles
        funded.add_row(
            "payouts received (p5/p50/p95)",
            f"{_money(q['p5'])} / {_money(q['p50'])} / {_money(q['p95'])}",
        )
    if eco.days_to_first_payout_quantiles:
        q = eco.days_to_first_payout_quantiles
        funded.add_row("trading days to first payout (p50)", f"{q['p50']:.0f}")
    console.print(funded)

    econ = Table(title="Economics (per attempt)")
    econ.add_column("Metric")
    econ.add_column("Value", justify="right")
    econ.add_row("expected eval fees", _money(eco.expected_fees_per_attempt))
    econ.add_row("expected cost to get funded", _money(eco.expected_cost_to_funded))
    econ.add_row("expected payout value per funded account", _money(eco.expected_gross_payout))
    econ.add_row("[bold]expected net (single attempt)[/bold]", _money(eco.expected_net))
    econ.add_row("P(net > 0)", _pct(eco.p_net_positive))
    econ.add_row("VaR 95% / CVaR 95%", f"{_money(eco.var_95)} / {_money(eco.cvar_95)}")
    for k, ev in eco.ev_with_resets.items():
        econ.add_row(f"campaign EV, up to {k} attempt(s)", _money(ev))
    console.print(econ)


def render_reality(rc: Any, console: Console) -> None:
    """Terminal rendering of a RealityCheck (quant stress)."""
    costs = rc.costs
    cost_table = Table(title="Cost stress (added round-turn cost per contract)")
    cost_table.add_column("Scenario")
    cost_table.add_column("Added $/RT", justify="right")
    cost_table.add_column("Expectancy", justify="right")
    cost_table.add_column("PF", justify="right")
    has_mc = any(p.mc_pass_prob is not None for p in costs.grid)
    if has_mc:
        cost_table.add_column("MC pass prob", justify="right")
        cost_table.add_column("MC EV", justify="right")
    for p in costs.grid:
        row = [
            p.label,
            money(p.added_rt_per_contract),
            money(p.expectancy),
            "inf" if p.profit_factor == float("inf") else f"{p.profit_factor:.2f}",
        ]
        if has_mc:
            row.append(pct(p.mc_pass_prob) if p.mc_pass_prob is not None else "-")
            row.append(money(p.mc_expected_net) if p.mc_expected_net is not None else "-")
        cost_table.add_row(*row)
    console.print(cost_table)
    if costs.survives_ticks_rt is not None:
        console.print(
            f"breakeven: edge survives up to [bold]{costs.survives_ticks_rt:.1f} ticks[/bold] "
            f"of added round-turn cost (tick={money(costs.tick_value)}, "
            f"source {costs.tick_source})"
        )

    decay = rc.decay
    decay_table = Table(title="Edge decay panel")
    decay_table.add_column("Check")
    decay_table.add_column("Value", justify="right")
    decay_table.add_row(
        "First half expectancy",
        f"{money(decay.first_half.expectancy)} (n={decay.first_half.n})",
    )
    decay_table.add_row(
        "Second half expectancy",
        f"{money(decay.second_half.expectancy)} (n={decay.second_half.n})",
    )
    decay_table.add_row("HAC trend slope", f"{decay.hac.slope:+.3f}/trade (p={decay.hac.p:.3f})")
    decay_table.add_row("Mann-Kendall", f"z={decay.mk.z:.2f} (p={decay.mk.p:.3f})")
    decay_table.add_row(
        "Runs test",
        f"z={decay.runs.z:.2f} (p={decay.runs.p:.3f}) "
        f"[{decay.runs.n_wins}W/{decay.runs.n_losses}L, {decay.runs.runs} runs]",
    )
    if decay.wfe is not None:
        decay_table.add_row("Walk-forward efficiency", f"{decay.wfe:.2f} (>0.5 acceptable)")
    decay_table.add_row("DECAYED", "[red]YES[/red]" if decay.decayed else "[green]no[/green]")
    console.print(decay_table)

    d = rc.deflated
    stat_table = Table(title="Deflated statistics")
    stat_table.add_column("Statistic")
    stat_table.add_column("Value", justify="right")
    stat_table.add_row("Per-trade Sharpe", f"{d.sr_per_trade:.4f}")
    stat_table.add_row("PSR (P(true SR > 0))", pct(d.psr))
    stat_table.add_row("SQN (t-stat)", f"{d.sqn:.2f}")
    stat_table.add_row("SQN (Van Tharp, n capped 100)", f"{d.sqn_capped:.2f}")
    if d.min_trl is not None:
        stat_table.add_row("MinTRL (trades to trust SR>0 @95%)", f"{d.min_trl:.0f}")
    if d.dsr is not None:
        stat_table.add_row(f"DSR ({d.n_trials} trials declared)", pct(d.dsr))
    if d.minbtl_years is not None:
        stat_table.add_row("MinBTL (yrs to support SR=1/yr)", f"{d.minbtl_years:.1f}")
    if d.haircut_pct is not None:
        stat_table.add_row("Harvey-Liu haircut", pct(d.haircut_pct))
    console.print(stat_table)

    dd = rc.drawdown
    dd_table = Table(title="Permutation drawdown (assumes trade independence)")
    dd_table.add_column("Statistic")
    dd_table.add_column("Value", justify="right")
    dd_table.add_row("Median max drawdown", money(dd.median_max_dd))
    dd_table.add_row("95th percentile max drawdown", money(dd.p95_max_dd))
    if dd.p_ruin is not None:
        dd_table.add_row(f"P(ruin at {money(dd.ruin_capital or 0)})", pct(dd.p_ruin))
    console.print(dd_table)

    if rc.haircuts:
        hc_table = Table(title="Literature-anchored decay scenarios (never a fitted half-life)")
        hc_table.add_column("Haircut")
        hc_table.add_column("Anchor")
        hc_table.add_column("Expectancy", justify="right")
        if any(h.mc_pass_prob is not None for h in rc.haircuts):
            hc_table.add_column("MC pass prob", justify="right")
            hc_table.add_column("MC EV", justify="right")
        for h in rc.haircuts:
            row = [pct(h.haircut), h.label, money(h.expectancy)]
            if h.mc_pass_prob is not None:
                row.append(pct(h.mc_pass_prob))
                row.append(money(h.mc_expected_net) if h.mc_expected_net is not None else "-")
            hc_table.add_row(*row)
        console.print(hc_table)

    if rc.clustering is not None:
        cl = rc.clustering
        cl_table = Table(title="Volatility clustering (daily PnL)")
        cl_table.add_column("Test")
        cl_table.add_column("Statistic", justify="right")
        cl_table.add_column("p-value", justify="right")
        cl_table.add_row(
            f"ARCH-LM ({cl.arch_lm_lags} lags)", f"{cl.arch_lm_stat:.2f}", f"{cl.arch_lm_p:.4f}"
        )
        cl_table.add_row(
            f"McLeod-Li ({cl.mcleod_li_lags} lags)",
            f"{cl.mcleod_li_stat:.2f}",
            f"{cl.mcleod_li_p:.4f}",
        )
        if not cl.tested:
            verdict = f"[yellow]insufficient data ({cl.n_days} days)[/yellow]"
        elif cl.clustered:
            verdict = "[red]CLUSTERED[/red]"
        else:
            verdict = "[green]no clustering[/green]"
        cl_table.add_row("Verdict", verdict, "")
        console.print(cl_table)

    if rc.voltarget is not None:
        vt = rc.voltarget
        vt_table = Table(
            title=f"Vol-target counterfactual (lambda={vt.lam:g}, "
            f"clip [{vt.clip_lo:g}, {vt.clip_hi:g}], avg weight {vt.avg_weight:.2f})"
        )
        vt_table.add_column("Metric")
        vt_table.add_column("Fixed size", justify="right")
        vt_table.add_column("Vol-targeted", justify="right")
        vt_table.add_row("Net PnL", money(vt.fixed["net"]), money(vt.targeted["net"]))
        vt_table.add_row(
            "Daily Sharpe (ann.)",
            f"{vt.fixed['daily_sharpe_ann']:.2f}",
            f"{vt.targeted['daily_sharpe_ann']:.2f}",
        )
        vt_table.add_row(
            "Max drawdown", money(vt.fixed["max_drawdown"]), money(vt.targeted["max_drawdown"])
        )
        vt_table.add_row(
            "Worst month", money(vt.fixed["worst_month"]), money(vt.targeted["worst_month"])
        )
        if vt.mc_fixed is not None and vt.mc_targeted is not None:
            vt_table.add_row(
                "MC pass prob", pct(vt.mc_fixed["pass_prob"]), pct(vt.mc_targeted["pass_prob"])
            )
            vt_table.add_row(
                "MC expected net",
                money(vt.mc_fixed["expected_net"]),
                money(vt.mc_targeted["expected_net"]),
            )
            vt_table.add_row(
                "MC risk of ruin",
                pct(vt.mc_fixed["risk_of_ruin_funded"]),
                pct(vt.mc_targeted["risk_of_ruin_funded"]),
            )
        console.print(vt_table)
        console.print(f"[dim]{vt.assumption}[/dim]")

    for warning in rc.warnings:
        console.print(Panel(warning, style="yellow", title="warning"))
