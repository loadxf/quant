"""Contract-exposure normalization shared by deterministic and MC engines."""

from __future__ import annotations

import datetime as dt

from quantlab.errors import ConfigError
from quantlab.metrics.contracts import resolve_contract
from quantlab.prop.config import (
    ContractLimitSpec,
    FirmConfig,
    PhaseConfig,
    ScalingPlanSpec,
)
from quantlab.schema.trade import Trade, TradeLog


def peak_contract_equivalents(trades: list[Trade], spec: ContractLimitSpec) -> float:
    """Conservative peak concurrent gross exposure in mini equivalents."""
    events: list[tuple[dt.datetime, int, float]] = []
    for trade in trades:
        contract = resolve_contract(trade.symbol)
        divisor = (
            spec.micros_multiplier
            if contract is not None and contract.root in {"MES", "MNQ"}
            else 1.0
        )
        equivalent = trade.quantity / divisor
        events.append((trade.entry_time, 0, equivalent))
        events.append((trade.exit_time, 1, -equivalent))
    exposure = peak = 0.0
    for _, _, change in sorted(events):
        exposure += change
        peak = max(peak, exposure)
    return peak


def scaling_contract_limit(phase: PhaseConfig) -> ContractLimitSpec | None:
    """Return the mini-equivalent unit definition for a scaling phase."""
    if not any(isinstance(rule, ScalingPlanSpec) for rule in phase.rules):
        return None
    limits = [rule for rule in phase.rules if isinstance(rule, ContractLimitSpec)]
    if len(limits) != 1:
        raise ConfigError(
            f"scaling phase {phase.name!r} needs exactly one contract_limit "
            "to define mini/micro equivalent units"
        )
    return limits[0]


def firm_scaling_contract_limit(firm: FirmConfig) -> ContractLimitSpec | None:
    limits = [
        limit
        for phase in [*firm.phases, firm.funded]
        if (limit := scaling_contract_limit(phase)) is not None
    ]
    if not limits:
        return None
    multipliers = {limit.micros_multiplier for limit in limits}
    if len(multipliers) != 1:
        raise ConfigError("all scaling phases must use the same micros_multiplier")
    return limits[0]


def scaling_base_contracts(
    log: TradeLog, spec: ContractLimitSpec | None = None
) -> float | None:
    """Peak concurrent gross exposure in the scaling plan's unit system.

    Firm tiers are mini-equivalents: by default one mini equals ten micros.
    A phase without a scaling plan may still use raw quantity for callers that
    need a generic base.
    """
    return (
        peak_contract_equivalents(log.trades, spec)
        if spec is not None
        else log.peak_gross_quantity()
    )
