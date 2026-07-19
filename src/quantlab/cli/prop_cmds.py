"""`quant prop ...` commands."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import typer
from rich.console import Console
from rich.table import Table

from quantlab.prop.evaluator import EvaluationResult, evaluate, evaluate_sequence
from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.prop.registry import list_firms, load_firm
from quantlab.report.terminal import render_report
from quantlab.schema.io import read_trade_log
from quantlab.schema.trade import Side, Trade, TradeLog

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


@prop_app.command("simulate")
def simulate_cmd(
    trades: Path = typer.Argument(..., exists=True, help="trades.parquet"),
    firm_name: str = typer.Option(..., "--firm", help="Preset name or firm YAML path."),
    paths: int = typer.Option(10_000, "--paths", help="Monte Carlo paths."),
    seed: int = typer.Option(42, "--seed"),
    bootstrap: str = typer.Option(
        "stationary", "--bootstrap", help="stationary | iid_day | iid_trade"
    ),
    block_len: int | None = typer.Option(None, "--block-len"),
    scale: float = typer.Option(1.0, "--scale", help="PnL scale (position sizing what-if)."),
    challenge_scale: float | None = typer.Option(None, "--challenge-scale"),
    funded_scale: float | None = typer.Option(None, "--funded-scale"),
    challenge_horizon: int = typer.Option(120, "--challenge-horizon", help="Trading days."),
    funded_horizon: int = typer.Option(252, "--funded-horizon", help="Trading days."),
    json_out: Path | None = typer.Option(None, "--json", help="Write JSON summary here."),
) -> None:
    """Monte Carlo the challenge + funded phases from a trade log."""
    log = read_trade_log(trades)
    firm = load_firm(firm_name)
    cfg = MCConfig(
        n_paths=paths,
        seed=seed,
        bootstrap=bootstrap,  # type: ignore[arg-type]
        block_len=block_len,
        scale=scale,
        challenge_scale=challenge_scale,
        funded_scale=funded_scale,
        challenge_horizon_days=challenge_horizon,
        funded_horizon_days=funded_horizon,
    )
    report = run_monte_carlo(log, firm, cfg)
    render_report(report, console)
    if json_out is not None:
        json_out.write_text(json.dumps(report.to_json_dict(), indent=2))
        console.print(f"JSON summary written to {json_out}")


def synthetic_geometry_log(
    win_rate: float,
    rr: float,
    trades_per_day: int,
    risk: float,
    ev: float,
    days: int,
    seed: int,
) -> TradeLog:
    """Bernoulli strategy: win = +rr*risk, loss = -risk. The sample is built
    with EXACT win counts and demeaned so its realized per-trade mean equals
    `ev` exactly — bootstrapping resamples this log, so any sampling drift in
    a naive finite sample would otherwise swamp the geometry effect (a
    +7/trade accident compounds to thousands over a challenge horizon).
    No intra-trade noise (MAE/MFE = PnL extremes)."""
    rng = np.random.default_rng(seed)
    n_total = days * trades_per_day
    n_wins = round(win_rate * n_total)
    pnls = np.concatenate([np.full(n_wins, rr * risk), np.full(n_total - n_wins, -risk)])
    pnls = rng.permutation(pnls)
    pnls += ev - pnls.mean()  # exact realized EV
    ct = ZoneInfo("America/Chicago")
    date = dt.date(2026, 1, 5)
    trades: list[Trade] = []
    for day in range(days):
        while date.weekday() >= 5:
            date += dt.timedelta(days=1)
        for k in range(trades_per_day):
            pnl = float(pnls[day * trades_per_day + k])
            entry = dt.datetime.combine(date, dt.time(9, 0), tzinfo=ct) + dt.timedelta(
                minutes=15 * k
            )
            trades.append(
                Trade(
                    entry_time=entry,
                    exit_time=entry + dt.timedelta(minutes=10),
                    symbol="SYN",
                    side=Side.LONG,
                    quantity=1,
                    pnl=pnl,
                    mae=min(0.0, pnl),
                    mfe=max(0.0, pnl),
                )
            )
        date += dt.timedelta(days=1)
    return TradeLog(trades=trades, source="synthetic")


@prop_app.command("geometry")
def geometry_cmd(
    firm_name: str = typer.Option(..., "--firm", help="Preset name or firm YAML path."),
    win_rate: float = typer.Option(0.5, "--win-rate", min=0.01, max=0.99),
    rr: float = typer.Option(1.0, "--rr", help="Reward:risk ratio (take-profit / stop)."),
    trades_per_day: int = typer.Option(3, "--trades-per-day", min=1),
    risk: float = typer.Option(100.0, "--risk", help="$ risked per trade (stop distance)."),
    ev: float = typer.Option(0.0, "--ev", help="Per-trade expected value in $."),
    days: int = typer.Option(250, "--days", help="Synthetic source days."),
    paths: int = typer.Option(10_000, "--paths"),
    seed: int = typer.Option(42, "--seed"),
    json_out: Path | None = typer.Option(None, "--json"),
) -> None:
    """Explore pass-rate/EV for a synthetic risk geometry — no trade log needed.

    Replicates the zero-EV geometry analysis from the QuantPad methodology:
    at fixed EV, lower-RR/higher-win-rate geometries pass trailing-drawdown
    challenges more often than high-RR/low-win-rate ones.
    """
    log = synthetic_geometry_log(win_rate, rr, trades_per_day, risk, ev, days, seed)
    firm = load_firm(firm_name)
    console.print(
        f"synthetic geometry: win rate {win_rate:.0%}, RR {rr:g}, "
        f"{trades_per_day}/day, ${risk:g} risk, EV ${ev:g}/trade"
    )
    report = run_monte_carlo(log, firm, MCConfig(n_paths=paths, seed=seed))
    render_report(report, console)
    if json_out is not None:
        json_out.write_text(json.dumps(report.to_json_dict(), indent=2))
