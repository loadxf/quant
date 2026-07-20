"""Loop-3 diagnostics (deviation D3): family-wide Reality Check, DSR arithmetic
for the best candidate, and the survivorship autopsy of the range-vol family.

Writes report/loop3_diagnostics.json. All backtests ledgered as always.
"""

from __future__ import annotations

import json

import pandas as pd

from . import CANDIDATES_DIR, REPO_ROOT, VALIDATION_END, VALIDATION_START
from .backtest import ledger_trial_stats, run_backtest
from .gates import load_equity_fields, load_etf_fields
from .stats import (
    deflated_sharpe_ratio,
    newey_west_tstat,
    reality_check_pvalue,
    sharpe_ratio,
)


def _val(s: pd.Series) -> pd.Series:
    return s[(s.index >= pd.Timestamp(VALIDATION_START)) & (s.index <= pd.Timestamp(VALIDATION_END))]


def main() -> None:
    out: dict = {}

    # 1. Family-wide Reality Check on all candidates' validation net returns.
    panel = pd.read_parquet(CANDIDATES_DIR / "family_returns_train_val.parquet")
    val_panel = _val(panel)
    out["reality_check_validation"] = reality_check_pvalue(val_panel, n_boot=1000)
    out["reality_check_note"] = (
        "H0: best candidate of the gated family has zero mean net validation return; "
        "p-value from stationary-bootstrap max statistic (White 2000 style)"
    )

    # 2. DSR of the best candidate (C015) against the FULL ledger.
    n_trials, var_sr = ledger_trial_stats()
    c015 = val_panel["C015"].dropna()
    out["c015_dsr_full_ledger"] = deflated_sharpe_ratio(c015, n_trials, var_sr)

    # 3. Survivorship autopsy of the range-vol family (C015 construct).
    eq = load_equity_fields()
    rng_frac = (eq["high"] - eq["low"]) / eq["close"]
    sig = rng_frac.rolling(63, min_periods=31).std()

    long_only = sig.rank(axis=1, pct=True).ge(0.9).astype(float)
    long_only = long_only.div(long_only.sum(axis=1), axis=0).fillna(0.0)
    short_only = sig.rank(axis=1, pct=True).le(0.1).astype(float)
    short_only = short_only.div(short_only.sum(axis=1), axis=0).fillna(0.0)
    rets = eq["adjclose"].pct_change(fill_method=None)
    ew = rets.mean(axis=1)
    long_leg = (long_only.shift(2) * rets).sum(axis=1)
    short_leg = (short_only.shift(2) * rets).sum(axis=1)
    out["c015_leg_decomposition_validation"] = {
        "long_leg_minus_ew_sr": sharpe_ratio(_val(long_leg - ew)),
        "short_leg_minus_ew_sr": sharpe_ratio(_val(short_leg - ew)),
        "long_leg_sr": sharpe_ratio(_val(long_leg)),
        "short_leg_sr": sharpe_ratio(_val(short_leg)),
        "note": "if the premium lives in the long (high-vol) leg beating the market on "
                "current constituents, survivorship inflation is the prime suspect",
    }

    # ETF-universe replication (no deletion-style survivorship in current ETF list).
    etf = load_etf_fields()
    etf_rng = (etf["high"] - etf["low"]) / etf["close"]
    etf_sig = etf_rng.rolling(63, min_periods=31).std()
    etf_bt = run_backtest(
        etf_sig, etf["adjclose"], candidate_id="diag_rangevol_etf",
        split="diag_val", cost_bps=5.0, quantile=0.2, holding_days=5, min_names=30,
    )
    v = _val(etf_bt.returns_net)
    out["rangevol_on_etfs_validation"] = {
        "sr_net": sharpe_ratio(v),
        "nw_t": newey_west_tstat(v),
        "n_obs": int(len(v)),
    }

    # Sub-period stability on equities (train halves + validation).
    eq_bt = run_backtest(
        sig, eq["adjclose"], candidate_id="diag_rangevol_eq",
        split="diag_full", cost_bps=10.0, quantile=0.1, holding_days=5,
    )
    r = eq_bt.returns_net
    out["rangevol_equities_subperiods"] = {
        "2005_2011_sr": sharpe_ratio(r[(r.index >= "2005-01-01") & (r.index <= "2011-12-31")]),
        "2012_2018_sr": sharpe_ratio(r[(r.index >= "2012-01-01") & (r.index <= "2018-12-31")]),
        "2019_2023_sr": sharpe_ratio(_val(r)),
    }

    out["ledger"] = {"n_trials": n_trials, "var_sr_annualized": var_sr}
    path = REPO_ROOT / "report" / "loop3_diagnostics.json"
    path.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
