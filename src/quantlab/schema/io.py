"""Parquet round-trip for TradeLog.

Trades are stored as a parquet table; TradeLog-level metadata
(account currency, source) rides in the parquet schema metadata,
so a single file is fully self-describing.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from quantlab.errors import QuantLabError
from quantlab.output import prepared
from quantlab.schema.trade import Side, Trade, TradeLog

_META_KEY = b"quantlab.tradelog"
SCHEMA_VERSION = 1


def write_trade_log(log: TradeLog, path: Path | str) -> None:
    if not isinstance(log, TradeLog):
        raise QuantLabError("write_trade_log requires a TradeLog")
    path = prepared(path)  # missing parent dirs must not fail the write
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        frame = log.to_frame()
        table = pa.Table.from_pandas(frame, preserve_index=False)
        meta = dict(table.schema.metadata or {})
        meta[_META_KEY] = json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "account_currency": log.account_currency,
                "source": log.source,
            }
        ).encode()
        pq.write_table(table.replace_schema_metadata(meta), str(temporary))
        temporary.replace(path)
    except Exception as exc:
        raise QuantLabError(f"Could not write trade log {path}: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def read_trade_log(path: Path | str) -> TradeLog:
    path = Path(path)
    if not path.exists():
        raise QuantLabError(f"Trade log not found: {path}")
    try:
        table = pq.read_table(str(path))
    except Exception as exc:
        # The classic mistake is pointing a command at the original CSV.
        raise QuantLabError(
            f"Could not read trade log {path}: {exc} — if this is a CSV, "
            "run `quant ingest trades` on it first"
        ) from exc
    meta_raw = (table.schema.metadata or {}).get(_META_KEY)
    try:
        meta = json.loads(meta_raw.decode()) if meta_raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QuantLabError(f"Trade log {path} has invalid metadata") from exc
    if not isinstance(meta, dict):
        raise QuantLabError(f"Trade log {path} metadata must be a JSON object")
    raw_version = meta.get("schema_version", SCHEMA_VERSION)
    if type(raw_version) is not int or raw_version < 1:
        raise QuantLabError(
            f"{path} carries an unreadable trade-log schema_version {raw_version!r}"
        )
    version = raw_version
    if version > SCHEMA_VERSION:
        raise QuantLabError(
            f"{path} was written with trade-log schema v{version}; this build "
            f"reads up to v{SCHEMA_VERSION} — upgrade loadx-quant to read it."
        )
    frame = table.to_pandas()
    required = {"entry_time", "exit_time", "symbol", "side", "quantity", "pnl"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise QuantLabError(f"Trade log {path} is missing required columns: {missing}")
    for name, default in {
        "entry_price": None,
        "exit_price": None,
        "fees": 0.0,
        "mae": None,
        "mfe": None,
    }.items():
        if name not in frame:
            frame[name] = default

    trades = []
    for position, row in enumerate(frame.itertuples(index=False)):
        try:
            trades.append(
                Trade(
                    entry_time=pd.Timestamp(row.entry_time).to_pydatetime(),
                    exit_time=pd.Timestamp(row.exit_time).to_pydatetime(),
                    symbol=str(row.symbol),
                    side=Side(row.side),
                    quantity=float(row.quantity),
                    pnl=float(row.pnl),
                    entry_price=None if pd.isna(row.entry_price) else float(row.entry_price),
                    exit_price=None if pd.isna(row.exit_price) else float(row.exit_price),
                    fees=0.0 if pd.isna(row.fees) else float(row.fees),
                    mae=None if pd.isna(row.mae) else float(row.mae),
                    mfe=None if pd.isna(row.mfe) else float(row.mfe),
                )
            )
        except Exception as exc:
            raise QuantLabError(
                f"Trade log {path} has an invalid row at position {position}: {exc}"
            ) from exc
    return TradeLog(
        trades=trades,
        account_currency=meta.get("account_currency", "USD"),
        source=meta.get("source", "csv"),
    )
