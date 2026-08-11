"""`quant cloud ...` commands (QuantConnect Cloud)."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from quantlab.errors import QuantLabError
from quantlab.output import prepared, write_text
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
    firm: str | None = typer.Option(
        None,
        "--firm",
        help="Cross-check the TRUE mark-to-market equity against this firm's "
        "trailing/static/daily-loss rules (fetches the equity chart "
        "automatically).",
    ),
) -> None:
    """Download full backtest results via the REST API -> canonical trades.parquet.

    (Verified: no lean CLI command downloads result JSON — the API is the
    only route; closedTrades carries MAE/MFE for intraday rule fidelity.)
    """
    # Resolve the firm BEFORE any network call: a typo'd preset name must
    # not burn the download and up to a minute of chart polling first.
    firm_cfg = None
    if firm is not None:
        from quantlab.prop.registry import load_firm

        firm_cfg = load_firm(firm)
        if not with_chart:
            # The check the user asked for needs the equity chart — fetch
            # it implicitly rather than silently skipping the check.
            with_chart = True
            console.print(
                "[dim]--firm implies --chart: fetching the Strategy Equity series "
                "(writes the .equity.csv side file; may poll up to ~60s)[/dim]"
            )
    client = QCClient()
    backtest = client.read_backtest(project_id, backtest_id)
    if save_json is not None:
        # Written BEFORE any status check so a crashed backtest's raw
        # payload is still retrievable for diagnosis.
        write_text(save_json, json.dumps(backtest, indent=2, default=str))
        console.print(f"raw result saved to {save_json}")

    error_text = str(backtest.get("error") or backtest.get("stacktrace") or "").strip()
    if error_text:
        raise QuantLabError(
            f"backtest {backtest_id} ended with a runtime error — its trades "
            f"(if any) do not represent the full strategy. Algorithm error:\n"
            f"{error_text[:1000]}"
            + ("" if save_json else "\n(re-run with --save-json to keep the full payload)")
        )
    completed = backtest.get("completed")
    if completed is False:
        progress = backtest.get("progress")
        pct = f" (progress {float(progress):.0%})" if isinstance(progress, int | float) else ""
        console.print(
            f"[yellow]warning[/yellow]: backtest is still running{pct} — "
            "trades below are a PARTIAL snapshot, not the final result"
        )

    log, skipped = parse_closed_trades(backtest)
    write_trade_log(log, output)
    console.print(
        f"[green]{len(log)} closed trades[/green] -> {output} "
        f"(MAE/MFE {'present' if log.has_excursions else 'missing'}; "
        f"pnl = profitLoss - totalFees)"
    )
    for reason in skipped[:10]:
        console.print(f"[yellow]skipped[/yellow] {reason}")
    if len(skipped) > 10:
        console.print(f"[yellow]... and {len(skipped) - 10} more skipped trades[/yellow]")
    console.print(f"next: quant report {output} --firm topstep_50k -o report.html")
    if with_chart:
        chart = client.read_backtest_chart(project_id, backtest_id)
        curve = parse_equity_chart(chart)
        chart_path = output.with_suffix(".equity.csv")
        curve.to_series().rename("equity").to_csv(prepared(chart_path), index_label="datetime")
        console.print(f"equity chart: {len(curve.points)} points -> {chart_path}")
        if firm_cfg is not None:
            from quantlab.prop.equity_check import check_equity_curve

            check = check_equity_curve(curve, firm_cfg)
            if check.first_breach is not None:
                b = check.first_breach
                console.print(
                    f"[red]open-equity breach[/red] ({check.phase}): {b.rule} at "
                    f"{b.when}: {b.detail}"
                )
            else:
                console.print(
                    f"open-equity check ({check.phase}): no trailing/static/daily-loss "
                    f"breach across {check.n_marks} marks"
                )
            for w in check.warnings:
                console.print(f"[yellow]note[/yellow]: {w}")
            console.print(
                f"deep check: quant prop evaluate {output} --firm {firm} --equity-csv {chart_path}"
            )
