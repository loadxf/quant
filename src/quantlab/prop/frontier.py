"""Scale frontier and multi-account EV: from measurement to recommendation.

Scale frontier — the simulator can rerun the whole campaign at any
position-size multiple (`MCConfig.scale`), so instead of reporting one
point it sweeps a grid and reports EV, pass probability, funded ruin,
and CVaR as functions of scale. Framing: risk-constrained growth
(Busseti, Ryu & Boyd 2016, "Risk-constrained Kelly gambling") — the
useful outputs are the EV-maximizing scale AND the largest scale that
keeps funded ruin under a chosen cap, which is usually smaller. The
classic fractional-Kelly caveat applies: EV estimated from one log is
noisy, and overbetting a noisy edge is worse than underbetting it.
Common random numbers (same seed, same day draws) across grid points
keep the frontier smooth instead of MC-jittery.

Multi-account EV — prop traders commonly copy-trade one strategy on k
accounts. Same fills on every account means PERFECT correlation: EV,
VaR, and CVaR all scale by exactly k, and P(everything fails) stays
P(one fails) — k accounts are leverage, not diversification. The naive
independence math (P(all fail) = p^k) that marketing implies is shown
side by side to make the illusion explicit. Staggering start dates does
not change this while the same strategy trades the same sessions.

Both reuse the same-fill linear-scaling assumption (see voltarget):
identical entries/exits at scaled size; ignores sub-contract
granularity, margin, and larger-size psychology.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field

import numpy as np

from quantlab.errors import QuantLabError
from quantlab.prop.config import FirmConfig
from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.prop.outcomes import MonteCarloReport
from quantlab.prop.voltarget import SAME_FILL_CAVEAT
from quantlab.schema.trade import TradeLog

DEFAULT_SCALES = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
DEFAULT_RUIN_CAP = 0.5  # funded risk-of-ruin ceiling for the constrained pick


@dataclass(frozen=True, slots=True)
class FrontierPoint:
    scale: float
    pass_prob: float
    expected_net: float
    risk_of_ruin_funded: float
    cvar_95: float
    p_net_positive: float


@dataclass
class ScaleFrontier:
    points: list[FrontierPoint]
    best_ev_scale: float
    ruin_cap: float
    best_scale_within_ruin: float | None  # largest grid scale with ruin <= cap
    assumption: str = SAME_FILL_CAVEAT
    warnings: list[str] = field(default_factory=list)
    # The x1.0 grid run, kept so a follow-up multi-account table reuses it
    # instead of re-simulating the identical config. Never serialized.
    base_report: MonteCarloReport | None = None

    def to_json_dict(self) -> dict:
        return {
            "points": [dataclasses.asdict(p) for p in self.points],
            "best_ev_scale": self.best_ev_scale,
            "ruin_cap": self.ruin_cap,
            "best_scale_within_ruin": self.best_scale_within_ruin,
            "assumption": self.assumption,
            "warnings": self.warnings,
        }


def compute_scale_frontier(
    log: TradeLog,
    firm: FirmConfig,
    mc_cfg: MCConfig | None = None,
    scales: tuple[float, ...] = DEFAULT_SCALES,
    ruin_cap: float = DEFAULT_RUIN_CAP,
) -> ScaleFrontier:
    """EV / pass-prob / ruin / CVaR across position-size multiples.

    Grid points share the seed (common random numbers), so differences
    between scales are the treatment effect, not resampling noise."""
    if not scales or any(not math.isfinite(s) or s <= 0 for s in scales):
        raise QuantLabError(f"--scales must be positive (got {list(scales)})")
    if not math.isfinite(ruin_cap) or not 0 <= ruin_cap <= 1:
        raise QuantLabError(f"--ruin-cap must be in [0, 1] (got {ruin_cap})")
    from quantlab.prop.montecarlo import ensure_crn_seed

    cfg = ensure_crn_seed(mc_cfg or MCConfig())
    points = []
    base_report = None
    engine_warnings: list[str] = []
    for i, s in enumerate(sorted(scales)):
        run = run_monte_carlo(
            log,
            firm,
            # The frontier sweeps ONE common scale; explicit per-phase
            # scales would silently multiply with it.
            dataclasses.replace(cfg, scale=s, challenge_scale=None, funded_scale=None),
        )
        if i == 0:
            # Per-run engine disclosures (scaling-plan base assumption,
            # bootstrap fallback, excursion fidelity) are identical across
            # grid points — surface the first run's once at frontier level
            # instead of silently discarding them.
            engine_warnings = list(run.warnings)
        if s == 1.0:
            base_report = run
        eco = run.economics
        points.append(
            FrontierPoint(
                scale=s,
                pass_prob=eco.pass_prob,
                expected_net=eco.expected_net,
                risk_of_ruin_funded=eco.risk_of_ruin_funded,
                cvar_95=eco.cvar_95,
                p_net_positive=eco.p_net_positive,
            )
        )

    best = max(points, key=lambda p: p.expected_net)
    within = [p for p in points if p.risk_of_ruin_funded <= ruin_cap]
    best_within = max(within, key=lambda p: p.scale).scale if within else None

    warnings: list[str] = engine_warnings
    # A one-point grid has no trend to report — the single point is
    # trivially "the top of the grid".
    if len(points) > 1 and best.scale == max(s.scale for s in points) and best.expected_net > 0:
        warnings.append(
            f"EV is still rising at the top of the grid (x{best.scale:g}) — the "
            "same-fill assumption gets less realistic as size grows; treat "
            "larger scales as extrapolation, not recommendation"
        )
    if best_within is None:
        warnings.append(
            f"no grid scale keeps funded risk-of-ruin under {ruin_cap:.0%} — "
            "the strategy busts funded accounts at any size; scale cannot fix that"
        )
    return ScaleFrontier(
        points=points,
        best_ev_scale=best.scale,
        ruin_cap=ruin_cap,
        best_scale_within_ruin=best_within,
        warnings=warnings,
        base_report=base_report,
    )


@dataclass(frozen=True, slots=True)
class MultiAccountRow:
    k: int
    expected_net: float  # k x single-account EV (holds under any correlation)
    correlated_cvar_95: float  # same fills: k x single-account CVaR
    correlated_p_all_lose: float  # = P(single loses): accounts fail together
    independent_cvar_95: float  # the illusion: k independent accounts
    independent_p_all_lose: float  # = P(lose)^k


@dataclass
class MultiAccountEV:
    rows: list[MultiAccountRow]
    note: str = (
        "copy-trading k accounts is k-times leverage, not diversification: "
        "identical fills make outcomes perfectly correlated, so worst cases "
        "scale by k and P(all accounts fail) stays P(one fails). The "
        "'independent' columns show the diversification the correlation "
        "destroys. Staggered starts do not decorrelate the same strategy. "
        "Check each firm's copy-trade rules before running multiple accounts."
    )

    def to_json_dict(self) -> dict:
        return dataclasses.asdict(self)


def compute_multiaccount(
    report: MonteCarloReport, k_list: tuple[int, ...] = (2, 3, 5, 10), seed: int = 0
) -> MultiAccountEV:
    """Correlated (real) vs independent (imagined) k-account outcomes from
    the single-attempt per-path net distribution."""
    net = report.economics.net_per_path
    if net is None:
        raise QuantLabError("report carries no per-path net (older report object)")
    if not k_list or any(k < 1 for k in k_list):
        raise QuantLabError(f"--accounts must be >= 1 (got {list(k_list)})")
    p_lose = float(np.mean(net < 0))
    var5 = float(np.percentile(net, 5))
    cvar1 = float(net[net <= var5].mean()) if (net <= var5).any() else var5
    ev1 = float(net.mean())
    rng = np.random.default_rng(seed)
    rows = []
    for k in sorted(set(k_list)):
        # Independent counterfactual: sums of k draws with replacement.
        sums = net[rng.integers(0, net.size, size=(net.size, k))].sum(axis=1)
        ivar5 = float(np.percentile(sums, 5))
        icvar = float(sums[sums <= ivar5].mean()) if (sums <= ivar5).any() else ivar5
        rows.append(
            MultiAccountRow(
                k=k,
                expected_net=k * ev1,
                correlated_cvar_95=k * cvar1,
                correlated_p_all_lose=p_lose,
                independent_cvar_95=icvar,
                independent_p_all_lose=p_lose**k,
            )
        )
    return MultiAccountEV(rows=rows)
