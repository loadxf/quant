"""Topstep XFA payout paths (D1), the post-payout MLL reset event (D2),
and deterministic/Monte-Carlo semantic equivalence.

Rule semantics verified against help.topstep.com 2026-08-13 (articles
8284208, 8284215, 8284233): Standard = 5 winning days of $150+ with
positive profit since the prior payout (first exempt); Consistency =
>= 3 active days, best day <= 40% of window total (INCLUSIVE), window
resets after each payout; both cap at 50% of balance with per-size
ladders; the MLL "resets to $0 permanently" at each payout approval.
"""

from __future__ import annotations

import numpy as np
import pytest

from quantlab.prop.dayprofile import DayProfile
from quantlab.prop.evaluator import evaluate
from quantlab.prop.montecarlo import _resolve_rules, _simulate_phase
from quantlab.prop.outcomes import (
    OUTCOME_ACTIVE,
    OUTCOME_BREACHED,
    OUTCOME_LABELS,
)
from quantlab.prop.payout import resolve_payout
from quantlab.prop.registry import load_firm
from quantlab.schema.trade import DayBoundary

from ..conftest import random_log
from .conftest import day_trades, simple

EQUIV_OUTCOME = {
    "incomplete": OUTCOME_ACTIVE,
    "survived": OUTCOME_ACTIVE,
    "breached": OUTCOME_BREACHED,
}


def mc_funded_identity(log, firm, path=None, base_contracts=1):
    """One vectorized path replaying the log verbatim through the funded
    phase WITH payout machinery."""
    boundary = DayBoundary(firm.day_boundary.tz, firm.day_boundary.cutoff_hour)
    profile = DayProfile.from_log(log, boundary)
    idx = np.arange(profile.n_days, dtype=np.int64)[None, :]
    initial = firm.funded.resolved_initial(firm.account_size)
    gates = _resolve_rules(firm.funded, firm, initial).payout_gate_pcts
    payout = resolve_payout(firm, initial, gates, path_override=path)
    return _simulate_phase(
        profile, idx, firm.funded, firm, payout, 1, base_contracts=base_contracts
    )


def both_engines(log, firm, path=None):
    scalar = evaluate(log, firm, phase="funded", with_payouts=True, payout_path=path)
    vector = mc_funded_identity(log, firm, path=path)
    assert OUTCOME_LABELS[EQUIV_OUTCOME[scalar.outcome]] == OUTCOME_LABELS[int(vector.outcome[0])]
    assert float(vector.total_withdrawn[0]) == pytest.approx(scalar.total_withdrawn)
    assert int(vector.payout_count[0]) == scalar.payout_count
    assert float(vector.final_balance[0]) == pytest.approx(scalar.final_balance)
    return scalar, vector


class TestMllResetEvent:
    def test_plus750_regression(self) -> None:
        """The prespecified D2 case: 50K XFA, five days of +150 -> balance
        750, ordinary trailing floor -1,250; first payout 375 (50% of
        balance); the MLL must reset to $0 — not stay at -1,250."""
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(150)]] * 5)
        scalar, _ = both_engines(log, firm)
        assert scalar.payout_count == 1
        assert scalar.total_withdrawn == pytest.approx(375.0)
        assert scalar.final_balance == pytest.approx(375.0)
        # Pre-payout floor: min(hwm 750 - 2000, cap 0) = -1250; post: 0.
        floors = list(scalar.timeline["trailing_floor"])
        assert floors[3] == pytest.approx(-1400.0)  # day 4: 600 - 2000
        assert floors[4] == pytest.approx(0.0)  # payout day: reset event

    def test_loss_to_zero_after_reset_closes_account(self) -> None:
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(150)]] * 5 + [[simple(-375)]])
        scalar, vector = both_engines(log, firm)
        assert scalar.outcome == "breached"
        assert scalar.breach is not None
        assert scalar.breach.rule == "trailing_drawdown[eod]"
        assert scalar.final_balance == pytest.approx(0.0)
        assert int(vector.end_day[0]) == 5

    def test_without_reset_flag_floor_stays_negative(self) -> None:
        """Counterfactual: the same account with mll_reset_on_payout off
        survives the -375 day (floor still -1,250 + payout rebound) —
        exactly the optimism D2 removes."""
        firm = load_firm("topstep_50k")
        firm = firm.model_copy(
            update={"payout": firm.payout.model_copy(update={"mll_reset_on_payout": False})}
        )
        log = day_trades([[simple(150)]] * 5 + [[simple(-375)]])
        scalar, _ = both_engines(log, firm)
        assert scalar.outcome == "survived"


