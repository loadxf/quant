"""C001: reversal conditioned on volume-shock recession speed (see spec.md)."""

import numpy as np
import pandas as pd

from quantlab.grammar import build_terminals

SPIKE_Z = 1.5
POST_DAYS = 5
WINDOW = 252
MIN_SPIKES = 3


def compute_signal(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    terms = build_terminals(
        fields["open"], fields["high"], fields["low"],
        fields["close"], fields["adjclose"], fields["volume"],
    )
    volz = terms["volz"]
    ret5 = terms["ret5"]

    # Per spike day s: recession = volz[s] - mean(volz[s+1..s+5]).
    post_mean = sum(volz.shift(-k) for k in range(1, POST_DAYS + 1)) / POST_DAYS
    recession = (volz - post_mean).where(volz > SPIKE_Z)
    # The value for spike day s is only known at s+POST_DAYS; stamp it there.
    recession_known = recession.shift(POST_DAYS)
    rec_speed = recession_known.rolling(WINDOW, min_periods=MIN_SPIKES).mean()
    n_spikes = recession_known.notna().rolling(WINDOW, min_periods=1).sum()
    rec_speed = rec_speed.where(n_spikes >= MIN_SPIKES)

    rev = -ret5
    weight = rec_speed.rank(axis=1, pct=True)
    return rev * weight
