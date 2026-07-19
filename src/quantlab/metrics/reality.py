"""Reality Check orchestrator: one entry point for CLI and reports.

Bundles the honesty layer — cost stress, decay panel, deflated
statistics, permutation drawdowns, and literature-anchored haircut
scenarios — into a single JSON-serializable result.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass, field

import numpy as np

from quantlab.errors import QuantLabError
from quantlab.metrics.costs import (
    CostStress,
    HaircutScenario,
    gross_pnl_warning,
    run_cost_sweep,
    run_haircut_scenarios,
)
from quantlab.metrics.decay import DecayPanel, compute_decay
from quantlab.metrics.deflate import DeflatedStats, compute_deflated
from quantlab.metrics.drawdown_mc import DrawdownMC, permutation_drawdown
from quantlab.prop.config import FirmConfig
from quantlab.prop.montecarlo import MCConfig
from quantlab.schema.trade import TradeLog


@dataclass
class RealityCheck:
    costs: CostStress
    decay: DecayPanel
    deflated: DeflatedStats
    drawdown: DrawdownMC
    haircuts: list[HaircutScenario]
    warnings: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict:
        return {
            "schema_version": 1,
            "costs": self.costs.to_json_dict(),
            "decay": dataclasses.asdict(self.decay),
            "deflated": dataclasses.asdict(self.deflated),
            "drawdown": dataclasses.asdict(self.drawdown),
            "haircuts": [dataclasses.asdict(h) for h in self.haircuts],
            "warnings": self.warnings,
        }


def compute_reality_check(
    log: TradeLog,
    firm: FirmConfig | None = None,
    trials: int = 1,
    tick_value: float | None = None,
    commission_rt: float | None = None,
    stop_slip_ticks: float = 1.0,
    decay_window: int = 30,
    mc_paths: int = 2000,
    seed: int = 42,
    scale: float = 1.0,
    ruin_capital: float | None = None,
    oos_start: dt.datetime | None = None,
    baseline_mc=None,
) -> RealityCheck:
    if len(log) < 3:
        raise QuantLabError(f"reality check needs >= 3 trades (got {len(log)})")
    if trials < 1:
        raise QuantLabError(f"--trials must be >= 1 (got {trials})")
    if decay_window < 2:
        raise QuantLabError(f"--window must be >= 2 (got {decay_window})")
    pnls = np.array([t.pnl for t in log.trades], dtype=float)
    # Same scale as the caller's headline simulation, so the sweep's
    # baseline anchor and the report's headline never disagree.
    mc_cfg = MCConfig(n_paths=mc_paths, seed=seed, scale=scale)
    costs = run_cost_sweep(
        log,
        firm=firm,
        tick_value=tick_value,
        commission_rt=commission_rt,
        stop_slip_ticks=stop_slip_ticks,
        mc_cfg=mc_cfg,
        baseline_report=baseline_mc,
    )
    decay = compute_decay(log, window=decay_window, oos_start=oos_start)
    deflated = compute_deflated(pnls, n_trials=trials)
    drawdown = permutation_drawdown(log, seed=seed, ruin_capital=ruin_capital)
    haircuts = run_haircut_scenarios(log, firm=firm, mc_cfg=mc_cfg)

    warnings = list(costs.warnings)
    gross = gross_pnl_warning(log)
    if gross:
        warnings.append(gross)
    if decay.runs.z < 0 and decay.runs.p < 0.05:
        warnings.append(
            "wins/losses cluster (runs test) — the permutation drawdown "
            "understates risk; trust the block-bootstrap numbers"
        )
    if trials == 1:
        warnings.append(
            "n_trials=1 declared: DSR/MinBTL/haircut-Sharpe skipped — if you "
            "tried multiple strategy variants before this one, rerun with "
            "--trials N for honest multiple-testing deflation"
        )
    return RealityCheck(
        costs=costs,
        decay=decay,
        deflated=deflated,
        drawdown=drawdown,
        haircuts=haircuts,
        warnings=warnings,
    )
