"""Transaction-cost stress testing and literature-anchored haircuts.

The transcript-verified core warning: most published "edges" die under
real costs. Conventions per Kevin Davey ("Building Winning Algorithmic
Trading Systems") and Robert Pardo: model >= 1 tick/side slippage on
market orders (stops fill worse), and require the edge to survive 2x
assumed costs before trusting it.

Haircut scenarios are cross-sectional literature anchors — NEVER a
fitted decay rate (unidentifiable from one log):
- 26%: McLean & Pontiff (J. Finance 2016) out-of-sample decline —
  the statistical-bias upper bound.
- 50%: Falck, Rej & Thesmar (Quantitative Finance 2022) / Rej et al.
  backtest-discounting — live Sharpe ~ half of backtest, worse for
  recent/complex signals.
- 58%: McLean & Pontiff total post-publication decline. US-specific:
  Jacobs & Mueller (JFE 2020) find no reliable post-publication decay
  outside the US.
- 90%: crowded-strategy tail per Khandani & Lo (2007): the canonical
  contrarian strategy decayed 1.38%/day (1995) -> 0.13%/day (2007).
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from quantlab.errors import QuantLabError
from quantlab.metrics.contracts import resolve_contract
from quantlab.metrics.core import profit_factor
from quantlab.prop.config import FirmConfig
from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.schema.trade import TradeLog

HAIRCUT_SCENARIOS: tuple[tuple[float, str], ...] = (
    (0.26, "out-of-sample bias (McLean-Pontiff 2016)"),
    (0.50, "live vs backtest (Falck-Rej-Thesmar 2022)"),
    (0.58, "post-publication, US-specific (McLean-Pontiff 2016; Jacobs-Mueller 2020)"),
    (0.90, "crowded-strategy tail (Khandani-Lo 2007)"),
)


def apply_cost(log: TradeLog, cost_per_contract_rt: float) -> TradeLog:
    """Charge an ADDITIONAL round-turn cost per contract to every trade."""
    trades = [
        dataclasses.replace(
            t,
            pnl=t.pnl - cost_per_contract_rt * t.quantity,
            fees=t.fees + cost_per_contract_rt * t.quantity,
        )
        for t in log.trades
    ]
    return TradeLog(trades=trades, account_currency=log.account_currency, source=log.source)


def haircut_log(log: TradeLog, haircut: float) -> TradeLog:
    """Shrink the mean by `haircut` via a uniform per-trade shift.

    Mirrors synthetic.py's demeaning: geometry and variance are
    preserved while EV drops — the honest way to model "same strategy,
    smaller edge" without inventing a new distribution.
    """
    pnls = np.array([t.pnl for t in log.trades], dtype=float)
    shift = haircut * float(pnls.mean())
    trades = [dataclasses.replace(t, pnl=t.pnl - shift) for t in log.trades]
    return TradeLog(trades=trades, account_currency=log.account_currency, source=log.source)


def gross_pnl_warning(log: TradeLog) -> str | None:
    if log.source == "lean-cloud":
        return None  # QC results are netted at parse time
    if any(t.fees != 0 for t in log.trades):
        return None
    return (
        "every trade reports zero fees — the log's PnL may be GROSS of "
        "commissions/slippage, which overstates the edge; the cost sweep "
        "shows how much survives realistic costs"
    )


@dataclass(frozen=True, slots=True)
class CostPoint:
    label: str
    slip_ticks_per_side: float
    commission_mult: float
    added_rt_per_contract: float
    expectancy: float
    profit_factor: float
    mc_pass_prob: float | None = None
    mc_expected_net: float | None = None


@dataclass(frozen=True, slots=True)
class HaircutScenario:
    haircut: float
    label: str
    expectancy: float
    mc_pass_prob: float | None = None
    mc_expected_net: float | None = None


@dataclass
class CostStress:
    tick_value: float
    tick_source: str  # "resolved:MNQ" | "user" | "unavailable"
    commission_rt: float
    commission_in_log: bool  # True when the log already records fees
    breakeven_added_cost_per_trade: float
    survives_ticks_rt: float | None
    grid: list[CostPoint] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict:
        return dataclasses.asdict(self)


def _point_metrics(pnls: np.ndarray) -> tuple[float, float]:
    return float(pnls.mean()), profit_factor(pnls)


def _dominant_spec(log: TradeLog):
    counts = Counter(t.symbol for t in log.trades)
    dominant, _ = counts.most_common(1)[0]
    spec = resolve_contract(dominant)
    mixed = len(counts) > 1
    return spec, dominant, mixed


def resolve_cost_basis(
    log: TradeLog, tick_value: float | None, commission_rt: float | None
) -> tuple[float, str, float, list[str]]:
    """(tick_value, tick_source, commission_rt, warnings)."""
    warnings: list[str] = []
    spec, dominant, mixed = _dominant_spec(log)
    if mixed:
        warnings.append(
            f"log mixes symbols; cost basis uses the dominant one ({dominant}) — "
            "run per-symbol sweeps for precision"
        )
    if tick_value is None:
        if spec is None:
            raise QuantLabError(
                f"cannot resolve a tick value for symbol {dominant!r} — pass "
                "--tick-value (dollars per tick per contract) explicitly"
            )
        tick_value = spec.tick_value
        tick_source = f"resolved:{spec.root}"
    else:
        tick_source = "user"
    if commission_rt is None:
        commission_rt = spec.commission_rt if spec is not None else 0.0
        if spec is None:
            warnings.append(
                "no commission default for this symbol — commission rows assume $0; "
                "pass --commission for realistic numbers"
            )
    return tick_value, tick_source, commission_rt, warnings


def run_cost_sweep(
    log: TradeLog,
    firm: FirmConfig | None = None,
    tick_value: float | None = None,
    commission_rt: float | None = None,
    stop_slip_ticks: float = 1.0,
    mc_cfg: MCConfig | None = None,
    baseline_report=None,
) -> CostStress:
    """Edge-vs-cost sweep. Metrics at every grid point; the prop-firm
    Monte Carlo (when a firm is given) at three anchor points only —
    baseline, the standard 1-tick assumption, and the Davey "2x costs"
    survival test — to keep runtime sane."""
    tick_value, tick_source, commission_rt, warnings = resolve_cost_basis(
        log, tick_value, commission_rt
    )
    pnls = np.array([t.pnl for t in log.trades], dtype=float)
    quantities = np.array([t.quantity for t in log.trades], dtype=float)
    mean_qty = float(quantities.mean())
    commission_in_log = any(t.fees != 0 for t in log.trades)
    # If the log never recorded fees, the 1x commission row ADDS the
    # baseline commission (the log is presumed gross); if fees are
    # recorded, 1x means "as recorded" and only 2x adds a surcharge.
    commission_offset = 0 if commission_in_log else 1

    grid_points: list[tuple[str, float, float]] = []
    for slip in (0.0, 1.0, 2.0):
        for mult in (1.0, 2.0):
            grid_points.append((f"{slip:g} tick/side, {mult:g}x commission", slip, mult))
    grid_points.append(
        (
            f"stop-stress: {1 + stop_slip_ticks:g} tick/side, 1x commission",
            1.0 + stop_slip_ticks,
            1.0,
        )
    )

    mc_anchors = {
        "0 tick/side, 1x commission": "baseline",
        "1 tick/side, 1x commission": "standard",
        "2 tick/side, 2x commission": "davey_2x",
    }

    grid: list[CostPoint] = []
    for label, slip, mult in grid_points:
        added = 2.0 * slip * tick_value + (mult - 1 + commission_offset) * commission_rt
        stressed_pnls = pnls - added * quantities
        expectancy, pf = _point_metrics(stressed_pnls)
        mc_pass = mc_net = None
        if firm is not None and label in mc_anchors:
            if added == 0.0 and baseline_report is not None:
                # quant report already simulated the unstressed log (at
                # full path count) — reuse it so one HTML never shows two
                # different pass probabilities for the same baseline.
                report = baseline_report
            else:
                stressed_log = apply_cost(log, added) if added else log
                report = run_monte_carlo(
                    stressed_log, firm, mc_cfg or MCConfig(n_paths=2000, seed=42)
                )
            mc_pass = report.economics.pass_prob
            mc_net = report.economics.expected_net
        grid.append(
            CostPoint(
                label=label,
                slip_ticks_per_side=slip,
                commission_mult=mult,
                added_rt_per_contract=added,
                expectancy=expectancy,
                profit_factor=pf,
                mc_pass_prob=mc_pass,
                mc_expected_net=mc_net,
            )
        )

    # Headline numbers share the grid's fee stance: a fee-less (gross)
    # log's baseline already deducts 1x commission, so breakeven/survives
    # start from that net figure — not the gross mean the grid contradicts.
    baseline_expectancy = float(pnls.mean()) - commission_offset * commission_rt * mean_qty
    survives = (
        baseline_expectancy / (mean_qty * tick_value)
        if baseline_expectancy > 0 and mean_qty > 0 and tick_value > 0
        else None
    )
    return CostStress(
        tick_value=tick_value,
        tick_source=tick_source,
        commission_rt=commission_rt,
        commission_in_log=commission_in_log,
        breakeven_added_cost_per_trade=baseline_expectancy,
        survives_ticks_rt=survives,
        grid=grid,
        warnings=warnings,
    )


def run_haircut_scenarios(
    log: TradeLog, firm: FirmConfig | None = None, mc_cfg: MCConfig | None = None
) -> list[HaircutScenario]:
    """EV under the literature-anchored decay scenarios (see module
    docstring). A positive-EV log only — haircutting a negative mean
    would INCREASE the edge, which is nonsense."""
    pnls = np.array([t.pnl for t in log.trades], dtype=float)
    if float(pnls.mean()) <= 0:
        return []
    mean = float(pnls.mean())
    out: list[HaircutScenario] = []
    for haircut, label in HAIRCUT_SCENARIOS:
        mc_pass = mc_net = None
        if firm is not None:
            # The shifted log is only needed to feed the simulator.
            report = run_monte_carlo(
                haircut_log(log, haircut), firm, mc_cfg or MCConfig(n_paths=2000, seed=42)
            )
            mc_pass = report.economics.pass_prob
            mc_net = report.economics.expected_net
        out.append(
            HaircutScenario(
                haircut=haircut,
                label=label,
                expectancy=mean * (1.0 - haircut),  # uniform shift: exact
                mc_pass_prob=mc_pass,
                mc_expected_net=mc_net,
            )
        )
    return out
