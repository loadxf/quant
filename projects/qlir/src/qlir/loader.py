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

Ordering: (ts_event, sequence, ts_recv) — Sol round 2 §4.2. Precise
behavior contract (round-5 wording correction): `signed_flow` and
`unknown_side_fraction` FILTER to action='T' rows via `trades_only()`
and accept mixed frames; `aggressor_sign` RAISES on frames containing
book actions. Treating book updates as trades is the failure mode this
module exists to prevent — by filtering in the flow aggregates and by
refusal in the per-row sign primitive.

Sources: `.parquet` (decoded-record fixtures) and `.dbn`/`.dbn.zst` via
databento. DBN decoding REQUIRES a VALIDATED SINGLE-DATE
instrument_id -> raw_symbol map (produced by
`ContractMap.flat_map_for_date` from the date-aware two-step
composition — ids can remap across dates, so a flat map is only valid
for one date); without one it fails closed rather than mislabel the
contract. `allow_unresolved=True` exists solely for the acquisition
probe pass that derives the file's event date before binding; it labels
raw_symbol '<unresolved>' and must never feed research code.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from qlir import QlirError
from qlir.spec import AcquisitionSpec

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
    # Instrument ids are only guaranteed unique per publisher (and per
    # day for some publishers) — publisher_id is identity, not metadata
    # (round 6, finding 2).
    "publisher_id",
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
    out["publisher_id"] = out["publisher_id"].astype("int64")
    if (out["publisher_id"] <= 0).any():
        raise QlirError(f"{source}: non-positive publisher_id present")
    out["price"] = out["price"].astype("float64")
    # Deterministic research ordering: ts_event, then sequence, then ts_recv.
    out = out.sort_values(["ts_event", "sequence", "ts_recv"], kind="mergesort", ignore_index=True)
    return out


_DBN_SCHEMA_NAMES = {"trades": "trades", "tbbo": "tbbo", "mbp-1": "mbp-1"}


def _validate_dbn_metadata(store: object, spec: AcquisitionSpec, path: Path) -> list[str]:
    """Bind the self-describing DBN metadata to the acquisition spec
    (round 6, finding 2: an XNAS.ITCH/NQ file decoded cleanly through a
    GLBX/ES contract map). Returns the file's requested symbols."""
    metadata = store.metadata  # type: ignore[attr-defined]
    meta_dataset = str(getattr(metadata, "dataset", "") or "")
    if meta_dataset != spec.dataset:
        raise QlirError(
            f"{path}: DBN metadata dataset {meta_dataset!r} does not match the "
            f"acquisition spec dataset {spec.dataset!r} — refusing to bind "
            "unrelated data"
        )
    meta_schema = str(getattr(metadata, "schema", None) or "")
    if meta_schema and meta_schema.replace("_", "-") != _DBN_SCHEMA_NAMES[spec.schema]:
        raise QlirError(
            f"{path}: file metadata declares schema {meta_schema!r}, the spec says "
            f"{spec.schema!r} — refusing to misinterpret records"
        )
    for attr, expected in (("stype_in", spec.stype_in), ("stype_out", spec.stype_out)):
        got = getattr(metadata, attr, None)
        if got is None:
            continue
        got_name = str(got).split(".")[-1].lower()  # SType enum or plain string
        if got_name.replace("_", "") != expected.lower().replace("_", ""):
            raise QlirError(
                f"{path}: DBN metadata {attr}={got!r} does not match the spec ({expected!r})"
            )
    symbols = [str(s) for s in (getattr(metadata, "symbols", []) or [])]
    if not symbols:
        raise QlirError(f"{path}: DBN metadata carries no requested symbols")
    unknown = sorted(set(symbols) - set(spec.symbols))
    if unknown:
        raise QlirError(
            f"{path}: DBN metadata symbols {unknown} are not in the acquisition "
            f"spec symbols {sorted(spec.symbols)}"
        )
    meta_start = getattr(metadata, "start", None)
    meta_end = getattr(metadata, "end", None)
    spec_start_ns = int(spec.start_utc.timestamp() * 1_000_000_000)
    spec_end_ns = int(spec.end_utc.timestamp() * 1_000_000_000)
    if meta_start is not None and int(meta_start) < spec_start_ns:
        raise QlirError(f"{path}: DBN metadata start precedes the spec range")
    if meta_end is not None and int(meta_end) > spec_end_ns:
        raise QlirError(f"{path}: DBN metadata end exceeds the spec range")
    return symbols


