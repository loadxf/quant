"""User-data ingestion: trade-log CSVs and OHLCV CSVs -> canonical schemas."""

from quantlab.ingest.mapping import ColumnMapping, autodetect_mapping
from quantlab.ingest.tradelog import IngestReport, load_trade_log

__all__ = ["ColumnMapping", "IngestReport", "autodetect_mapping", "load_trade_log"]
