"""EOD pass adjudication (Sol/Fable round 3, defect 1).

Topstep locks each day's value at 3:10 PM CT ("that day's value locks
into your trading history"), so the Combine target is adjudicated on the
COMPLETED-SESSION balance: touching the target intraday and giving it
back the same session is not a pass. Intraday breaches remain real-time.
"""

from __future__ import annotations

import numpy as np
import pytest

from quantlab.prop.evaluator import evaluate
from quantlab.prop.outcomes import OUTCOME_ACTIVE, OUTCOME_BREACHED, OUTCOME_PASSED
from quantlab.prop.registry import load_firm

from .conftest import day_trades, make_firm, simple
from .test_montecarlo import identity_phase_run


class TestSolReproduction:
    """The exact round-3 reproduction: Day 1 +1,500; Day 2 +1,500 then
    -1,000. The old engines passed intraday at 53,000 and ignored trade
    2; the actual session close is 52,000 — not eligible."""

    def test_intraday_touch_does_not_pass(self) -> None:
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(1500)], [simple(1500), simple(-1000)]])
        scalar = evaluate(log, firm, phase="challenge")
        assert scalar.outcome == "incomplete"
        assert scalar.final_balance == pytest.approx(52_000.0)
        vector = identity_phase_run(log, firm, "challenge")
        assert int(vector.outcome[0]) == OUTCOME_ACTIVE
        assert float(vector.final_balance[0]) == pytest.approx(52_000.0)

    def test_pass_lands_when_session_close_holds_target(self) -> None:
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(1500)], [simple(1500), simple(-1000)], [simple(1000)]])
        scalar = evaluate(log, firm, phase="challenge")
        # Day 3 close: total +3,000, best locked day 1,500 = exactly 50%
        # of the target (inclusive) -> passes at 53,000 on day 3.
        assert scalar.outcome == "passed"
        assert scalar.pass_day_index == 2
        assert scalar.final_balance == pytest.approx(53_000.0)
        vector = identity_phase_run(log, firm, "challenge")
        assert int(vector.outcome[0]) == OUTCOME_PASSED
        assert int(vector.end_day[0]) == 2

    def test_single_day_touch_and_give_back(self) -> None:
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(3500), simple(-600)]])
        scalar = evaluate(log, firm, phase="challenge")
        assert scalar.outcome == "incomplete"  # close +2,900 < 3,000
        vector = identity_phase_run(log, firm, "challenge")
        assert int(vector.outcome[0]) == OUTCOME_ACTIVE


class TestBreachStaysRealTime:
    def test_intraday_breach_beats_would_be_eod_pass(self) -> None:
        """Reaching the target intraday does not immunize the session:
        a later same-day MLL touch fails the account in real time."""
        firm = make_firm(
            [
                {
                    "type": "trailing_drawdown",
                    "amount": 2000,
                    "ratchet": "eod",
                    "threshold_cap": 50_000,
                }
            ],
            target=3000,
        )
        # Trade 1 reaches +3,500; trade 2 MAE touches -2,000 from the
        # running balance (53,500 -> 51,500... needs low <= 48,000):
        # day_open 50,000, cum +3,500; trade 2 mae -5,600 -> low 47,900
        # breaches the 48,000 floor before its +100 close.
        log = day_trades([[simple(3500), (100, -5600.0, 100.0)]])
        scalar = evaluate(log, firm, phase="challenge")
        assert scalar.outcome == "breached"
        vector = identity_phase_run(log, firm, "challenge")
        assert int(vector.outcome[0]) == OUTCOME_BREACHED

    def test_dll_locked_day_still_adjudicates_at_close(self) -> None:
        """A DLL lockout is a soft breach: the truncated session still
        closes, feeds the EOD adjudication, and the account passes on a
        later day from the truncated balance."""
        firm = make_firm(
            [
                {
                    "type": "trailing_drawdown",
                    "amount": 2000,
                    "ratchet": "eod",
                    "threshold_cap": 50_000,
                },
                {"type": "daily_loss_limit", "amount": 1000, "effect": "lockout"},
            ],
            target=3000,
        )
        log = day_trades([[simple(2400)], [simple(-1500)], [simple(1700)]])
        scalar = evaluate(log, firm, phase="challenge")
        # Day 1 close 52,400 < 53,000: no pass. Day 2 truncates at
        # -1,000 (lockout): close 51,400. Day 3 close 53,100 -> passes.
        assert scalar.outcome == "passed"
        assert scalar.pass_day_index == 2
        assert scalar.lockout_days == 1
        assert scalar.final_balance == pytest.approx(53_100.0)
        vector = identity_phase_run(log, firm, "challenge")
        assert int(vector.outcome[0]) == OUTCOME_PASSED
        assert int(vector.end_day[0]) == 2


class TestGoldenParityUnderEodAdjudication:
    @pytest.mark.parametrize("seed", [21, 22, 23, 24])
    def test_random_logs_agree(self, seed: int) -> None:
        from ..conftest import random_log

        firm = load_firm("topstep_50k")
        log = random_log(n_days=60, mean=45.0, std=260.0, seed=seed, with_excursions=True)
        scalar = evaluate(log, firm, phase="challenge")
        vector = identity_phase_run(log, firm, "challenge")
        outcome_map = {
            "incomplete": OUTCOME_ACTIVE,
            "passed": OUTCOME_PASSED,
            "breached": OUTCOME_BREACHED,
        }
        assert int(vector.outcome[0]) == outcome_map[scalar.outcome]
        if scalar.outcome == "passed":
            assert int(vector.end_day[0]) == scalar.pass_day_index
        assert float(vector.final_balance[0]) == pytest.approx(scalar.final_balance) or (
            scalar.outcome == "breached"
        )
        assert np.isfinite(vector.final_balance[0])
