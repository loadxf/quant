"""C008: gap-intraday coherence premium (spec.md)."""

import pandas as pd

from quantlab.grammar import build_terminals

SMOOTH = 3


def compute_signal(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    terms = build_terminals(
        fields["open"], fields["high"], fields["low"],
        fields["close"], fields["adjclose"], fields["volume"],
    )
    coherence = terms["gap"] * terms["intraday"]
    return coherence.rolling(SMOOTH, min_periods=2).mean()