class TestStandardPath:
    def test_first_and_subsequent_payouts(self) -> None:
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(150)]] * 10)
        scalar, _ = both_engines(log, firm)
        assert scalar.payout_count == 2
        # Payout 1 on day 5: 50% x 750 = 375. Payout 2 on day 10:
        # balance 375 + 750 = 1125 -> 562.50.
        assert scalar.total_withdrawn == pytest.approx(375.0 + 562.50)

    def test_qualifying_window_resets_after_payout(self) -> None:
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(150)]] * 6)
        scalar, _ = both_engines(log, firm)
        # Day 6 is only the FIRST qualifying day of the next cycle — the
        # payout-request day never counts toward it.
        assert scalar.payout_count == 1

    def test_subsequent_payout_with_positive_window(self) -> None:
        """Cycle 2: qualifying days 6-9 (+150 each), a -660 day, then the
        5th qualifying day with the window at +90 — pays 50% x 465."""
        firm = load_firm("topstep_50k")
        days = (
            [[simple(150)]] * 5  # payout 1 -> balance 375, anchor 375
            + [[simple(150)]] * 4  # balance 975, 4 qualifying days
            + [[simple(-660)]]  # balance 315: profit_since = -60
            + [[simple(150)]]  # 5th qualifying day, profit_since = +90 -> pays
        )
        log = day_trades(days)
        scalar, _ = both_engines(log, firm)
        assert scalar.payout_count == 2
        assert scalar.total_withdrawn == pytest.approx(375.0 + 232.50)

    def test_profit_since_gate_blocks_when_window_flat(self) -> None:
        """Five fresh qualifying days whose window nets NEGATIVE must not
        pay; the sixth day that turns the window positive pays."""
        firm = load_firm("topstep_50k")
        days = (
            [[simple(150)]] * 5  # payout 1 -> balance 375
            + [[simple(150)]] * 4  # +600
            + [[simple(-900)]]  # window: -300
            + [[simple(150)]]  # 5 qual days done, window -150: blocked
            + [[simple(200)]]  # window +50: pays
        )
        log = day_trades(days)
        scalar, _ = both_engines(log, firm)
        assert scalar.payout_count == 2
        # Second payout on the FINAL day, not the day the 5th qualifying
        # day landed (which was window-negative).
        payouts = list(scalar.timeline["payout"])
        assert payouts[-1] > 0.0
        assert payouts[-2] == 0.0


