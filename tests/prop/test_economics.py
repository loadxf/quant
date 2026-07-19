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
