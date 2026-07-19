"""User OHLCV CSV -> normalized canonical bars.

Canonical format (what the Object Store demo strategy reads):
    datetime,open,high,low,close,volume
with UTC ISO-8601 timestamps, strictly increasing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from quantlab.errors import MappingError

# pandas 3 raises ValueError from ambiguous="infer" failures; pandas 2.x
# (allowed by our >=2.1 pin) raises pytz.AmbiguousTimeError, which is NOT
# a ValueError subclass — and pytz may be absent from a pandas-3 install.
try:
    from pytz.exceptions import (  # type: ignore[import-untyped]
        AmbiguousTimeError as _PytzAmbiguousTimeError,
    )

    _AMBIGUOUS_ERRORS: tuple[type[Exception], ...] = (ValueError, _PytzAmbiguousTimeError)
except ImportError:  # pragma: no cover - depends on installed pandas stack
    _AMBIGUOUS_ERRORS = (ValueError,)

_SYNONYMS = {
    "datetime": ("datetime", "date", "time", "timestamp", "dt", "bartime"),
    "open": ("open", "o"),
    "high": ("high", "h"),
    "low": ("low", "l"),
    "close": ("close", "c", "last", "settle"),
    "volume": ("volume", "vol", "v", "totalvolume"),
}


@dataclass
class OhlcvReport:
    rows_read: int = 0
    bars_kept: int = 0
    dropped: list[tuple[int, str]] = field(default_factory=list)
    duplicate_timestamps: int = 0
    weekday_gaps: int = 0  # missing weekdays inside the covered span
    columns_used: dict[str, str] = field(default_factory=dict)


def _normalize_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def _detect_columns(headers: list[str]) -> dict[str, str]:
    normalized = {_normalize_header(h): h for h in headers}
    found: dict[str, str] = {}
    for field_name, synonyms in _SYNONYMS.items():
        for candidate in synonyms:
            if candidate in normalized:
                found[field_name] = normalized[candidate]
                break
    missing = [f for f in ("datetime", "open", "high", "low", "close") if f not in found]
    if missing:
        raise MappingError(f"Could not detect OHLCV columns {missing} from headers {headers}")
    return found


def load_ohlcv(path: Path | str, tz: str = "UTC") -> tuple[pd.DataFrame, OhlcvReport]:
    frame = pd.read_csv(path)
    frame.columns = [str(c).strip() for c in frame.columns]
    columns = _detect_columns(list(frame.columns))
    report = OhlcvReport(rows_read=len(frame), columns_used=columns)

    tzinfo = ZoneInfo(tz)
    out = pd.DataFrame()
    stamps = pd.to_datetime(frame[columns["datetime"]], errors="coerce")
    valid = stamps.dropna()
    if valid.is_monotonic_decreasing and not valid.is_monotonic_increasing:
        # Newest-first export (common broker format): DST inference below
        # needs chronological order — with reversed input it does NOT fail,
        # it silently assigns the fall-back hour's two passes swapped UTC
        # offsets. Reverse while keeping the original index so drop-report
        # row numbers still match the file.
        frame = frame.iloc[::-1]
        stamps = stamps.iloc[::-1]
    if getattr(stamps.dt, "tz", None) is None:
        # DST edges: fall-back-hour bars are real data — "infer" uses bar
        # ordering to label the first pass daylight time and the second
        # standard time (a blanket ambiguous=True stamps both passes with
        # the same UTC offset, and the dedupe below would silently delete
        # the whole second hour). Nonexistent spring-forward stamps shift
        # forward instead of deleting an hour every transition.
        try:
            stamps = stamps.dt.tz_localize(tzinfo, nonexistent="shift_forward", ambiguous="infer")
        except _AMBIGUOUS_ERRORS:
            # Ordering gives no answer — usually a feed that records the
            # folded hour ONCE (nothing to infer from). Fall back to
            # labeling those stamps daylight time: it keeps every bar (an
            # ambiguous="NaT" fallback would drop the fold-hour bars of
            # EVERY transition in the file over one bad one), at the cost
            # of a 1-hour offset error on any bar that was really the
            # standard-time pass.
            stamps = stamps.dt.tz_localize(tzinfo, nonexistent="shift_forward", ambiguous=True)
    out["datetime"] = stamps.dt.tz_convert("UTC")
    for name in ("open", "high", "low", "close"):
        out[name] = pd.to_numeric(frame[columns[name]], errors="coerce")
    out["volume"] = (
        pd.to_numeric(frame[columns["volume"]], errors="coerce") if "volume" in columns else 0.0
    )

    bad_time = out["datetime"].isna()
    bad_price = out[["open", "high", "low", "close"]].isna().any(axis=1)
    bad_ohlc = (out["high"] < out[["open", "close"]].max(axis=1)) | (
        out["low"] > out[["open", "close"]].min(axis=1)
    )
    for index in out.index[bad_time]:
        report.dropped.append((int(index), "unparseable timestamp"))
    for index in out.index[~bad_time & bad_price]:
        report.dropped.append((int(index), "non-numeric price"))
    for index in out.index[~bad_time & ~bad_price & bad_ohlc]:
        report.dropped.append((int(index), "inconsistent OHLC (high/low violate open/close)"))

    out = out[~(bad_time | bad_price | bad_ohlc)].sort_values("datetime", kind="stable")
    before = len(out)
    out = out.drop_duplicates(subset="datetime", keep="first")
    report.duplicate_timestamps = before - len(out)

    if out.empty:
        raise MappingError(f"No valid OHLCV bars in {path}")

    days = pd.DatetimeIndex(out["datetime"]).normalize().unique()
    span = pd.bdate_range(days.min(), days.max())
    report.weekday_gaps = len(set(span) - set(days))
    report.bars_kept = len(out)
    return out.reset_index(drop=True), report


def write_normalized(frame: pd.DataFrame, out_path: Path | str) -> Path:
    out_path = Path(out_path)
    export = frame.copy()
    export["datetime"] = pd.DatetimeIndex(export["datetime"]).strftime("%Y-%m-%dT%H:%M:%SZ")
    export.to_csv(out_path, index=False)
    return out_path
