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
    TRAIN_START,
)
from .backtest import (
    MIXED_LEDGER_DSR_UNAVAILABLE,
    ledger_trial_stats,
    record_failed_trial,
    run_backtest,
)
from .costs import cost_rate
from .gates import (
    load_equity_fields,
    load_etf_fields,
    signal_metadata,
)
from .holdout_gate import (
    authorize,
    authorized_research_snapshot,
    authorized_signal_source,
    record_results,
    reverify_authorized_state,
)
from .jsonutil import sanitize
from .signals import compute_declared_signal
from .stats import newey_west_tstat, sharpe_ratio

GATE3 = {"min_dsr": 0.95, "min_pooled_abs_t": 3.0}


def evaluate_holdout(candidate_id: str) -> dict:
    token = authorize(candidate_id)
    try:
        signal_source = authorized_signal_source(token, candidate_id)
        # Freeze the multiple-testing budget before opening or evaluating the
        # holdout. The holdout trial itself must not influence its own DSR or
        # later candidates' pre-registered research benchmark.
        entry, ledger_prefix = authorized_research_snapshot(token, candidate_id)
        research_ledger_stats = ledger_trial_stats(payload=ledger_prefix)
        holdout_end = entry["holdout_end"]

        metadata = signal_metadata(candidate_id, source_text=signal_source)
        is_etf = metadata.get("UNIVERSE", "equities") == "etfs"
        loader = load_etf_fields if is_etf else load_equity_fields
        fields = loader(end=holdout_end, token=token, candidate_id=candidate_id)
        hold = int(metadata.get("HOLD", 1))
        quantile = float(metadata.get("QUANTILE", 0.1))
        min_names = int(metadata.get("MIN_NAMES", 20))

        signal = compute_declared_signal(fields, metadata)
        # All executable/input state is now snapshotted in memory. Recheck the
        # seal before run_backtest performs its required ledger append; doing
        # this afterward would mistake our own audit row for outside tampering.
        reverify_authorized_state(token, candidate_id)
        result = run_backtest(
            signal,
            fields["adjclose"],
            candidate_id=candidate_id,
            split="holdout",
            cost_bps=cost_rate("etfs" if is_etf else "equities"),
            quantile=quantile,
            holding_days=hold,
            min_names=min_names,
            start_date=TRAIN_START,
            ledger_start_date=HOLDOUT_START,
            ledger_end_date=holdout_end,
        )
        out = sanitize(_score_result(candidate_id, result, research_ledger_stats))
    except Exception as exc:
        ledger_audit_error = None
        if not getattr(exc, "_edgelab_trial_recorded", False):
            try:
                record_failed_trial(candidate_id, "holdout", "registered signal", exc)
            except Exception as audit_exc:
                ledger_audit_error = f"{type(audit_exc).__name__}: {audit_exc}"
        out = {
            "candidate_id": candidate_id,
            "error": f"{type(exc).__name__}: {exc}",
            "gate3": {"pass": False},
        }
        if ledger_audit_error is not None:
            out["ledger_audit_error"] = ledger_audit_error
        record_results(candidate_id, out, token)
        return out
    record_results(candidate_id, out, token)
    return out


def _score_result(candidate_id: str, result, research_ledger_stats: tuple[int, float]) -> dict:
    net = result.returns_net
    holdout_net = net[net.index >= pd.Timestamp(HOLDOUT_START)]
    pooled_net = net[net.index >= pd.Timestamp(TRAIN_START)]

    if len(holdout_net) == 0:
        out = {
            "candidate_id": candidate_id,
            "error": "no live holdout returns (signal produced no positions in holdout window)",
            "gate3": {"pass": False},
        }
        return out

    n_trials, var_sr = research_ledger_stats
    dsr = {
        "dsr": None,
        "n_trials": n_trials,
        "raw_mixed_var_sr_annualized": var_sr,
        "unavailable_reason": MIXED_LEDGER_DSR_UNAVAILABLE,
    }

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
        "dsr_gt_0.95": False,
        "pooled_abs_t_gt_3": bool(abs(out["pooled"]["nw_t"]) > GATE3["min_pooled_abs_t"]),
    }
    gate3["pass"] = all(gate3.values())
    out["gate3"] = gate3

    return out


if __name__ == "__main__":
    for cid in sys.argv[1:]:
        res = evaluate_holdout(cid)
        print(json.dumps(res["gate3"], indent=1))
