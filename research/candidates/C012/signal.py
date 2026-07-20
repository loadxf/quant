"""C012: G2 rediscovery — one-month reversal (spec.md)."""

import pandas as pd

from quantlab.grammar import build_terminals, evaluate

EXPR = ("neg", "ret21")


def compute_signal(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    terms = build_terminals(
        fields["open"], fields["high"], fields["low"],
        fields["close"], fields["adjclose"], fields["volume"],
    )
    return evaluate(EXPR, terms)
