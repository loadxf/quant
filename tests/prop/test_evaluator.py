"""Hand-computed edge-case sequences for the deterministic evaluator.

Every scenario's expected numbers are worked out in comments — these are
the executable spec for the rule semantics (and, later, the golden
reference for the vectorized Monte Carlo engine).
"""

from __future__ import annotations

from typing import ClassVar

from quantlab.prop.evaluator import evaluate, evaluate_sequence

from .conftest import day_trades, make_firm, simple

TRAIL_EOD = {"type": "trailing_drawdown", "amount": 2000, "ratchet": "eod"}
TRAIL_INTRA = {"type": "trailing_drawdown", "amount": 2000, "ratchet": "intraday"}


class TestTrailingRatchetDivergence:
    """Same trade sequence; intraday ratchet breaches where EOD survives.

    Day1: +1500 (mfe 1500)          -> close 51,500
    Day2: -300 with mfe +1000       -> intraday hwm 52,500; close 51,200
    Day3: -900 with mae -1000       -> low 50,200
    EOD:      hwm 51,500 -> floor 49,500; low 50,200 > 49,500  -> survives
    Intraday: hwm 52,500 -> floor 50,500; low 50,200 <= 50,500 -> breach
    """

    LOG = day_trades(
        [
            [(1500, 0.0, 1500)],
            [(-300, -300, 1000)],
            [(-900, -1000, 0.0)],
        ]
    )

    def test_eod_survives(self) -> None:
        firm = make_firm([TRAIL_EOD], target=100_000)  # unreachable target
        result = evaluate(self.LOG, firm)
        assert result.outcome == "incomplete"
        assert result.final_balance == 50_300

    def test_intraday_breaches_day3(self) -> None:
        firm = make_firm([TRAIL_INTRA], target=100_000)
        result = evaluate(self.LOG, firm)
        assert result.outcome == "breached"
        assert result.breach is not None
        assert result.breach.rule == "trailing_drawdown[intraday]"
        assert result.breach.day_index == 2
        assert result.breach.threshold == 50_500


class TestThresholdCapLock:
    """Topstep-style lock at starting balance.

    Closes +1500, +800 -> hwm 52,300, raw floor 50,300 CAPPED at 50,000.
    Day3 dips to 50,100 -> survives (uncapped floor would have breached).
    Day4 touches 50,000 exactly -> inclusive breach at the cap.
    """

    def _firm(self):
        rule = {**TRAIL_EOD, "threshold_cap": 50_000}
        return make_firm([rule], target=100_000)

    LOG_SURVIVE = day_trades(
        [
            [simple(1500)],
            [simple(800)],
            [(-2150, -2200, 0.0)],  # low 52,300-2,200 = 50,100
        ]
    )
    LOG_TOUCH = day_trades(
        [
            [simple(1500)],
            [simple(800)],
            [(-2150, -2300, 0.0)],  # low 50,000 exactly
        ]
    )

    def test_cap_saves_day3(self) -> None:
        result = evaluate(self.LOG_SURVIVE, self._firm())
        assert result.outcome == "incomplete"

    def test_touch_at_cap_breaches(self) -> None:
        result = evaluate(self.LOG_TOUCH, self._firm())
        assert result.outcome == "breached"
        assert result.breach is not None and result.breach.threshold == 50_000


class TestConsistencyRaisesTarget:
    """Topstep Combine: best day 2,000 > 50% of 3,000 target
    -> required total = 2,000/0.5 = 4,000."""

    RULES: ClassVar = [
        TRAIL_EOD,
        {"type": "consistency", "max_best_day_pct": 50, "basis": "profit_target"},
    ]

    def test_pass_delayed_until_raised_target(self) -> None:
        log = day_trades(
            [
                [simple(2000)],  # 52,000: raised target 4,000 -> no pass
                [simple(1500)],  # 53,500 (+3,500 < 4,000) -> no pass
                [simple(600)],  # 54,100 (+4,100 >= 4,000) -> PASS
            ]
        )
        result = evaluate(log, make_firm(self.RULES, target=3000))
        assert result.outcome == "passed"
        assert result.pass_day_index == 2
        assert result.effective_target == 4000

    def test_no_raise_when_best_day_small(self) -> None:
        log = day_trades([[simple(1400)], [simple(1700)]])  # best 1,700 ... wait
        # best day 1,700 > 1,500 (50% of target) -> required 3,400; total 3,100 -> no pass
        result = evaluate(log, make_firm(self.RULES, target=3000))
        assert result.outcome == "incomplete"
        assert result.effective_target == 3400

    def test_current_day_counts_toward_best(self) -> None:
        # Single +3,000 day: best day 3,000 -> required 6,000 -> cannot pass today
        log = day_trades([[simple(3000)]])
        result = evaluate(log, make_firm(self.RULES, target=3000))
        assert result.outcome == "incomplete"
        assert result.effective_target == 6000


