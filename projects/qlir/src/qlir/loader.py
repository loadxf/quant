"""Event loading and canonical schema for Q-LIR market data.

Canonical trade-event frame (one file = one dataset/schema/symbol/date):

    ts_event   datetime64[ns, UTC]  matching-engine event time (primary clock)
    ts_recv    datetime64[ns, UTC]  gateway receive time (diagnostics only)
    sequence   int64                venue sequence number (ordering tiebreak)
    price      float64              trade price (> 0)
    size       int64                trade size (> 0)
    side       'B' | 'A' | 'N'      aggressor: Bid=buy, Ask=sell, None=unknown
    symbol     str                  requested continuous symbol (e.g. ES.v.0)
    raw_symbol str                  resolved contract (e.g. ESH1)
    instrument_id int64

Ordering: rows sort by (ts_event, sequence, ts_recv) — Sol round 2 §4.2.
Aggressor sign: B=+1, A=-1, N=0; unknown-side volume contributes to total
volume and its per-window fraction is a mandatory control variable.

Sources: `.parquet` (decoded records — also the synthetic-fixture format,
since databento's Python bindings expose no DBN encoder) and
`.dbn`/`.dbn.zst` via the databento package when installed. The DBN
decode is a thin wrapper over DBNStore and is exercised by a test that
skips until a real file exists — it cannot be synthesized locally.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from qlir import QlirError

CANONICAL_COLUMNS = (
    "ts_event",
    "ts_recv",
    "sequence",
    "price",
    "size",
    "side",
    "symbol",
    "raw_symbol",
    "instrument_id",
)
VALID_SIDES = {"B", "A", "N"}
SIDE_SIGN = {"B": 1, "A": -1, "N": 0}


def aggressor_sign(side: pd.Series) -> pd.Series:
    """B(id)=buy aggressor=+1, A(sk)=sell aggressor=-1, N(one)=0."""
    return side.map(SIDE_SIGN).astype("int64")


def unknown_side_fraction(df: pd.DataFrame) -> float:
    """Unknown-side VOLUME fraction — a mandatory expected-impact control;
    windows are never dropped for an inconvenient value."""
    total = int(df["size"].sum())
    if total == 0:
        return 0.0
    return float(df.loc[df["side"] == "N", "size"].sum() / total)


def validate_events(df: pd.DataFrame, source: str = "<frame>") -> pd.DataFrame:
    missing = [column for column in CANONICAL_COLUMNS if column not in df.columns]
    if missing:
        raise QlirError(f"{source}: missing canonical columns {missing}")
    out = df.loc[:, list(CANONICAL_COLUMNS)].copy()
    for column in ("ts_event", "ts_recv"):
        series = out[column]
        if not isinstance(series.dtype, pd.DatetimeTZDtype):
            try:
                series = pd.to_datetime(series, utc=True)
            except (ValueError, TypeError) as exc:
                raise QlirError(f"{source}: {column} is not tz-aware UTC datetime") from exc
        elif str(series.dt.tz) != "UTC":
            series = series.dt.tz_convert("UTC")
        out[column] = series
    bad_sides = set(out["side"].unique()) - VALID_SIDES
    if bad_sides:
        raise QlirError(f"{source}: invalid side values {sorted(bad_sides)} (want B/A/N)")
    if not (out["price"] > 0).all():
        raise QlirError(f"{source}: non-positive prices present")
    if not (out["size"] > 0).all():
        raise QlirError(f"{source}: non-positive sizes present")
    out["sequence"] = out["sequence"].astype("int64")
    out["size"] = out["size"].astype("int64")
    out["instrument_id"] = out["instrument_id"].astype("int64")
    out["price"] = out["price"].astype("float64")
    # Deterministic research ordering: ts_event, then sequence, then ts_recv.
    out = out.sort_values(["ts_event", "sequence", "ts_recv"], kind="mergesort", ignore_index=True)
    return out


def _load_dbn(path: Path) -> pd.DataFrame:
    try:
        from databento import DBNStore
    except ImportError:
        raise QlirError(
            f"{path} is a DBN file but the databento package is not installed — "
            "pip install databento"
        ) from None
    store = DBNStore.from_file(path)
    frame = store.to_df().reset_index()
    renames = {"ts_recv": "ts_recv", "ts_event": "ts_event"}
    frame = frame.rename(columns=renames)
    if "symbol" in frame.columns and "raw_symbol" not in frame.columns:
        # DBNStore maps the raw contract into `symbol`; the requested
        # continuous symbol comes from metadata.
        frame["raw_symbol"] = frame["symbol"]
        requested = list(getattr(store.metadata, "symbols", []) or ["<unknown>"])
        frame["symbol"] = requested[0] if len(requested) == 1 else "<multi>"
    return validate_events(frame, source=str(path))


def load_events(path: str | Path) -> pd.DataFrame:
    """Load one canonical event file (.parquet fixture or .dbn[.zst])."""
    path = Path(path)
    if not path.exists():
        raise QlirError(f"no such event file: {path}")
    suffixes = "".join(path.suffixes)
    if suffixes.endswith(".parquet"):
        return validate_events(pd.read_parquet(path), source=str(path))
    if suffixes.endswith((".dbn", ".dbn.zst")):
        return _load_dbn(path)
    raise QlirError(f"unsupported event-file type: {path.name}")


def signed_flow(df: pd.DataFrame) -> float:
    """Sum of sign * sqrt(size) over the frame (Q-LIR Q variable)."""
    signs = aggressor_sign(df["side"]).to_numpy(dtype="float64")
    return float(np.sum(signs * np.sqrt(df["size"].to_numpy(dtype="float64"))))
