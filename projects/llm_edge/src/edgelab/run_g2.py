"""G2 driver: evolutionary search over the signal grammar on TRAIN data only.

Variants (loop 2, deviation D2):
  python -m edgelab.run_g2            # loop-1 config: equities, 1-day hold
  python -m edgelab.run_g2 equities5  # equities, 5-day holding overlap
  python -m edgelab.run_g2 etf5      # ETF cross-section, 5-day hold, 5 bps

Fitness never sees validation or holdout. Every evaluation is ledgered.
"""

from __future__ import annotations

import sys

import pandas as pd

from . import CANDIDATES_DIR, TRAIN_END, TRAIN_START
from .costs import EQUITY_BPS, ETF_BPS
from .gates import load_equity_fields, load_etf_fields
from .grammar import build_terminals
from .jsonutil import atomic_write_text, dumps
from .search import evolve

TOP_K = 12

VARIANTS = {
    "equities1": {
        "universe": "equities",
        "holding_days": 1,
        "cost_bps": EQUITY_BPS,
        "quantile": 0.1,
        "seed": 20260719,
        "population": 120,
        "generations": 8,
        "train_start": TRAIN_START,
        "subsample": None,
    },
    # loop-2 variants (D2 addendum): search fitness on the 2010-2018 train
    # subwindow and a stride-sampled 252-name subuniverse for speed and
    # restart-resilience; gates still evaluate on the FULL universe/period.
    "equities5": {
        "universe": "equities",
        "holding_days": 5,
        "cost_bps": EQUITY_BPS,
        "quantile": 0.1,
        "seed": 20260720,
        "population": 100,
        "generations": 6,
        "train_start": "2010-01-01",
        "subsample": 2,
    },
    "etf5": {
        "universe": "etfs",
        "holding_days": 5,
        "cost_bps": ETF_BPS,
        "quantile": 0.2,
        "seed": 20260721,
        "population": 100,
        "generations": 6,
        "train_start": TRAIN_START,
        "subsample": None,
    },
}


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "equities1"
    cfg = VARIANTS[name]
    if cfg["universe"] == "equities":
        fields = load_equity_fields(end=TRAIN_END)
    else:
        fields = load_etf_fields(end=TRAIN_END)
    if cfg["subsample"]:
        cols = sorted(fields["adjclose"].columns)[:: cfg["subsample"]]
        fields = {
            key: value[[column for column in cols if column in value.columns]]
            if isinstance(value, pd.DataFrame)
            else value
            for key, value in fields.items()
        }
    terms = build_terminals(
        fields["open"],
        fields["high"],
        fields["low"],
        fields["close"],
        fields["adjclose"],
        fields["volume"],
    )
    results = evolve(
        terms,
        fields["adjclose"],
        population=cfg["population"],
        generations=cfg["generations"],
        seed=cfg["seed"],
        log_path=f"candidates/g2_search_history_{name}.json",
        holding_days=cfg["holding_days"],
        cost_bps=cfg["cost_bps"],
        quantile=cfg["quantile"],
        split=f"train_g2_{name}",
        checkpoint_path=f"candidates/g2_checkpoint_{name}.json",
        start_date=cfg["train_start"],
    )
    finite = [r for r in results if pd.notna(r.train_sharpe)]
    survivors = []
    seen_prefix = set()
    for r in finite:
        key = r.expr_str.split(" ")[0]
        if len(survivors) < TOP_K and (key not in seen_prefix or len(survivors) < 6):
            survivors.append(
                {
                    "expr": r.expr_str,
                    "train_sr_net": r.train_sharpe,
                    "fitness": r.fitness,
                    "n_nodes": r.n_nodes,
                }
            )
            seen_prefix.add(key)
        if len(survivors) >= TOP_K:
            break
    atomic_write_text(CANDIDATES_DIR / f"g2_survivors_{name}.json", dumps(survivors, indent=1))
    print(f"[{name}] evaluated {len(results)} distinct expressions; wrote top {len(survivors)}")
    for s in survivors[:5]:
        print(f"  SR={s['train_sr_net']:.2f} fit={s['fitness']:.2f} {s['expr']}")


if __name__ == "__main__":
    main()
