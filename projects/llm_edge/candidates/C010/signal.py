"""C010: G2 winner — 63-day vol of the daily range fraction (spec.md)."""

import pandas as pd
from edgelab.grammar import build_terminals, evaluate

EXPR = ("roll_std", "rng", 63)


def compute_signal(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    terms = build_terminals(
        fields["open"],
        fields["high"],
        fields["low"],
        fields["close"],
        fields["adjclose"],
        fields["volume"],
    )
    return evaluate(EXPR, terms)
