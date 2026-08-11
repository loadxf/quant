"""`quant prop ...` commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from quantlab.output import write_text
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
    equity_csv: Path | None = typer.Option(
        None,
        "--equity-csv",
        exists=True,
        dir_okay=False,
        help="Mark-to-market equity CSV (datetime,equity — e.g. from "
        "`quant cloud results --chart`): cross-checks intraday-sensitive "
        "rules against TRUE open equity, not just fills.",
    ),
) -> None:
    """Deterministically replay a trade log against a firm's rules."""
    log = read_trade_log(trades)
    firm = load_firm(firm_name)
    fidelity = {
        "full": "MAE/MFE-refined",
        "partial": "partial MAE/MFE — missing sides are optimistic",
        "close-only": "trade-close only — intraday checks are optimistic",
    }[log.excursion_fidelity]
    console.print(f"[bold]{firm.display_name or firm.name}[/bold]  (fidelity: {fidelity})")
    if phase is not None:
        first = evaluate(log, firm, phase)
        _print_result(first)
    else:
        results = evaluate_sequence(log, firm)
        for result in results:
            _print_result(result)
        first = results[0]
    if equity_csv is not None:
        from quantlab.prop.equity_check import check_equity_curve, load_equity_csv

        check = check_equity_curve(
            load_equity_csv(equity_csv), firm, phase_name=phase or firm.phases[0].name
        )
        _print_equity_check(check, first)


def _print_equity_check(check, trade_log_result: EvaluationResult) -> None:
    console.print(
        f"[bold]mark-to-market cross-check[/bold] ({check.n_marks} equity marks, "
        f"{check.n_sessions} sessions, "
        f"{'intraday' if check.intraday_marks else '~daily'} resolution)"
    )
    log_breached = trade_log_result.outcome == "breached"
    if check.first_breach is not None:
        b = check.first_breach
        console.print(f"  [red]open-equity breach[/red]: {b.rule} at {b.when}: {b.detail}")
        if not log_breached:
            console.print(
                "  [red]DISCREPANCY[/red]: the trade-log replay said "
                f"{trade_log_result.outcome.upper()} — true open equity breached where "
                "fill-level fidelity saw nothing. Trust the equity curve."
            )
    else:
        console.print("  no open-equity breach of trailing/static/daily-loss rules")
        if log_breached:
            console.print(
                "  note: the trade-log replay breached but the sampled equity marks "
                "never crossed — likely an excursion between marks; the trade-log "
                "verdict stands (MAE/MFE sees inside bars, sampled marks may not)."
            )
    for hit in check.daily_loss_hits:
        console.print(f"  [yellow]daily-loss crossing[/yellow] {hit.when}: {hit.detail}")
    for w in check.warnings:
        console.print(f"  [yellow]note[/yellow]: {w}")


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
        help="fixed | vol_target (per-path EWMA vol targeting) | cushion "
        "(size by the live buffer above the drawdown floor).",
    ),
    vol_lambda: float = typer.Option(
        0.94, "--vol-lambda", help="EWMA decay (RiskMetrics daily 0.94)."
    ),
    vol_target: float | None = typer.Option(
        None, "--vol-target", help="Target daily $ vol (default: median EWMA sigma of the log)."
    ),
    vol_clip_lo: float = typer.Option(0.5, "--vol-clip-lo", help="Weight floor."),
    vol_clip_hi: float = typer.Option(1.5, "--vol-clip-hi", help="Weight cap (Moreira-Muir 1.5)."),
    cushion_clip_lo: float = typer.Option(
        0.25, "--cushion-clip-lo", help="Cushion-sizing weight floor."
    ),
    cushion_clip_hi: float = typer.Option(
        1.5, "--cushion-clip-hi", help="Cushion-sizing weight cap."
    ),
    base_contracts: float | None = typer.Option(
        None,
        "--base-contracts",
        help="Your full mini-equivalent contract allowance for scaling-plan caps "
        "(default: the log's peak concurrent gross exposure).",
    ),
    payout_policy: str = typer.Option(
        "asap", "--payout-policy", help="asap | keep_buffer (leave --keep-buffer $ working)."
    ),
    keep_buffer: float = typer.Option(
        0.0, "--keep-buffer", help="$ cushion left above the payout floor (keep_buffer policy)."
    ),
    extract_weight: float | None = typer.Option(
        None,
        "--extract-weight",
        help="Cut size to this weight once the cycle's qualifying days are banked (0<w<=1).",
    ),
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
    accounts: str | None = typer.Option(
        None,
        "--accounts",
        help="Comma-separated k values for the multi-account comparison (e.g. 2,3,5).",
    ),
    json_out: Path | None = typer.Option(None, "--json", help="Write JSON summary here."),
) -> None:
    """Monte Carlo the challenge + funded phases from a trade log."""
    from quantlab.prop.config import with_fee_overrides

    log = read_trade_log(trades)
    firm = with_fee_overrides(load_firm(firm_name), extra_monthly, per_payout_fee, payout_haircut)
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
        cushion_clip=(cushion_clip_lo, cushion_clip_hi),
        base_contracts=base_contracts,
        payout_policy=payout_policy,
        keep_buffer=keep_buffer,
        extract_weight=extract_weight,
    )
    report = run_monte_carlo(log, firm, cfg)
    render_report(report, console)
    payload = report.to_json_dict()
    if accounts is not None:
        from quantlab.prop.frontier import compute_multiaccount
        from quantlab.report.terminal import render_multiaccount

        ma = compute_multiaccount(report, k_list=_parse_int_list(accounts, "--accounts"))
        render_multiaccount(ma, console)
        payload["multi_account"] = ma.to_json_dict()
    if json_out is not None:
        write_text(json_out, json.dumps(sanitize(payload), indent=2))
        console.print(f"JSON summary written to {json_out}")


