"""C011: G2 winner — gap volatility minus monthly return (spec.md)."""

import pandas as pd
from edgelab.grammar import build_terminals, evaluate

EXPR = ("sub", ("roll_std", "gap", 63), "ret21")


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
