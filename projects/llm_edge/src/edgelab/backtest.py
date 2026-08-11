"""Vectorized daily cross-sectional long-short backtest engine.

Timing convention (protocol.md section 5): a signal value at date t may use
data up to the close of t. The position is formed at the close of t+1 (one-day
implementation lag) and earns the return over t+1 -> t+2. Therefore weights
derived from the signal at t are applied to simple returns at t+2, i.e.
``weights.shift(2)`` against day-t returns.

LEDGER: every call to ``run_backtest`` appends one row to
candidates/trials_ledger.csv (the concurrency-safe multiple-testing ledger). This
happens inside the engine so no evaluation can escape the Deflated Sharpe
Ratio's trial count N. Do not add bypass flags.
"""

from __future__ import annotations

import csv
import datetime as _dt
import fcntl
import hashlib
import io
import json
import math
import numbers
import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import LEDGER_PATH
from .costs import EQUITY_BPS
from .stats import sharpe_ratio

LEDGER_COLUMNS = ["timestamp", "candidate_id", "params_hash", "split", "sr_net", "n_obs"]
MIXED_LEDGER_DSR_UNAVAILABLE = (
    "historical validation-labeled rows contain train-plus-validation Sharpe values; "
    "their mixed trial dispersion is not a calibrated DSR input (retrospective deviation D5)"
)


@dataclass
class BacktestResult:
    returns_gross: pd.Series
    returns_net: pd.Series
    turnover: pd.Series
    weights: pd.DataFrame
    cost_bps: float
    meta: dict = field(default_factory=dict)

    @property
    def sharpe_net(self) -> float:
        return sharpe_ratio(self.returns_net)

    @property
    def sharpe_gross(self) -> float:
        return sharpe_ratio(self.returns_gross)


def quantile_weights(
    signal: pd.DataFrame, quantile: float = 0.1, min_names: int = 20
) -> pd.DataFrame:
    """Equal-weight long-short weights: long the top `quantile` of the
    cross-section by signal, short the bottom. Long leg sums to +1, short to -1.
    Rows with fewer than ``min_names`` valid signals get zero weights.
    """
    if (
        not isinstance(quantile, numbers.Real)
        or isinstance(quantile, bool)
        or not math.isfinite(float(quantile))
        or not 0 < quantile <= 0.5
    ):
        raise ValueError(f"quantile must be in (0, 0.5] (got {quantile})")
    if not isinstance(min_names, int) or isinstance(min_names, bool) or min_names < 2:
        raise ValueError(f"min_names must be >= 2 (got {min_names})")
    values = signal.to_numpy(dtype=float)
    if np.isinf(values).any():
        raise ValueError("signal contains infinite values")
    ranks = signal.rank(axis=1, method="average")
    valid = signal.notna().sum(axis=1)
    # Normalize order statistics symmetrically onto [0, 1]. Pandas' pct=True
    # maps the minimum to 1/N, which can omit the short leg for small N; ties
    # at the median can likewise put the entire row on one side.
    symmetric_rank = ranks.sub(1.0).div(valid.sub(1.0), axis=0)
    long_mask = symmetric_rank.gt(1.0 - quantile)
    short_mask = symmetric_rank.lt(quantile)
    n_long = long_mask.sum(axis=1).replace(0, np.nan)
    n_short = short_mask.sum(axis=1).replace(0, np.nan)
    weights = long_mask.astype(float).div(n_long, axis=0) - short_mask.astype(float).div(
        n_short, axis=0
    )
    has_both_legs = n_long.notna() & n_short.notna()
    weights.loc[(valid < min_names) | ~has_both_legs] = 0.0
    return weights.fillna(0.0)


def _params_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, allow_nan=False).encode()
    ).hexdigest()[:16]


def _signal_sha256(signal: pd.DataFrame) -> str:
    """Content identity for the exact strategy output evaluated in a trial."""
    hashed = pd.util.hash_pandas_object(signal, index=True).to_numpy(dtype="uint64")
    columns = "\x1f".join(map(str, signal.columns)).encode()
    return hashlib.sha256(hashed.tobytes() + columns).hexdigest()


