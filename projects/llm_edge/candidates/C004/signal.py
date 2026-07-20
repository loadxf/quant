"""C004 CONTROL: plain 5-day short-term reversal (spec.md)."""

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
    return -terms["ret5"]
