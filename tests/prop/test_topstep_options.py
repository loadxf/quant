"""Topstep purchase options (round-4 hardening).

The purchase DLL is FIXED at $1,000/$2,000/$3,000 by account size
(help.topstep.com article 10490293, 2026-08-13) — no arbitrary amounts.
The adjustable personal daily loss limit (PDLL) is a different product,
separately labeled, never promotionally eligible. All options are
Topstep-only: they must never mutate another firm's preset.
"""

from __future__ import annotations

import pytest

from quantlab.errors import ConfigError
from quantlab.prop.config import (
    DailyLossLimitSpec,
    apply_topstep_options,
    with_optional_dll,
    with_personal_dll,
    with_promo_payout_caps,
)
from quantlab.prop.evaluator import evaluate
from quantlab.prop.registry import load_firm

from .conftest import day_trades, simple


class TestPurchaseDll:
    @pytest.mark.parametrize(
        ("preset", "amount"),
        [("topstep_50k", 1000.0), ("topstep_100k", 2000.0), ("topstep_150k", 3000.0)],
    )
    def test_official_fixed_amount_by_account_size(self, preset: str, amount: float) -> None:
        firm = with_optional_dll(load_firm(preset))
        for phase in [*firm.phases, firm.funded]:
            dlls = [rule for rule in phase.rules if isinstance(rule, DailyLossLimitSpec)]
            assert len(dlls) == 1
            assert dlls[0].amount == amount
            assert dlls[0].effect == "lockout"

    def test_no_arbitrary_amount_parameter_exists(self) -> None:
        """The purchase DLL is fixed at checkout — a '$750 Topstep DLL'
        must be inexpressible through this function."""
        with pytest.raises(TypeError):
            with_optional_dll(load_firm("topstep_50k"), 750.0)  # type: ignore[call-arg]

    def test_unknown_size_is_a_hard_error(self) -> None:
        firm = load_firm("topstep_50k").model_copy(update={"account_size": 77_000.0})
        with pytest.raises(ConfigError, match="official purchase-DLL"):
            with_optional_dll(firm)

    def test_double_dll_rejected(self) -> None:
        firm = with_optional_dll(load_firm("topstep_50k"))
        with pytest.raises(ConfigError, match="already defines"):
            with_optional_dll(firm)

    def test_dll_locks_out_instead_of_failing(self) -> None:
        firm = with_optional_dll(load_firm("topstep_50k"))
        log = day_trades([[simple(500)], [simple(-1500)], [simple(300)]])
        result = evaluate(log, firm, phase="challenge")
        assert result.outcome == "incomplete"
        assert result.lockout_days == 1
        assert result.final_balance == pytest.approx(49_800.0)  # 500 - 1000 + 300

    def test_baseline_unchanged_without_dll(self) -> None:
        firm = load_firm("topstep_50k")
        assert not any(
            isinstance(rule, DailyLossLimitSpec)
            for phase in [*firm.phases, firm.funded]
            for rule in phase.rules
        )


class TestTopstepOnly:
    """Round-4 blocker 3: the options mutated an Apex account."""

    @pytest.mark.parametrize("preset", ["apex40_50k_intraday", "tpt_50k", "ftmo_1step_100k"])
    def test_purchase_dll_refused_for_other_firms(self, preset: str) -> None:
        with pytest.raises(ConfigError, match="Topstep"):
            with_optional_dll(load_firm(preset))

    def test_promo_caps_refused_for_other_firms(self) -> None:
        with pytest.raises(ConfigError, match="Topstep"):
            with_promo_payout_caps(load_firm("apex40_50k_intraday"))

    def test_pdll_refused_for_other_firms(self) -> None:
        with pytest.raises(ConfigError, match="Topstep"):
            with_personal_dll(load_firm("apex40_50k_eod"), 500.0)

    def test_apply_options_refused_for_other_firms(self) -> None:
        with pytest.raises(ConfigError, match="Topstep"):
            apply_topstep_options(load_firm("apex40_50k_intraday"), dll=True, promo_caps=True)


class TestPersonalDll:
    def test_pdll_is_a_separate_labeled_scenario(self) -> None:
        firm = with_personal_dll(load_firm("topstep_50k"), 750.0)
        dll = next(rule for rule in firm.phases[0].rules if isinstance(rule, DailyLossLimitSpec))
        assert dll.amount == 750.0
        assert dll.effect == "lockout"

    def test_pdll_never_promotionally_eligible(self) -> None:
        with pytest.raises(ConfigError, match="PDLL setting confers no promotional"):
            apply_topstep_options(load_firm("topstep_50k"), pdll_amount=750.0, promo_caps=True)

    def test_pdll_and_purchase_dll_mutually_exclusive(self) -> None:
        with pytest.raises(ConfigError, match="mutually exclusive"):
            apply_topstep_options(load_firm("topstep_50k"), dll=True, pdll_amount=500.0)


class TestPromoCaps:
    def test_doubles_both_ladders(self) -> None:
        firm = with_promo_payout_caps(load_firm("topstep_50k"))
        assert firm.payout.payout_cap_ladder == [4000.0]
        assert firm.payout.consistency is not None
        assert firm.payout.consistency.payout_cap_ladder == [6000.0]

    def test_promo_requires_purchase_dll(self) -> None:
        with pytest.raises(ConfigError, match="promotional"):
            apply_topstep_options(load_firm("topstep_50k"), dll=False, promo_caps=True)

    def test_composed_options(self) -> None:
        firm = apply_topstep_options(load_firm("topstep_100k"), dll=True, promo_caps=True)
        dll = next(rule for rule in firm.phases[0].rules if isinstance(rule, DailyLossLimitSpec))
        assert dll.amount == 2000.0
        assert firm.payout.payout_cap_ladder == [6000.0]
        assert firm.payout.consistency is not None
        assert firm.payout.consistency.payout_cap_ladder == [8000.0]

    def test_noop_is_identity_even_for_other_firms(self) -> None:
        apex = load_firm("apex40_50k_eod")
        assert apply_topstep_options(apex) is apex
