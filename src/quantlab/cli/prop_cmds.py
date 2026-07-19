"""`quant prop ...` commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from quantlab.prop.evaluator import EvaluationResult, evaluate, evaluate_sequence
from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.prop.registry import list_firms, load_firm
from quantlab.prop.synthetic import resolve_geometry, synthetic_geometry_log
from quantlab.report.format import money
from quantlab.report.jsonout import sanitize
from quantlab.report.terminal import render_report
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
            money(firm.account_size, decimals=0),
            " -> ".join(
                f"{p.name} (+{money(p.profit_target, decimals=0)})"
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
        f"(final balance {money(result.final_balance)}, "
        f"{result.trading_days} trading days)"
    )
    if result.effective_target is not None:
        console.print(
            f"  effective target: {money(result.effective_target)}"
            f" (best day {money(result.best_day)})"
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
    sizing: str = typer.Option(
        "fixed",
        "--sizing",
        help="fixed | vol_target (dynamic per-path EWMA vol-targeted sizing, M9).",
    ),
    vol_lambda: float = typer.Option(
        0.94, "--vol-lambda", help="EWMA decay (RiskMetrics daily 0.94)."
    ),
    vol_target: float | None = typer.Option(
        None, "--vol-target", help="Target daily $ vol (default: median EWMA sigma of the log)."
    ),
    vol_clip_lo: float = typer.Option(0.5, "--vol-clip-lo", help="Weight floor."),
    vol_clip_hi: float = typer.Option(1.5, "--vol-clip-hi", help="Weight cap (Moreira-Muir 1.5)."),
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
        sizing=sizing,
        vol_lambda=vol_lambda,
        vol_target=vol_target,
        vol_clip=(vol_clip_lo, vol_clip_hi),
    )
    report = run_monte_carlo(log, firm, cfg)
    render_report(report, console)
    if json_out is not None:
        json_out.write_text(json.dumps(sanitize(report.to_json_dict()), indent=2))
        console.print(f"JSON summary written to {json_out}")


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

    Note: for pure barrier rules at zero EV, pass probability is
    geometry-independent in the diffusion limit (static: D/(T+D);
    trailing: exp(-T/D)) — geometry effects emerge from day-scale rules
    (daily loss limits, consistency, time limits) and finite trade sizes.
    """
    log = synthetic_geometry_log(win_rate, rr, trades_per_day, risk, ev, days, seed)
    firm = load_firm(firm_name)
    geometry = resolve_geometry(win_rate, rr, risk, ev)
    console.print(
        f"synthetic geometry: win rate {win_rate:.0%}, RR {rr:g}, "
        f"{trades_per_day}/day, ${risk:g} risk, EV ${ev:g}/trade "
        f"(effective win {geometry.win_size:+.2f} / loss {geometry.loss_size:+.2f})"
    )
    if geometry.distorted:
        console.print(
            f"[yellow]warning:[/yellow] the requested EV is inconsistent with "
            f"win_rate x RR x risk (shift {geometry.shift:+.2f}/trade) — the "
            "simulated geometry differs from the stated stop/target sizes."
        )
    report = run_monte_carlo(log, firm, MCConfig(n_paths=paths, seed=seed))
    render_report(report, console)
    if json_out is not None:
        json_out.write_text(json.dumps(sanitize(report.to_json_dict()), indent=2))
        console.print(f"JSON summary written to {json_out}")
