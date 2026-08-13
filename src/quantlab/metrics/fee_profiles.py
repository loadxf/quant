"""Named platform commission profiles — exact published round-turn fees.

The generic ContractSpec defaults in metrics.contracts are mid-range
retail ESTIMATES. A fee profile pins the exact all-in round-turn fee a
specific platform publishes, keyed by contract root. Firm presets select
one via `fee_profile:`; cost analyses then price every trade from the
profile and FAIL LOUDLY for any symbol the profile does not cover — a
result labeled with the platform never silently falls back to the
generic defaults.

topstepx_2026_08_13 — help.topstep.com article 8284213 ("TopstepX
Commissions and Fees"), fetched 2026-08-13. Fees apply across the
Trading Combine, Express Funded Account, and Live Funded Account on
TopstepX. Per-side = half the round turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quantlab.errors import ConfigError, QuantLabError
from quantlab.metrics.contracts import resolve_contract


@dataclass(frozen=True)
class FeeProfile:
    name: str
    as_of: str
    commissions_rt: dict[str, float] = field(default_factory=dict)  # root -> $ round turn

    def commission_for(self, symbol: str) -> float:
        spec = resolve_contract(symbol)
        if spec is None:
            raise QuantLabError(
                f"fee profile {self.name!r} cannot price symbol {symbol!r} — the contract "
                "root is unrecognized; pass --commission explicitly"
            )
        if spec.root not in self.commissions_rt:
            raise QuantLabError(
                f"fee profile {self.name!r} has no commission for {spec.root} "
                f"(symbol {symbol!r}) — extend the profile or pass --commission"
            )
        return self.commissions_rt[spec.root]


FEE_PROFILES: dict[str, FeeProfile] = {
    "topstepx_2026_08_13": FeeProfile(
        name="topstepx_2026_08_13",
        as_of="2026-08-13",
        commissions_rt={
            "ES": 3.78,
            "NQ": 3.78,
            "RTY": 3.78,
            "YM": 3.78,
            "MES": 1.22,
            "MNQ": 1.22,
            "M2K": 1.22,
            "MYM": 1.22,
            "ZN": 2.62,
            "CL": 4.02,
            "GC": 4.32,
        },
    ),
}


def get_fee_profile(name: str) -> FeeProfile:
    profile = FEE_PROFILES.get(name)
    if profile is None:
        raise ConfigError(
            f"unknown fee profile {name!r}; available: {', '.join(sorted(FEE_PROFILES))}"
        )
    return profile
