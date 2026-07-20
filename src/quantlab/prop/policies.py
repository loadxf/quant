"""Funded-phase policy comparison: payout timing x extraction.

The engine's default payout behavior — withdraw the maximum as soon as
eligible — is itself a POLICY, not a law of nature. Withdrawing shrinks
the cushion above the trailing floor, so "take money off the table now"
trades directly against "survive longer and extract more later". The
grid makes that trade-off visible on the trader's own distribution:

- payout timing: asap vs keep_buffer B (leave $B of cushion working
  above the payout floor). Empirically the buffer COMPOUNDS — often
  higher long-run EV — but the first payout lands later, so
  ruin-before-any-payout can rise. Neither direction is universal;
  that is exactly why the grid runs on the trader's own distribution.
- extraction: once the cycle's qualifying days are banked, cut size to
  extract_weight until the payout lands (protect the banked cycle) —
  typically delays the payout in exchange for defending it.

Every cell reruns the FULL Monte Carlo with common random numbers (same
seed), so differences between cells are the policy effect, not
resampling noise. This is a mechanical comparison of simple policies on
one log — not an optimal-stopping solution, and framed as such.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

import numpy as np

from quantlab.errors import QuantLabError
from quantlab.prop.config import FirmConfig
from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.schema.trade import TradeLog

DEFAULT_BUFFERS = (0.0, 1000.0, 2000.0, 4000.0)
DEFAULT_EXTRACTS: tuple[float | None, ...] = (None, 0.5)


@dataclass(frozen=True, slots=True)
class PolicyCell:
    label: str
    keep_buffer: float
    extract_weight: float | None
    pass_prob: float
    expected_net: float
    risk_of_ruin_funded: float
    p_payout: float
    expected_gross_payout: float
    days_to_first_payout_p50: float | None


@dataclass
class PolicyGrid:
    cells: list[PolicyCell]
    best_net_label: str
    lowest_ruin_label: str
    note: str = (
        "each cell reruns the full Monte Carlo with common random numbers; "
        "differences are the policy effect. A mechanical comparison of "
        "simple payout/extraction policies on YOUR distribution — not an "
        "optimal-stopping claim."
    )
    warnings: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict:
        return {
            "cells": [dataclasses.asdict(c) for c in self.cells],
            "best_net_label": self.best_net_label,
            "lowest_ruin_label": self.lowest_ruin_label,
            "note": self.note,
            "warnings": self.warnings,
        }


def _label(buffer: float, extract: float | None) -> str:
    timing = "asap" if buffer == 0 else f"keep ${buffer:,.0f}"
    return timing if extract is None else f"{timing} + extract {extract:g}x"


def compute_policy_grid(
    log: TradeLog,
    firm: FirmConfig,
    mc_cfg: MCConfig | None = None,
    buffers: tuple[float, ...] = DEFAULT_BUFFERS,
    extract_weights: tuple[float | None, ...] = DEFAULT_EXTRACTS,
) -> PolicyGrid:
    """Full-MC comparison across the payout-policy grid (CRN per cell)."""
    if not buffers or any(b < 0 for b in buffers):
        raise QuantLabError(f"--buffers must be >= 0 (got {list(buffers)})")
    cfg = mc_cfg or MCConfig()
    if cfg.seed is None:
        cfg = dataclasses.replace(cfg, seed=int(np.random.default_rng().integers(0, 2**31 - 1)))
    if firm.payout.qualifying_days.count == 0 and any(e is not None for e in extract_weights):
        extract_weights = tuple(e for e in extract_weights if e is None) or (None,)

    cells: list[PolicyCell] = []
    warnings: list[str] = []
    for buffer in sorted(set(buffers)):
        for extract in extract_weights:
            run = run_monte_carlo(
                log,
                firm,
                dataclasses.replace(
                    cfg,
                    payout_policy="asap" if buffer == 0 else "keep_buffer",
                    keep_buffer=buffer,
                    extract_weight=extract,
                ),
            )
            eco = run.economics
            days = eco.days_to_first_payout_quantiles
            cells.append(
                PolicyCell(
                    label=_label(buffer, extract),
                    keep_buffer=buffer,
                    extract_weight=extract,
                    pass_prob=eco.pass_prob,
                    expected_net=eco.expected_net,
                    risk_of_ruin_funded=eco.risk_of_ruin_funded,
                    p_payout=eco.p_payout,
                    expected_gross_payout=eco.expected_gross_payout,
                    days_to_first_payout_p50=days.get("p50") if days else None,
                )
            )
    if len({c.expected_net for c in cells}) == 1:
        warnings.append(
            "every policy produced identical EV — payouts likely never "
            "trigger on this log/firm (check qualifying days and horizon)"
        )
    best_net = max(cells, key=lambda c: c.expected_net)
    lowest_ruin = min(cells, key=lambda c: c.risk_of_ruin_funded)
    return PolicyGrid(
        cells=cells,
        best_net_label=best_net.label,
        lowest_ruin_label=lowest_ruin.label,
        warnings=warnings,
    )
