"""Transaction-cost model (protocol.md section 5).

Flat per-side costs charged on turnover: 10 bps single-name equities, 5 bps
ETFs. Sensitivity sweeps use {0, 5, 10, 25} bps.
"""

EQUITY_BPS = 10.0
ETF_BPS = 5.0
SWEEP_BPS = (0.0, 5.0, 10.0, 25.0)


def cost_rate(universe_kind: str) -> float:
    """Per-side cost in bps for a universe kind ('equities' or 'etfs')."""
    if universe_kind == "etfs":
        return ETF_BPS
    return EQUITY_BPS
