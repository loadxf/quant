"""C013: volume-recession-conditioned monthly reversal, held 21 days (spec.md)."""

import pandas as pd
from edgelab.grammar import build_terminals

SPIKE_Z = 1.5
POST_DAYS = 5
WINDOW = 252
MIN_SPIKES = 3
HOLD = 21


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

    post_mean = sum(volz.shift(-k) for k in range(1, POST_DAYS + 1)) / POST_DAYS
    recession = (volz - post_mean).where(volz > SPIKE_Z)
    recession_known = recession.shift(POST_DAYS)
    rec_speed = recession_known.rolling(WINDOW, min_periods=MIN_SPIKES).mean()
    n_spikes = recession_known.notna().rolling(WINDOW, min_periods=1).sum()
    rec_speed = rec_speed.where(n_spikes >= MIN_SPIKES)

    rev21 = -terms["ret21"]
    return rev21 * rec_speed.rank(axis=1, pct=True)
