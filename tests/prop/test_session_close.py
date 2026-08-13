"""Session-close rule (D3): flat by 15:10 America/Chicago, verified
against Topstep 2026-08-13. CST and CDT dates, boundary instants,
overnight positions, evening entries, earlier product closes, and the
Monte Carlo's source-log screen."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from quantlab.errors import QuantLabError
from quantlab.prop.evaluator import evaluate
from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.prop.registry import load_firm
from quantlab.schema.trade import Side, Trade, TradeLog

from .conftest import make_firm

CT = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")

SESSION_CLOSE = {"type": "session_close", "tz": "America/Chicago", "hard_close": "15:10:00"}


def trade_at(
    entry: dt.datetime, exit_: dt.datetime, pnl: float = 50.0, symbol: str = "MNQ"
) -> Trade:
    return Trade(
        entry_time=entry,
        exit_time=exit_,
        symbol=symbol,
        side=Side.LONG,
        quantity=1,
        pnl=pnl,
        mae=min(0.0, pnl),
        mfe=max(0.0, pnl),
    )


def one_trade_log(trade: Trade) -> TradeLog:
    return TradeLog(trades=[trade], source="synthetic")


def firm_with_close(hard_close: str = "15:10:00"):
    return make_firm(
        [
            {"type": "trailing_drawdown", "amount": 2000, "ratchet": "eod", "threshold_cap": 50000},
            {**SESSION_CLOSE, "hard_close": hard_close},
        ],
        target=3000,
    )


class TestHardCloseBoundary:
    def test_exit_one_second_before_close_is_legal_cst(self) -> None:
        """January date: 15:09:59 CST — legal."""
        day = dt.date(2026, 1, 12)  # Monday, CST
        trade = trade_at(
            dt.datetime.combine(day, dt.time(14, 0), tzinfo=CT),
            dt.datetime.combine(day, dt.time(15, 9, 59), tzinfo=CT),
        )
        result = evaluate(one_trade_log(trade), firm_with_close())
        assert result.outcome == "incomplete"
        assert result.breach is None

    def test_exit_at_close_instant_breaches_cst(self) -> None:
        """15:10:00 exactly: the position was open AT the deadline."""
        day = dt.date(2026, 1, 12)
        trade = trade_at(
            dt.datetime.combine(day, dt.time(14, 0), tzinfo=CT),
            dt.datetime.combine(day, dt.time(15, 10, 0), tzinfo=CT),
        )
        result = evaluate(one_trade_log(trade), firm_with_close())
        assert result.outcome == "breached"
        assert result.breach is not None and result.breach.rule == "session_close"

    def test_cdt_conversion_from_utc_timestamps(self) -> None:
        """July date (CDT, UTC-5): 20:10 UTC == 15:10 CDT breaches;
        20:09:59 UTC == 15:09:59 CDT is legal. A fixed UTC offset would
        get one of these wrong."""
        day = dt.date(2026, 7, 13)  # Monday, CDT
        legal = trade_at(
            dt.datetime(2026, 7, 13, 19, 0, tzinfo=UTC),
            dt.datetime(2026, 7, 13, 20, 9, 59, tzinfo=UTC),
        )
        assert evaluate(one_trade_log(legal), firm_with_close()).outcome == "incomplete"
        violating = trade_at(
            dt.datetime.combine(day, dt.time(14, 0), tzinfo=CT),
            dt.datetime(2026, 7, 13, 20, 10, 0, tzinfo=UTC),
        )
        result = evaluate(one_trade_log(violating), firm_with_close())
        assert result.outcome == "breached"
        assert result.breach is not None and result.breach.rule == "session_close"

    def test_overnight_position_breaches(self) -> None:
        """Entered 10:00 CT, exited 09:00 CT the NEXT day: spans its entry
        session's 15:10 close."""
        trade = trade_at(
            dt.datetime(2026, 1, 12, 10, 0, tzinfo=CT),
            dt.datetime(2026, 1, 13, 9, 0, tzinfo=CT),
        )
        result = evaluate(one_trade_log(trade), firm_with_close())
        assert result.outcome == "breached"
        assert result.breach is not None and result.breach.rule == "session_close"

    def test_evening_entry_held_to_morning_is_legal(self) -> None:
        """Entered 18:00 CT (belongs to the NEXT session after the 17:00
        roll), exited 09:00 the next morning: never spans ITS session's
        15:10 — legal."""
        trade = trade_at(
            dt.datetime(2026, 1, 12, 18, 0, tzinfo=CT),
            dt.datetime(2026, 1, 13, 9, 0, tzinfo=CT),
        )
        result = evaluate(one_trade_log(trade), firm_with_close())
        assert result.outcome == "incomplete"
        assert result.breach is None

    def test_entry_inside_prohibited_window_breaches(self) -> None:
        """15:30-15:45 CT is after the hard close but before the 17:00
        roll — still the same session, still a violation."""
        trade = trade_at(
            dt.datetime(2026, 1, 12, 15, 30, tzinfo=CT),
            dt.datetime(2026, 1, 12, 15, 45, tzinfo=CT),
        )
        result = evaluate(one_trade_log(trade), firm_with_close())
        assert result.outcome == "breached"

    def test_earlier_product_close(self) -> None:
        """A product with an earlier close uses its own hard_close: a
        13:00 exit is legal under 15:10 but breaches under 12:00."""
        day = dt.date(2026, 1, 12)
        trade = trade_at(
            dt.datetime.combine(day, dt.time(10, 0), tzinfo=CT),
            dt.datetime.combine(day, dt.time(13, 0), tzinfo=CT),
        )
        assert evaluate(one_trade_log(trade), firm_with_close("15:10:00")).outcome == "incomplete"
        early = evaluate(one_trade_log(trade), firm_with_close("12:00:00"))
        assert early.outcome == "breached"

    def test_violation_preempts_pass(self) -> None:
        """A trade that reaches the profit target but exits after the hard
        close cannot deliver the pass — its recorded exit could not have
        happened on a compliant account."""
        day = dt.date(2026, 1, 12)
        trade = trade_at(
            dt.datetime.combine(day, dt.time(14, 0), tzinfo=CT),
            dt.datetime.combine(day, dt.time(15, 20), tzinfo=CT),
            pnl=5000.0,
        )
        result = evaluate(one_trade_log(trade), firm_with_close())
        assert result.outcome == "breached"
        assert result.breach is not None and result.breach.rule == "session_close"


