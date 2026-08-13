"""CME futures contract specs for cost modeling.

Tick values verified against CME contract specifications and broker
spec sheets (July 2026; RTY/YM/ZN/CL/GC families re-verified August
2026): E-mini S&P (ES) $12.50/tick at 0.25 index points, Micro (MES)
$1.25; E-mini Nasdaq (NQ) $5.00, Micro (MNQ) $0.50; E-mini Russell
(RTY) $5.00 at 0.10, Micro (M2K) $0.50; E-mini Dow (YM) $5.00 at 1
point, Micro (MYM) $0.50; 10-Year Note (ZN) $15.625 at half of 1/32;
Crude (CL) $10.00 at $0.01, Micro (MCL) $1.00; Gold (GC) $10.00 at
$0.10, Micro (MGC) $1.00.

Default all-in round-turn commissions (broker + exchange/clearing +
regulatory) sit mid-range of 2025-26 retail pricing: ~$1.50 for
micros, ~$3.00 for equity-index minis, more for energy/metals whose
exchange fees are higher. These are GENERIC RETAIL ESTIMATES — for a
platform's exact published schedule (e.g. TopstepX) use a named fee
profile (metrics.fee_profiles); firm presets that set `fee_profile`
apply it automatically. Sources: cmegroup.com contract specs; retail
broker comparisons (Tradovate/AMP/NinjaTrader published rates).
Fees change quarterly — users can override via --commission.

`mini_equivalent` is the contract's weight in full-size(-mini) units of
its own product family (micros = 0.1), used for exposure normalization.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContractSpec:
    root: str
    tick_size: float  # price points
    tick_value: float  # $ per tick per contract
    commission_rt: float  # default all-in round-turn $ per contract
    mini_equivalent: float = 1.0  # weight in full-size units of its family

    @property
    def point_value(self) -> float:
        """$ per full price point per contract (contract multiplier)."""
        return self.tick_value / self.tick_size


CONTRACTS: dict[str, ContractSpec] = {
    # Equity index
    "MES": ContractSpec("MES", 0.25, 1.25, 1.50, mini_equivalent=0.1),
    "MNQ": ContractSpec("MNQ", 0.25, 0.50, 1.50, mini_equivalent=0.1),
    "M2K": ContractSpec("M2K", 0.10, 0.50, 1.50, mini_equivalent=0.1),
    "MYM": ContractSpec("MYM", 1.00, 0.50, 1.50, mini_equivalent=0.1),
    "ES": ContractSpec("ES", 0.25, 12.50, 3.00),
    "NQ": ContractSpec("NQ", 0.25, 5.00, 3.00),
    "RTY": ContractSpec("RTY", 0.10, 5.00, 3.00),
    "YM": ContractSpec("YM", 1.00, 5.00, 3.00),
    # Rates
    "ZN": ContractSpec("ZN", 0.015625, 15.625, 2.80),
    # Energy
    "CL": ContractSpec("CL", 0.01, 10.00, 4.00),
    "MCL": ContractSpec("MCL", 0.01, 1.00, 1.50, mini_equivalent=0.1),
    # Metals
    "GC": ContractSpec("GC", 0.10, 10.00, 4.20),
    "MGC": ContractSpec("MGC", 0.10, 1.00, 1.60, mini_equivalent=0.1),
}

_DELIVERY_DAY = r"(?:0?[1-9]|[12]\d|3[01])"
# Micro roots before their full-size prefixes (MES before ES, MYM before
# YM, MCL before CL, MGC before GC) — alternation is ordered.
_ROOTS = "MES|MNQ|M2K|MYM|MCL|MGC|ES|NQ|RTY|YM|ZN|CL|GC"
_FUTURES_SYMBOL = re.compile(
    rf"^({_ROOTS})(?:(?:{_DELIVERY_DAY})?[FGHJKMNQUVXZ]\d{{1,4}}|[1-9]\d*!|=F)?$"
)


def resolve_contract(symbol: str) -> ContractSpec | None:
    """Match standard and QC-dated symbols (ES, ESH26, ES15H24, /ES)."""
    if not isinstance(symbol, str):
        return None
    cleaned = symbol.strip().upper().lstrip("/@")
    match = _FUTURES_SYMBOL.fullmatch(cleaned)
    return CONTRACTS[match.group(1)] if match else None
