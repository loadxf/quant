"""C005 CONTROL: low-volume-conditioned reversal, inverted conditioning (spec.md)."""

import pandas as pd

from quantlab.grammar import build_terminals


def compute_signal(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    terms = build_terminals(
        fields["open"], fields["high"], fields["low"],
        fields["close"], fields["adjclose"], fields["volume"],
    )
    low_vol_weight = 1.0 - terms["volz"].rank(axis=1, pct=True)
    return -terms["ret5"] * low_vol_weight
