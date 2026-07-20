"""C015: 63-day std of daily range fraction, long high (spec.md)."""

import pandas as pd

WINDOW = 63
HOLD = 5


def compute_signal(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rng_frac = (fields["high"] - fields["low"]) / fields["close"]
    return rng_frac.rolling(WINDOW, min_periods=WINDOW // 2).std()
