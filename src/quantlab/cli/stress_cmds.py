"""`quant stress` — the Reality Check command."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import typer
from rich.console import Console

from quantlab.errors import QuantLabError
from quantlab.metrics.reality import compute_reality_check
from quantlab.prop.registry import load_firm
from quantlab.report.jsonout import sanitize
from quantlab.report.terminal import render_reality
from quantlab.schema.io import read_trade_log

console = Console()


def register_stress_commands(app: typer.Typer) -> None:
    @app.command("stress")
    def stress(
        trades: Path = typer.Argument(..., help="Canonical trade-log parquet."),
        firm: str | None = typer.Option(
            None, "--firm", help="Firm preset (adds MC pass-prob columns to the sweep)."
        ),
        tick_value: float | None = typer.Option(
            None,
            "--tick-value",
            min=0.0,
            help="$ per tick per contract (auto-resolved for ES/MES/NQ/MNQ).",
        ),
        commission: float | None = typer.Option(
            None, "--commission", min=0.0, help="All-in round-turn commission $ per contract."
        ),
        stop_slip: float = typer.Option(
            1.0,
            "--stop-slip",
            min=0.0,
            help="Extra ticks/side for the stop-stress row (stops fill worse).",
        ),
        trials: int = typer.Option(
            1,
            "--trials",
            help="Strategy variants tried before this one — enables DSR/MinBTL/haircut Sharpe.",
        ),
        window: int = typer.Option(30, "--window", help="Rolling-expectancy window (trades)."),
        paths: int = typer.Option(2000, "--paths", help="MC paths per sweep anchor point."),
        seed: int = typer.Option(42, "--seed"),
        ruin_capital: float | None = typer.Option(
            None, "--ruin-capital", help="Capital for P(ruin) in the permutation drawdown."
        ),
        oos_start: str | None = typer.Option(
            None,
            "--oos-start",
            help="ISO date where out-of-sample begins (e.g. strategy went live) — "
            "adds the walk-forward-efficiency row.",
        ),
        ohlcv: Path | None = typer.Option(
            None,
            "--ohlcv",
            exists=True,
            dir_okay=False,
            help="Market bars CSV (any broker export) — adds the descriptive "
            "trend x vol market-regime table.",
        ),
        outer: int = typer.Option(
            100,
            "--outer",
            help="Outer bootstrap resamples for the source-log sampling band (0 to skip).",
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
        json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
    ) -> None:
        """Cost stress, edge decay, and deflated statistics for a trade log.

        The honesty layer: does the edge survive realistic costs, is it
        deteriorating within the log, and does it clear multiple-testing
        deflation? Methods and thresholds are literature-anchored — see
        docs/research-notes.md for citations.
        """
        from quantlab.prop.config import with_fee_overrides

        log = read_trade_log(trades)
        firm_cfg = load_firm(firm) if firm else None
        if firm_cfg is not None:
            firm_cfg = with_fee_overrides(firm_cfg, extra_monthly, per_payout_fee, payout_haircut)
        bars = None
        if ohlcv is not None:
            from quantlab.ingest.ohlcv import load_ohlcv

            bars, _ = load_ohlcv(ohlcv)
        oos_dt: dt.datetime | None = None
        if oos_start is not None:
            try:
                oos_dt = dt.datetime.fromisoformat(oos_start)
            except ValueError:
                raise QuantLabError(
                    f"--oos-start {oos_start!r} is not an ISO date (e.g. 2026-03-01)"
                ) from None
            if oos_dt.tzinfo is None:
                oos_dt = oos_dt.replace(tzinfo=dt.UTC)
        rc = compute_reality_check(
            log,
            firm=firm_cfg,
            trials=trials,
            tick_value=tick_value,
            commission_rt=commission,
            stop_slip_ticks=stop_slip,
            decay_window=window,
            mc_paths=paths,
            seed=seed,
            ruin_capital=ruin_capital,
            oos_start=oos_dt,
            outer=outer,
            inner_paths=inner_paths,
            ohlcv=bars,
        )
        if json_out:
            typer.echo(json.dumps(sanitize(rc.to_json_dict()), indent=2, default=str))
            return
        render_reality(rc, console)
