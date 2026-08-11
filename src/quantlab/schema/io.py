"""Parquet round-trip for TradeLog.

Trades are stored as a parquet table; TradeLog-level metadata
(account currency, source) rides in the parquet schema metadata,
so a single file is fully self-describing.
"""

from __future__ import annotations

import json
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
    pq.write_table(table.replace_schema_metadata(meta), str(prepared(path)))


def read_trade_log(path: Path | str) -> TradeLog:
    path = Path(path)
    if not path.exists():
        raise QuantLabError(f"Trade log not found: {path}")
    try:
        table = pq.read_table(str(path))
    except (pa.ArrowInvalid, pa.ArrowIOError, OSError) as exc:
        # The classic mistake is pointing a command at the original CSV.
        raise QuantLabError(
            f"{path} is not a quantlab trades parquet ({exc}) — "
            "run `quant ingest trades` on your CSV first"
        ) from None
    meta_raw = (table.schema.metadata or {}).get(_META_KEY)
    meta = json.loads(meta_raw.decode()) if meta_raw else {}
    try:
        version = int(meta.get("schema_version", SCHEMA_VERSION))
    except (TypeError, ValueError) as exc:
        raise QuantLabError(
            f"{path} carries an unreadable trade-log schema_version {meta.get('schema_version')!r}"
        ) from exc
    if version > SCHEMA_VERSION:
        raise QuantLabError(
            f"{path} was written with trade-log schema v{version}; this build "
            f"reads up to v{SCHEMA_VERSION} — upgrade loadx-quant to read it."
        )
    frame = table.to_pandas()

    trades = []
    for row in frame.itertuples(index=False):
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
    return TradeLog(
        trades=trades,
        account_currency=meta.get("account_currency", "USD"),
        source=meta.get("source", "csv"),
    )
