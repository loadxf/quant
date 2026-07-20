"""B003 BASELINE: spike-entry episode reversal held 10 days (C003 comparison)."""

import pandas as pd
from edgelab.grammar import build_terminals

HOLD = 10
MIN_NAMES = 4
QUANTILE = 0.5


def compute_signal(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    terms = build_terminals(
        fields["open"],
        fields["high"],
        fields["low"],
        fields["close"],
        fields["adjclose"],
        fields["volume"],
    )
    trigger = terms["volz"] > 2.0
    return (-terms["ret5"]).where(trigger)
