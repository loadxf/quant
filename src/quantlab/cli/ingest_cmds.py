"""`quant ingest ...` commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from quantlab.ingest.mapping import ColumnMapping
from quantlab.ingest.tradelog import load_trade_log
from quantlab.schema.io import write_trade_log

ingest_app = typer.Typer(no_args_is_help=True)
console = Console()


@ingest_app.command("trades")
def ingest_trades(
    input_csv: Path = typer.Argument(..., exists=True, readable=True, help="Trade-log CSV."),
    mapping_file: Path | None = typer.Option(
        None, "--mapping", help="YAML column-mapping file (see examples/trades_mapping.yaml)."
    ),
    map_pairs: list[str] = typer.Option(
        [],
        "--map",
        help="Inline mapping overrides, e.g. --map pnl=NetPL --map tz=America/New_York.",
    ),
    output: Path = typer.Option(Path("trades.parquet"), "--output", "-o"),
    currency: str = typer.Option("USD", "--currency"),
) -> None:
    """Convert a trade-log CSV into the canonical trades.parquet."""
    mapping: ColumnMapping | None = None
    if mapping_file is not None:
        mapping = ColumnMapping.from_yaml(mapping_file)
    if map_pairs:
        mapping = ColumnMapping.from_pairs(map_pairs, base=mapping)

    log, report = load_trade_log(input_csv, mapping, account_currency=currency)
    write_trade_log(log, output)

    table = Table(title=f"Ingested {input_csv.name}")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Rows read", str(report.rows_read))
    table.add_row("Trades loaded", str(report.trades_loaded))
    table.add_row("Rows dropped", str(report.rows_dropped))
    table.add_row("Mapping", "auto-detected" if report.autodetected else "user-provided")
    table.add_row(
        "MAE/MFE fidelity",
        {
            "full": "full",
            "partial": "partial (missing sides optimistic)",
            "close-only": "none (intraday checks optimistic)",
        }[log.excursion_fidelity],
    )
    table.add_row("Output", str(output))
    console.print(table)

    if report.mapping_used:
        console.print("[dim]Columns used:[/dim]", report.mapping_used)
    for row_index, reason in report.dropped[:10]:
        console.print(f"[yellow]dropped row {row_index}[/yellow]: {reason}")
    if report.rows_dropped > 10:
        console.print(f"[yellow]... and {report.rows_dropped - 10} more dropped rows[/yellow]")


@ingest_app.command("ohlcv")
def ingest_ohlcv(
    input_csv: Path = typer.Argument(..., exists=True, readable=True, help="OHLCV bar CSV."),
    symbol: str = typer.Option(..., "--symbol", help="Symbol name (used in the Object Store key)."),
    tz: str = typer.Option("UTC", "--tz", help="Timezone of naive timestamps in the CSV."),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Normalized CSV path (default: <symbol>_normalized.csv)."
    ),
    upload: bool = typer.Option(
        False, "--upload", help="Upload to the QC Cloud Object Store for cloud backtests."
    ),
    key: str | None = typer.Option(
        None, "--key", help="Object Store key (default quantlab/<symbol>.csv)."
    ),
) -> None:
    """Normalize user OHLCV bars (and optionally upload for cloud backtests)."""
    from quantlab.ingest.ohlcv import load_ohlcv, write_normalized
    from quantlab.qc import objectstore

    frame, report = load_ohlcv(input_csv, tz=tz)
    out_path = output or Path(f"{symbol.lower()}_normalized.csv")
    write_normalized(frame, out_path)

    table = Table(title=f"Normalized {input_csv.name}")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Rows read", str(report.rows_read))
    table.add_row("Bars kept", str(report.bars_kept))
    table.add_row("Rows dropped", str(len(report.dropped)))
    table.add_row("Duplicate timestamps removed", str(report.duplicate_timestamps))
    table.add_row("Missing weekdays in span", str(report.weekday_gaps))
    table.add_row("Output", str(out_path))
    console.print(table)
    for row_index, reason in report.dropped[:10]:
        console.print(f"[yellow]dropped row {row_index}[/yellow]: {reason}")

    if upload:
        store_key = key or objectstore.default_key(symbol)
        objectstore.upload(out_path, store_key)
        console.print(
            f"[green]uploaded[/green] to Object Store key [bold]{store_key}[/bold] — "
            "point your custom-data strategy at it "
            "(see cloud/strategies/custom_data_demo)"
        )
