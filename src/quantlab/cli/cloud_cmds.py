"""`quant cloud ...` commands (QuantConnect Cloud)."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

import typer
from rich.console import Console

from quantlab.errors import QuantLabError
from quantlab.output import prepared
from quantlab.qc import runner
from quantlab.qc.api import QCClient
from quantlab.qc.results import (
    load_result_file,
    parse_closed_trades,
    parse_equity_chart,
    parse_equity_marks,
)
from quantlab.report.jsonout import sanitize
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
    project_id: int | None = typer.Option(None, "--project-id"),
    backtest_id: str | None = typer.Option(None, "--backtest-id"),
    from_json: Path | None = typer.Option(
        None,
        "--from-json",
        help="Parse a locally saved backtest result JSON instead of calling "
        "the REST API: the file the in-algorithm quantlab export block "
        "writes to the Object Store (download it in the web IDE), or an "
        "earlier --save-json file. Needs no credentials or lean CLI.",
    ),
    output: Path = typer.Option(Path("trades.parquet"), "--output", "-o"),
    save_json: Path | None = typer.Option(
        None, "--save-json", help="Also save the raw backtests/read response."
    ),
    with_chart: bool = typer.Option(
        False,
        "--chart",
        help="Also write the equity curve: the Strategy Equity chart series "
        "(API) or the export block's equityMarks (--from-json).",
    ),
    firm: str | None = typer.Option(
        None,
        "--firm",
        help="Cross-check the TRUE mark-to-market equity against this firm's "
        "trailing/static/daily-loss rules (fetches the equity curve "
        "automatically).",
    ),
) -> None:
    """Turn a QC backtest into the canonical trades.parquet.

    Two sources: the REST API (--project-id/--backtest-id) or a local file
    (--from-json) downloaded from the web IDE's Object Store — the API-free
    route. Both carry MAE/MFE for intraday rule fidelity. (Verified: no
    lean CLI command downloads result JSON.)
    """
    offline = from_json is not None
    if offline and (project_id is not None or backtest_id is not None):
        raise QuantLabError(
            "--from-json replaces --project-id/--backtest-id — pass one source, not both"
        )
    if not offline and (project_id is None or backtest_id is None):
        raise QuantLabError(
            "pass --project-id and --backtest-id (API download) or "
            "--from-json FILE (no API; the file the export block saved "
            "to the Object Store)"
        )
    if offline and save_json is not None:
        raise QuantLabError(
            "--save-json only applies to API downloads — the --from-json file is already local"
        )
    # Resolve the firm BEFORE any network call: a typo'd preset name must
    # not burn the download and up to a minute of chart polling first.
    firm_cfg = None
    if firm is not None:
        from quantlab.prop.registry import load_firm

        firm_cfg = load_firm(firm)
        if not with_chart:
            # The check the user asked for needs the equity curve — fetch
            # it implicitly rather than silently skipping the check.
            with_chart = True
            console.print(
                "[dim]--firm implies --chart: using the equity curve "
                "(writes the .equity.csv side file; API downloads may poll up to ~60s)[/dim]"
            )
    client = None
    if from_json is not None:
        backtest = load_result_file(from_json)
    else:
        assert project_id is not None and backtest_id is not None  # validated above
        client = QCClient()
        backtest = client.read_backtest(project_id, backtest_id)
    if save_json is not None:
        # Written BEFORE any status check so a crashed backtest's raw
        # payload is still retrievable for diagnosis.
        serialized = json.dumps(sanitize(backtest), indent=2, default=str, allow_nan=False)
        save_json.parent.mkdir(parents=True, exist_ok=True)
        temporary = save_json.with_name(f".{save_json.name}.{secrets.token_hex(6)}.tmp")
        try:
            temporary.write_text(serialized, encoding="utf-8")
            temporary.replace(save_json)
        finally:
            temporary.unlink(missing_ok=True)
        console.print(f"raw result saved to {save_json}")

    source_label = str(from_json) if offline else f"backtest {backtest_id}"
    error_text = str(backtest.get("error") or backtest.get("stacktrace") or "").strip()
    if error_text:
        raise QuantLabError(
            f"{source_label} ended with a runtime error — its trades "
            f"(if any) do not represent the full strategy. Algorithm error:\n"
            f"{error_text[:1000]}"
            + (
                ""
                if save_json or offline
                else "\n(re-run with --save-json to keep the full payload)"
            )
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
        if offline:
            curve = parse_equity_marks(backtest)
            if curve is None:
                raise QuantLabError(
                    "--chart/--firm need an equity curve, but this file has no "
                    "'equityMarks' — it came from --save-json or an export "
                    "block without equity sampling. Re-run the backtest with "
                    "the current export block, or use the API download."
                )
            console.print(
                "[dim]equity curve from the export block's hourly equityMarks — "
                "coarser than the API chart series; breaches between marks "
                "can't be seen[/dim]"
            )
        else:
            # Guaranteed by the source-validation branch above.
            assert client is not None and project_id is not None and backtest_id is not None
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
