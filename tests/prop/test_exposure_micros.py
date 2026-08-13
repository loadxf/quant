"""Micro-contract exposure normalization (Sol/Fable round 3, defect 3).

Micro classification comes from ContractSpec.mini_equivalent — every
micro root (MES, MNQ, M2K, MYM, MCL, MGC), not a hardcoded pair. Ten
micros = one mini-equivalent at the official 10:1 general ratio.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from quantlab.prop.config import ContractLimitSpec
from quantlab.prop.exposure import peak_contract_equivalents
from quantlab.schema.trade import Side, Trade

CT = ZoneInfo("America/Chicago")
SPEC = ContractLimitSpec(max_contracts=5)


def trade(symbol: str, quantity: float, start_min: int = 0, end_min: int = 60) -> Trade:
    base = dt.datetime(2026, 1, 12, 9, 0, tzinfo=CT)
    return Trade(
        entry_time=base + dt.timedelta(minutes=start_min),
        exit_time=base + dt.timedelta(minutes=end_min),
        symbol=symbol,
        side=Side.LONG,
        quantity=quantity,
        pnl=10.0,
    )


class TestEveryMicroNormalizes:
    @pytest.mark.parametrize("symbol", ["MES", "MNQ", "M2K", "MYM", "MCL", "MGC"])
    def test_ten_micros_equal_one_mini(self, symbol: str) -> None:
        assert peak_contract_equivalents([trade(symbol, 10)], SPEC) == pytest.approx(1.0)

    @pytest.mark.parametrize("symbol", ["ES", "NQ", "RTY", "YM", "ZN", "CL", "GC"])
    def test_full_size_counts_one_to_one(self, symbol: str) -> None:
        assert peak_contract_equivalents([trade(symbol, 3)], SPEC) == pytest.approx(3.0)

    def test_dated_micro_symbols_normalize(self) -> None:
        assert peak_contract_equivalents([trade("M2K15H24", 10)], SPEC) == pytest.approx(1.0)
        assert peak_contract_equivalents([trade("MYM19U25", 20)], SPEC) == pytest.approx(2.0)


class TestMixedPortfolios:
    def test_concurrent_mini_plus_micro(self) -> None:
        """2 ES + 10 MYM held concurrently = 3 mini-equivalents."""
        trades = [trade("ES", 2, 0, 60), trade("MYM", 10, 10, 50)]
        assert peak_contract_equivalents(trades, SPEC) == pytest.approx(3.0)

    def test_non_overlapping_positions_do_not_stack(self) -> None:
        trades = [trade("RTY", 2, 0, 30), trade("M2K", 20, 40, 60)]
        assert peak_contract_equivalents(trades, SPEC) == pytest.approx(2.0)

    def test_energy_metals_micros(self) -> None:
        """1 CL + 10 MCL + 10 MGC concurrent = 3 mini-equivalents."""
        trades = [trade("CL", 1, 0, 60), trade("MCL", 10, 5, 55), trade("MGC", 10, 5, 55)]
        assert peak_contract_equivalents(trades, SPEC) == pytest.approx(3.0)


class TestConventions:
    def test_unresolved_symbol_counts_one_to_one(self) -> None:
        """Unknown roots stay 1:1 — conservative for an advisory limit."""
        assert peak_contract_equivalents([trade("6E", 2)], SPEC) == pytest.approx(2.0)

    def test_micros_multiplier_override_honored(self) -> None:
        spec = ContractLimitSpec(max_contracts=5, micros_multiplier=5.0)
        assert peak_contract_equivalents([trade("MGC", 10)], spec) == pytest.approx(2.0)