def _load_dbn(
    path: Path,
    spec: AcquisitionSpec,
    id_to_raw: dict[int, str] | None,
    allow_unresolved: bool = False,
) -> pd.DataFrame:
    try:
        from databento import DBNStore
    except ImportError:
        raise QlirError(
            f"{path} is a DBN file but the databento package is not installed — "
            "pip install databento"
        ) from None
    try:
        store = DBNStore.from_file(path)
        file_symbols = _validate_dbn_metadata(store, spec, path)
        frame = store.to_df().reset_index()
    except QlirError:
        raise
    except Exception as exc:
        # Round-7 finding 1: bytes that cannot decode cannot be counted,
        # so they cannot be attested — surface every decode failure as a
        # uniform refusal.
        raise QlirError(f"{path}: not decodable as DBN ({type(exc).__name__}: {exc})") from exc
    # Round-7 finding 5: metadata bounds alone do not bind the RECORDS.
    # Databento's historical range filters on ts_recv when available
    # (ts_event otherwise); ts_recv is canonical here, so every record
    # must sit inside the metadata's half-open [start, end).
    meta_start = getattr(store.metadata, "start", None)
    meta_end = getattr(store.metadata, "end", None)
    if meta_start is not None and meta_end is not None and len(frame):
        ts_ns = pd.to_datetime(frame["ts_recv"], utc=True).astype("int64")
        outside = int(((ts_ns < int(meta_start)) | (ts_ns >= int(meta_end))).sum())
        if outside:
            raise QlirError(
                f"{path}: {outside} record(s) fall outside the DBN metadata's "
                f"declared half-open range on ts_recv — the bytes do not match "
                "their own self-description"
            )
    rename = {
        "bid_px_00": "bid_px",
        "ask_px_00": "ask_px",
        "bid_sz_00": "bid_sz",
        "ask_sz_00": "ask_sz",
    }
    frame = frame.rename(columns=rename)
    if len(file_symbols) == 1:
        frame["symbol"] = file_symbols[0]
    else:
        # '<multi>' is not an analyzable identity: multi-symbol files may
        # only pass through the acquisition path, which re-binds the
        # requested symbol PER RECORD via ContractMap.symbol_for.
        if not allow_unresolved:
            raise QlirError(
                f"{path}: multi-symbol DBN file needs per-record symbol binding — "
                "load it through qlir.acquire.load_acquired_file"
            )
        frame["symbol"] = "<unbound>"
    # instrument_id is the PRIMARY identity; the dated raw contract comes
    # from the acquisition's second symbology step. Fail closed rather
    # than mislabel (round 4: "losing the actual raw-contract mapping").
    if id_to_raw is None:
        if not allow_unresolved:
            raise QlirError(
                f"{path}: DBN decoding needs a validated single-date "
                "instrument_id -> raw_symbol map (ContractMap.flat_map_for_date); "
                "refusing to guess the dated contract"
            )
        frame["raw_symbol"] = "<unresolved>"
        return validate_events(frame, spec.schema, source=str(path))
    ids = frame["instrument_id"].astype("int64")
    unmapped = sorted(set(ids.unique()) - set(id_to_raw))
    if unmapped:
        raise QlirError(f"{path}: no raw_symbol mapping for instrument_id(s) {unmapped}")
    frame["raw_symbol"] = ids.map(id_to_raw)
    return validate_events(frame, spec.schema, source=str(path))


def load_events(
    path: str | Path,
    schema: str | None = None,
    id_to_raw: dict[int, str] | None = None,
    allow_unresolved: bool = False,
    spec: AcquisitionSpec | None = None,
) -> pd.DataFrame:
    """Load one canonical event file.

    `.parquet` fixtures need `schema` only. `.dbn`/`.dbn.zst` REQUIRE a
    full AcquisitionSpec — DBN is self-describing, and its dataset,
    schema, stypes, symbols, and interval must bind to the spec before a
    single record is interpreted (round 6, finding 2)."""
    path = Path(path)
    if spec is not None:
        schema = spec.schema
    if schema not in SCHEMAS:
        raise QlirError(f"unsupported schema {schema!r} (want one of {SCHEMAS})")
    if not path.exists():
        raise QlirError(f"no such event file: {path}")
    suffixes = "".join(path.suffixes)
    if suffixes.endswith(".parquet"):
        return validate_events(pd.read_parquet(path), schema, source=str(path))
    if suffixes.endswith((".dbn", ".dbn.zst")):
        if spec is None:
            raise QlirError(
                f"{path}: DBN loading requires an AcquisitionSpec so the file's "
                "self-described metadata can be bound to the acquisition"
            )
        return _load_dbn(path, spec, id_to_raw, allow_unresolved=allow_unresolved)
    raise QlirError(f"unsupported event-file type: {path.name}")
