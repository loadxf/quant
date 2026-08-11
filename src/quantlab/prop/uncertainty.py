"""Source-log sampling uncertainty via an outer (nested) bootstrap.

The headline pass-probability's Wilson CI measures SIMULATION noise only
— how many Monte Carlo paths were run — and shrinks with `--paths`
regardless of how little data the paths were resampled from. A 60-day
log and a 250-day log can both report ±0.5pp, which is dishonest: the
dominant uncertainty is that the source log itself is one sample of the
strategy's process.

The outer bootstrap makes that visible (nested/double bootstrap; see
Chang & Hall 2015 and Efron & Tibshirani 1993 §12): resample the SOURCE
DAYS with the same stationary block scheme the engine uses, rerun a
smaller inner Monte Carlo on each resampled profile, and report the
spread of the resulting pass probabilities and EVs. The band answers
"had my log come out slightly differently, what would this tool have
told me?" — the question the Wilson CI cannot.

Convention: outer resamples have the SAME length as the source log
(uncertainty at the observed sample size), and each inner run re-derives
its own Politis-White block length and auto vol-target from the
resampled profile, exactly as a fresh log would.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

import numpy as np

from quantlab.prop.bootstrap import MIN_DAYS_FOR_BLOCKS, resolve_sampler
from quantlab.prop.config import FirmConfig
from quantlab.prop.dayprofile import DayProfile
from quantlab.prop.montecarlo import (
    MCConfig,
    _run_from_profile,
    observed_sessions_per_week,
)
from quantlab.schema.trade import TradeLog

QUANTILES = (5, 25, 50, 75, 95)
WIDE_BAND_PP = 20.0  # p5-p95 pass-prob spread (in points) that triggers the warning


@dataclass(frozen=True, slots=True)
class SamplingUncertainty:
    n_outer: int
    inner_paths: int
    source_days: int
    outer_bootstrap: str
    outer_block_len: int | None
    pass_prob_quantiles: dict[str, float]
    expected_net_quantiles: dict[str, float]
    band_width_pp: float  # p95 - p5 of pass prob, in percentage points
    warnings: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict:
        return dataclasses.asdict(self)


def source_uncertainty(
    log: TradeLog,
    firm: FirmConfig,
    mc_cfg: MCConfig | None = None,
    n_outer: int = 100,
    inner_paths: int = 500,
) -> SamplingUncertainty:
    """Distribution of (pass_prob, expected_net) across outer block-bootstrap
    resamples of the source days. `mc_cfg` carries the headline run's scale,
    horizons, sizing, and seed; its n_paths is replaced by `inner_paths`."""
    cfg = mc_cfg or MCConfig()
    boundary = firm.day_boundary.to_boundary()
    days = log.daily_groups(boundary)
    sessions_per_week = observed_sessions_per_week(log, boundary, days=days)
    profile = DayProfile.from_log(log, boundary, days=days)
    n_days = profile.n_days

    warnings: list[str] = []
    outer_sampler, outer_name, outer_block, fell_back = resolve_sampler(
        "stationary", profile.day_pnl
    )
    if fell_back:
        warnings.append(
            f"only {n_days} source days (<{MIN_DAYS_FOR_BLOCKS}): outer resampling "
            "fell back to iid days — the band itself is low-confidence"
        )
    outer_rng = np.random.default_rng(cfg.seed)
    outer_idx = outer_sampler.sample(n_days, n_outer, n_days, outer_rng)

    inner_cfg = dataclasses.replace(cfg, n_paths=inner_paths)
    pass_probs = np.empty(n_outer)
    nets = np.empty(n_outer)
    for b in range(n_outer):
        rp = profile.gather(outer_idx[b])
        # Each inner run treats its resample as a fresh log: own block
        # length, own auto vol-target (via _run_from_profile), own seed
        # stream (deterministic in (cfg.seed, b)).
        inner_sampler, _, inner_block, _ = resolve_sampler(outer_name, rp.day_pnl)
        report = _run_from_profile(
            rp,
            firm,
            inner_cfg,
            rng=np.random.default_rng((cfg.seed if cfg.seed is not None else 0, b)),
            sampler=inner_sampler,
            bootstrap_name=outer_name,
            block_len_used=inner_block,
            sessions_per_week=sessions_per_week,
            source_trades=len(log),
            warnings=[],
            base_contracts=(
                cfg.base_contracts if cfg.base_contracts is not None else log.max_abs_quantity()
            ),
        )
        if b == 0:
            # Inner runs share cfg/firm/base, so their engine-level
            # disclosures (e.g. scaling-plan base assumption) are
            # identical — surface the first run's once at band level.
            warnings.extend(w for w in report.warnings if w not in warnings)
        pass_probs[b] = report.economics.pass_prob
        nets[b] = report.economics.expected_net

    pq = {f"p{q}": float(np.percentile(pass_probs, q)) for q in QUANTILES}
    nq = {f"p{q}": float(np.percentile(nets, q)) for q in QUANTILES}
    band = (pq["p95"] - pq["p5"]) * 100.0
    if band > WIDE_BAND_PP:
        warnings.append(
            f"pass probability is deeply uncertain from {n_days} source days alone: "
            f"resampling the log moves it {pq['p5']:.0%}-{pq['p95']:.0%} — collect "
            "more history before trusting the point estimate"
        )
    return SamplingUncertainty(
        n_outer=n_outer,
        inner_paths=inner_paths,
        source_days=n_days,
        outer_bootstrap=outer_name,
        outer_block_len=outer_block,
        pass_prob_quantiles=pq,
        expected_net_quantiles=nq,
        band_width_pp=band,
        warnings=warnings,
    )
