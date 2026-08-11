"""Gate 1/2 evaluation driver (protocol.md section 7).

Runs a candidate's signal.py against train+validation data, computes every
pre-registered gate quantity, and writes candidates/C###/results_validation.json.
Gate 3 (holdout) lives in holdout_eval.py and is NOT reachable from here.

Per-candidate knobs are read from optional module constants in signal.py:
HOLD (holding days), QUANTILE, MIN_NAMES. Gate-2 parameter perturbation scales
every numeric UPPERCASE module constant by 0.75x and 1.25x and re-runs
validation (ints rounded, minimum 1). All runs are ledgered by the engine.
"""

from __future__ import annotations

import importlib.util
import json
import sys

import numpy as np
import pandas as pd

from . import (
    CANDIDATES_DIR,
    REPO_ROOT,
    TRAIN_START,
    VALIDATION_END,
    VALIDATION_START,
)
from .backtest import run_backtest
from .costs import cost_rate
from .cpcv import cpcv_sharpe_distribution
from .data import load_panel
from .stats import newey_west_tstat, sharpe_ratio

GATE1 = {"min_val_sr": 0.5, "min_abs_t": 2.0, "min_cpcv_median": 0.0}


def load_signal_module(candidate_id: str):
    path = CANDIDATES_DIR / candidate_id / "signal.py"
    spec = importlib.util.spec_from_file_location(f"signal_{candidate_id}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_equity_fields(end: str | None = None, token: str | None = None) -> dict[str, pd.DataFrame]:
    universe = json.loads((REPO_ROOT / "data" / "universe.json").read_text())
    fields = {}
    for f in ["open", "high", "low", "close", "adjclose", "volume"]:
        panel = load_panel(field=f, end=end, _holdout_token=token)
        eq = [t for t in universe["equities"] if t in panel.columns]
        fields[f] = panel[eq]
        if f == "adjclose":
            etfs = [t for t in universe["etfs"] if t in panel.columns]
            fields["etf_adjclose"] = panel[etfs]
    return fields


def _slice(series: pd.Series, start: str, end: str) -> pd.Series:
    return series[(series.index >= pd.Timestamp(start)) & (series.index <= pd.Timestamp(end))]


def load_etf_fields(end: str | None = None, token: str | None = None) -> dict[str, pd.DataFrame]:
    universe = json.loads((REPO_ROOT / "data" / "universe.json").read_text())
    fields = {}
    for f in ["open", "high", "low", "close", "adjclose", "volume"]:
        panel = load_panel(field=f, end=end, _holdout_token=token)
        etfs = [t for t in universe["etfs"] if t in panel.columns]
        fields[f] = panel[etfs]
    return fields


def evaluate_candidate(candidate_id: str, fields: dict[str, pd.DataFrame]) -> dict:
    module = load_signal_module(candidate_id)
    hold = int(getattr(module, "HOLD", 1))
    quantile = float(getattr(module, "QUANTILE", 0.1))
    min_names = int(getattr(module, "MIN_NAMES", 20))
    base_cost = cost_rate(getattr(module, "UNIVERSE", "equities"))

    signal = module.compute_signal(fields)

    def bt(split_name: str, cost_bps: float = base_cost, sig=None, cid=None):
        return run_backtest(
            sig if sig is not None else signal,
            fields["adjclose"],
            candidate_id=cid or candidate_id,
            split=split_name,
            cost_bps=cost_bps,
            quantile=quantile,
            holding_days=hold,
            min_names=min_names,
        )

    full = bt("train_val")
    val_net = _slice(full.returns_net, VALIDATION_START, VALIDATION_END)
    train_net = _slice(full.returns_net, TRAIN_START, "2018-12-31")

    results: dict = {
        "candidate_id": candidate_id,
        "params": {"hold": hold, "quantile": quantile, "min_names": min_names},
        "train": {
            "sr_net": sharpe_ratio(train_net),
            "nw_t": newey_west_tstat(train_net),
            "n_obs": len(train_net),
        },
        "validation": {
            "sr_net": sharpe_ratio(val_net),
            "sr_gross": sharpe_ratio(_slice(full.returns_gross, VALIDATION_START, VALIDATION_END)),
            "nw_t": newey_west_tstat(val_net),
            "n_obs": len(val_net),
            "mean_daily_turnover": float(
                _slice(full.turnover, VALIDATION_START, VALIDATION_END).mean()
            ),
        },
    }

    # Gate 1
    cpcv = cpcv_sharpe_distribution(full.returns_net)
    results["cpcv"] = cpcv
    if len(val_net) == 0:
        # Degenerate candidate (all-NaN signal, empty quantiles, MIN_NAMES
        # above the cross-section): record failing gates instead of
        # crashing the whole batch on the mid-split below. The on-disk
        # record is written exactly like the normal path — a stale PASS
        # file from an earlier run must not survive a now-degenerate
        # signal.
        results["gate1"] = {"pass": False, "reason": "no live validation days"}
        results["gate2"] = {"pass": False, "reason": "no live validation days"}
        results["strategy_returns_net_train_val"] = None
        out_path = CANDIDATES_DIR / candidate_id / "results_validation.json"
        out_path.write_text(json.dumps(results, indent=1, default=str))
        return results | {"_returns_net": val_net}
    g1 = {
        "val_sr_gt_0.5": bool(results["validation"]["sr_net"] > GATE1["min_val_sr"]),
        "abs_t_gt_2": bool(abs(results["validation"]["nw_t"]) > GATE1["min_abs_t"]),
        "sign_positive": bool(results["validation"]["sr_net"] > 0),
        "cpcv_median_gt_0": bool(cpcv["median_sr"] > GATE1["min_cpcv_median"]),
    }
    g1["pass"] = all(g1.values())
    results["gate1"] = g1

    # Gate 2 (run regardless, for the record)
    mid = val_net.index[len(val_net) // 2]
    half1, half2 = val_net[val_net.index <= mid], val_net[val_net.index > mid]

    ew_ret = fields["adjclose"].pct_change(fill_method=None).mean(axis=1)
    realized_vol = ew_ret.rolling(63).std()
    vol_at = realized_vol.reindex(val_net.index)
    hi_vol = val_net[vol_at > vol_at.median()]
    lo_vol = val_net[vol_at <= vol_at.median()]

    cost25 = bt("val_cost25", cost_bps=25.0)
    val25 = _slice(cost25.returns_net, VALIDATION_START, VALIDATION_END)

    perturb_srs = {}
    for attr in dir(module):
        if (
            attr.isupper()
            and isinstance(getattr(module, attr), (int, float))
            and attr not in ("HOLD", "QUANTILE", "MIN_NAMES")  # portfolio knobs, not signal params
        ):
            base_val = getattr(module, attr)
            for factor in (0.75, 1.25):
                new_val = base_val * factor
                if isinstance(base_val, int):
                    new_val = max(1, round(new_val))
                    if new_val == base_val:
                        continue
                setattr(module, attr, new_val)
                try:
                    psig = module.compute_signal(fields)
                    pres = bt("val_perturb", sig=psig, cid=f"{candidate_id}_p_{attr}_{factor}")
                    perturb_srs[f"{attr}x{factor}"] = sharpe_ratio(
                        _slice(pres.returns_net, VALIDATION_START, VALIDATION_END)
                    )
                except Exception as err:
                    perturb_srs[f"{attr}x{factor}"] = f"error: {err}"
                finally:
                    setattr(module, attr, base_val)

    g2 = {
        "subhalf1_sr": sharpe_ratio(half1),
        "subhalf2_sr": sharpe_ratio(half2),
        "hivol_sr": sharpe_ratio(hi_vol),
        "lovol_sr": sharpe_ratio(lo_vol),
        "cost25_sr": sharpe_ratio(val25),
        "perturbations": perturb_srs,
    }
    numeric_perturbs = [v for v in perturb_srs.values() if isinstance(v, float) and np.isfinite(v)]
    g2["pass"] = bool(
        g2["subhalf1_sr"] > 0
        and g2["subhalf2_sr"] > 0
        and g2["hivol_sr"] > 0
        and g2["lovol_sr"] > 0
        and g2["cost25_sr"] > 0
        and (all(v > 0 for v in numeric_perturbs) if numeric_perturbs else True)
    )
    results["gate2"] = g2
    results["strategy_returns_net_train_val"] = None  # filled by driver for RC test

    out_path = CANDIDATES_DIR / candidate_id / "results_validation.json"
    out_path.write_text(json.dumps(results, indent=1, default=str))
    return results | {"_returns_net": full.returns_net}


def main() -> None:
    ids = sys.argv[1:]
    if not ids:
        ids = sorted(p.name for p in CANDIDATES_DIR.iterdir() if (p / "signal.py").exists())
    eq_fields = load_equity_fields()
    etf_fields = None
    family_returns = {}
    for cid in ids:
        module = load_signal_module(cid)
        if getattr(module, "UNIVERSE", "equities") == "etfs":
            if etf_fields is None:
                etf_fields = load_etf_fields()
            fields = etf_fields
        else:
            fields = eq_fields
        res = evaluate_candidate(cid, fields)
        family_returns[cid] = res.pop("_returns_net")
        v = res["validation"]
        print(
            f"{cid}: val SR={v['sr_net']:.2f} t={v['nw_t']:.2f} "
            f"gate1={'PASS' if res['gate1']['pass'] else 'fail'} "
            f"gate2={'PASS' if res['gate2']['pass'] else 'fail'}"
        )
    panel = pd.DataFrame(family_returns)
    prev_path = CANDIDATES_DIR / "family_returns_train_val.parquet"
    if prev_path.exists():
        prev = pd.read_parquet(prev_path)
        keep = [c for c in prev.columns if c not in panel.columns]
        panel = prev[keep].join(panel, how="outer")
    panel.to_parquet(prev_path)


if __name__ == "__main__":
    main()
