"""Regression tests for the adversarial-review findings (engine cluster).

Each test reproduces a confirmed bug from the review; they must stay
green forever.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from quantlab.errors import ConfigError, QuantLabError
from quantlab.prop.bootstrap import make_bootstrapper
from quantlab.prop.dayprofile import DayProfile, trade_points
from quantlab.prop.evaluator import evaluate
from quantlab.prop.montecarlo import (
    MCConfig,
    _resolve_payout,
    _resolve_rules,
    _simulate_phase,
    calendar_to_trading_days,
    observed_sessions_per_week,
    run_monte_carlo,
)
from quantlab.prop.outcomes import OUTCOME_BREACHED, OUTCOME_PASSED
from quantlab.prop.registry import load_firm
from quantlab.prop.synthetic import resolve_geometry, synthetic_geometry_log
from quantlab.schema.trade import Side, Trade, TradeLog

from .conftest import day_trades, make_firm, simple


class TestPayoutTrailingInteraction:
    def test_certain_winner_survives_payouts_on_uncapped_trail(self) -> None:
        """FTMO 1-Step: a +1,500/day certain winner must NOT be breached by
        its own withdrawals (was: funded breach rate 1.0 after payout 1)."""
        firm = load_firm("ftmo_1step_100k")
        log = day_trades([[simple(1500)]] * 100)
        report = run_monte_carlo(log, firm, MCConfig(n_paths=50, seed=1, funded_horizon_days=100))
        outcome = report.funded.outcome
        assert float(np.mean(outcome == OUTCOME_BREACHED)) == 0.0
        assert report.funded.payout_count is not None
        assert int(np.median(report.funded.payout_count)) >= 3

    def test_max_drawdown_excludes_withdrawals(self) -> None:
        """Topstep XFA zero-loss winner: withdrawals rebase the peak, so
        trading max drawdown stays 0 (was: reported ~$790)."""
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(200)]] * 40)
        profile = DayProfile.from_log(log, firm.day_boundary.to_boundary())
        idx = np.arange(profile.n_days)[None, :]
        gates = _resolve_rules(firm.funded, firm, 0.0).payout_gate_pcts
        payout = _resolve_payout(firm, 0.0, gates)
        outcome = _simulate_phase(profile, idx, firm.funded, firm, payout, 1, base_contracts=1)
        assert float(outcome.max_drawdown[0]) == 0.0
        assert outcome.payout_count is not None and outcome.payout_count[0] >= 1


class TestConsistencyStrictBoundary:
    def test_exact_tie_blocks_total_profit_basis(self) -> None:
        """TPT: best day exactly 50% of total must NOT pass ('no day may be
        >= 50%'); one more profitable day unblocks it."""
        firm = load_firm("tpt_50k")
        tie = day_trades(
            [[simple(750)], [simple(750)], [simple(0.0)], [simple(0.0)], [simple(1500)]]
        )
        assert evaluate(tie, firm).outcome == "incomplete"
        unblocked = day_trades(
            [[simple(750)], [simple(750)], [simple(1.0)], [simple(0.0)], [simple(1500)]]
        )
        assert evaluate(unblocked, firm).outcome == "passed"

    def test_topstep_profit_target_basis_stays_inclusive(self) -> None:
        """Topstep: best day exactly 50% of the TARGET is allowed."""
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(1500)], [simple(1500)]])
        result = evaluate(log, firm)
        assert result.outcome == "passed"

    def test_vector_engine_mirrors_tie_block(self) -> None:
        firm = load_firm("tpt_50k")
        tie = day_trades(
            [[simple(750)], [simple(750)], [simple(0.0)], [simple(0.0)], [simple(1500)]]
        )
        profile = DayProfile.from_log(tie, firm.day_boundary.to_boundary())
        idx = np.arange(profile.n_days)[None, :]
        outcome = _simulate_phase(profile, idx, firm.phases[0], firm, None, 1)
        assert int(outcome.outcome[0]) != OUTCOME_PASSED