class TestDailyLossLockoutVsFail:
    def test_lockout_truncates_day_and_does_not_fail(self) -> None:
        """DLL 1,000 lockout: two -600 trades; second dips low to -1,200 cum.
        Day PnL truncates at exactly -1,000; account survives."""
        rules = [
            {**TRAIL_EOD, "threshold_cap": 50_000},
            {"type": "daily_loss_limit", "amount": 1000, "effect": "lockout"},
        ]
        log = day_trades(
            [
                [simple(-600), simple(-600)],  # trade2 low: 49,400-600 = 48,800 <= 49,000
                [simple(500)],
            ]
        )
        result = evaluate(log, make_firm(rules, target=100_000))
        assert result.outcome == "incomplete"
        assert result.lockout_days == 1
        assert result.timeline.iloc[0]["day_pnl"] == -1000  # truncated exactly
        assert result.final_balance == 49_500

    def test_higher_fail_level_beats_lockout(self) -> None:
        """Trailing floor 49,200 sits ABOVE the DLL level 49,000: the dip
        hits the trailing floor first -> breach, not lockout."""
        rules = [
            {"type": "trailing_drawdown", "amount": 800, "ratchet": "eod"},
            {"type": "daily_loss_limit", "amount": 1000, "effect": "lockout"},
        ]
        log = day_trades([[(-850, -900, 0.0)]])  # low 49,100
        result = evaluate(log, make_firm(rules, target=100_000))
        assert result.outcome == "breached"
        assert result.breach is not None
        assert result.breach.rule.startswith("trailing_drawdown")
        assert result.lockout_days == 0

    def test_daily_fail_ends_phase(self) -> None:
        rules = [{"type": "daily_loss_limit", "amount": 1000, "effect": "fail"}]
        log = day_trades([[simple(-1200)]])
        result = evaluate(log, make_firm(rules, target=100_000))
        assert result.outcome == "breached"
        assert result.breach is not None
        assert result.breach.rule == "daily_loss_limit[fail]"


class TestFtmoSemantics:
    """FTMO 2-Step style: width 5% of initial, anchored to day-open balance
    (midnight re-anchor -> the level MOVES DOWN after losing days), static
    10% floor, both with the strictly-below comparator."""

    RULES: ClassVar = [
        {"type": "static_max_loss", "pct": 10, "inclusive": False},
        {
            "type": "daily_loss_limit",
            "pct": 5,
            "anchor": "prev_midnight_balance",
            "effect": "fail",
            "inclusive": False,
        },
    ]

    def _firm(self):
        return make_firm(
            self.RULES,
            target=10_000,
            size=100_000,
            day_boundary={"tz": "Europe/Prague", "cutoff_hour": 0},
        )

    def test_level_reanchors_down_and_exact_touch_survives(self) -> None:
        # Day1: -3,000 -> balance 97,000. Day2 level = 92,000 (moved DOWN).
        # Day2 dips to exactly 92,000: NOT below -> survives (exclusive).
        log = day_trades([[simple(-3000)], [(-4999, -5000, 0.0)]])
        result = evaluate(log, self._firm())
        assert result.outcome == "incomplete"
        assert result.final_balance == 92_001

    def test_one_dollar_below_breaches(self) -> None:
        log = day_trades([[simple(-3000)], [(-4999, -5001, 0.0)]])
        result = evaluate(log, self._firm())
        assert result.outcome == "breached"
        assert result.breach is not None
        assert result.breach.rule == "daily_loss_limit[fail]"

    def test_static_floor_fires_before_lower_daily_level(self) -> None:
        # Balance 92,001 after day2; day3 daily level 87,001 but static floor
        # 90,000 is higher -> dipping to 89,901 hits the STATIC floor first.
        log = day_trades([[simple(-3000)], [(-4999, -5000, 0.0)], [(-2000, -2100, 0.0)]])
        result = evaluate(log, self._firm())
        assert result.outcome == "breached"
        assert result.breach is not None
        assert result.breach.rule == "static_max_loss"
        assert result.breach.threshold == 90_000