def _parse_int_list(raw: str, flag: str) -> tuple[int, ...]:
    from quantlab.errors import QuantLabError

    try:
        values = tuple(int(part) for part in raw.split(",") if part.strip())
    except ValueError:
        raise QuantLabError(f"{flag} expects comma-separated integers (got {raw!r})") from None
    if not values:
        raise QuantLabError(f"{flag} expects at least one value (got {raw!r})")
    return values


def _parse_float_list(raw: str, flag: str) -> tuple[float, ...]:
    from quantlab.errors import QuantLabError

    try:
        values = tuple(float(part) for part in raw.split(",") if part.strip())
    except ValueError:
        raise QuantLabError(f"{flag} expects comma-separated numbers (got {raw!r})") from None
    if not values:
        raise QuantLabError(f"{flag} expects at least one value (got {raw!r})")
    return values


@prop_app.command("frontier")
def frontier_cmd(
    trades: Path = typer.Argument(..., exists=True, help="trades.parquet"),
    firm_name: str = typer.Option(..., "--firm", help="Preset name or firm YAML path."),
    paths: int = typer.Option(2000, "--paths", help="MC paths per grid point."),
    seed: int = typer.Option(42, "--seed"),
    scales: str = typer.Option(
        "0.25,0.5,0.75,1.0,1.25,1.5,2.0", "--scales", help="Comma-separated size multiples."
    ),
    ruin_cap: float = typer.Option(
        0.5, "--ruin-cap", help="Funded risk-of-ruin ceiling for the constrained pick."
    ),
    accounts: str | None = typer.Option(
        None, "--accounts", help="Also show the k-account comparison at scale 1.0 (e.g. 2,3,5)."
    ),
    chart: Path | None = typer.Option(
        None, "--chart", help="Write a self-contained frontier chart HTML here."
    ),
    json_out: Path | None = typer.Option(None, "--json", help="Write JSON summary here."),
) -> None:
    """Sweep position-size multiples: EV, pass prob, and ruin vs scale.

    From measurement to recommendation: reports the EV-maximizing scale
    AND the largest scale keeping funded ruin under --ruin-cap (usually
    smaller — the risk-constrained pick). Same-fill caveat applies.
    """
    from quantlab.prop.frontier import compute_multiaccount, compute_scale_frontier
    from quantlab.report.terminal import render_frontier, render_multiaccount

    log = read_trade_log(trades)
    firm = load_firm(firm_name)
    cfg = MCConfig(n_paths=paths, seed=seed)
    fr = compute_scale_frontier(
        log, firm, mc_cfg=cfg, scales=_parse_float_list(scales, "--scales"), ruin_cap=ruin_cap
    )
    render_frontier(fr, console)
    payload = fr.to_json_dict()
    if accounts is not None:
        # Reuse the frontier's own x1.0 run when the grid contains it;
        # only rerun when the user's --scales excluded 1.0.
        base = fr.base_report
        if base is None:
            base = run_monte_carlo(log, firm, cfg)
            console.print("[dim]multi-account table anchored at x1.0 (not in --scales)[/dim]")
        ma = compute_multiaccount(base, k_list=_parse_int_list(accounts, "--accounts"))
        render_multiaccount(ma, console)
        payload["multi_account"] = ma.to_json_dict()
    if chart is not None:
        from quantlab.report.charts import fig_scale_frontier

        write_text(chart, fig_scale_frontier(fr).to_html(full_html=True, include_plotlyjs=True))
        console.print(f"chart written to {chart}")
    if json_out is not None:
        write_text(json_out, json.dumps(sanitize(payload), indent=2))
        console.print(f"JSON summary written to {json_out}")


@prop_app.command("policies")
def policies_cmd(
    trades: Path = typer.Argument(..., exists=True, help="trades.parquet"),
    firm_name: str = typer.Option(..., "--firm", help="Preset name or firm YAML path."),
    paths: int = typer.Option(2000, "--paths", help="MC paths per grid cell."),
    seed: int = typer.Option(42, "--seed"),
    buffers: str = typer.Option(
        "0,1000,2000,4000",
        "--buffers",
        help="keep_buffer levels ($ left working above the payout floor); 0 = asap.",
    ),
    extract: float | None = typer.Option(
        0.5,
        "--extract",
        help="Extraction weight compared against no-extraction (0 disables the column).",
    ),
    sizing: str = typer.Option("fixed", "--sizing", help="fixed | vol_target | cushion."),
    json_out: Path | None = typer.Option(None, "--json", help="Write JSON summary here."),
) -> None:
    """Compare funded-phase payout/extraction policies on your own log.

    Withdraw-ASAP is a policy, not a law: leaving a buffer working above
    the payout floor (and cutting size once the cycle's qualifying days
    are banked) trades payout speed against survival. The grid shows the
    trade on your distribution — mechanical comparison, not optimal
    stopping.
    """
    from quantlab.prop.policies import compute_policy_grid
    from quantlab.report.terminal import render_policies

    log = read_trade_log(trades)
    firm = load_firm(firm_name)
    extracts: tuple[float | None, ...] = (None,) if not extract else (None, extract)
    grid = compute_policy_grid(
        log,
        firm,
        mc_cfg=MCConfig(n_paths=paths, seed=seed, sizing=sizing),
        buffers=_parse_float_list(buffers, "--buffers"),
        extract_weights=extracts,
    )
    render_policies(grid, console)
    if json_out is not None:
        write_text(json_out, json.dumps(sanitize(grid.to_json_dict()), indent=2))
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
        write_text(json_out, json.dumps(sanitize(report.to_json_dict()), indent=2))
        console.print(f"JSON summary written to {json_out}")
