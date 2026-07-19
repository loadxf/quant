"""CME index-futures contract specs for cost modeling.

Tick values verified against CME contract specifications and broker
spec sheets (July 2026): E-mini S&P (ES) $12.50/tick, Micro (MES)
$1.25/tick, E-mini Nasdaq (NQ) $5.00/tick, Micro (MNQ) $0.50/tick —
all at a 0.25-index-point minimum tick.
Default all-in round-turn commissions (broker + exchange/clearing +
regulatory) sit mid-range of 2025-26 retail pricing: ~$1.50 for
micros, ~$3.00 for minis. Sources: cmegroup.com contract specs;
retail broker comparisons (Tradovate/AMP/NinjaTrader published rates).
Fees change quarterly — users can override via --commission.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContractSpec:
    root: str
    tick_size: float  # index points
    tick_value: float  # $ per tick per contract
    commission_rt: float  # default all-in round-turn $ per contract


CONTRACTS: dict[str, ContractSpec] = {
    "MES": ContractSpec("MES", 0.25, 1.25, 1.50),
    "MNQ": ContractSpec("MNQ", 0.25, 0.50, 1.50),
    "ES": ContractSpec("ES", 0.25, 12.50, 3.00),
    "NQ": ContractSpec("NQ", 0.25, 5.00, 3.00),
}

# Longest roots first so MESH26/MES1! never prefix-match ES.
_ROOTS_BY_LENGTH = sorted(CONTRACTS, key=len, reverse=True)


def resolve_contract(symbol: str) -> ContractSpec | None:
    """Match a trade symbol (MNQ, MNQH26, MES1!, /ES) to a known contract."""
    cleaned = symbol.strip().upper().lstrip("/@")
    for root in _ROOTS_BY_LENGTH:
        if cleaned.startswith(root):
            return CONTRACTS[root]
    return None
