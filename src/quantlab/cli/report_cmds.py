"""`quant verdict` and `quant report` commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from quantlab.metrics.core import compute_metrics
from quantlab.metrics.scorecard import compute_scorecard
from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.prop.registry import load_firm
from quantlab.report.html import build_html_report
from quantlab.report.jsonout import combined_json
from quantlab.report.terminal import render_report
from quantlab.schema.io import read_trade_log

console = Console()


def _render_verdict(verdict) -> None:
    table = Table(title=f"The Verdict: {verdict.overall}")
    table.add_column("Pillar")
    table.add_column("Grade", justify="center")
    table.add_column("Detail")
    for pillar in verdict.pillars:
        table.add_row(pillar.name, pillar.grade, pillar.detail)
    console.print(table)
    if verdict.capped_by_sample:
        console.print("[yellow]overall grade capped by the sample-size pillar[/yellow]")
    for flag in verdict.flags:
        marker = "[red]!!:[/red]" if flag.triggered else "[green]ok:[/green]"
        console.print(f"{marker} {flag.name.replace('_', ' ')} — {flag.explanation}")


def register_report_commands(app: typer.Typer) -> None:
    @app.command("verdict")
    def verdict_cmd(
        trades: Path = typer.Argument(..., exists=True, help="trades.parquet"),
        equity: float = typer.Option(50_000.0, "--equity"),
        as_json: bool = typer.Option(False, "--json"),
        html: Path | None = typer.Option(None, "--html", help="Also write an HTML report."),
    ) -> None:
        """Grade the strategy A-F (edge, robustness, risk, sample size)."""
        log = read_trade_log(trades)
        metrics = compute_metrics(log, starting_equity=equity)
        verdict = compute_scorecard(log, metrics)
        if as_json:
            typer.echo(json.dumps(combined_json(metrics, verdict), indent=2, default=str))
        else:
            _render_verdict(verdict)
        if html is not None:
            build_html_report(log, metrics, verdict, html, title="Strategy verdict")
            console.print(f"HTML report written to {html}")

    @app.command("report")
    def report_cmd(
        trades: Path = typer.Argument(..., exists=True, help="trades.parquet"),
        firm_name: str = typer.Option(..., "--firm", help="Preset name or firm YAML path."),
        output: Path = typer.Option(Path("report.html"), "--output", "-o"),
        equity: float | None = typer.Option(
            None, "--equity", help="Starting equity for metrics context (default: account size)."
        ),
        paths: int = typer.Option(10_000, "--paths"),
        seed: int = typer.Option(42, "--seed"),
        scale: float = typer.Option(1.0, "--scale"),
        json_out: Path | None = typer.Option(None, "--json"),
    ) -> None:
        """The full experience: metrics + verdict + prop-firm Monte Carlo -> HTML."""
        log = read_trade_log(trades)
        firm = load_firm(firm_name)
        metrics = compute_metrics(
            log, starting_equity=equity if equity is not None else firm.account_size
        )
        verdict = compute_scorecard(log, metrics)
        mc = run_monte_carlo(log, firm, MCConfig(n_paths=paths, seed=seed, scale=scale))

        _render_verdict(verdict)
        render_report(mc, console)
        build_html_report(
            log,
            metrics,
            verdict,
            output,
            mc=mc,
            firm=firm,
            title=f"Strategy report — {mc.firm_display}",
        )
        console.print(f"\n[bold green]HTML report written to {output}[/bold green]")
        if json_out is not None:
            json_out.write_text(
                json.dumps(combined_json(metrics, verdict, mc), indent=2, default=str)
            )
            console.print(f"JSON summary written to {json_out}")