class TestTimeLimitExpiry:
    def test_apex_30_day_expiry(self) -> None:
        rules = [TRAIL_INTRA, {"type": "time_limit", "max_calendar_days": 30}]
        # 25 weekday sessions of +100 starting Mon 2026-01-05; the session on
        # 2026-02-04 is calendar day 30 -> expired before trading it.
        log = day_trades([[simple(100)]] * 25)
        result = evaluate(log, make_firm(rules, target=3000))
        assert result.outcome == "expired"
        assert result.trading_days == 22

    def test_pass_before_expiry(self) -> None:
        rules = [TRAIL_INTRA, {"type": "time_limit", "max_calendar_days": 30}]
        log = day_trades([[simple(1600)], [simple(1600)]])
        result = evaluate(log, make_firm(rules, target=3000))
        assert result.outcome == "passed"


class TestSameDayBreachVsTarget:
    RULES: ClassVar = [TRAIL_EOD]

    def test_target_hit_after_surviving_dip(self) -> None:
        # Trade1 +2,900; trade2 dips to 49,950 (floor 48,000 -> fine) then
        # closes +200 -> 53,100 >= 53,000 -> PASSED on trade 2.
        log = day_trades([[(2900, -50, 2900), (200, -2950, 200)]])
        result = evaluate(log, make_firm(self.RULES, target=3000))
        assert result.outcome == "passed"
        assert result.pass_day_index == 0

    def test_breach_wins_inside_the_same_trade(self) -> None:
        # Same trade would close at target, but its dip touches the floor
        # first: low 52,900-4,950 = 47,950 <= 48,000 -> breached, no pass.
        log = day_trades([[(2900, -50, 2900), (200, -4950, 200)]])
        result = evaluate(log, make_firm(self.RULES, target=3000))
        assert result.outcome == "breached"


class TestMinTradingDays:
    def test_pass_delayed_to_second_day(self) -> None:
        rules = [TRAIL_EOD, {"type": "min_trading_days", "days": 2}]
        log = day_trades([[simple(1500)], [simple(10)]])
        result = evaluate(log, make_firm(rules, target=1000))
        assert result.outcome == "passed"
        assert result.pass_day_index == 1
        assert result.trading_days == 2


class TestFidelity:
    def test_missing_excursions_is_optimistic(self) -> None:
        """A +500 trade that dipped 2,100 intraday: with MAE the trailing
        floor is hit; without MAE (trade-close fidelity) it is invisible."""
        with_mae = day_trades([[simple(300)], [(500, -2100, 500)]])
        without = day_trades([[(300, None, None)], [(500, None, None)]])
        firm = make_firm([TRAIL_EOD], target=100_000)
        assert evaluate(with_mae, firm).outcome == "breached"
        result = evaluate(without, firm).outcome
        assert result == "incomplete"
        assert evaluate(without, firm).fidelity == "trade_close"


