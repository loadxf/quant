"""C003: marginal-value-theorem patch-abandonment reversal, held 10 days (spec.md)."""

import numpy as np
import pandas as pd
from edgelab.grammar import build_terminals

EPISODE_Z = 2.0
LOOKBACK = 10
HOLD = 10  # applied via holding_days in the driver
QUANTILE = 0.5  # median split: trigger days are cross-sectionally sparse
MIN_NAMES = 4


def compute_signal(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    terms = build_terminals(
        fields["open"],
        fields["high"],
        fields["low"],
        fields["close"],
        fields["adjclose"],
        fields["volume"],
    )
    volz = terms["volz"]
    ret1 = terms["ret1"]

    spike = (volz > EPISODE_Z).fillna(False)
    episode_live = spike.shift(1, fill_value=False).rolling(LOOKBACK, min_periods=1).max() == 1.0
    crossing = (volz < 0) & (volz.shift(1) >= 0)
    trigger = episode_live & crossing

    # Episode return = cumulative log return from the EARLIEST spike day within
    # the lookback through t-1. Looping k upward and overwriting leaves the
    # largest k (earliest spike) in place.
    logret = np.log1p(ret1)
    episode_ret = pd.DataFrame(np.nan, index=ret1.index, columns=ret1.columns)
    for k in range(2, LOOKBACK + 1):
        spiked_k_ago = spike.shift(k, fill_value=False)
        cum_since = logret.shift(1).rolling(k - 1, min_periods=1).sum()
        episode_ret = episode_ret.mask(spiked_k_ago, cum_since)

    return (-np.expm1(episode_ret)).where(trigger)
