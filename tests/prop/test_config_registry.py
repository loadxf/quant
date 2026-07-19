"""Preset loading + config validation."""

from __future__ import annotations

import pytest

from quantlab.errors import ConfigError
from quantlab.prop.config import (
    ConsistencySpec,
    DailyLossLimitSpec,
    StaticMaxLossSpec,
    TrailingDrawdownSpec,
    resolved_amount,
)
from quantlab.prop.registry import list_firms, load_firm
from quantlab.prop.rules import ConsistencyGate


class TestRegistry:
    def test_all_presets_load(self) -> None:
        names = list_firms()
        assert len(names) == 18
        for name in names:
            firm = load_firm(name)
            assert firm.verified_as_of == "2026-07-19"
            assert firm.sources

    def test_unknown_name(self) -> None:
        with pytest.raises(ConfigError, match="Unknown firm"):
            load_firm("nope_9000k")

    def test_user_yaml_path(self, tmp_path) -> None:
        path = tmp_path / "myfirm.yaml"
        path.write_text(
            """
name: myfirm
account_size: 10000
phases:
  - name: challenge
    profit_target: 800
    rules:
      - {type: trailing_drawdown, amount: 500, ratchet: intraday}
funded:
  name: funded
  rules: []
"""
        )
        firm = load_firm(path)
        assert firm.account_size == 10_000


class TestVerifiedPresetShapes:
    def test_topstep_50k(self) -> None:
        firm = load_firm("topstep_50k")
        trail = firm.phases[0].rules[0]
        assert isinstance(trail, TrailingDrawdownSpec)
        assert trail.ratchet == "eod" and trail.threshold_cap == 50_000
        # No DLL by default (removed on TopstepX Aug 2024)
        assert not any(isinstance(r, DailyLossLimitSpec) for r in firm.phases[0].rules)
        cons = next(r for r in firm.phases[0].rules if isinstance(r, ConsistencySpec))
        assert cons.basis == "profit_target"
        assert firm.funded.initial_balance == 0  # XFA starts at $0
        assert firm.payout.profit_split == 0.9

    def test_apex_variants(self) -> None:
        intra = load_firm("apex40_50k_intraday")
        eod = load_firm("apex40_50k_eod")
        t_intra = intra.phases[0].rules[0]
        t_eod = eod.phases[0].rules[0]
        assert isinstance(t_intra, TrailingDrawdownSpec) and t_intra.ratchet == "intraday"
        assert isinstance(t_eod, TrailingDrawdownSpec) and t_eod.ratchet == "eod"
        # Eval threshold freezes only at initial+target; PA at start+100
        assert t_intra.threshold_cap == 53_000
        assert intra.funded.rules[0].threshold_cap == 50_100  # type: ignore[union-attr]
        # DLL only on the EOD variant, and it's a lockout
        assert not any(isinstance(r, DailyLossLimitSpec) for r in intra.phases[0].rules)
        dll = next(r for r in eod.phases[0].rules if isinstance(r, DailyLossLimitSpec))
        assert dll.effect == "lockout" and dll.amount == 1000
        assert eod.payout.max_lifetime_payouts == 6
        assert eod.payout.profit_split == 1.0
        assert sum(eod.payout.payout_cap_ladder) == 13_000  # verified lifetime total
        assert eod.fees.one_time > 0 and eod.fees.monthly == 0  # 30-day one-time model

    def test_tpt_pro_is_intraday(self) -> None:
        firm = load_firm("tpt_50k")
        assert firm.phases[0].rules[0].ratchet == "eod"  # type: ignore[union-attr]
        assert firm.funded.rules[0].ratchet == "intraday"  # type: ignore[union-attr]
        assert firm.payout.buffer_above_initial == 2000
        assert firm.payout.profit_split == 0.8

    def test_ftmo_percent_resolution(self) -> None:
        firm = load_firm("ftmo_2step_100k")
        assert len(firm.phases) == 2  # Challenge -> Verification
        static = firm.phases[0].rules[0]
        assert isinstance(static, StaticMaxLossSpec)
        assert resolved_amount(static, firm.account_size) == 10_000
        daily = firm.phases[0].rules[1]
        assert isinstance(daily, DailyLossLimitSpec)
        assert resolved_amount(daily, firm.account_size) == 5_000
        assert daily.inclusive is False and daily.anchor == "prev_midnight_balance"
        assert firm.day_boundary.tz == "Europe/Prague"
        assert firm.fees.refundable_on_first_payout is True
        one_step = load_firm("ftmo_1step_100k")
        assert isinstance(one_step.phases[0].rules[0], TrailingDrawdownSpec)
        assert resolved_amount(one_step.phases[0].rules[1], 100_000) == 3_000  # type: ignore[arg-type]


class TestConfigValidation:
    def test_eval_phase_requires_target(self) -> None:
        from quantlab.prop.config import FirmConfig

        with pytest.raises(Exception, match="profit_target"):
            FirmConfig.model_validate(
                {
                    "name": "bad",
                    "account_size": 1000,
                    "phases": [{"name": "challenge", "rules": []}],
                    "funded": {"name": "funded", "rules": []},
                }
            )

    def test_amount_pct_exclusive(self) -> None:
        spec = TrailingDrawdownSpec(amount=100, pct=5)
        with pytest.raises(ConfigError, match="not both"):
            resolved_amount(spec, 1000)
        with pytest.raises(ConfigError, match="required"):
            resolved_amount(TrailingDrawdownSpec(), 1000)


class TestConsistencyGateMath:
    def test_bases_agree_on_unified_formula(self) -> None:
        pt = ConsistencyGate(ConsistencySpec(basis="profit_target", max_best_day_pct=50))
        tp = ConsistencyGate(ConsistencySpec(basis="total_profit", max_best_day_pct=50))
        # Below the threshold: no raise
        assert pt.required_total(3000, 1400) == 3000
        assert tp.required_total(3000, 1400) == 3000
        # Above: both raise to best/pct
        assert pt.required_total(3000, 2000) == 4000
        assert tp.required_total(3000, 2000) == 4000

    def test_payout_eligibility(self) -> None:
        gate = ConsistencyGate(
            ConsistencySpec(basis="total_profit", max_best_day_pct=50, effect="gate_payout")
        )
        assert gate.payout_eligible(best_day=400, total_profit=1000)
        assert not gate.payout_eligible(best_day=600, total_profit=1000)
        assert not gate.payout_eligible(best_day=100, total_profit=0)
