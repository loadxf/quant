"""Economics math: Wilson CI, reset-campaign EV, fee models."""

from __future__ import annotations

import pytest

from quantlab.prop.economics import wilson_ci
from quantlab.prop.montecarlo import MCConfig, calendar_to_trading_days, run_monte_carlo
from quantlab.prop.registry import load_firm

from .conftest import day_trades, simple


class TestWilsonCI:
    def test_basic_properties(self) -> None:
        lo, hi = wilson_ci(50, 100)
        assert lo < 0.5 < hi
        assert hi - lo < 0.2
        lo2, hi2 = wilson_ci(500, 1000)
        assert hi2 - lo2 < hi - lo  # shrinks with n
        assert wilson_ci(0, 0) == (0.0, 1.0)
        lo3, _ = wilson_ci(0, 100)
        assert lo3 == 0.0


class TestCalendarConversion:
    def test_apex_30_days(self) -> None:
        assert calendar_to_trading_days(30) == 22
        assert calendar_to_trading_days(7) == 5


class TestFeeAndEvModels:
    def test_certain_loser_ev_is_minus_k_fees(self) -> None:
        """p=0: campaign EV with k resets = -k x per-attempt fee."""
        firm = load_firm("topstep_50k")  # monthly $49
        log = day_trades([[simple(-500)]] * 20)  # breaches MLL in ~4 days
        report = run_monte_carlo(log, firm, MCConfig(n_paths=200, seed=1))
        eco = report.economics
        assert eco.pass_prob == 0.0
        assert eco.expected_fees_per_attempt == pytest.approx(49.0)
        assert eco.ev_with_resets[3] == pytest.approx(-3 * 49.0)
        assert eco.expected_cost_to_funded == float("inf")
        assert eco.expected_net == pytest.approx(-49.0)

    def test_certain_winner_ev_constant_across_resets(self) -> None:
        """p=1: extra allowed resets never trigger, EV_k identical for all k."""
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(700), simple(700)]] * 60)  # steady +1,400/day
        report = run_monte_carlo(log, firm, MCConfig(n_paths=200, seed=2))
        eco = report.economics
        assert eco.pass_prob == 1.0
        evs = list(eco.ev_with_resets.values())
        assert all(ev == pytest.approx(evs[0]) for ev in evs)
        assert eco.p_net_positive == 1.0
        # 90/10 split applied to withdrawals
        assert eco.expected_gross_payout > 0

    def test_apex_one_time_fee_model(self) -> None:
        firm = load_firm("apex40_50k_intraday")  # one-time $131
        log = day_trades([[simple(-500)]] * 20)
        report = run_monte_carlo(log, firm, MCConfig(n_paths=100, seed=3))
        assert report.economics.expected_fees_per_attempt == pytest.approx(131.0)

    def test_ftmo_refund_included_when_payout(self) -> None:
        """FTMO 2-Step refunds the fee on first payout: for a sure winner the
        expected gross payout includes the 540 refund."""
        firm = load_firm("ftmo_2step_100k")
        log = day_trades([[simple(1500)]] * 100)
        report = run_monte_carlo(log, firm, MCConfig(n_paths=100, seed=4, funded_horizon_days=100))
        eco = report.economics
        assert eco.pass_prob == 1.0
        assert eco.p_payout == 1.0
        # withdrawn * 0.8 + refund 540; withdrawals are large here, just check
        # the refund pushes gross payout above the pure split of withdrawals
        funded = report.funded
        assert funded.total_withdrawn is not None
        pure_split = float((funded.total_withdrawn * 0.8).mean())
        assert eco.expected_gross_payout == pytest.approx(pure_split + 540.0)