class TestDensityAwareTimeLimits:
    def _sparse_log(self) -> TradeLog:
        ct = ZoneInfo("America/Chicago")
        trades = []
        day = dt.date(2026, 1, 5)
        count = 0
        while count < 30:
            if day.weekday() in (0, 2):  # Mon/Wed only
                entry = dt.datetime.combine(day, dt.time(9, 0), tzinfo=ct)
                trades.append(Trade(entry, entry, "MNQ", Side.LONG, 1, 100.0, mae=0.0, mfe=100.0))
                count += 1
            day += dt.timedelta(days=1)
        return TradeLog(trades=trades, source="synthetic")

    def test_sparse_trader_gets_fewer_sessions(self) -> None:
        log = self._sparse_log()
        firm = load_firm("apex40_50k_intraday")
        boundary = firm.day_boundary.to_boundary()
        density = observed_sessions_per_week(log, boundary)
        assert density == pytest.approx(2.0, abs=0.15)
        # 30 calendar days at ~2 sessions/week -> ~9 sessions, matching the
        # deterministic evaluator's real calendar clock (was: always 22).
        report = run_monte_carlo(log, firm, MCConfig(n_paths=20, seed=2, funded_horizon_days=5))
        assert float(np.median(report.phases[0].end_day)) <= 9

    def test_dense_conversion_unchanged(self) -> None:
        assert calendar_to_trading_days(30) == 22
        assert calendar_to_trading_days(30, sessions_per_week=2.0) == 9


class TestEconomicsRetryPricing:
    def test_reset_fee_discounts_retries(self) -> None:
        """TPT declares reset $99 vs monthly $170: retries must be cheaper
        than first attempts (was: every retry billed a fresh subscription)."""
        firm = load_firm("tpt_50k")
        log = day_trades([[simple(-700)]] * 10)  # certain fail in ~3 days
        report = run_monte_carlo(log, firm, MCConfig(n_paths=100, seed=3))
        eco = report.economics
        assert eco.pass_prob == 0.0
        # First attempt: 1 month at $170. Retries: $170 - $170 + $99 = $99.
        assert eco.ev_with_resets[1] == pytest.approx(-170.0)
        assert eco.ev_with_resets[3] == pytest.approx(-(170.0 + 99.0 + 99.0))

    def test_full_price_retries_unchanged(self) -> None:
        firm = load_firm("topstep_50k")  # reset == monthly -> no discount
        log = day_trades([[simple(-500)]] * 20)
        report = run_monte_carlo(log, firm, MCConfig(n_paths=100, seed=4))
        assert report.economics.ev_with_resets[3] == pytest.approx(-3 * 49.0)


class TestTradePointsClamp:
    def test_close_below_recorded_mae_still_counts(self) -> None:
        """Inconsistent exports (net pnl below gross MAE) must not hide a
        breach: low clamps to include the close."""
        trade = Trade(
            entry_time=dt.datetime(2026, 1, 5, 15, 0, tzinfo=dt.UTC),
            exit_time=dt.datetime(2026, 1, 5, 15, 30, tzinfo=dt.UTC),
            symbol="MNQ",
            side=Side.LONG,
            quantity=1,
            pnl=-100.0,
            mae=-50.0,  # platform exported gross MAE above the net loss
            mfe=10.0,
        )
        high, low, close = trade_points(trade, 0.0)
        assert low == -100.0  # not -50
        assert close == -100.0
        assert high == 10.0


class TestBootstrapNameValidation:
    def test_typo_raises_instead_of_silent_iid(self) -> None:
        with pytest.raises(QuantLabError, match="stationery"):
            make_bootstrapper("stationery")  # type: ignore[arg-type]


class TestGeometryHonesty:
    def test_synthetic_log_reports_trade_close_fidelity(self) -> None:
        log = synthetic_geometry_log(0.5, 1.0, 3, 100.0, 0.0, 30, 1)
        assert not log.has_excursions  # optimism warning must stay visible

    def test_distortion_detection(self) -> None:
        consistent = resolve_geometry(0.5, 1.0, 100.0, 0.0)
        assert not consistent.distorted
        inconsistent = resolve_geometry(0.6, 1.0, 100.0, 0.0)  # implied EV +20
        assert inconsistent.distorted
        assert inconsistent.shift == pytest.approx(-20.0)
        assert inconsistent.loss_size == pytest.approx(-120.0)


