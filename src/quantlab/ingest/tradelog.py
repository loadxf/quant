"""Trade-log CSV -> canonical TradeLog.

Handles the messy realities of exported trade logs: `$`/comma currency
formatting, parenthesized negatives, naive timestamps in a local timezone,
missing optional columns, and rows that can't be parsed (dropped with a
reason, reported — never silently).
"""

from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from quantlab.errors import MappingError
from quantlab.ingest.mapping import ColumnMapping, autodetect_mapping
from quantlab.schema.trade import Side, Trade, TradeLog

_CURRENCY_RE = re.compile(r"[$€£,\s]")


@dataclass
class IngestReport:
    rows_read: int = 0
    trades_loaded: int = 0
    dropped: list[tuple[int, str]] = field(default_factory=list)  # (row index, reason)
    mapping_used: dict[str, str] = field(default_factory=dict)
    autodetected: bool = False

    @property
    def rows_dropped(self) -> int:
        return len(self.dropped)


def parse_money(value: object) -> float:
    """Parse '$1,234.56', '(500)', unicode-minus '\u221212', ' 3.5 ' etc. into a float."""
    if isinstance(value, int | float):
        if isinstance(value, float) and math.isnan(value):
            raise ValueError("missing money value (NaN)")
        return float(value)
    text = str(value).strip().replace("\u2212", "-")  # unicode minus
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = _CURRENCY_RE.sub("", text)
    if text in ("", "-", "--"):
        raise ValueError(f"empty money value {value!r}")
    number = float(text)
    return -abs(number) if negative else number


def _parse_time(value: object, mapping: ColumnMapping, tzinfo: ZoneInfo) -> dt.datetime:
    if mapping.datetime_format:
        stamp = pd.to_datetime(str(value), format=mapping.datetime_format)
    else:
        stamp = pd.to_datetime(str(value))
    if pd.isna(stamp):
        raise ValueError(f"unparseable timestamp {value!r}")
    py = stamp.to_pydatetime()
    if py.tzinfo is None:
        py = py.replace(tzinfo=tzinfo)
    return py.astimezone(dt.UTC)


def _parse_side(value: object, mapping: ColumnMapping) -> Side:
    assert mapping.side is not None
    text = str(value).strip().lower()
    if text in mapping.side.long_values:
        return Side.LONG
    if text in mapping.side.short_values:
        return Side.SHORT
    raise ValueError(f"unrecognized side value {value!r}")


def load_trade_log(
    path: Path | str,
    mapping: ColumnMapping | None = None,
    account_currency: str = "USD",
) -> tuple[TradeLog, IngestReport]:
    path = Path(path)
    frame = pd.read_csv(path, dtype=str, skipinitialspace=True)
    frame.columns = [str(c).strip() for c in frame.columns]
    headers = list(frame.columns)

    report = IngestReport(rows_read=len(frame))
    if mapping is None:
        mapping = autodetect_mapping(headers)
        report.autodetected = True
    mapping.validate_against(headers)
    report.mapping_used = {
        f: (getattr(mapping, f).column if f == "side" and mapping.side else getattr(mapping, f))
        for f in ("entry_time", "exit_time", "symbol", "side", "quantity", "pnl", "mae", "mfe")
        if getattr(mapping, f) is not None
    }

    assert mapping.exit_time is not None and mapping.pnl is not None  # validate_against ran
    tzinfo = ZoneInfo(mapping.tz)
    trades: list[Trade] = []
    for index, row in frame.iterrows():
        try:
            exit_time = _parse_time(row[mapping.exit_time], mapping, tzinfo)
            entry_time = (
                _parse_time(row[mapping.entry_time], mapping, tzinfo)
                if mapping.entry_time
                else exit_time
            )
            mae = (
                parse_money(row[mapping.mae])
                if mapping.mae and pd.notna(row[mapping.mae])
                else None
            )
            mfe = (
                parse_money(row[mapping.mfe])
                if mapping.mfe and pd.notna(row[mapping.mfe])
                else None
            )
            trades.append(
                Trade(
                    entry_time=entry_time,
                    exit_time=exit_time,
                    symbol=(
                        str(row[mapping.symbol]).strip()
                        if mapping.symbol
                        else mapping.default_symbol
                    ),
                    side=_parse_side(row[mapping.side.column], mapping)
                    if mapping.side
                    else Side.LONG,
                    quantity=parse_money(row[mapping.quantity]) if mapping.quantity else 1.0,
                    pnl=parse_money(row[mapping.pnl]),
                    entry_price=(
                        parse_money(row[mapping.entry_price])
                        if mapping.entry_price and pd.notna(row[mapping.entry_price])
                        else None
                    ),
                    exit_price=(
                        parse_money(row[mapping.exit_price])
                        if mapping.exit_price and pd.notna(row[mapping.exit_price])
                        else None
                    ),
                    fees=(
                        parse_money(row[mapping.fees])
                        if mapping.fees and pd.notna(row[mapping.fees])
                        else 0.0
                    ),
                    # Excursions: clamp tiny sign noise (some platforms export MAE as +)
                    mae=-abs(mae) if mae is not None else None,
                    mfe=abs(mfe) if mfe is not None else None,
                )
            )
        except Exception as exc:
            report.dropped.append((int(str(index)), f"{type(exc).__name__}: {exc}"))

    if not trades:
        raise MappingError(
            f"No trades could be parsed from {path} "
            f"({report.rows_dropped}/{report.rows_read} rows dropped; "
            f"first reason: {report.dropped[0][1] if report.dropped else 'file empty'})"
        )
    report.trades_loaded = len(trades)
    return TradeLog(trades=trades, account_currency=account_currency, source="csv"), report
