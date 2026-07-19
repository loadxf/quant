"""Rich terminal rendering of a MonteCarloReport."""

from __future__ import annotations

import numpy as np
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from quantlab.prop.outcomes import OUTCOME_ACTIVE, MonteCarloReport


def _money(value: float) -> str:
    if value == float("inf"):
        return "inf"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


def _pct(value: float) -> str:
    return f"{value:.1%}"


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
