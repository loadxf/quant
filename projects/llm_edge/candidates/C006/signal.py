"""C006 CONTROL: intraday-component 5-day reversal (spec.md)."""

import pandas as pd
from edgelab.grammar import build_terminals


def compute_signal(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    terms = build_terminals(
        fields["open"],
        fields["high"],
        fields["low"],
        fields["close"],
        fields["adjclose"],
        fields["volume"],
    )
    return -terms["intraday"].rolling(5, min_periods=3).sum()