class TestOverheadKnobs:
    """M10: generic --extra-monthly / --per-payout-fee overheads."""

    def test_overrides_reduce_ev_and_report_block(self) -> None:
        from quantlab.prop.config import with_fee_overrides

        from ..conftest import random_log

        firm = load_firm("topstep_50k")
        log = random_log(n_days=100, mean=40.0, std=300.0, seed=7)
        cfg = MCConfig(n_paths=300, seed=5)
        base = run_monte_carlo(log, firm, cfg).economics
        loaded = run_monte_carlo(
            log, with_fee_overrides(firm, extra_monthly=100.0, per_payout=30.0), cfg
        ).economics
        assert base.overhead is None
        assert loaded.overhead is not None
        assert loaded.overhead["extra_monthly"] == 100.0
        assert loaded.overhead["per_payout"] == 30.0
        assert loaded.expected_net < base.expected_net
        assert loaded.expected_fees_per_attempt > base.expected_fees_per_attempt

    def test_zero_overrides_return_same_firm(self) -> None:
        from quantlab.prop.config import with_fee_overrides

        firm = load_firm("topstep_50k")
        assert with_fee_overrides(firm) is firm

    def test_certain_loser_bills_one_month_of_overhead(self) -> None:
        from quantlab.prop.config import with_fee_overrides

        firm = with_fee_overrides(load_firm("topstep_50k"), extra_monthly=100.0)
        log = day_trades([[simple(-500)]] * 20)  # breaches in ~4 days
        eco = run_monte_carlo(log, firm, MCConfig(n_paths=100, seed=1)).economics
        assert eco.expected_fees_per_attempt == pytest.approx(49.0 + 100.0)
        assert eco.expected_net == pytest.approx(-149.0)


class TestReactivationOption:
    """M10: Back2Funded-style analytic option value (topstep presets carry
    reactivations: {max: 2, fees: [599, 599]})."""

    def test_block_internally_consistent(self) -> None:
        from ..conftest import random_log

        firm = load_firm("topstep_50k")
        log = random_log(n_days=100, mean=40.0, std=300.0, seed=7)
        eco = run_monte_carlo(log, firm, MCConfig(n_paths=400, seed=5)).economics
        r = eco.reactivation
        assert r is not None
        assert r["max"] == 2 and r["fees"] == [599.0, 599.0]
        assert r["p_ruin_before_payout"] == pytest.approx(eco.risk_of_ruin_funded)
        ruin = r["p_ruin_before_payout"]
        expect = sum(
            ruin**k * max(r["fresh_funded_value"] - fee, 0.0)
            for k, fee in enumerate(r["fees"], start=1)
        )
        assert r["ev_uplift_per_funded"] == pytest.approx(expect)
        assert r["ev_uplift_single_attempt"] == pytest.approx(eco.pass_prob * expect)
        assert r["worth_exercising"] == (r["fresh_funded_value"] > 599.0)

    def test_option_never_negative(self) -> None:
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(-500)]] * 20)  # certain loser: never funded
        eco = run_monte_carlo(log, firm, MCConfig(n_paths=100, seed=1)).economics
        assert eco.reactivation is not None
        assert eco.reactivation["ev_uplift_single_attempt"] == 0.0

    def test_absent_when_firm_has_none(self) -> None:
        firm = load_firm("apex40_50k_eod")  # no reactivations defined
        log = day_trades([[simple(-500)]] * 20)
        eco = run_monte_carlo(log, firm, MCConfig(n_paths=50, seed=1)).economics
        assert eco.reactivation is None


class TestSemanticsReviewFixes:
    """Regressions from the M10 adversarial review (semantics pass)."""

    def test_gross_payout_stays_gross_under_per_payout_fee(self) -> None:
        # Was: expected_gross_payout silently became net of processing
        # fees, contradicting its documented E[withdrawn*split + refund].
        from quantlab.prop.config import with_fee_overrides

        from ..conftest import random_log

        firm = load_firm("topstep_50k")
        log = random_log(n_days=100, mean=40.0, std=300.0, seed=7)
        cfg = MCConfig(n_paths=300, seed=5)
        base = run_monte_carlo(log, firm, cfg).economics
        fee = run_monte_carlo(log, with_fee_overrides(firm, per_payout=30.0), cfg).economics
        assert fee.expected_gross_payout == pytest.approx(base.expected_gross_payout)
        assert fee.expected_net < base.expected_net  # the fee still bites the net

    def test_funded_overhead_key_names_denominator(self) -> None:
        from quantlab.prop.config import with_fee_overrides

        from ..conftest import random_log

        firm = with_fee_overrides(load_firm("topstep_50k"), extra_monthly=100.0)
        log = random_log(n_days=60, mean=40.0, std=300.0, seed=7)
        eco = run_monte_carlo(log, firm, MCConfig(n_paths=100, seed=5)).economics
        assert eco.overhead is not None
        assert "expected_funded_overhead_per_funded" in eco.overhead