class TestConsistencyPath:
    def test_exactly_40_percent_qualifies(self) -> None:
        """Largest day exactly 40% of the window total is INCLUSIVE-allowed
        (unlike the strict Apex-style gates)."""
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(200)], [simple(100)], [simple(200)]])
        scalar, _ = both_engines(log, firm, path="consistency")
        # total 500, best 200 = 0.40 x 500 -> eligible on day 3;
        # amount = min(50% x 500, cap 3000) = 250.
        assert scalar.payout_count == 1
        assert scalar.total_withdrawn == pytest.approx(250.0)

    def test_just_above_40_percent_blocks(self) -> None:
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(210)], [simple(100)], [simple(200)]])
        scalar, _ = both_engines(log, firm, path="consistency")
        # total 510, best 210 > 204 -> never eligible.
        assert scalar.payout_count == 0

    def test_negative_day_worsens_ratio(self) -> None:
        firm = load_firm("topstep_50k")
        clean = day_trades([[simple(200)], [simple(150)], [simple(150)]])
        scalar_clean, _ = both_engines(clean, firm, path="consistency")
        assert scalar_clean.payout_count == 1  # 200 <= 0.4 x 500
        dented = day_trades([[simple(200)], [simple(150)], [simple(-125)], [simple(150)]])
        scalar_dented, _ = both_engines(dented, firm, path="consistency")
        # Window total 375: best 200 > 150 — the loss day blocks what the
        # clean sequence paid.
        assert scalar_dented.payout_count == 0

    def test_three_active_days_with_a_no_trade_gap(self) -> None:
        """A calendar day with no trades is not an active day; the third
        ACTIVE day satisfies the 3-day minimum."""
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(200)], [simple(100)], [], [simple(200)]])
        scalar = evaluate(log, firm, phase="funded", with_payouts=True, payout_path="consistency")
        assert scalar.trading_days == 3
        assert scalar.payout_count == 1

    def test_window_resets_after_payout(self) -> None:
        firm = load_firm("topstep_50k")
        log = day_trades(
            [
                *[[simple(200)], [simple(100)], [simple(200)]],  # pays 250 on day 3
                *[[simple(100)], [simple(150)], [simple(150)]],  # fresh window
            ]
        )
        scalar, _ = both_engines(log, firm, path="consistency")
        assert scalar.payout_count == 2
        payouts = [p for p in scalar.timeline["payout"] if p > 0]
        # Window 2: total 400, best 150 <= 160 -> eligible exactly 3 days
        # after the payout day; amount = 50% x (250 + 400) = 325.
        assert payouts == [pytest.approx(250.0), pytest.approx(325.0)]

    def test_consistency_caps_differ_from_standard(self) -> None:
        firm = load_firm("topstep_50k")
        params_std = resolve_payout(firm, 0.0, [], path_override="standard")
        params_con = resolve_payout(firm, 0.0, [], path_override="consistency")
        assert params_std.ladder.tolist() == [2000.0]
        assert params_con.ladder.tolist() == [3000.0]
        assert params_con.c_min_days == 3
        assert params_con.c_frac == pytest.approx(0.40)


class TestScalingInteraction:
    def test_payout_drops_scaling_tier(self) -> None:
        """A payout that pulls the balance below a tier boundary reduces
        the next day's allowed size (tier lookup on the prior close)."""
        firm = load_firm("topstep_50k")
        # base 3 mini-equivalents: tier caps 2/3 (balance < 1500), 1
        # (>= 1500), 5/3 (>= 2000). Raw +900 days scale to +600 below
        # 1500 and +900 at full size.
        log = day_trades([[simple(900)]] * 5)
        vector = mc_funded_identity(log, firm, path="consistency", base_contracts=3)
        balances = vector.equity_samples[0]
        # Days 1-3 at w=2/3: 600, 1200, 1800 -> payout 900 -> close 900.
        assert balances[2] == pytest.approx(900.0)
        # Day 4 starts at 900 (below 1500 AGAIN because of the payout):
        # w=2/3 -> +600 -> 1500. Without the payout the start would have
        # been 1800 -> full size -> +900.
        assert balances[3] == pytest.approx(1500.0)
        # Day 5 starts at 1500 -> full size -> +900 -> 2400.
        assert balances[4] == pytest.approx(2400.0)


LOG_SPECS = [
    dict(n_days=90, mean=40.0, std=180.0, seed=11),
    dict(n_days=90, mean=-40.0, std=180.0, seed=12),
    dict(n_days=90, mean=0.0, std=260.0, seed=13),
    dict(n_days=90, mean=15.0, std=350.0, seed=14),
    dict(n_days=40, mean=60.0, std=120.0, seed=15),
    dict(n_days=90, mean=5.0, std=60.0, seed=16),
]


class TestPayoutGoldenEquivalence:
    """Sol/Fable mandate: the deterministic evaluator and the vectorized
    Monte Carlo must agree on payout replays — outcome, withdrawals,
    payout count, and final balance — on both paths."""

    @pytest.mark.parametrize("path", ["standard", "consistency"])
    @pytest.mark.parametrize("spec_index", range(len(LOG_SPECS)))
    def test_identity_resample_matches_evaluator(self, path: str, spec_index: int) -> None:
        firm = load_firm("topstep_50k")
        log = random_log(with_excursions=True, **LOG_SPECS[spec_index])
        both_engines(log, firm, path=path)
