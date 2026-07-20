"""C002: turn-of-month phase-gated one-day-shock reversal, held 5 days (spec.md)."""

import numpy as np
import pandas as pd

from quantlab.grammar import build_terminals

HOLD = 5  # applied via holding_days in the driver


def tom_mask(index: pd.DatetimeIndex) -> pd.Series:
    """1 on the last 2 and first 3 trading days of each calendar month.

    Month-end classification must not depend on where the sample stops (the
    exchange calendar is known in advance), so the index is extended with
    future business days before locating each month's last trading days.
    """
    extended = index.append(pd.bdate_range(index[-1], periods=11, freq="B")[1:])
    months = extended.to_period("M")
    flags = np.zeros(len(extended))
    for month in months.unique():
        locs = np.flatnonzero(months == month)
        take = list(locs[:3]) + list(locs[-2:])
        flags[take] = 1.0
    return pd.Series(flags[: len(index)], index=index)


def compute_signal(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    terms = build_terminals(
        fields["open"], fields["high"], fields["low"],
        fields["close"], fields["adjclose"], fields["volume"],
    )
    ret1 = terms["ret1"]
    tom = tom_mask(ret1.index)
    return (-ret1).mul(tom, axis=0)
