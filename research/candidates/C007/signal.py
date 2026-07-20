"""C007: lag-7 band reversal — minus the return over days t-8..t-6 (spec.md)."""

import pandas as pd

BAND_LAG = 6  # nearest edge of the band
BAND_LEN = 3  # band covers t-8..t-6


def compute_signal(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    adj = fields["adjclose"]
    # pct_change(2).shift(6) = adj(t-6)/adj(t-8) - 1: the t-8..t-6 band
    band_ret = adj.pct_change(BAND_LEN - 1, fill_method=None).shift(BAND_LAG)
    return -band_ret
