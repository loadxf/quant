"""`quant pbo` — CSCV probability of backtest overfitting."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from quantlab.metrics.pbo import DEFAULT_PARTITIONS, compute_pbo, load_variant_matrix
from quantlab.report.jsonout import sanitize

console = Console()


def register_pbo_commands(app: typer.Typer) -> None:
    @app.command("pbo")
    def pbo_cmd(
        variants: Path = typer.Argument(
            ...,
            exists=True,
            help="CSV of per-variant daily PnL: one column per strategy variant "
            "(e.g. a QC parameter sweep), one row per day, optional date column.",
        ),
        partitions: int = typer.Option(
            DEFAULT_PARTITIONS, "--partitions", help="Even number of CSCV blocks (paper: 16)."
        ),
        seed: int = typer.Option(0, "--seed", help="Split-sampling seed above C(S,S/2) cap."),
        json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
    ) -> None:
        """Probability that picking your best backtest picked noise (CSCV).

        Bailey-Borwein-Lopez de Prado-Zhu (2017): PBO ~ 0.5 means the
        in-sample winner is a coin flip out-of-sample; near 0 means the
        winner genuinely dominates. The measured complement to --trials.
        """
        matrix, _names, notes = load_variant_matrix(variants)
        result = compute_pbo(matrix, partitions=partitions, seed=seed)
        if json_out:
            payload = result.to_json_dict()
            payload["loader_notes"] = notes
            typer.echo(json.dumps(sanitize(payload), indent=2, default=str))
            return
        for note in notes:
            console.print(f"[dim]{note}[/dim]")
        table = Table(title=f"PBO / CSCV ({result.n_variants} variants, {result.n_days} days)")
        table.add_column("Statistic")
        table.add_column("Value", justify="right")
        table.add_row("[bold]PBO (IS winner in bottom half OOS)[/bold]", f"{result.pbo:.1%}")
        table.add_row("P(IS winner loses money OOS)", f"{result.p_oos_loss:.1%}")
        table.add_row(
            "logit mean / median",
            f"{result.logit_mean:+.2f} / {result.logit_quantiles['p50']:+.2f}",
        )
        table.add_row(
            "degradation (OOS SR vs IS SR)",
            f"slope {result.degradation_slope:+.2f}, intercept {result.degradation_intercept:+.3f}",
        )
        table.add_row("splits evaluated", f"{result.combos_evaluated:,} of {result.combos_total:,}")
        console.print(table)
        verdict = (
            "SEVERE overfitting risk — the backtest winner is noise"
            if result.pbo >= 0.5
            else (
                "elevated overfitting risk"
                if result.pbo >= 0.2
                else "selection looks meaningful (low PBO)"
            )
        )
        console.print(f"verdict: {verdict}")
        for w in result.warnings:
            console.print(f"[yellow]note[/yellow]: {w}")
