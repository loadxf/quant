"""Schema-aware event loading for Q-LIR market data (round-4 redesign).

Canonical frame (one file = one dataset/schema/symbol/date):

    ts_event   datetime64[ns, UTC]  matching-engine event time (primary clock)
    ts_recv    datetime64[ns, UTC]  gateway receive time (diagnostics only)
    sequence   int64                venue sequence number (ordering tiebreak)
    action     'A'|'C'|'M'|'R'|'T'|'F'|'N'  book action; trades/tbbo are all 'T'
    price      float64              record price (> 0 for trades; NaN allowed
                                    on non-trade book actions)
    size       int64                record size (> 0 for trades)
    side       'B' | 'A' | 'N'      for action='T': aggressor (Bid=buy);
                                    for book actions: the book side updated —
                                    NEVER a flow signal (Databento defines
                                    `side` per action)
    symbol     str                  requested continuous symbol (e.g. ES.v.0)
    raw_symbol str                  resolved dated contract (e.g. ESH2)
    instrument_id int64             the PRIMARY identity (continuous symbols
                                    resolve to instrument_id; raw symbols come
                                    from a SECOND resolution step)

tbbo / mbp-1 additionally carry the top-of-book:

    bid_px, ask_px  float64  (NaN = empty book side)
    bid_sz, ask_sz  int64

Ordering: (ts_event, sequence, ts_recv) — Sol round 2 §4.2. Signed flow
uses ONLY action='T' rows; treating book updates as trades is the
round-4 failure mode this module exists to prevent.

Sources: `.parquet` (decoded-record fixtures) and `.dbn`/`.dbn.zst` via
databento. DBN decoding REQUIRES an instrument_id -> raw_symbol map
(from the acquisition's second symbology step); without one it fails
closed rather than silently mislabeling the contract.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from qlir import QlirError

SCHEMAS = ("trades", "tbbo", "mbp-1")
CORE_COLUMNS = (
    "ts_event",
    "ts_recv",
    "sequence",
    "action",
    "price",
    "size",
    "side",
    "symbol",
    "raw_symbol",
    "instrument_id",
)
BBO_COLUMNS = ("bid_px", "ask_px", "bid_sz", "ask_sz")
VALID_SIDES = {"B", "A", "N"}
VALID_ACTIONS = {"A", "C", "M", "R", "T", "F", "N"}
SIDE_SIGN = {"B": 1, "A": -1, "N": 0}


def schema_columns(schema: str) -> tuple[str, ...]:
    if schema not in SCHEMAS:
        raise QlirError(f"unsupported schema {schema!r} (want one of {SCHEMAS})")
    return CORE_COLUMNS if schema == "trades" else (*CORE_COLUMNS, *BBO_COLUMNS)


def trades_only(df: pd.DataFrame) -> pd.DataFrame:
    """The action='T' rows — the ONLY rows signed flow may touch."""
    return df[df["action"] == "T"]


def aggressor_sign(df: pd.DataFrame) -> pd.Series:
    """Aggressor sign for TRADE rows: B(id)=+1, A(sk)=-1, N(one)=0.
    Refuses frames containing book actions — filter with trades_only()
    first; `side` on a book update is not an aggressor."""
    if (df["action"] != "T").any():
        raise QlirError(
            "aggressor_sign received non-trade actions — side on book updates "
            "is the book side, not an aggressor; filter with trades_only()"
        )
    return df["side"].map(SIDE_SIGN).astype("int64")


def unknown_side_fraction(df: pd.DataFrame) -> float:
    """Unknown-side VOLUME fraction over TRADE rows — a mandatory
    expected-impact control; windows are never dropped for it."""
    trades = trades_only(df)
    total = int(trades["size"].sum())
    if total == 0:
        return 0.0
    return float(trades.loc[trades["side"] == "N", "size"].sum() / total)


def signed_flow(df: pd.DataFrame) -> float:
    """Sum of sign * sqrt(size) over TRADE rows only (Q-LIR Q variable)."""
    trades = trades_only(df)
    signs = aggressor_sign(trades).to_numpy(dtype="float64")
    return float(np.sum(signs * np.sqrt(trades["size"].to_numpy(dtype="float64"))))


def best_bid_ask(df: pd.DataFrame) -> pd.DataFrame:
    """The executable top-of-book series (tbbo/mbp-1 frames)."""
    missing = [column for column in BBO_COLUMNS if column not in df.columns]
    if missing:
        raise QlirError(f"frame lacks BBO columns {missing} — trades schema cannot price Layer B")
    return df.loc[:, ["ts_event", *BBO_COLUMNS]]


def validate_events(df: pd.DataFrame, schema: str, source: str = "<frame>") -> pd.DataFrame:
    columns = schema_columns(schema)
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise QlirError(f"{source}: missing canonical columns {missing} for schema {schema!r}")
    out = df.loc[:, list(columns)].copy()
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
    bad_actions = set(out["action"].unique()) - VALID_ACTIONS
    if bad_actions:
        raise QlirError(f"{source}: invalid action values {sorted(bad_actions)}")
    if schema in ("trades", "tbbo") and (out["action"] != "T").any():
        raise QlirError(f"{source}: schema {schema!r} must contain only action='T' records")
    bad_sides = set(out["side"].unique()) - VALID_SIDES
    if bad_sides:
        raise QlirError(f"{source}: invalid side values {sorted(bad_sides)} (want B/A/N)")
    trade_rows = out["action"] == "T"
    if not (out.loc[trade_rows, "price"] > 0).all():
        raise QlirError(f"{source}: non-positive trade prices present")
    if not (out.loc[trade_rows, "size"] > 0).all():
        raise QlirError(f"{source}: non-positive trade sizes present")
    if (out["size"] < 0).any():
        raise QlirError(f"{source}: negative sizes present")
    if schema != "trades":
        for column in ("bid_sz", "ask_sz"):
            if (out[column].fillna(0) < 0).any():
                raise QlirError(f"{source}: negative {column} present")
        out["bid_sz"] = out["bid_sz"].fillna(0).astype("int64")
        out["ask_sz"] = out["ask_sz"].fillna(0).astype("int64")
        for column in ("bid_px", "ask_px"):
            out[column] = out[column].astype("float64")
    out["sequence"] = out["sequence"].astype("int64")
    out["size"] = out["size"].astype("int64")
    out["instrument_id"] = out["instrument_id"].astype("int64")
    out["price"] = out["price"].astype("float64")
    # Deterministic research ordering: ts_event, then sequence, then ts_recv.
    out = out.sort_values(["ts_event", "sequence", "ts_recv"], kind="mergesort", ignore_index=True)
    return out


_DBN_SCHEMA_NAMES = {"trades": "trades", "tbbo": "tbbo", "mbp-1": "mbp-1"}


def _load_dbn(path: Path, schema: str, id_to_raw: dict[int, str] | None) -> pd.DataFrame:
    try:
        from databento import DBNStore
    except ImportError:
        raise QlirError(
            f"{path} is a DBN file but the databento package is not installed — "
            "pip install databento"
        ) from None
    store = DBNStore.from_file(path)
    meta_schema = str(getattr(store.metadata, "schema", None) or "")
    if meta_schema and meta_schema.replace("_", "-") != _DBN_SCHEMA_NAMES[schema]:
        raise QlirError(
            f"{path}: file metadata declares schema {meta_schema!r}, caller asked "
            f"for {schema!r} — refusing to misinterpret records"
        )
    frame = store.to_df().reset_index()
    rename = {
        "bid_px_00": "bid_px",
        "ask_px_00": "ask_px",
        "bid_sz_00": "bid_sz",
        "ask_sz_00": "ask_sz",
    }
    frame = frame.rename(columns=rename)
    requested = list(getattr(store.metadata, "symbols", []) or [])
    frame["symbol"] = requested[0] if len(requested) == 1 else "<multi>"
    # instrument_id is the PRIMARY identity; the dated raw contract comes
    # from the acquisition's second symbology step. Fail closed rather
    # than mislabel (round 4: "losing the actual raw-contract mapping").
    if id_to_raw is None:
        raise QlirError(
            f"{path}: DBN decoding needs the instrument_id -> raw_symbol map "
            "from the acquisition manifest (second resolution step); refusing "
            "to guess the dated contract"
        )
    ids = frame["instrument_id"].astype("int64")
    unmapped = sorted(set(ids.unique()) - set(id_to_raw))
    if unmapped:
        raise QlirError(f"{path}: no raw_symbol mapping for instrument_id(s) {unmapped}")
    frame["raw_symbol"] = ids.map(id_to_raw)
    return validate_events(frame, schema, source=str(path))


def load_events(
    path: str | Path, schema: str, id_to_raw: dict[int, str] | None = None
) -> pd.DataFrame:
    """Load one canonical event file (.parquet fixture or .dbn[.zst])."""
    path = Path(path)
    if schema not in SCHEMAS:
        raise QlirError(f"unsupported schema {schema!r} (want one of {SCHEMAS})")
    if not path.exists():
        raise QlirError(f"no such event file: {path}")
    suffixes = "".join(path.suffixes)
    if suffixes.endswith(".parquet"):
        return validate_events(pd.read_parquet(path), schema, source=str(path))
    if suffixes.endswith((".dbn", ".dbn.zst")):
        return _load_dbn(path, schema, id_to_raw)
    raise QlirError(f"unsupported event-file type: {path.name}")
