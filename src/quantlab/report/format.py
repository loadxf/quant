"""Shared money/percent formatting for every user-facing surface.

One implementation (terminal, HTML, CLI tables) so sign placement,
rounding, and non-finite handling can never diverge.
"""

from __future__ import annotations

import math


def money(value: float, decimals: int = 2) -> str:
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    if math.isnan(value):
        return "n/a"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.{decimals}f}"


def pct(value: float) -> str:
    if math.isinf(value) or math.isnan(value):
        return "n/a"
    return f"{value:.1%}"
