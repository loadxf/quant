"""Fees, payouts, and expected-value math over simulated paths.

Models the account as a structured product: capped downside (fees paid)
with upside from funded-phase withdrawals net of profit split and
activation costs — the convex payoff structure that can make prop-firm
campaigns +EV even for marginal strategies.

Approximations (documented): fee months are 21 trading days at the
5-sessions/week baseline, scaled by the source log's observed density so
a 2-sessions/week trader's 21 trading days bill as the ~2.5 calendar
months they actually span; free reset credits (Topstep banks 1/rebill)
are ignored, making reset EV slightly pessimistic; FTMO's fee refund
applies on the first funded payout; retry attempts replace the attempt
fee (monthly rebill or one-time purchase) with the discounted reset fee
when the firm defines one, full price otherwise; funded-account
reactivations (Topstep Back2Funded) are valued as an OPTIONAL analytic
option (fresh-funded-phase approximation, floored at zero, reported
separately from the headline EV — never silently added to it).
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

TRADING_DAYS_PER_MONTH = 21  # at the 5-sessions/week baseline density
BASELINE_SESSIONS_PER_WEEK = 5.0


class MCConfigProtocol(Protocol):
    n_paths: int
    seed: int | None
    block_len: int | None


def _sizing_block(cfg: MCConfigProtocol) -> dict:
    mode = getattr(cfg, "sizing", "fixed")
    if mode == "vol_target":
        return {
            "mode": mode,
            "vol_lambda": getattr(cfg, "vol_lambda", None),
            "vol_target": getattr(cfg, "vol_target", None),
            "vol_clip": list(getattr(cfg, "vol_clip", (0.5, 1.5))),
        }
    if mode == "cushion":
        return {"mode": mode, "cushion_clip": list(getattr(cfg, "cushion_clip", (0.25, 1.5)))}
    return {"mode": "fixed"}


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
    sessions_per_week: float = BASELINE_SESSIONS_PER_WEEK,
    block_len_used: int | None = None,
    base_contracts: float | None = None,
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
    # Density-aware month count: N trading days of a sparse trader span
    # more calendar months (and rebills) than the same N of a daily trader.
    days_per_month = TRADING_DAYS_PER_MONTH * sessions_per_week / BASELINE_SESSIONS_PER_WEEK
    if fees.one_time > 0:
        attempt_fees = np.full(n, float(fees.one_time))
    elif fees.monthly > 0:
        months = np.ceil(days_used / days_per_month)
        attempt_fees = fees.monthly * np.maximum(months, 1)
    else:
        attempt_fees = np.zeros(n)
    # Generic recurring overhead (data/platform subscriptions) bills over
    # the same density-aware months as the eval subscription; folding it
    # into attempt_fees makes every downstream figure (retry campaign EV,
    # cost-to-funded, VaR) overhead-aware with one insertion point.
    overhead = None
    if fees.extra_monthly > 0:
        eval_overhead = fees.extra_monthly * np.maximum(np.ceil(days_used / days_per_month), 1)
        attempt_fees = attempt_fees + eval_overhead
        overhead = {"expected_eval_overhead_per_attempt": float(eval_overhead.mean())}

    # ---- funded value per path ----
    assert funded.total_withdrawn is not None and funded.payout_count is not None
    assert funded.first_payout_day is not None
    # received_gross stays E[withdrawn * split] — the documented meaning of
    # expected_gross_payout; processing costs reduce only the NET figures
    # (funded_value, payout_quantiles, the reactivation fresh value). The
    # payout-trust haircut is different: denial risk is value never
    # received AT ALL, so it scales gross and net alike.
    received_gross = funded.total_withdrawn * payout.profit_split
    if fees.payout_haircut > 0:
        received_gross = received_gross * (1.0 - fees.payout_haircut)
        warnings.append(
            f"payout values haircut {fees.payout_haircut:.0%} for counterparty "
            "risk — a USER-SUPPLIED assumption, not firm data"
        )
    received = received_gross
    if fees.per_payout > 0:
        received = received_gross - fees.per_payout * funded.payout_count
    refund = (
        float(fees.one_time) * (funded.payout_count >= 1)
        if fees.refundable_on_first_payout and fees.one_time > 0
        else np.zeros(n)
    )
    if fees.payout_haircut > 0:
        # The refund is disbursed WITH the first payout — the same
        # denial/firm-failure risk the haircut prices applies to it.
        refund = refund * (1.0 - fees.payout_haircut)
    funded_value = received + refund - fees.activation
    if fees.extra_monthly > 0:
        funded_months = np.ceil((funded.end_day + 1) / days_per_month)
        funded_value = funded_value - fees.extra_monthly * funded_months
        assert overhead is not None
        # Denominator made explicit in the key: this is PER FUNDED ACCOUNT
        # (the funded sim runs on every path); the per-attempt EV drag is
        # pass_prob times this, never a straight sum with the eval figure.
        overhead["expected_funded_overhead_per_funded"] = float(
            (fees.extra_monthly * funded_months).mean()
        )
    if fees.per_payout > 0:
        # Kept alongside the knob so the EV-waterfall chart can show the
        # full overhead drag and still sum exactly to expected_net.
        overhead = (overhead or {}) | {
            "expected_payout_processing_per_funded": float(
                (fees.per_payout * funded.payout_count).mean()
            )
        }
    if fees.extra_monthly > 0 or fees.per_payout > 0:
        overhead = (overhead or {}) | {
            "extra_monthly": fees.extra_monthly,
            "per_payout": fees.per_payout,
        }

    # ---- single-attempt net distribution ----
    net = -attempt_fees + passed_all * funded_value
    expected_net = float(net.mean())
    var_95 = float(np.percentile(net, 5))
    cvar_95 = float(net[net <= var_95].mean()) if (net <= var_95).any() else var_95

    # ---- exact EV decomposition (the waterfall's bars) ----
    # Path-level means of the linear pieces of `net`, so the parts sum to
    # expected_net EXACTLY (an analytic pass_prob * E[...] decomposition
    # differs by Monte Carlo covariance and would not add up on screen).
    overhead_per_path = np.zeros(n)
    if fees.per_payout > 0:
        overhead_per_path = overhead_per_path + fees.per_payout * funded.payout_count
    if fees.extra_monthly > 0:
        overhead_per_path = overhead_per_path + fees.extra_monthly * np.ceil(
            (funded.end_day + 1) / days_per_month
        )
    ev_decomposition = {
        "eval_fees": float(-attempt_fees.mean()),
        "payout_value": float(np.mean(passed_all * (received_gross + refund))),
        "activation": -pass_prob * float(fees.activation),
        "overheads": float(-np.mean(passed_all * overhead_per_path)),
    }

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
    # Retry attempts: a declared reset fee replaces the attempt's base fee
    # (the monthly rebill it pushes out, or the one-time purchase price) —
    # gating on monthly alone would bill one_time-fee firms full price.
    base_fee = fees.monthly if fees.monthly > 0 else fees.one_time
    retry_discount = base_fee - fees.reset if base_fee > 0 and fees.reset > 0 else 0.0
    retry_fail = max(cost_fail - retry_discount, 0.0)
    retry_pass = max(cost_pass - retry_discount, 0.0)
    value_funded = float(funded_value.mean())
    # The refund models "fee returned with the first payout" — it returns
    # what the PASSING attempt actually cost. A pass on a discounted retry
    # must refund the reset price, not the full first-attempt fee, or every
    # retried pass injects phantom EV worth the discount.
    p_refund = (
        float(np.mean(funded.payout_count >= 1))
        if fees.refundable_on_first_payout and fees.one_time > 0
        else 0.0
    )
    # The retried-pass refund correction is refund value too, so the
    # counterparty haircut applies to it as well.
    retry_value_funded = value_funded - retry_discount * p_refund * (1.0 - fees.payout_haircut)
    ev_with_resets: dict[int, float] = {}
    for k in range(1, 6):
        ev = 0.0
        fail_costs_before = 0.0
        for j in range(1, k + 1):
            attempt_pass_cost = cost_pass if j == 1 else retry_pass
            attempt_value = value_funded if j == 1 else retry_value_funded
            ev += (1 - p) ** (j - 1) * p * (attempt_value - attempt_pass_cost - fail_costs_before)
            fail_costs_before += cost_fail if j == 1 else retry_fail
        ev -= (1 - p) ** k * fail_costs_before
        ev_with_resets[k] = ev

    if p > 0:
        # First attempt at full price; geometric retries at reset pricing.
        expected_cost_to_funded = p * cost_pass + (1 - p) * (
            cost_fail + retry_fail * (1 - p) / p + retry_pass
        )
    else:
        expected_cost_to_funded = float("inf")

    # ---- funded-phase risk stats ----
    got_payout = funded.payout_count >= 1
    p_payout = float(np.mean(got_payout))
    ruin = float(np.mean((funded.outcome == OUTCOME_BREACHED) & ~got_payout))

    # ---- reactivation option value (Topstep Back2Funded-style) ----
    # Analytic layer over the MC estimates, like ev_with_resets. Eligibility
    # mirrors the firm rule AND the ruin metric: the account was lost before
    # any payout. Approximations (documented in research-notes): each paid
    # reactivation restarts a FRESH funded phase whose expected trader value
    # is E[received] (profit-split net of per-payout costs; activation and
    # eval-fee-refund mechanics are not re-applied), and the k-th
    # opportunity arises with probability ruin^k. Exercise is OPTIONAL, so
    # every term is floored at 0 — the option can only add EV; when the
    # fresh-funded value is below the fee the block says so explicitly.
    reactivation = None
    react = payout.reactivations
    if react.max > 0 and react.fees:
        fresh_value = float(received.mean())
        uplift = 0.0
        chain = 1.0
        fee_list = [
            float(react.fees[k] if k < len(react.fees) else react.fees[-1])
            for k in range(react.max)
        ]
        for fee_k in fee_list:
            chain *= ruin
            uplift += chain * max(fresh_value - fee_k, 0.0)
        reactivation = {
            "max": react.max,
            "fees": fee_list,
            "p_ruin_before_payout": ruin,
            "fresh_funded_value": fresh_value,
            "worth_exercising": fresh_value > min(fee_list),
            "ev_uplift_per_funded": uplift,
            "ev_uplift_single_attempt": pass_prob * uplift,
        }

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
        expected_gross_payout=float((received_gross + refund).mean()),
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
        overhead=overhead,
        reactivation=reactivation,
        net_per_path=net,
        received_per_path=received,
        ev_decomposition=ev_decomposition,
    )
    return MonteCarloReport(
        firm_name=firm.name,
        firm_display=firm.display_name or firm.name,
        account_size=firm.account_size,
        n_paths=n,
        seed=cfg.seed,
        bootstrap=bootstrap_used,
        # IID resampling has no block length, even if an irrelevant explicit
        # value was supplied in the shared configuration.
        block_len=block_len_used,
        fidelity=fidelity,
        scale_challenge=scale_challenge,
        scale_funded=scale_funded,
        source_days=source_days,
        source_trades=source_trades,
        phases=phases,
        funded=funded,
        economics=economics,
        warnings=warnings,
        sizing=_sizing_block(cfg),
        policy={
            "payout_policy": getattr(cfg, "payout_policy", "asap"),
            "keep_buffer": getattr(cfg, "keep_buffer", 0.0),
            "extract_weight": getattr(cfg, "extract_weight", None),
            "base_contracts": base_contracts,
        },
    )