class TestConfigGuards:
    def test_fee_exclusivity_enforced(self) -> None:
        from quantlab.prop.config import FeeSchedule

        with pytest.raises(ConfigError, match="not both"):
            FeeSchedule(monthly=100, one_time=200)

    def test_bad_rule_amount_fails_at_load_with_context(self, tmp_path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text(
            """
name: badfirm
account_size: 10000
phases:
  - name: challenge
    profit_target: 800
    rules:
      - {type: trailing_drawdown, ratchet: eod}
funded:
  name: funded
  rules: []
"""
        )
        with pytest.raises(ConfigError, match=r"badfirm|bad\.yaml"):
            load_firm(path)


class TestDensityEndpointBias:
    """Pass-2 findings: span endpoint bias inflated sessions/week."""

    def test_one_week_dense_log_uses_default_not_seven(self) -> None:
        # 5 Mon-Fri sessions span 5 calendar days: the raw endpoint ratio
        # is 7.0/week, which converted Apex's 30-day expiry to 30 trading
        # days instead of 22. Under two weeks of span -> default density.
        firm = load_firm("apex40_50k_intraday")
        boundary = firm.day_boundary.to_boundary()
        log = day_trades([[simple(100)]] * 5)
        assert observed_sessions_per_week(log, boundary) == 5.0

    def test_multi_week_dense_log_converges_to_five(self) -> None:
        firm = load_firm("apex40_50k_intraday")
        boundary = firm.day_boundary.to_boundary()
        log = day_trades([[simple(100)]] * 20)  # 4 Mon-Fri weeks
        density = observed_sessions_per_week(log, boundary)
        assert density == pytest.approx(5.0, abs=0.35)
        assert calendar_to_trading_days(30, density) <= 22


class TestPayoutUncappedTrailNotStranded:
    def test_full_profit_above_floor_is_withdrawable(self) -> None:
        """FTMO 1-Step: the trail rebases 1:1 with the withdrawal, so the
        pre-withdrawal threshold must not cap the amount (was: every
        payout clipped at width - 0.01, stranding profit each cycle)."""
        firm = load_firm("ftmo_1step_100k")
        log = day_trades([[simple(2000)]] * 60)
        profile = DayProfile.from_log(log, firm.day_boundary.to_boundary())
        idx = np.arange(profile.n_days)[None, :]
        gates = _resolve_rules(firm.funded, firm, 100_000.0).payout_gate_pcts
        payout = _resolve_payout(firm, 100_000.0, gates)
        outcome = _simulate_phase(profile, idx, firm.funded, firm, payout, 1, base_contracts=1)
        assert outcome.outcome[0] != OUTCOME_BREACHED
        assert outcome.total_withdrawn is not None
        # 6 payout cycles x 20k profit each; the old bound capped the total
        # at ~60k (6 x 9,999.99).
        assert float(outcome.total_withdrawn[0]) >= 90_000


class TestRetryPricingOneTimeFees:
    def test_one_time_firm_with_reset_prices_retries_at_reset(self) -> None:
        firm = load_firm("tpt_50k").model_copy(
            update={"fees": type(load_firm("tpt_50k").fees)(one_time=297, reset=35)}
        )
        log = day_trades([[simple(-700)]] * 10)  # certain fail
        report = run_monte_carlo(log, firm, MCConfig(n_paths=50, seed=5))
        assert report.economics.pass_prob == 0.0
        assert report.economics.ev_with_resets[3] == pytest.approx(-(297.0 + 35.0 + 35.0))


class TestConfigDefaultsAndContext:
    def test_period_days_defaults_to_biweekly(self) -> None:
        from quantlab.prop.config import PayoutPolicy

        assert PayoutPolicy().period_days == 14

    def test_fee_exclusivity_error_names_the_file(self, tmp_path) -> None:
        path = tmp_path / "myfirm.yaml"
        path.write_text(
            """
name: myfirm
account_size: 10000
fees: {monthly: 99, one_time: 297}
phases:
  - name: challenge
    profit_target: 800
    rules: []
funded:
  name: funded
  rules: []
"""
        )
        with pytest.raises(ConfigError, match=r"myfirm\.yaml"):
            load_firm(path)


class TestSyntheticResidualWarning:
    def test_small_sample_rounding_residual_warns(self) -> None:
        with pytest.warns(UserWarning, match="rounding shifted"):
            synthetic_geometry_log(0.45, 2.0, 1, 100.0, 35.0, 10, 1)

    def test_exact_sample_stays_silent(self) -> None:
        import warnings as _warnings

        with _warnings.catch_warnings():
            _warnings.simplefilter("error")
            synthetic_geometry_log(0.5, 1.0, 3, 100.0, 0.0, 30, 1)


class TestDensityCompleteWeeks:
    """Pass-3 finding: ceil-week span padding UNDERestimated density for any
    log not ending on a week boundary (a full 22-session month rated
    4.4/week -> Apex expiry 19 trading days instead of 22)."""

    def test_month_not_ending_on_friday_rates_five(self) -> None:
        firm = load_firm("apex40_50k_intraday")
        boundary = firm.day_boundary.to_boundary()
        log = day_trades([[simple(100)]] * 22)  # Mon Jan 5 .. Tue Feb 3
        density = observed_sessions_per_week(log, boundary)
        assert density == pytest.approx(5.0)
        assert calendar_to_trading_days(30, density) == 22

    def test_log_ending_monday_rates_five(self) -> None:
        firm = load_firm("apex40_50k_intraday")
        boundary = firm.day_boundary.to_boundary()
        log = day_trades([[simple(100)]] * 11)  # Mon .. Mon, 2 complete weeks
        assert observed_sessions_per_week(log, boundary) == pytest.approx(5.0)


class TestRefundOnDiscountedRetry:
    """Pass-3 finding: a pass on a discounted retry must refund the reset
    price, not the full first-attempt fee (phantom EV worth the discount)."""

    def test_retry_pass_refunds_reset_not_full_fee(self) -> None:
        from quantlab.prop.config import FeeSchedule
        from quantlab.prop.economics import summarize
        from quantlab.prop.outcomes import OUTCOME_ACTIVE, PhaseOutcome

        firm = make_firm(
            [{"type": "static_max_loss", "amount": 2000}],
            target=1000,
            size=10_000,
            funded_rules=[{"type": "static_max_loss", "amount": 2000}],
        ).model_copy(
            update={"fees": FeeSchedule(one_time=499, reset=99, refundable_on_first_payout=True)}
        )
        n = 4
        eval_phase = PhaseOutcome(
            phase="challenge",
            initial_balance=10_000,
            horizon=10,
            outcome=np.array([OUTCOME_PASSED, OUTCOME_PASSED, OUTCOME_BREACHED, OUTCOME_BREACHED]),
            end_day=np.zeros(n, dtype=int),
            fail_rule=np.full(n, -1, dtype=np.int16),
            rule_names=["static_max_loss"],
            final_balance=np.full(n, 11_000.0),
            max_drawdown=np.zeros(n),
            equity_samples=np.full((2, 10), np.nan),
            lockout_days=np.zeros(n, dtype=int),
        )
        funded = PhaseOutcome(
            phase="funded",
            initial_balance=10_000,
            horizon=10,
            outcome=np.full(n, OUTCOME_ACTIVE, dtype=np.int8),
            end_day=np.full(n, 9, dtype=int),
            fail_rule=np.full(n, -1, dtype=np.int16),
            rule_names=["static_max_loss"],
            final_balance=np.full(n, 10_000.0),
            max_drawdown=np.zeros(n),
            equity_samples=np.full((2, 10), np.nan),
            lockout_days=np.zeros(n, dtype=int),
            total_withdrawn=np.full(n, 1000.0),
            payout_count=np.ones(n, dtype=int),
            first_payout_day=np.zeros(n, dtype=int),
        )

        report = summarize(
            firm=firm,
            phases=[eval_phase],
            funded=funded,
            cfg=MCConfig(n_paths=n),
            bootstrap_used="iid_day",
            fidelity="trade_close",
            source_days=10,
            source_trades=10,
            scale_challenge=1.0,
            scale_funded=1.0,
            warnings=[],
        )
        # p=0.5; value_funded = 1000*split(1.0) + 499 refund = 1499 wait —
        # firm.payout.profit_split defaults to 1.0 in make_firm, so:
        # value_funded = 1000 + 499 = 1499; retry_discount = 400, p_refund=1
        # retry value = 1099; retry fees = 99.
        # k=2: 0.5*(1499-499) + 0.25*(1099-99-499) - 0.25*(499+99) = 475.75
        # (old full-refund math gave 575.75)
        assert report.economics.ev_with_resets[2] == pytest.approx(475.75)
