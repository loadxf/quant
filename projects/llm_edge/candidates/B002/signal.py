"""B002 BASELINE: ungated one-day reversal held 5 days (C002 comparison)."""

import pandas as pd
from edgelab.grammar import build_terminals

HOLD = 5


def compute_signal(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    terms = build_terminals(
        fields["open"],
        fields["high"],
        fields["low"],
        fields["close"],
        fields["adjclose"],
        fields["volume"],
    )
    return -terms["ret1"]
