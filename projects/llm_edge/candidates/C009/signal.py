"""C009: sector-ETF next-day member reversal (spec.md).

Uses the driver-provided fields["etf_adjclose"] panel (same end date as the
equity fields, so the holdout discipline is preserved by construction).
"""

import json

import pandas as pd
from edgelab import REPO_ROOT

SECTOR_TO_ETF = {
    "Materials": "XLB",
    "Communication Services": "XLC",
    "Energy": "XLE",
    "Financials": "XLF",
    "Industrials": "XLI",
    "Information Technology": "XLK",
    "Consumer Staples": "XLP",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Health Care": "XLV",
    "Consumer Discretionary": "XLY",
}


def compute_signal(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    adj = fields["adjclose"]
    etf_ret = fields["etf_adjclose"].pct_change(fill_method=None).reindex(adj.index)

    sectors = json.loads((REPO_ROOT / "data" / "universe.json").read_text())["sectors"]
    signal = pd.DataFrame(index=adj.index, columns=adj.columns, dtype=float)
    for ticker in adj.columns:
        etf = SECTOR_TO_ETF.get(sectors.get(ticker, ""))
        if etf is not None and etf in etf_ret.columns:
            signal[ticker] = -etf_ret[etf]
    return signal
