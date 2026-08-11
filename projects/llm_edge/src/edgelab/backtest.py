"""Vectorized daily cross-sectional long-short backtest engine.

Timing convention (protocol.md section 5): a signal value at date t may use
data up to the close of t. The position is formed at the close of t+1 (one-day
implementation lag) and earns the return over t+1 -> t+2. Therefore weights
derived from the signal at t are applied to simple returns at t+2, i.e.
``weights.shift(2)`` against day-t returns.

LEDGER: every call to ``run_backtest`` appends one row to
candidates/trials_ledger.csv (the append-only multiple-testing ledger). This
happens inside the engine so no evaluation can escape the Deflated Sharpe
Ratio's trial count N. Do not add bypass flags.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import LEDGER_PATH
from .stats import sharpe_ratio

LEDGER_COLUMNS = ["timestamp", "candidate_id", "params_hash", "split", "sr_net", "n_obs"]


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
    ranks = signal.rank(axis=1, pct=True)
    valid = signal.notna().sum(axis=1)
    long_mask = ranks.ge(1.0 - quantile)
    short_mask = ranks.le(quantile)
    n_long = long_mask.sum(axis=1).replace(0, np.nan)
    n_short = short_mask.sum(axis=1).replace(0, np.nan)
    weights = long_mask.astype(float).div(n_long, axis=0) - short_mask.astype(float).div(
        n_short, axis=0
    )
    weights.loc[valid < min_names] = 0.0
    return weights.fillna(0.0)


def _params_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[
        :16
    ]


def _append_ledger(row: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    header = not LEDGER_PATH.exists()
    with LEDGER_PATH.open("a") as fh:
        if header:
            fh.write(",".join(LEDGER_COLUMNS) + "\n")
        fh.write(",".join(str(row[c]) for c in LEDGER_COLUMNS) + "\n")


def run_backtest(
    signal: pd.DataFrame,
    adjclose: pd.DataFrame,
    candidate_id: str,
    split: str,
    cost_bps: float = 10.0,
    quantile: float = 0.1,
    holding_days: int = 1,
    min_names: int = 20,
    ledger: bool = True,
) -> BacktestResult:
    """Backtest a cross-sectional signal panel against an adjclose panel.

    ``signal`` and ``adjclose`` share the (date x ticker) shape. Signal at t
    must only use information available at close t; the engine applies the
    t+2 alignment so even a "perfect foresight of tomorrow" signal cannot
    profit from leakage (enforced by tests/test_no_lookahead.py).
    """
    signal = signal.reindex(index=adjclose.index, columns=adjclose.columns)
    returns = adjclose.pct_change(fill_method=None)

    raw_weights = quantile_weights(signal, quantile=quantile, min_names=min_names)
    if holding_days > 1:
        raw_weights = raw_weights.rolling(holding_days, min_periods=1).mean()
    # fillna(0): the book is flat before the first formed position, so the
    # first live day's entry is charged full turnover (NaN diffs would charge 0).
    held = raw_weights.shift(2).fillna(0.0)

    gross = (held * returns).sum(axis=1)
    turnover = held.diff().abs().sum(axis=1)
    costs = turnover * (cost_bps / 10_000.0)
    net = gross - costs

    # Held OR traded: the day the book goes flat carries the liquidation
    # turnover on a held==0 row — dropping it would charge the re-entry
    # cost but never the exit cost, silently inflating sharpe_net for any
    # signal with intermittent coverage.
    live = (held.abs().sum(axis=1) > 0) | (turnover > 0)
    gross, net, turnover = gross[live], net[live], turnover[live]

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
            "cost_bps": cost_bps,
            "n_obs": len(net),
        },
    )
    if ledger:
        _append_ledger(
            {
                "timestamp": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
                "candidate_id": candidate_id,
                "params_hash": _params_hash(result.meta),
                "split": split,
                "sr_net": round(result.sharpe_net, 6) if len(net) > 20 else "nan",
                "n_obs": len(net),
            }
        )
    return result


def ledger_trial_stats() -> tuple[int, float]:
    """(N, Var of net SRs) across every trial ever run — feeds the DSR."""
    if not LEDGER_PATH.exists():
        return 0, float("nan")
    df = pd.read_csv(LEDGER_PATH)
    srs = pd.to_numeric(df["sr_net"], errors="coerce").dropna()
    return len(df), float(srs.var(ddof=1)) if len(srs) > 1 else float("nan")
