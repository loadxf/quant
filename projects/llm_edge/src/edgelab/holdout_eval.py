"""Gate 3: the one-shot holdout evaluation (protocol.md sections 4 and 7).

Usage: python -m edgelab.holdout_eval C001
Requires the candidate's registration to be committed (holdout_gate enforces).
Writes the immutable holdout_results.json. There is no re-run path.
"""

from __future__ import annotations

import json
import sys

import pandas as pd

from . import (
    HOLDOUT_START,
    POST_CUTOFF_START,
    REGISTRY_PATH,
)
from .backtest import ledger_trial_stats, run_backtest
from .costs import cost_rate
from .gates import load_equity_fields, load_etf_fields, load_signal_module
from .holdout_gate import authorize, record_results
from .stats import deflated_sharpe_ratio, newey_west_tstat, sharpe_ratio

GATE3 = {"min_dsr": 0.95, "min_pooled_abs_t": 3.0}


def evaluate_holdout(candidate_id: str) -> dict:
    token = authorize(candidate_id)
    registry = json.loads(REGISTRY_PATH.read_text())
    entry = registry[candidate_id]
    holdout_end = entry.get("holdout_end", "2030-01-01")

    module = load_signal_module(candidate_id)
    universe = entry.get("universe", getattr(module, "UNIVERSE", "equities"))
    if universe == "etfs":
        fields = load_etf_fields(end=holdout_end, token=token)
    else:
        fields = load_equity_fields(end=holdout_end, token=token)
    hold = int(getattr(module, "HOLD", 1))
    quantile = float(getattr(module, "QUANTILE", 0.1))
    min_names = int(getattr(module, "MIN_NAMES", 20))

    signal = module.compute_signal(fields)
    result = run_backtest(
        signal,
        fields["adjclose"],
        candidate_id=candidate_id,
        split="holdout",
        cost_bps=cost_rate(universe),
        quantile=quantile,
        holding_days=hold,
        min_names=min_names,
    )
    net = result.returns_net
    holdout_net = net[net.index >= pd.Timestamp(HOLDOUT_START)]
    pooled_net = net  # train + validation + holdout, same engine and params

    if len(holdout_net) == 0:
        out = {
            "candidate_id": candidate_id,
            "error": "no live holdout returns (signal produced no positions in holdout window)",
            "gate3": {"pass": False},
        }
        record_results(candidate_id, out)
        return out

    n_trials, var_sr = ledger_trial_stats()
    dsr = deflated_sharpe_ratio(holdout_net, n_trials, var_sr)

    post_cutoff = holdout_net[holdout_net.index >= pd.Timestamp(POST_CUTOFF_START)]
    out = {
        "candidate_id": candidate_id,
        "holdout_window": [
            str(holdout_net.index.min().date()),
            str(holdout_net.index.max().date()),
        ],
        "holdout": {
            "sr_net": sharpe_ratio(holdout_net),
            "nw_t": newey_west_tstat(holdout_net),
            "n_obs": len(holdout_net),
        },
        "pooled": {
            "sr_net": sharpe_ratio(pooled_net),
            "nw_t": newey_west_tstat(pooled_net),
            "n_obs": len(pooled_net),
        },
        "dsr": dsr,
        "post_cutoff_directional": {
            "window_start": POST_CUTOFF_START,
            "sr_net": sharpe_ratio(post_cutoff) if len(post_cutoff) > 20 else None,
            "mean_daily_bps": float(post_cutoff.mean() * 1e4) if len(post_cutoff) > 0 else None,
            "n_obs": len(post_cutoff),
            "note": "directional consistency check only; never primary evidence (protocol R3)",
        },
    }
    gate3 = {
        "holdout_sr_gt_0": bool(out["holdout"]["sr_net"] > 0),
        "dsr_gt_0.95": bool(dsr["dsr"] > GATE3["min_dsr"]),
        "pooled_abs_t_gt_3": bool(abs(out["pooled"]["nw_t"]) > GATE3["min_pooled_abs_t"]),
    }
    gate3["pass"] = all(gate3.values())
    out["gate3"] = gate3

    record_results(candidate_id, out)
    return out


if __name__ == "__main__":
    for cid in sys.argv[1:]:
        res = evaluate_holdout(cid)
        print(json.dumps(res["gate3"], indent=1))