class TestFundedPhaseAndSequence:
    def test_xfa_starts_at_zero_and_locks_at_zero(self) -> None:
        """Topstep XFA: balance 0, MLL 2,000 capping at 0."""
        firm = make_firm(
            [TRAIL_EOD],
            target=3000,
            funded_rules=[{**TRAIL_EOD, "threshold_cap": 0}],
            funded_initial=0,
        )
        # closes +1,000, +1,100 -> hwm 2,100 -> floor capped at 0.
        # Day3 dips to 200 -> survives; then to -50 -> breach at 0.
        survive = day_trades([[simple(1000)], [simple(1100)], [(-1800, -1900, 0.0)]])
        result = evaluate(survive, firm, phase="funded")
        assert result.outcome == "survived"
        breach = day_trades([[simple(1000)], [simple(1100)], [(-2000, -2150, 0.0)]])
        result = evaluate(breach, firm, phase="funded")
        assert result.outcome == "breached"
        assert result.breach is not None and result.breach.threshold == 0

    def test_two_step_sequence_chains_days(self) -> None:
        """FTMO-style 2-step: 4 days x +2,600 passes challenge (10k target,
        min 4 days), next 4 days x +1,300 pass verification (5k), rest
        survives funded."""
        phases = [
            {
                "name": "challenge",
                "profit_target": 10_000,
                "rules": [
                    {"type": "static_max_loss", "pct": 10, "inclusive": False},
                    {"type": "min_trading_days", "days": 4},
                ],
            },
            {
                "name": "verification",
                "profit_target": 5_000,
                "rules": [
                    {"type": "static_max_loss", "pct": 10, "inclusive": False},
                    {"type": "min_trading_days", "days": 4},
                ],
            },
        ]
        firm = make_firm(
            [],
            phases=phases,
            size=100_000,
            funded_rules=[{"type": "static_max_loss", "pct": 10, "inclusive": False}],
        )
        log = day_trades([[simple(2600)]] * 4 + [[simple(1300)]] * 4 + [[simple(100)]] * 3)
        results = evaluate_sequence(log, firm)
        assert [r.phase for r in results] == ["challenge", "verification", "funded"]
        assert [r.outcome for r in results] == ["passed", "passed", "survived"]
        assert results[0].days_consumed == 4
        assert results[1].days_consumed == 4
        assert results[2].trading_days == 3

    def test_sequence_stops_at_failed_phase(self) -> None:
        firm = make_firm(
            [{"type": "static_max_loss", "amount": 2000}],
            target=3000,
        )
        log = day_trades([[simple(-2500)]])
        results = evaluate_sequence(log, firm)
        assert len(results) == 1
        assert results[0].outcome == "breached"


class TestAdvisories:
    def test_contract_limit_is_advisory(self) -> None:
        rules = [TRAIL_EOD, {"type": "contract_limit", "max_contracts": 5}]
        import datetime as dt
        from zoneinfo import ZoneInfo

        from quantlab.schema.trade import Side, Trade, TradeLog

        entry = dt.datetime(2026, 1, 5, 9, 0, tzinfo=ZoneInfo("America/Chicago"))
        log = TradeLog(
            trades=[
                Trade(entry, entry, "NQ", Side.LONG, quantity=8, pnl=100.0, mae=0.0, mfe=100.0)
            ]
        )
        result = evaluate(log, make_firm(rules, target=100_000))
        assert result.outcome == "incomplete"  # not a failure
        assert any("exposure 8" in a for a in result.advisories)

    def test_contract_limit_counts_overlap_and_micro_equivalents(self) -> None:
        rules = [TRAIL_EOD, {"type": "contract_limit", "max_contracts": 1}]
        import datetime as dt
        from zoneinfo import ZoneInfo

        from quantlab.schema.trade import Side, Trade, TradeLog

        entry = dt.datetime(2026, 1, 5, 9, 0, tzinfo=ZoneInfo("America/Chicago"))
        trades = [
            Trade(
                entry,
                entry + dt.timedelta(hours=1),
                "MNQ",
                Side.LONG,
                quantity=6,
                pnl=10,
                mae=0,
                mfe=10,
            ),
            Trade(
                entry + dt.timedelta(minutes=1),
                entry + dt.timedelta(hours=1),
                "MNQ",
                Side.LONG,
                quantity=6,
                pnl=10,
                mae=0,
                mfe=10,
            ),
        ]
        result = evaluate(TradeLog(trades), make_firm(rules, target=100_000))
        assert any("exposure 1.2" in advisory for advisory in result.advisories)
        assert any("portfolio equity path" in advisory for advisory in result.advisories)

    def test_contract_advisory_checks_source_rows_after_early_pass(self) -> None:
        import datetime as dt
        from zoneinfo import ZoneInfo

        from quantlab.schema.trade import Side, Trade, TradeLog

        rules = [TRAIL_EOD, {"type": "contract_limit", "max_contracts": 5}]
        start = dt.datetime(2026, 1, 5, 9, 0, tzinfo=ZoneInfo("America/Chicago"))
        trades = [
            Trade(start, start, "NQ", Side.LONG, 1, 100, mae=0, mfe=100),
            Trade(
                start + dt.timedelta(days=1),
                start + dt.timedelta(days=1),
                "NQ",
                Side.LONG,
                50,
                0,
                mae=0,
                mfe=0,
            ),
        ]
        result = evaluate(TradeLog(trades), make_firm(rules, target=100))
        assert result.outcome == "passed"
        assert any("exposure 50" in advisory for advisory in result.advisories)
