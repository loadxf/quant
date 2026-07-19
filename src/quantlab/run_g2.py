"""G2 driver: evolutionary search over the signal grammar on TRAIN data only.

Fitness never sees validation or holdout. The top distinct survivors are
written to candidates/g2_survivors.json for validation evaluation by the
Phase B driver. Every fitness evaluation is ledgered by the engine.

Usage: python -m quantlab.run_g2
"""

from __future__ import annotations

import json

import pandas as pd

from . import CANDIDATES_DIR, TRAIN_END
from .gates import load_equity_fields
from .grammar import build_terminals
from .search import evolve

TOP_K = 12


def main() -> None:
    fields = load_equity_fields(end=TRAIN_END)
    terms = build_terminals(
        fields["open"], fields["high"], fields["low"],
        fields["close"], fields["adjclose"], fields["volume"],
    )
    results = evolve(
        terms,
        fields["adjclose"],
        population=120,
        generations=8,
        log_path="candidates/g2_search_history.json",
    )
    finite = [r for r in results if pd.notna(r.train_sharpe)]
    survivors = []
    seen_prefix = set()
    for r in finite:
        # crude family dedupe: skip expressions sharing an identical top-level form
        key = r.expr_str.split(" ")[0]
        if len(survivors) < TOP_K and (key not in seen_prefix or len(survivors) < 6):
            survivors.append(
                {"expr": r.expr_str, "train_sr_net": r.train_sharpe,
                 "fitness": r.fitness, "n_nodes": r.n_nodes}
            )
            seen_prefix.add(key)
        if len(survivors) >= TOP_K:
            break
    (CANDIDATES_DIR / "g2_survivors.json").write_text(json.dumps(survivors, indent=1))
    print(f"evaluated {len(results)} distinct expressions; wrote top {len(survivors)}")
    for s in survivors[:5]:
        print(f"  SR={s['train_sr_net']:.2f} fit={s['fitness']:.2f} {s['expr']}")


if __name__ == "__main__":
    main()
