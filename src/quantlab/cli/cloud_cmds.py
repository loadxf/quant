"""`quant cloud ...` commands (QuantConnect Cloud)."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from quantlab.qc import runner
from quantlab.qc.api import QCClient
from quantlab.qc.results import parse_closed_trades, parse_equity_chart
from quantlab.schema.io import write_trade_log

cloud_app = typer.Typer(no_args_is_help=True)
console = Console()


@cloud_app.command("push")
def push_cmd(
    project: Path = typer.Argument(..., help="LEAN project dir, e.g. cloud/strategies/orb_equity"),
) -> None:
    """Push a local LEAN project to QuantConnect Cloud (Docker-free)."""
    runner.push_project(project)
    console.print(f"[green]pushed[/green] {project}")


@cloud_app.command("backtest")
def backtest_cmd(
    project: str = typer.Argument(..., help="Cloud project name or local dir (with --push)."),
    name: str | None = typer.Option(None, "--name", help="Backtest name."),
    push: bool = typer.Option(False, "--push", help="Push local changes first."),
) -> None:
    """Run a cloud backtest; prints the ids needed by `quant cloud results`."""
    run = runner.run_cloud_backtest(Path(project), name=name, push=push)
    console.print(run.stdout)
    if run.project_id and run.backtest_id:
        console.print(
            f"[green]done[/green] — fetch trades with:\n"
            f"  quant cloud results --project-id {run.project_id} "
            f"--backtest-id {run.backtest_id} -o trades.parquet"
        )
    else:
        console.print(
            "[yellow]Could not parse project/backtest ids from the CLI output — "
            "copy them from the printed QuantConnect URL and run "
            "`quant cloud results --project-id N --backtest-id ID`.[/yellow]"
        )


@cloud_app.command("results")
def results_cmd(
    project_id: int = typer.Option(..., "--project-id"),
    backtest_id: str = typer.Option(..., "--backtest-id"),
    output: Path = typer.Option(Path("trades.parquet"), "--output", "-o"),
    save_json: Path | None = typer.Option(
        None, "--save-json", help="Also save the raw backtests/read response."
    ),
    with_chart: bool = typer.Option(
        False, "--chart", help="Also fetch the Strategy Equity chart series."
    ),
) -> None:
    """Download full backtest results via the REST API -> canonical trades.parquet.

    (Verified: no lean CLI command downloads result JSON — the API is the
    only route; closedTrades carries MAE/MFE for intraday rule fidelity.)
    """
    client = QCClient()
    backtest = client.read_backtest(project_id, backtest_id)
    if save_json is not None:
        save_json.write_text(json.dumps(backtest, indent=2, default=str))
        console.print(f"raw result saved to {save_json}")

    log = parse_closed_trades(backtest)
    write_trade_log(log, output)
    console.print(
        f"[green]{len(log)} closed trades[/green] -> {output} "
        f"(MAE/MFE {'present' if log.has_excursions else 'missing'})"
    )
    console.print(f"next: quant report {output} --firm topstep_50k -o report.html")
    if with_chart:
        chart = client.read_backtest_chart(project_id, backtest_id)
        curve = parse_equity_chart(chart)
        console.print(f"equity chart: {len(curve.points)} points fetched")
