"""Named platform fee profiles (D4) and the extended contract table (D5).

TopstepX published round-turn fees (help.topstep.com article 8284213,
fetched 2026-08-13) must be used for any cost analysis labeled with a
Topstep preset — never the generic retail defaults — and must fail
loudly for symbols the profile does not price.
"""

from __future__ import annotations

import pytest

from quantlab.errors import ConfigError, QuantLabError
from quantlab.metrics.contracts import CONTRACTS, resolve_contract
from quantlab.metrics.costs import run_cost_sweep
from quantlab.metrics.fee_profiles import get_fee_profile
from quantlab.prop.registry import load_firm

from ..conftest import trades_from_daily


class TestTopstepXProfile:
    def test_published_round_turn_fees(self) -> None:
        profile = get_fee_profile("topstepx_2026_08_13")
        assert profile.as_of == "2026-08-13"
        for root in ("ES", "NQ", "RTY", "YM"):
            assert profile.commissions_rt[root] == 3.78
        for root in ("MES", "MNQ", "M2K", "MYM"):
            assert profile.commissions_rt[root] == 1.22
        assert profile.commissions_rt["ZN"] == 2.62
        assert profile.commissions_rt["CL"] == 4.02
        assert profile.commissions_rt["GC"] == 4.32

    def test_unknown_profile_rejected(self) -> None:
        with pytest.raises(ConfigError, match="unknown fee profile"):
            get_fee_profile("topstepx_1999_01_01")

    def test_unpriced_symbol_fails_loudly(self) -> None:
        profile = get_fee_profile("topstepx_2026_08_13")
        with pytest.raises(QuantLabError, match="unrecognized"):
            profile.commission_for("6E")  # unmodeled root
        with pytest.raises(QuantLabError, match="no commission for MCL"):
            profile.commission_for("MCL")  # known contract, absent from profile

    @pytest.mark.parametrize("preset", ["topstep_50k", "topstep_100k", "topstep_150k"])
    def test_topstep_presets_select_the_profile(self, preset: str) -> None:
        assert load_firm(preset).fee_profile == "topstepx_2026_08_13"

    def test_cost_sweep_prices_topstep_at_published_fees(self) -> None:
        """A fee-less ES log under a Topstep firm gets $3.78 RT added at
        baseline — not the $3.00 generic default."""
        log = trades_from_daily([[100.0, -50.0]] * 30, symbol="ES")
        firm = load_firm("topstep_50k")
        stress = run_cost_sweep(log, firm=firm)
        generic = run_cost_sweep(log, firm=None)
        base = next(p for p in stress.grid if p.label == "0 tick/side, 1x commission")
        generic_base = next(p for p in generic.grid if p.label == "0 tick/side, 1x commission")
        assert base.added_rt_per_contract == pytest.approx(3.78)
        assert generic_base.added_rt_per_contract == pytest.approx(3.00)
        assert any("topstepx_2026_08_13" in w for w in stress.warnings)

    def test_explicit_commission_overrides_profile(self) -> None:
        log = trades_from_daily([[100.0, -50.0]] * 30, symbol="ES")
        firm = load_firm("topstep_50k")
        stress = run_cost_sweep(log, firm=firm, commission_rt=2.0)
        base = next(p for p in stress.grid if p.label == "0 tick/side, 1x commission")
        assert base.added_rt_per_contract == pytest.approx(2.0)

    def test_generic_defaults_unchanged(self) -> None:
        """D4 preserves the generic retail defaults exactly."""
        assert CONTRACTS["ES"].commission_rt == 3.00
        assert CONTRACTS["NQ"].commission_rt == 3.00
        assert CONTRACTS["MES"].commission_rt == 1.50
        assert CONTRACTS["MNQ"].commission_rt == 1.50
        assert CONTRACTS["ES"].tick_value == 12.50
        assert CONTRACTS["MES"].tick_value == 1.25


class TestExtendedContracts:
    """D5: CME specs for the confirmation universe, verified against
    exchange contract definitions."""

    @pytest.mark.parametrize(
        ("root", "tick_size", "tick_value", "point_value", "mini_equivalent"),
        [
            ("RTY", 0.10, 5.00, 50.0, 1.0),
            ("M2K", 0.10, 0.50, 5.0, 0.1),
            ("YM", 1.00, 5.00, 5.0, 1.0),
            ("MYM", 1.00, 0.50, 0.5, 0.1),
            ("ZN", 0.015625, 15.625, 1000.0, 1.0),
            ("CL", 0.01, 10.00, 1000.0, 1.0),
            ("MCL", 0.01, 1.00, 100.0, 0.1),
            ("GC", 0.10, 10.00, 100.0, 1.0),
            ("MGC", 0.10, 1.00, 10.0, 0.1),
        ],
    )
    def test_specs(
        self,
        root: str,
        tick_size: float,
        tick_value: float,
        point_value: float,
        mini_equivalent: float,
    ) -> None:
        spec = CONTRACTS[root]
        assert spec.tick_size == tick_size
        assert spec.tick_value == tick_value
        assert spec.point_value == pytest.approx(point_value)
        assert spec.mini_equivalent == mini_equivalent

    @pytest.mark.parametrize(
        ("symbol", "root"),
        [
            ("RTYU26", "RTY"),
            ("M2K15H24", "M2K"),
            ("/RTY", "RTY"),
            ("YMZ5", "YM"),
            ("MYM19U25", "MYM"),
            ("ZNH26", "ZN"),
            ("CLF27", "CL"),
            ("MCL20M25", "MCL"),
            ("GCJ26", "GC"),
            ("MGC=F", "MGC"),
            ("rty", "RTY"),
        ],
    )
    def test_dated_symbol_resolution(self, symbol: str, root: str) -> None:
        spec = resolve_contract(symbol)
        assert spec is not None and spec.root == root

    def test_micro_never_matches_full_size(self) -> None:
        assert resolve_contract("MYM").tick_value == 0.50
        assert resolve_contract("YM").tick_value == 5.00
        assert resolve_contract("MCL").tick_value == 1.00
        assert resolve_contract("CL").tick_value == 10.00
        assert resolve_contract("MGC").tick_value == 1.00
        assert resolve_contract("GC").tick_value == 10.00
