"""Fees, payouts, and expected-value math over simulated paths.

Models the account as a structured product: capped downside (fees paid)
with upside from funded-phase withdrawals net of profit split and
activation costs — the convex payoff structure that can make prop-firm
campaigns +EV even for marginal strategies.

Approximations (documented): fee months are 21 trading days; free reset
credits (Topstep banks 1/rebill) are ignored, making reset EV slightly
pessimistic; FTMO's fee refund applies on the first funded payout.
"""

from __future__ import annotations

import math
from typing import Protocol

import numpy as np

from quantlab.prop.config import FirmConfig
from quantlab.prop.outcomes import (
    OUTCOME_BREACHED,
    EconomicsSummary,
    MonteCarloReport,
    PhaseOutcome,
)

TRADING_DAYS_PER_MONTH = 21


class MCConfigProtocol(Protocol):
    n_paths: int
    seed: int | None
    block_len: int | None


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def _quantiles(values: np.ndarray) -> dict[str, float]:
    if values.size == 0:
        return {}
    return {f"p{q}": float(np.percentile(values, q)) for q in (5, 25, 50, 75, 95)}


def summarize(
    firm: FirmConfig,
    phases: list[PhaseOutcome],
    funded: PhaseOutcome,
    cfg: MCConfigProtocol,
    bootstrap_used: str,
    fidelity: str,
    source_days: int,
    source_trades: int,
    scale_challenge: float,
    scale_funded: float,
    warnings: list[str],
) -> MonteCarloReport:
    n = cfg.n_paths
    fees = firm.fees
    payout = firm.payout

    # ---- challenge outcome across phases (phase sims are independent) ----
    passed_all = np.ones(n, dtype=bool)
    days_used = np.zeros(n)  # trading days consumed until the attempt resolves
    still_going = np.ones(n, dtype=bool)
    for ph in phases:
        phase_days = ph.end_day + 1
        days_used = np.where(still_going, days_used + phase_days, days_used)
        passed_here = ph.passed
        passed_all &= passed_here
        still_going &= passed_here
    pass_prob = float(np.mean(passed_all))
    ci = wilson_ci(int(passed_all.sum()), n)

    # ---- per-attempt evaluation fees ----
    if fees.one_time > 0:
        attempt_fees = np.full(n, float(fees.one_time))
    elif fees.monthly > 0:
        months = np.ceil(days_used / TRADING_DAYS_PER_MONTH)
        attempt_fees = fees.monthly * np.maximum(months, 1)
    else:
        attempt_fees = np.zeros(n)

    # ---- funded value per path ----
    assert funded.total_withdrawn is not None and funded.payout_count is not None
    assert funded.first_payout_day is not None
    received = funded.total_withdrawn * payout.profit_split
    refund = (
        float(fees.one_time) * (funded.payout_count >= 1)
        if fees.refundable_on_first_payout and fees.one_time > 0
        else np.zeros(n)
    )
    funded_value = received + refund - fees.activation

    # ---- single-attempt net distribution ----
    net = -attempt_fees + passed_all * funded_value
    expected_net = float(net.mean())
    var_95 = float(np.percentile(net, 5))
    cvar_95 = float(net[net <= var_95].mean()) if (net <= var_95).any() else var_95

    # ---- reset-campaign EV (analytic from MC estimates) ----
    p = pass_prob
    cost_fail = (
        float(attempt_fees[~passed_all].mean())
        if (~passed_all).any()
        else float(attempt_fees.mean())
    )
    cost_pass = (
        float(attempt_fees[passed_all].mean()) if passed_all.any() else float(attempt_fees.mean())
    )
    value_funded = float(funded_value.mean())
    ev_with_resets: dict[int, float] = {}
    for k in range(1, 6):
        ev = 0.0
        for j in range(1, k + 1):
            ev += (1 - p) ** (j - 1) * p * (value_funded - cost_pass - (j - 1) * cost_fail)
        ev -= (1 - p) ** k * k * cost_fail
        ev_with_resets[k] = ev

    expected_cost_to_funded = cost_fail * (1 - p) / p + cost_pass if p > 0 else float("inf")

    # ---- funded-phase risk stats ----
    got_payout = funded.payout_count >= 1
    p_payout = float(np.mean(got_payout))
    ruin = float(np.mean((funded.outcome == OUTCOME_BREACHED) & ~got_payout))

    time_to_pass = _quantiles(days_used[passed_all]) if passed_all.any() else {}
    to_first = passed_all & got_payout
    days_to_first_payout = (
        _quantiles((days_used + funded.first_payout_day + 1)[to_first]) if to_first.any() else {}
    )

    economics = EconomicsSummary(
        pass_prob=pass_prob,
        pass_prob_ci=ci,
        expected_fees_per_attempt=float(attempt_fees.mean()),
        expected_cost_to_funded=expected_cost_to_funded,
        expected_gross_payout=float((received + refund).mean()),
        expected_net=expected_net,
        ev_with_resets=ev_with_resets,
        p_net_positive=float(np.mean(net > 0)),
        var_95=var_95,
        cvar_95=cvar_95,
        p_payout=p_payout,
        risk_of_ruin_funded=ruin,
        payout_quantiles=_quantiles(received),
        time_to_pass_quantiles=time_to_pass,
        days_to_first_payout_quantiles=days_to_first_payout,
    )
    return MonteCarloReport(
        firm_name=firm.name,
        firm_display=firm.display_name or firm.name,
        account_size=firm.account_size,
        n_paths=n,
        seed=cfg.seed,
        bootstrap=bootstrap_used,
        block_len=cfg.block_len,
        fidelity=fidelity,
        scale_challenge=scale_challenge,
        scale_funded=scale_funded,
        source_days=source_days,
        source_trades=source_trades,
        phases=phases,
        funded=funded,
        economics=economics,
        warnings=warnings,
    )
