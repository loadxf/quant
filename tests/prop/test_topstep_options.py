"""Opt-in DLL and promotional payout caps (Sol/Fable round 3, item 6).

DLL verified against help.topstep.com article 10490293 (2026-08-13):
$1,000/$2,000/$3,000 by account size, chosen at checkout, fixed,
LOCKOUT-only (flatten + no new trades until 5 PM CT — never a failure).
Promotional doubled caps apply only to accounts purchased WITH the DLL;
the no-DLL non-promotional configuration stays the primary baseline.
"""

from __future__ import annotations

import pytest

from quantlab.errors import ConfigError
from quantlab.prop.config import (
    DailyLossLimitSpec,
    apply_topstep_options,
    with_optional_dll,
    with_promo_payout_caps,
)
from quantlab.prop.evaluator import evaluate
from quantlab.prop.registry import load_firm

from .conftest import day_trades, simple


class TestOptionalDll:
    @pytest.mark.parametrize(
        ("preset", "amount"),
        [("topstep_50k", 1000.0), ("topstep_100k", 2000.0), ("topstep_150k", 3000.0)],
    )
    def test_official_amount_by_account_size(self, preset: str, amount: float) -> None:
        firm = with_optional_dll(load_firm(preset))
        for phase in [*firm.phases, firm.funded]:
            dlls = [rule for rule in phase.rules if isinstance(rule, DailyLossLimitSpec)]
            assert len(dlls) == 1
            assert dlls[0].amount == amount
            assert dlls[0].effect == "lockout"

    def test_explicit_amount_override(self) -> None:
        firm = with_optional_dll(load_firm("topstep_50k"), amount=750.0)
        dll = next(rule for rule in firm.phases[0].rules if isinstance(rule, DailyLossLimitSpec))
        assert dll.amount == 750.0

    def test_unknown_size_requires_explicit_amount(self) -> None:
        firm = load_firm("topstep_50k").model_copy(update={"account_size": 77_000.0})
        with pytest.raises(ConfigError, match="dll-amount"):
            with_optional_dll(firm)

    def test_double_dll_rejected(self) -> None:
        firm = with_optional_dll(load_firm("topstep_50k"))
        with pytest.raises(ConfigError, match="already defines"):
            with_optional_dll(firm)

    def test_dll_locks_out_instead_of_failing(self) -> None:
        """A -1,500 day truncates at exactly -1,000 and the account
        survives — the DLL is a soft breach."""
        firm = with_optional_dll(load_firm("topstep_50k"))
        log = day_trades([[simple(500)], [simple(-1500)], [simple(300)]])
        result = evaluate(log, firm, phase="challenge")
        assert result.outcome == "incomplete"
        assert result.lockout_days == 1
        # 50,000 + 500 - 1,000 + 300
        assert result.final_balance == pytest.approx(49_800.0)

    def test_baseline_unchanged_without_dll(self) -> None:
        firm = load_firm("topstep_50k")
        assert not any(
            isinstance(rule, DailyLossLimitSpec)
            for phase in [*firm.phases, firm.funded]
            for rule in phase.rules
        )


class TestPromoCaps:
    def test_doubles_both_ladders(self) -> None:
        firm = with_promo_payout_caps(load_firm("topstep_50k"))
        assert firm.payout.payout_cap_ladder == [4000.0]
        assert firm.payout.consistency is not None
        assert firm.payout.consistency.payout_cap_ladder == [6000.0]

    def test_promo_requires_dll(self) -> None:
        with pytest.raises(ConfigError, match="promotional"):
            apply_topstep_options(load_firm("topstep_50k"), dll=False, promo_caps=True)

    def test_dll_amount_requires_dll_flag(self) -> None:
        with pytest.raises(ConfigError, match="--dll-amount requires"):
            apply_topstep_options(load_firm("topstep_50k"), dll=False, dll_amount=500.0)

    def test_composed_options(self) -> None:
        firm = apply_topstep_options(load_firm("topstep_100k"), dll=True, promo_caps=True)
        dll = next(rule for rule in firm.phases[0].rules if isinstance(rule, DailyLossLimitSpec))
        assert dll.amount == 2000.0
        assert firm.payout.payout_cap_ladder == [6000.0]
        assert firm.payout.consistency is not None
        assert firm.payout.consistency.payout_cap_ladder == [8000.0]

    def test_noop_is_identity(self) -> None:
        firm = load_firm("topstep_50k")
        assert apply_topstep_options(firm) is firm
