"""Funded-phase payout-path resolution shared by both engines.

Encodes the payout semantics verified against help.topstep.com on
2026-08-13 (articles 8284208, 8284215, 8284233):

- Standard path: N qualifying (winning) days of at least $q each; a
  payout request needs positive profit since the prior payout (first
  payout exempt when `require_profit_since` is set).
- Consistency path: at least `c_min_days` active trading days since the
  window began, positive total net profit in the window, and the largest
  positive day at MOST `c_frac` of that total (inclusive — exactly 40%
  still qualifies, unlike the strict Apex-style gate_pcts).
- Both paths: the payout-request day itself never counts toward the next
  cycle (the window counters reset on the payout day).
- `mll_reset_on_payout`: at each payout approval the trailing floor
  snaps to its cap ("Your Maximum Loss Limit (MLL) resets to $0
  permanently" — Topstep payout policy) even when ordinary trailing
  would leave it below.

The deterministic evaluator and the vectorized Monte Carlo both resolve
their parameters here so the two engines cannot drift apart.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from quantlab.errors import ConfigError, QuantLabError
from quantlab.prop.config import FirmConfig

DEFAULT_SESSIONS_PER_WEEK = 5.0

# Keep withdrawn balances strictly above trailing floors so a payout can
# never itself trigger an inclusive-touch breach on the next bar.
PAYOUT_FLOOR_MARGIN = 0.01


def calendar_to_trading_days(
    calendar_days: int, sessions_per_week: float = DEFAULT_SESSIONS_PER_WEEK
) -> int:
    if calendar_days < 1 or not math.isfinite(sessions_per_week) or sessions_per_week <= 0:
        raise QuantLabError("calendar_days and sessions_per_week must be positive")
    return max(1, math.ceil(calendar_days * sessions_per_week / 7))


@dataclass
class PayoutParams:
    floor: float  # withdrawals never take balance below this
    share_of_balance: float | None
    ladder: np.ndarray  # per-payout caps; last entry repeats
    max_lifetime: int | None
    min_payout: float
    q_count: int
    q_min_profit: float
    period_td: int
    gate_pcts: list[float]
    keep_buffer: float = 0.0  # cushion left working above the payout floor
    path: str = "standard"  # "standard" | "consistency"
    c_min_days: int = 0  # consistency path: min active trading days per window
    c_frac: float = 0.0  # consistency path: best day <= c_frac * window total (INCLUSIVE)
    require_profit_since: bool = False  # standard path: subsequent payouts need profit
    mll_reset_on_payout: bool = False  # trailing floor snaps to its cap at payout


def resolve_payout(
    firm: FirmConfig,
    initial: float,
    gate_pcts: list[float],
    sessions_per_week: float = DEFAULT_SESSIONS_PER_WEEK,
    keep_buffer: float = 0.0,
    path_override: str | None = None,
) -> PayoutParams:
    p = firm.payout
    path = path_override if path_override is not None else p.path
    if path not in ("standard", "consistency"):
        raise ConfigError(f"unknown payout path {path!r} (standard | consistency)")
    floor_candidates = [initial]
    if p.safety_net_floor is not None:
        floor_candidates.append(p.safety_net_floor)
    if p.buffer_above_initial is not None:
        floor_candidates.append(initial + p.buffer_above_initial)
    c_min_days = 0
    c_frac = 0.0
    q_count = p.qualifying_days.count
    q_min_profit = p.qualifying_days.min_daily_profit
    ladder_source = p.payout_cap_ladder
    if path == "consistency":
        if p.consistency is None:
            raise ConfigError(
                f"firm {firm.name!r} selects the consistency payout path but defines "
                "no payout.consistency block"
            )
        c_min_days = p.consistency.min_days
        c_frac = p.consistency.max_best_day_pct / 100.0
        ladder_source = p.consistency.payout_cap_ladder or p.payout_cap_ladder
        # Standard qualifying-day machinery is inert on this path.
        q_count = 0
        q_min_profit = 0.0
    ladder = np.array(ladder_source or [np.inf], dtype=float)
    return PayoutParams(
        floor=max(floor_candidates),
        share_of_balance=p.payout_share_of_balance,
        ladder=ladder,
        max_lifetime=p.max_lifetime_payouts,
        min_payout=max(p.min_payout, 1e-9),
        q_count=q_count,
        q_min_profit=q_min_profit,
        period_td=(
            calendar_to_trading_days(p.period_days, sessions_per_week) if p.period_days else 0
        ),
        gate_pcts=gate_pcts,
        keep_buffer=keep_buffer,
        path=path,
        c_min_days=c_min_days,
        c_frac=c_frac,
        require_profit_since=p.require_profit_since_prior_payout,
        mll_reset_on_payout=p.mll_reset_on_payout,
    )
