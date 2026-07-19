"""`quant metrics` command."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from quantlab.metrics.core import Metrics, compute_metrics
from quantlab.schema.io import read_trade_log

console = Console()


def _fmt(value: float, kind: str = "num") -> str:
    if kind == "money":
        return f"${value:,.2f}"
    if kind == "pct":
        return f"{value:.1%}"
    if value == float("inf"):
        return "inf"
    return f"{value:.2f}"


def render_metrics_table(metrics: Metrics) -> Table:
    table = Table(title="Strategy metrics")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    rows: list[tuple[str, str]] = [
        ("Trades", str(metrics.trade_count)),
        ("Trading days", str(metrics.trading_days)),
        ("Net profit", _fmt(metrics.net_profit, "money")),
        ("Win rate", _fmt(metrics.win_rate, "pct")),
        (
            "Avg win / avg loss",
            f"{_fmt(metrics.avg_win, 'money')} / {_fmt(metrics.avg_loss, 'money')}",
        ),
        ("Payoff ratio", _fmt(metrics.payoff_ratio)),
        ("Expectancy / trade", _fmt(metrics.expectancy, "money")),
        (
            "Expectancy 95% CI",
            f"[{_fmt(metrics.expectancy_ci95[0], 'money')}, "
            f"{_fmt(metrics.expectancy_ci95[1], 'money')}]",
        ),
        ("Expectancy t-stat", _fmt(metrics.expectancy_tstat)),
        ("Profit factor", _fmt(metrics.profit_factor)),
        (
            "Max drawdown",
            f"{_fmt(metrics.max_drawdown, 'money')} ({_fmt(metrics.max_drawdown_pct, 'pct')})",
        ),
        ("Sharpe (daily, ann.)", _fmt(metrics.sharpe)),
        ("Sortino (daily, ann.)", _fmt(metrics.sortino)),
        ("MAR", _fmt(metrics.mar)),
        ("Longest losing streak", str(metrics.longest_losing_streak)),
        (
            "Best day",
            f"{_fmt(metrics.best_day, 'money')} ({_fmt(metrics.best_day_share, 'pct')} of net)",
        ),
        ("Top-5 trades share", _fmt(metrics.top5_trade_share, "pct")),
    ]
    for name, value in rows:
        table.add_row(name, value)
    return table


def register_metrics_commands(app: typer.Typer) -> None:
    @app.command("metrics")
    def metrics_cmd(
        trades: Path = typer.Argument(
            ..., exists=True, help="trades.parquet from `quant ingest trades`."
        ),
        equity: float = typer.Option(
            50_000.0, "--equity", help="Starting equity for DD/Sharpe context."
        ),
        as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
    ) -> None:
        """Compute standard strategy statistics from a canonical trade log."""
        log = read_trade_log(trades)
        result = compute_metrics(log, starting_equity=equity)
        if as_json:
            payload = dataclasses.asdict(result)
            payload["schema_version"] = 1
            typer.echo(json.dumps(payload, indent=2, default=str))
        else:
            console.print(render_metrics_table(result))
            if not log.has_excursions:
                console.print(
                    "[yellow]Note:[/yellow] log has no MAE/MFE columns — "
                    "intraday-sensitive prop-firm checks will run at trade-close fidelity."
                )
