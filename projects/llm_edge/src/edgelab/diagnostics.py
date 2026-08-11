"""Loop-3 diagnostics (deviation D3): family-wide Reality Check, an explicit
DSR-unavailable audit, and the survivorship autopsy of the range-vol family.

Writes report/loop3_diagnostics.json. All backtests ledgered as always.
"""

from __future__ import annotations

import hashlib
import io
import json

import pandas as pd

from . import CANDIDATES_DIR, REPO_ROOT, TRAIN_START, VALIDATION_END, VALIDATION_START
from .backtest import (
    MIXED_LEDGER_DSR_UNAVAILABLE,
    ledger_trial_stats,
    run_backtest,
)
from .costs import EQUITY_BPS, ETF_BPS
from .gates import (
    FAMILY_META_PATH,
    FAMILY_RETURNS_PATH,
    family_artifact_identity,
    load_equity_fields,
    load_etf_fields,
)
from .jsonutil import atomic_write_text, dumps
from .stats import newey_west_tstat, reality_check_pvalue, sharpe_ratio


def _val(s: pd.Series) -> pd.Series:
    return s[
        (s.index >= pd.Timestamp(VALIDATION_START)) & (s.index <= pd.Timestamp(VALIDATION_END))
    ]


def _verified_family_returns() -> tuple[pd.DataFrame, dict[str, object]]:
    if not FAMILY_RETURNS_PATH.is_file() or not FAMILY_META_PATH.is_file():
        raise RuntimeError("family returns are missing; run the complete gate driver")
    try:
        metadata = json.loads(FAMILY_META_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid family returns metadata: {exc}") from exc
    candidate_ids = sorted(
        path.name for path in CANDIDATES_DIR.iterdir() if (path / "signal.py").is_file()
    )
    expected = family_artifact_identity(candidate_ids)
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise RuntimeError(f"family returns {key} is stale; rerun the complete gate driver")
    try:
        artifact = FAMILY_RETURNS_PATH.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"could not read family returns artifact: {exc}") from exc
    artifact_hash = hashlib.sha256(artifact).hexdigest()
    if metadata.get("artifact_sha256") != artifact_hash:
        raise RuntimeError("family returns artifact hash mismatch")
    try:
        # Parse the exact bytes that were hashed. Reopening the pathname here
        # would permit a same-path replacement between verification and use.
        panel = pd.read_parquet(io.BytesIO(artifact))
    except Exception as exc:
        raise RuntimeError(f"invalid family returns artifact: {exc}") from exc
    if list(panel.columns) != candidate_ids:
        raise RuntimeError("family returns columns do not match the declared candidate family")
    return panel, metadata


def _require_matching_inputs(fields, identity: dict[str, object]) -> None:
    input_identity = getattr(fields, "input_identity", {})
    for key in ("data_manifest_sha256", "universe_sha256"):
        if input_identity.get(key) != identity.get(key):
            raise RuntimeError(f"diagnostic fields were built from a different {key}")


def _held_leg_returns(
    held_weights: pd.DataFrame,
    adjclose: pd.DataFrame,
    *,
    start_date: str,
) -> tuple[pd.Series, pd.Series]:
    """Decompose exact central-backtest holdings over its evaluated horizon."""
    if not held_weights.index.equals(adjclose.index) or not held_weights.columns.equals(
        adjclose.columns
    ):
        raise ValueError("held weights and adjclose must have identical index and columns")
    returns = adjclose.pct_change(fill_method=None)
    evaluated = held_weights.index >= pd.Timestamp(start_date)
    held = held_weights.loc[evaluated]
    returns = returns.loc[evaluated]
    missing_held = (held != 0) & returns.isna()
    if missing_held.any().any():
        first_date, first_ticker = missing_held.stack().loc[lambda values: values].index[0]
        raise ValueError(
            f"held asset {first_ticker} has no return on {first_date}: "
            "repair delisting/missing-price data instead of treating it as zero"
        )
    long_weights = held.clip(lower=0.0)
    short_member_weights = -held.clip(upper=0.0)
    return (long_weights * returns).sum(axis=1), (short_member_weights * returns).sum(axis=1)


def main() -> None:
    out: dict = {}

    # 1. Family-wide Reality Check on all candidates' validation net returns.
    panel, family_identity = _verified_family_returns()
    out["research_identity"] = family_identity
    val_panel = _val(panel)
    out["reality_check_validation"] = reality_check_pvalue(val_panel, n_boot=1000)
    out["reality_check_note"] = (
        "H0: best candidate of the gated family has zero expected net validation return; "
        "p-value from the pre-registered stationary-bootstrap maximum-Sharpe statistic"
    )

    # 2. Survivorship autopsy of the range-vol family (C015 construct).
    eq = load_equity_fields()
    _require_matching_inputs(eq, family_identity)
    rng_frac = (eq["high"] - eq["low"]) / eq["close"]
    sig = rng_frac.rolling(63, min_periods=31).std()

    rets = eq["adjclose"].pct_change(fill_method=None)
    ew = rets.mean(axis=1)
    eq_bt = run_backtest(
        sig,
        eq["adjclose"],
        candidate_id="diag_rangevol_eq",
        split="diag_full",
        cost_bps=EQUITY_BPS,
        quantile=0.1,
        holding_days=5,
        start_date=TRAIN_START,
    )
    long_leg, short_leg = _held_leg_returns(
        eq_bt.weights,
        eq["adjclose"],
        start_date=TRAIN_START,
    )
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
    _require_matching_inputs(etf, family_identity)
    etf_rng = (etf["high"] - etf["low"]) / etf["close"]
    etf_sig = etf_rng.rolling(63, min_periods=31).std()
    etf_bt = run_backtest(
        etf_sig,
        etf["adjclose"],
        candidate_id="diag_rangevol_etf",
        split="diag_val",
        cost_bps=ETF_BPS,
        quantile=0.2,
        holding_days=5,
        min_names=30,
        start_date=TRAIN_START,
        ledger_start_date=VALIDATION_START,
        ledger_end_date=VALIDATION_END,
    )
    v = _val(etf_bt.returns_net)
    out["rangevol_on_etfs_validation"] = {
        "sr_net": sharpe_ratio(v),
        "nw_t": newey_west_tstat(v),
        "n_obs": len(v),
    }

    # Sub-period stability on equities (train halves + validation).
    r = eq_bt.returns_net
    out["rangevol_equities_subperiods"] = {
        "2005_2011_sr": sharpe_ratio(r[(r.index >= "2005-01-01") & (r.index <= "2011-12-31")]),
        "2012_2018_sr": sharpe_ratio(r[(r.index >= "2012-01-01") & (r.index <= "2018-12-31")]),
        "2019_2023_sr": sharpe_ratio(_val(r)),
    }

    # 3. Snapshot only after every diagnostic backtest above has reached the
    # ledger, so "full ledger" describes the artifact written by this run.
    n_trials, var_sr = ledger_trial_stats()
    out["c015_dsr_full_ledger"] = None
    out["c015_dsr_unavailable_reason"] = MIXED_LEDGER_DSR_UNAVAILABLE
    out["ledger"] = {
        "n_trials": n_trials,
        "raw_mixed_var_sr_annualized": var_sr,
        "trial_variance_comparable": False,
    }
    path = REPO_ROOT / "report" / "loop3_diagnostics.json"
    atomic_write_text(path, dumps(out, indent=1))
    print(dumps(out, indent=1))


if __name__ == "__main__":
    main()
