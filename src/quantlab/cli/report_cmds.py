"""`quant verdict` and `quant report` commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from quantlab.metrics.core import compute_metrics
from quantlab.metrics.reality import compute_reality_check
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
            typer.echo(json.dumps(combined_json(metrics, verdict, log=log), indent=2, default=str))
        else:
            _render_verdict(verdict)
        if html is not None:
            build_html_report(log, metrics, verdict, html, title="Strategy verdict")
            # Preserve stdout as one parseable JSON document in machine mode.
            typer.echo(f"HTML report written to {html}", err=as_json)

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
        trials: int = typer.Option(
            1, "--trials", help="Strategy variants tried (enables DSR deflation)."
        ),
        reality: bool = typer.Option(
            True, "--reality/--no-reality", help="Include the Reality Check section."
        ),
        outer: int = typer.Option(
            100, "--outer", help="Outer resamples for the sampling band (0 to skip)."
        ),
        inner_paths: int = typer.Option(500, "--inner-paths", help="MC paths per outer resample."),
        extra_monthly: float = typer.Option(
            0.0, "--extra-monthly", help="Recurring $/mo overhead (data feed, platform) in the EV."
        ),
        per_payout_fee: float = typer.Option(
            0.0, "--per-payout-fee", help="Processing cost deducted from each payout."
        ),
        payout_haircut: float = typer.Option(
            0.0,
            "--payout-haircut",
            help="Counterparty assumption (0-1): payout fraction lost to denials/failure.",
        ),
        ohlcv: Path | None = typer.Option(
            None, "--ohlcv", help="Market bars CSV — adds the trend x vol market-regime table."
        ),
        json_out: Path | None = typer.Option(None, "--json"),
    ) -> None:
        """The full experience: metrics + verdict + prop Monte Carlo + reality check -> HTML."""
        from quantlab.prop.config import with_fee_overrides

        log = read_trade_log(trades)
        firm = with_fee_overrides(
            load_firm(firm_name), extra_monthly, per_payout_fee, payout_haircut
        )
        bars = None
        if ohlcv is not None:
            from quantlab.ingest.ohlcv import load_ohlcv

            bars, _ = load_ohlcv(ohlcv)
        metrics = compute_metrics(
            log,
            starting_equity=equity if equity is not None else firm.account_size,
            boundary=firm.day_boundary.to_boundary(),
        )
        mc = run_monte_carlo(log, firm, MCConfig(n_paths=paths, seed=seed, scale=scale))
        rc = (
            compute_reality_check(
                log,
                firm=firm,
                trials=trials,
                seed=seed,
                scale=scale,
                baseline_mc=mc,
                outer=outer,
                inner_paths=inner_paths,
                ohlcv=bars,
            )
            if reality
            else None
        )
        # Reuse the reality check's decay/deflated panels — same log, same
        # trials — instead of computing them a second time inside the
        # scorecard (the Mann-Kendall panel dominates cost on large logs).
        verdict = compute_scorecard(
            log,
            metrics,
            trials=trials,
            decay=rc.decay if rc else None,
            deflated=rc.deflated if rc else None,
            clustering=rc.clustering if rc else None,
            regime=rc.regime if rc else None,
            boundary=firm.day_boundary.to_boundary(),
            firm=firm,
        )

        _render_verdict(verdict)
        render_report(mc, console)
        build_html_report(
            log,
            metrics,
            verdict,
            output,
            mc=mc,
            firm=firm,
            reality=rc,
            title=f"Strategy report — {mc.firm_display}",
        )
        console.print(f"\n[bold green]HTML report written to {output}[/bold green]")
        if json_out is not None:
            json_out.write_text(
                json.dumps(
                    combined_json(
                        metrics,
                        verdict,
                        mc,
                        reality=rc,
                        log=log,
                        boundary=firm.day_boundary.to_boundary(),
                    ),
                    indent=2,
                    default=str,
                )
            )
            console.print(f"JSON summary written to {json_out}")