def _date_bound(value: str | pd.Timestamp | None, name: str) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        bound = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a valid date (got {value!r})") from exc
    if pd.isna(bound) or bound.tz is not None:
        raise ValueError(f"{name} must be a finite timezone-naive date")
    return bound.normalize()


def _append_ledger(row: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a+", newline="") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.seek(0, 2)
            # Pin LF regardless of platform/Python defaults so append-only
            # rows do not turn the tracked ledger into a mixed-EOL file.
            writer = csv.DictWriter(fh, fieldnames=LEDGER_COLUMNS, lineterminator="\n")
            if fh.tell() == 0:
                writer.writeheader()
            writer.writerow({column: row[column] for column in LEDGER_COLUMNS})
            fh.flush()
            os.fsync(fh.fileno())
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def record_failed_trial(candidate_id: str, split: str, identity: str, error: Exception) -> None:
    """Ledger an attempted evaluation that failed before a Sharpe existed."""
    meta = {
        "candidate_id": candidate_id,
        "split": split,
        "strategy_identity": identity,
        "failure_type": type(error).__name__,
    }
    _append_ledger(
        {
            "timestamp": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
            "candidate_id": candidate_id,
            "params_hash": _params_hash(meta),
            "split": split,
            "sr_net": "error",
            "n_obs": 0,
        }
    )


def _run_backtest(
    signal: pd.DataFrame,
    adjclose: pd.DataFrame,
    candidate_id: str,
    split: str,
    cost_bps: float = EQUITY_BPS,
    quantile: float = 0.1,
    holding_days: int = 1,
    min_names: int = 20,
    start_date: str | pd.Timestamp | None = None,
    ledger_start_date: str | pd.Timestamp | None = None,
    ledger_end_date: str | pd.Timestamp | None = None,
) -> BacktestResult:
    """Backtest a cross-sectional signal panel against an adjclose panel.

    ``signal`` and ``adjclose`` share the (date x ticker) shape. Signal at t
    must only use information available at close t; the engine applies the
    t+2 alignment so even a "perfect foresight of tomorrow" signal cannot
    profit from leakage (enforced by tests/test_no_lookahead.py).
    """
    if (
        not isinstance(candidate_id, str)
        or not candidate_id.strip()
        or not isinstance(split, str)
        or not split.strip()
    ):
        raise ValueError("candidate_id and split must be non-empty")
    if (
        not isinstance(cost_bps, numbers.Real)
        or isinstance(cost_bps, bool)
        or not math.isfinite(float(cost_bps))
        or cost_bps < 0
    ):
        raise ValueError("cost_bps must be finite and non-negative")
    if not isinstance(holding_days, int) or isinstance(holding_days, bool) or holding_days < 1:
        raise ValueError("holding_days must be >= 1")
    if not isinstance(adjclose.index, pd.DatetimeIndex) or adjclose.empty:
        raise ValueError("adjclose must have a non-empty DatetimeIndex")
    if not adjclose.index.is_unique or not adjclose.index.is_monotonic_increasing:
        raise ValueError("adjclose index must be unique and increasing")
    if not adjclose.columns.is_unique:
        raise ValueError("adjclose columns must be unique")
    if not signal.index.equals(adjclose.index) or not signal.columns.equals(adjclose.columns):
        raise ValueError("signal and adjclose must have identical index and columns")
    evaluation_start = _date_bound(start_date, "start_date")
    ledger_start = _date_bound(ledger_start_date, "ledger_start_date")
    ledger_end = _date_bound(ledger_end_date, "ledger_end_date")
    if evaluation_start is not None and evaluation_start > adjclose.index[-1]:
        raise ValueError("start_date is after the price panel")
    if ledger_start is not None and ledger_end is not None and ledger_start > ledger_end:
        raise ValueError("ledger_start_date is after ledger_end_date")
    if (
        evaluation_start is not None
        and ledger_start is not None
        and ledger_start < evaluation_start
    ):
        raise ValueError("ledger_start_date cannot precede start_date")
    if ledger_start is not None or ledger_end is not None:
        ledger_sessions = np.ones(len(adjclose.index), dtype=bool)
        if evaluation_start is not None:
            ledger_sessions &= adjclose.index >= evaluation_start
        if ledger_start is not None:
            ledger_sessions &= adjclose.index >= ledger_start
        if ledger_end is not None:
            ledger_sessions &= adjclose.index <= ledger_end
        if not ledger_sessions.any():
            raise ValueError(
                "ledger scoring window contains no sessions in the evaluated price horizon"
            )
    observed_prices = adjclose.to_numpy(dtype=float)
    if (
        np.isinf(observed_prices).any()
        or (observed_prices[np.isfinite(observed_prices)] <= 0).any()
    ):
        raise ValueError("observed adjusted prices must be finite and positive")
    signal_values = signal.to_numpy(dtype=float)
    if np.isinf(signal_values).any():
        raise ValueError("signal contains infinite values")
    returns = adjclose.pct_change(fill_method=None)

    # A cross-sectional or macro signal can be finite for a current-universe
    # ticker before that security was listed. Such rows are not tradeable and
    # must not enter either quantile. This uses only same-date availability;
    # a missing later return for a position that was actually formed remains
    # a hard data-integrity failure below.
    eligible_signal = signal.where(adjclose.notna())
    raw_weights = quantile_weights(eligible_signal, quantile=quantile, min_names=min_names)
    if holding_days > 1:
        raw_weights = raw_weights.rolling(holding_days, min_periods=1).mean()
    # fillna(0): the book is flat before the first formed position, so the
    # first live day's entry is charged full turnover (NaN diffs would charge 0).
    held = raw_weights.shift(2).fillna(0.0)

    evaluation_mask = pd.Series(True, index=returns.index)
    if evaluation_start is not None:
        evaluation_mask = returns.index.to_series(index=returns.index) >= evaluation_start
    evaluated_held = held.loc[evaluation_mask]
    evaluated_returns = returns.loc[evaluation_mask]
    missing_held = (evaluated_held != 0) & evaluated_returns.isna()
    if missing_held.any().any():
        first_date, first_ticker = missing_held.stack().loc[lambda values: values].index[0]
        raise ValueError(
            f"held asset {first_ticker} has no return on {first_date}: "
            "repair delisting/missing-price data instead of treating it as zero"
        )
    gross = (evaluated_held * evaluated_returns).sum(axis=1)
    turnover = held.diff().abs().sum(axis=1)
    # The sample is a finite trade horizon. Liquidate any position remaining
    # after its final earned return and charge that closing turnover on the
    # same row; do not invent an extra return observation.
    terminal_exit = float(held.iloc[-1].abs().sum())
    if terminal_exit:
        turnover.iloc[-1] += terminal_exit
    turnover = turnover.loc[evaluation_mask]
    costs = turnover * (cost_bps / 10_000.0)
    net = gross - costs

    # Drop only the leading formation period. Once the strategy first trades,
    # internal and trailing flat calendar days are genuine zero-return
    # observations; deleting them would turn sparse timing signals into an
    # event-time series and then wrongly annualize it by sqrt(252).
    active = (evaluated_held.abs().sum(axis=1) > 0) | (turnover.fillna(0.0) > 0)
    # An explicit research horizon makes leading flat sessions genuine
    # in-sample observations, not an unknown formation period. Preserve them
    # so sparse/event strategies use the registered calendar and ledger n_obs
    # describes that exact horizon.
    if active.any() and evaluation_start is None:
        first = int(np.flatnonzero(active.to_numpy())[0])
        gross, net, turnover = gross.iloc[first:], net.iloc[first:], turnover.iloc[first:]
    elif not active.any():
        gross, net, turnover = gross.iloc[:0], net.iloc[:0], turnover.iloc[:0]

    ledger_net = net
    if ledger_start is not None:
        ledger_net = ledger_net[ledger_net.index >= ledger_start]
    if ledger_end is not None:
        ledger_net = ledger_net[ledger_net.index <= ledger_end]

    result = BacktestResult(
        returns_gross=gross,
        returns_net=net,
        turnover=turnover,
        weights=held,
        cost_bps=cost_bps,
        meta={
            "candidate_id": candidate_id,
            "split": split,
            "quantile": quantile,
            "holding_days": holding_days,
            "min_names": min_names,
            "start_date": str(evaluation_start.date()) if evaluation_start is not None else None,
            "ledger_start_date": str(ledger_start.date()) if ledger_start is not None else None,
            "ledger_end_date": str(ledger_end.date()) if ledger_end is not None else None,
            "cost_bps": cost_bps,
            "n_obs": len(net),
            "ledger_n_obs": len(ledger_net),
            "signal_sha256": _signal_sha256(signal),
        },
    )
    _append_ledger(
        {
            "timestamp": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
            "candidate_id": candidate_id,
            "params_hash": _params_hash(result.meta),
            "split": split,
            "sr_net": round(sharpe_ratio(ledger_net), 6) if len(ledger_net) > 20 else "nan",
            "n_obs": len(ledger_net),
        }
    )
    return result


def run_backtest(
    signal: pd.DataFrame,
    adjclose: pd.DataFrame,
    candidate_id: str,
    split: str,
    cost_bps: float = EQUITY_BPS,
    quantile: float = 0.1,
    holding_days: int = 1,
    min_names: int = 20,
    start_date: str | pd.Timestamp | None = None,
    ledger_start_date: str | pd.Timestamp | None = None,
    ledger_end_date: str | pd.Timestamp | None = None,
) -> BacktestResult:
    """Ledger both successful and failed identified evaluation attempts."""
    try:
        return _run_backtest(
            signal,
            adjclose,
            candidate_id,
            split,
            cost_bps=cost_bps,
            quantile=quantile,
            holding_days=holding_days,
            min_names=min_names,
            start_date=start_date,
            ledger_start_date=ledger_start_date,
            ledger_end_date=ledger_end_date,
        )
    except Exception as exc:
        if (
            isinstance(candidate_id, str)
            and candidate_id.strip()
            and isinstance(split, str)
            and split.strip()
        ):
            try:
                identity = (
                    _signal_sha256(signal)
                    if isinstance(signal, pd.DataFrame)
                    else type(signal).__name__
                )
                record_failed_trial(candidate_id, split, identity, exc)
                exc._edgelab_trial_recorded = True
            except Exception:
                pass  # Preserve the evaluation error if its audit sink is unavailable.
        raise


def ledger_trial_stats(
    prefix_bytes: int | None = None, *, payload: bytes | None = None
) -> tuple[int, float]:
    """Return trial count/variance from a file or an exact sealed snapshot."""
    if payload is not None and prefix_bytes is not None:
        raise RuntimeError("provide either a ledger snapshot or a byte prefix, not both")
    if payload is None and not LEDGER_PATH.exists():
        return 0, float("nan")
    try:
        if payload is None:
            payload = LEDGER_PATH.read_bytes()
        if prefix_bytes is not None:
            if (
                not isinstance(prefix_bytes, int)
                or isinstance(prefix_bytes, bool)
                or not 0 <= prefix_bytes <= len(payload)
            ):
                raise RuntimeError("invalid trials-ledger byte prefix")
            payload = payload[:prefix_bytes]
        df = pd.read_csv(io.BytesIO(payload))
    except (OSError, pd.errors.ParserError) as exc:
        raise RuntimeError(f"trials ledger is unreadable: {exc}") from exc
    if not set(LEDGER_COLUMNS) <= set(df.columns):
        raise RuntimeError("trials ledger is missing required columns")
    srs = pd.to_numeric(df["sr_net"], errors="coerce").dropna()
    return len(df), float(srs.var(ddof=1)) if len(srs) > 1 else float("nan")