class TestTopstepPresetsCarryTheRule:
    @pytest.mark.parametrize("preset", ["topstep_50k", "topstep_100k", "topstep_150k"])
    def test_preset_enforces_1510(self, preset: str) -> None:
        firm = load_firm(preset)
        day = dt.date(2026, 1, 12)
        trade = trade_at(
            dt.datetime.combine(day, dt.time(14, 0), tzinfo=CT),
            dt.datetime.combine(day, dt.time(15, 10, 0), tzinfo=CT),
        )
        result = evaluate(one_trade_log(trade), firm)
        assert result.outcome == "breached"
        assert result.breach is not None and result.breach.rule == "session_close"


class TestMonteCarloScreen:
    def test_mc_fails_closed_on_source_log_violations(self) -> None:
        """The day-granular MC cannot replay clock times; simulating a
        session-invalid log would overstate pass/payout probabilities,
        so it must REFUSE — a warning is not sufficient (round 3)."""
        firm = load_firm("topstep_50k")
        trades = []
        for i in range(35):
            day = dt.date(2026, 1, 5) + dt.timedelta(days=i * 7 // 5)  # weekdays-ish
            while day.weekday() >= 5:
                day += dt.timedelta(days=1)
            trades.append(
                trade_at(
                    dt.datetime.combine(day, dt.time(9, 0), tzinfo=CT),
                    dt.datetime.combine(day, dt.time(10, 0), tzinfo=CT),
                    pnl=100.0 if i % 3 else -80.0,
                )
            )
        # One violating trade on a fresh day.
        bad_day = dt.date(2026, 3, 2)
        trades.append(
            trade_at(
                dt.datetime.combine(bad_day, dt.time(14, 0), tzinfo=CT),
                dt.datetime.combine(bad_day, dt.time(15, 30), tzinfo=CT),
            )
        )
        log = TradeLog(trades=trades, source="synthetic")
        with pytest.raises(QuantLabError, match="session close"):
            run_monte_carlo(log, firm, MCConfig(n_paths=50, seed=1))

    def test_mc_runs_on_clean_log(self) -> None:
        firm = load_firm("topstep_50k")
        from ..conftest import random_log

        log = random_log(n_days=40, mean=20.0, std=100.0, seed=5, with_excursions=True)
        report = run_monte_carlo(log, firm, MCConfig(n_paths=50, seed=1))
        assert not any("session close" in w for w in report.warnings)


class TestEarlyCloses:
    def test_date_specific_early_close(self) -> None:
        """A holiday early close applies on its date only."""
        spec = {**SESSION_CLOSE, "early_closes": {"2026-11-27": "12:15:00"}}
        firm = make_firm(
            [
                {
                    "type": "trailing_drawdown",
                    "amount": 2000,
                    "ratchet": "eod",
                    "threshold_cap": 50000,
                },
                spec,
            ],
            target=3000,
        )
        holiday_trade = trade_at(
            dt.datetime(2026, 11, 27, 10, 0, tzinfo=CT),
            dt.datetime(2026, 11, 27, 12, 30, tzinfo=CT),
        )
        result = evaluate(one_trade_log(holiday_trade), firm)
        assert result.outcome == "breached"
        assert result.breach is not None and "12:15:00" in result.breach.detail
        normal_trade = trade_at(
            dt.datetime(2026, 11, 30, 10, 0, tzinfo=CT),
            dt.datetime(2026, 11, 30, 12, 30, tzinfo=CT),
        )
        assert evaluate(one_trade_log(normal_trade), firm).outcome == "incomplete"

    def test_early_close_never_extends_the_session(self) -> None:
        """An 'early close' LATER than hard_close must not loosen it."""
        spec = {**SESSION_CLOSE, "early_closes": {"2026-01-12": "16:00:00"}}
        firm = make_firm(
            [
                {
                    "type": "trailing_drawdown",
                    "amount": 2000,
                    "ratchet": "eod",
                    "threshold_cap": 50000,
                },
                spec,
            ],
            target=3000,
        )
        trade = trade_at(
            dt.datetime(2026, 1, 12, 14, 0, tzinfo=CT),
            dt.datetime(2026, 1, 12, 15, 30, tzinfo=CT),
        )
        assert evaluate(one_trade_log(trade), firm).outcome == "breached"

    def test_bad_early_close_config_rejected(self) -> None:
        from quantlab.errors import ConfigError
        from quantlab.prop.config import SessionCloseSpec

        with pytest.raises(ConfigError, match="ISO date"):
            SessionCloseSpec(early_closes={"Nov 27": "12:15:00"})
        with pytest.raises(ConfigError, match="early_closes"):
            SessionCloseSpec(early_closes={"2026-11-27": "25:00"})


class TestPendingOrdersDisclosure:
    def test_advisory_states_pending_orders_unobservable(self) -> None:
        firm = load_firm("topstep_50k")
        day = dt.date(2026, 1, 12)
        trade = trade_at(
            dt.datetime.combine(day, dt.time(9, 0), tzinfo=CT),
            dt.datetime.combine(day, dt.time(10, 0), tzinfo=CT),
        )
        result = evaluate(one_trade_log(trade), firm)
        assert any("pending-order" in a and "unobservable" in a for a in result.advisories)
