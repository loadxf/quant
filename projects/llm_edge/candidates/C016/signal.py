"""C016: 63-day skew of absolute cross-sectional volume-z rank, ETFs (spec.md)."""

import pandas as pd
from edgelab.grammar import build_terminals, evaluate, parse_expr

EXPR = "(roll_skew (abs_ (cs_rank volz)) 63)"
HOLD = 5
QUANTILE = 0.2
MIN_NAMES = 30
UNIVERSE = "etfs"


def compute_signal(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    terms = build_terminals(
        fields["open"],
        fields["high"],
        fields["low"],
        fields["close"],
        fields["adjclose"],
        fields["volume"],
    )
    return evaluate(parse_expr(EXPR), terms)
