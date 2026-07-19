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
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from quantlab.errors import MappingError
from quantlab.ingest.mapping import ColumnMapping, autodetect_mapping
from quantlab.schema.trade import Side, Trade, TradeLog

_CURRENCY_RE = re.compile(r"[$€£,\s]")
_TIME_ONLY_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?\s*([AaPp][Mm])?$")
_DATE_HEADER_SYNONYMS = ("date", "tradedate", "tradeday", "day")


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
    """Parse '$1,234.56', '(500)', '$(500.00)', unicode-minus '\u221212', etc.

    Currency symbols/commas are stripped BEFORE parenthesized-negative
    detection so accounting exports that put the symbol outside the parens
    ('$(500.00)') parse as negatives instead of being dropped."""
    if isinstance(value, int | float):
        if isinstance(value, float) and math.isnan(value):
            raise ValueError("missing money value (NaN)")
        return float(value)
    text = str(value).strip().replace("\u2212", "-")  # unicode minus
    text = _CURRENCY_RE.sub("", text)
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    if text in ("", "-", "--"):
        raise ValueError(f"empty money value {value!r}")
    number = float(text)
    return -abs(number) if negative else number


def _attach_tz(stamp: Any, tzinfo: ZoneInfo) -> dt.datetime:
    if pd.isna(stamp):
        raise ValueError("unparseable timestamp")
    py = pd.Timestamp(stamp).to_pydatetime()
    if py.tzinfo is None:
        py = py.replace(tzinfo=tzinfo)
    return py.astimezone(dt.UTC)


def _combine_split_date_time(frame: pd.DataFrame, column: str) -> str:
    """Handle exports with separate Date and Time columns.

    If the mapped timestamp column holds time-of-day only ('09:31:00'),
    pandas would silently fill in TODAY's date for every trade. Look for a
    companion date column and combine; fail loudly when there is none.
    """
    sample = frame[column].dropna().astype(str).head(20)
    if sample.empty or not all(_TIME_ONLY_RE.match(v.strip()) for v in sample):
        return column
    normalized = {re.sub(r"[^a-z0-9]", "", str(h).lower()): str(h) for h in frame.columns}
    for synonym in _DATE_HEADER_SYNONYMS:
        date_col = normalized.get(synonym)
        if date_col is not None and date_col != column:
            combined = f"__combined_{column}"
            frame[combined] = (
                frame[date_col].astype(str).str.strip()
                + " "
                + frame[column].astype(str).str.strip()
            )
            return combined
    raise MappingError(
        f"Column {column!r} contains time-of-day values only and no companion "
        "date column was found — pandas would assign today's date to every "
        "trade. Provide a combined datetime column or a Date column."
    )


def _parse_time_column(frame: pd.DataFrame, column: str, mapping: ColumnMapping) -> pd.Series:
    """Vectorized parse (one format inference per column, ~100x faster than
    per-row) with a per-row fallback so mixed-format columns still load.

    pandas infers ONE format from the first value and coerces every
    non-matching row to NaT — a broker export mixing '09:31:00' and
    '09:32:00.123' (fractional seconds only when nonzero) would silently
    drop the fractional rows. The rare stragglers re-parse row-by-row;
    rows that still fail stay NaT and are dropped with a reason.
    """
    combined = _combine_split_date_time(frame, column)
    # A user-declared format describes the ORIGINAL (time-only) column; it
    # cannot match once a Date column has been merged in front.
    fmt = mapping.datetime_format if combined == column else None
    parsed = pd.to_datetime(frame[combined], format=fmt, errors="coerce")
    missing = parsed.isna() & frame[combined].notna()
    for idx in frame.index[missing]:
        # dtype=str at read time, and the mask excludes nulls
        parsed.at[idx] = pd.to_datetime(str(frame.at[idx, combined]), format=fmt, errors="coerce")
    return parsed


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
    exit_stamps = _parse_time_column(frame, mapping.exit_time, mapping)
    entry_stamps = (
        _parse_time_column(frame, mapping.entry_time, mapping) if mapping.entry_time else None
    )
    trades: list[Trade] = []
    for position, (_, row) in enumerate(frame.iterrows()):
        try:
            exit_time = _attach_tz(exit_stamps.iloc[position], tzinfo)
            entry_time = (
                _attach_tz(entry_stamps.iloc[position], tzinfo)
                if entry_stamps is not None
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
            report.dropped.append((position, f"{type(exc).__name__}: {exc}"))

    if not trades:
        raise MappingError(
            f"No trades could be parsed from {path} "
            f"({report.rows_dropped}/{report.rows_read} rows dropped; "
            f"first reason: {report.dropped[0][1] if report.dropped else 'file empty'})"
        )
    report.trades_loaded = len(trades)
    return TradeLog(trades=trades, account_currency=account_currency, source="csv"), report
