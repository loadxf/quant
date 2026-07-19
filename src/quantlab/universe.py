"""Build data/universe.json: current S&P 500 constituents (Yahoo ticker form)
plus ~60 liquid ETFs across sectors, countries, bonds, and commodities.

Survivorship caveat (protocol.md R2): this is TODAY'S constituent list, so
long-only results on it are inflated; the experiment therefore prefers
cross-sectional long-short designs and flags long-only results as suspect.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from . import DATA_DIR

ETFS = [
    # broad US + style
    "SPY", "QQQ", "DIA", "IWM", "MDY", "IWD", "IWF", "VTV", "VUG",
    # sectors
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
    # industries
    "XHB", "XRT", "KRE", "KBE", "SMH", "IBB", "XOP", "OIH", "ITA", "VNQ",
    # countries / regions
    "EFA", "EEM", "EWA", "EWC", "EWG", "EWH", "EWI", "EWJ", "EWL", "EWM",
    "EWN", "EWO", "EWP", "EWQ", "EWS", "EWT", "EWU", "EWW", "EWY", "EWZ",
    "EZA", "FXI", "INDA", "ILF",
    # bonds
    "TLT", "IEF", "SHY", "LQD", "HYG", "AGG", "TIP", "EMB",
    # commodities + currencies
    "GLD", "SLV", "USO", "UNG", "DBC", "GDX", "UUP", "FXE", "FXY",
]


def yahoo_ticker(symbol: str) -> str:
    """S&P list uses dots for share classes (BRK.B); Yahoo uses dashes."""
    return symbol.replace(".", "-")


def build_universe(constituents_csv: Path) -> dict:
    with constituents_csv.open() as fh:
        rows = list(csv.DictReader(fh))
    equities = sorted({yahoo_ticker(r["Symbol"]) for r in rows})
    sectors = {yahoo_ticker(r["Symbol"]): r["GICS Sector"] for r in rows}
    universe = {
        "equities": equities,
        "etfs": ETFS,
        "sectors": sectors,
        "source": "github.com/datasets/s-and-p-500-companies (current constituents)",
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "universe.json").write_text(json.dumps(universe, indent=1, sort_keys=True))
    return universe


if __name__ == "__main__":
    csv_path = Path(sys.argv[1])
    u = build_universe(csv_path)
    print(f"universe: {len(u['equities'])} equities + {len(u['etfs'])} ETFs")
