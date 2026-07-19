"""`quant prop ...` commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from quantlab.prop.evaluator import EvaluationResult, evaluate, evaluate_sequence
from quantlab.prop.registry import list_firms, load_firm
from quantlab.schema.io import read_trade_log

prop_app = typer.Typer(no_args_is_help=True)
firms_app = typer.Typer(no_args_is_help=True)
prop_app.add_typer(firms_app, name="firms", help="List and inspect firm presets.")
console = Console()


@firms_app.command("list")
def firms_list() -> None:
    """List built-in firm presets."""
    table = Table(title="Firm presets")
    table.add_column("Name")
    table.add_column("Account", justify="right")
    table.add_column("Eval phases")
    table.add_column("Verified")
    for name in list_firms():
        firm = load_firm(name)
        table.add_row(
            name,
            f"${firm.account_size:,.0f}",
            " -> ".join(
                f"{p.name} (+${p.profit_target:,.0f})"
                for p in firm.phases
                if p.profit_target is not None
            ),
            firm.verified_as_of,
        )
    console.print(table)


@firms_app.command("show")
def firms_show(name: str = typer.Argument(..., help="Preset name or YAML path.")) -> None:
    """Show a firm's full resolved configuration."""
    firm = load_firm(name)
    console.print_json(firm.model_dump_json(indent=2))


def _print_result(result: EvaluationResult) -> None:
    color = {
        "passed": "green",
        "survived": "green",
        "breached": "red",
        "expired": "yellow",
        "incomplete": "yellow",
    }[result.outcome]
    console.print(
        f"[bold {color}]{result.phase}: {result.outcome.upper()}[/bold {color}]  "
        f"(final balance ${result.final_balance:,.2f}, "
        f"{result.trading_days} trading days)"
    )
    if result.effective_target is not None:
        console.print(
            f"  effective target: ${result.effective_target:,.2f}"
            f" (best day ${result.best_day:,.2f})"
        )
    if result.breach:
        b = result.breach
        console.print(
            f"  [red]breach[/red]: {b.rule} on {b.date} (trade {b.trade_index + 1}): {b.detail}"
        )
    if result.lockout_days:
        console.print(f"  daily-loss lockouts: {result.lockout_days} day(s)")
    for note in result.advisories:
        console.print(f"  [yellow]advisory[/yellow]: {note}")


@prop_app.command("evaluate")
def evaluate_cmd(
    trades: Path = typer.Argument(..., exists=True, help="trades.parquet"),
    firm_name: str = typer.Option(..., "--firm", help="Preset name or firm YAML path."),
    phase: str | None = typer.Option(
        None,
        "--phase",
        help="Evaluate one phase (e.g. challenge, verification, funded). "
        "Default: chain all phases through the log.",
    ),
) -> None:
    """Deterministically replay a trade log against a firm's rules."""
    log = read_trade_log(trades)
    firm = load_firm(firm_name)
    fidelity = (
        "MAE/MFE-refined"
        if log.has_excursions
        else "trade-close only — intraday checks are optimistic"
    )
    console.print(f"[bold]{firm.display_name or firm.name}[/bold]  (fidelity: {fidelity})")
    if phase is not None:
        _print_result(evaluate(log, firm, phase))
        return
    for result in evaluate_sequence(log, firm):
        _print_result(result)
