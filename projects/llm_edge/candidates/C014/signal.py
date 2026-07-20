"""C014: sustained-volume premium, 21-day hold (spec.md)."""

import pandas as pd
from edgelab.grammar import build_terminals

SMOOTH = 5
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
    return terms["volz"].rolling(SMOOTH, min_periods=3).mean()
