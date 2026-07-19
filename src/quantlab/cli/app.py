"""`quant` CLI entry point.

Command groups register lazily in their own modules so the pure-Python
core never imports QC-cloud code paths it doesn't need.
"""

from __future__ import annotations

import typer

from quantlab import __version__
from quantlab.cli.ingest_cmds import ingest_app
from quantlab.cli.metrics_cmds import register_metrics_commands
from quantlab.cli.prop_cmds import prop_app
from quantlab.errors import QuantLabError

app = typer.Typer(
    name="quant",
    help="QuantPad-style backtesting + prop-firm Monte Carlo testing on QuantConnect Cloud.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
app.add_typer(ingest_app, name="ingest", help="Convert user CSVs into canonical formats.")
app.add_typer(prop_app, name="prop", help="Prop-firm evaluation and Monte Carlo simulation.")
register_metrics_commands(app)


@app.callback()
def _root(
    version: bool = typer.Option(False, "--version", help="Print version and exit."),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


def main() -> None:
    try:
        app()
    except QuantLabError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    main()
