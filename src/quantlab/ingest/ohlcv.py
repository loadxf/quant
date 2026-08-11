"""User OHLCV CSV -> normalized canonical bars.

Canonical format (what the Object Store demo strategy reads):
    datetime,open,high,low,close,volume
with UTC ISO-8601 timestamps, strictly increasing.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd

from quantlab.errors import MappingError
from quantlab.output import prepared

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


_TIME_ONLY_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?\s*([AaPp][Mm])?$")
_DATE_ONLY_RE = re.compile(
    r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$|^\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}$|^\d{8}$"
)
_TIME_HEADER_SYNONYMS = ("time", "bartime", "timeofday")
_DATE_HEADER_SYNONYMS = ("date", "tradedate", "tradeday", "day")


def _detect_columns(headers: list[str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for h in headers:  # first-wins: duplicate-normalizing headers must not shadow
        normalized.setdefault(_normalize_header(h), h)
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


def _find_companion(frame: pd.DataFrame, exclude: str, synonyms: tuple[str, ...]) -> str | None:
    normalized: dict[str, str] = {}
    for h in frame.columns:
        normalized.setdefault(_normalize_header(str(h)), str(h))
    for syn in synonyms:
        candidate = normalized.get(syn)
        if candidate is not None and candidate != exclude:
            return candidate
    return None


def _combine(frame: pd.DataFrame, date_col: str, time_col: str) -> None:
    # Empty time cells become midnight explicitly: "" would leave a
    # date-only string in a mixed-format column, which pandas coerces to
    # NaT (row silently dropped); "nan" would poison the stamp outright.
    # Bare HH:MM values gain ":00" so the whole column parses under ONE
    # format alongside the injected midnights (pandas 3 infers a single
    # format and NaTs the stragglers).
    times = frame[time_col].fillna("").astype(str).str.strip().replace("", "00:00:00")
    times = times.str.replace(r"^(\d{1,2}:\d{2})$", r"\1:00", regex=True)
    frame["__combined_datetime"] = frame[date_col].astype(str).str.strip() + " " + times


def _combine_split_date_time(frame: pd.DataFrame, columns: dict[str, str]) -> str | None:
    """Split Date/Time exports: a bare Date column with a separate Time
    column would parse every bar to midnight and the timestamp dedupe
    below would then silently keep one bar per day. Combine them; a
    time-only column without any date companion cannot be loaded.
    Returns a display name for the report when a combine happened."""
    col = columns["datetime"]
    sample = frame[col].dropna().astype(str).head(20)
    if sample.empty:
        return None
    if all(_DATE_ONLY_RE.match(v.strip()) for v in sample):
        time_col = _find_companion(frame, col, _TIME_HEADER_SYNONYMS)
        if time_col is None:
            return None
        # Only combine when the companion actually holds time-of-day
        # values — a vestigial empty "Time" column must not poison every
        # stamp with " nan" suffixes.
        time_sample = frame[time_col].dropna().astype(str).head(20)
        if time_sample.empty or not all(_TIME_ONLY_RE.match(v.strip()) for v in time_sample):
            return None
        _combine(frame, col, time_col)
        columns["datetime"] = "__combined_datetime"
        return f"{col} + {time_col}"
    if all(_TIME_ONLY_RE.match(v.strip()) for v in sample):
        date_col = _find_companion(frame, col, _DATE_HEADER_SYNONYMS)
        if date_col is None:
            raise MappingError(
                f"Column {col!r} holds time-of-day values only and no Date column "
                "was found — bars cannot be dated. Provide a combined datetime "
                "column or a Date column."
            )
        _combine(frame, date_col, col)
        columns["datetime"] = "__combined_datetime"
        return f"{date_col} + {col}"
    return None


def _normalize_stamps(values: pd.Series, tzinfo: ZoneInfo) -> pd.Series:
    """Parse naive local times and explicit-offset instants without mixing them."""
    try:
        stamps = pd.to_datetime(values, errors="coerce")
    except (TypeError, ValueError):
        # pandas 3 rejects a vector containing valid summer/winter offsets.
        # The rare heterogeneous batch is parsed scalar-wise, then unified.
        stamps = values.map(lambda value: pd.to_datetime(value, errors="coerce"))

    if isinstance(stamps.dtype, pd.DatetimeTZDtype):
        return stamps.dt.tz_convert("UTC")
    if isinstance(stamps.dtype, np.dtype) and stamps.dtype.kind == "M":
        return stamps.dt.tz_localize(tzinfo, nonexistent="NaT", ambiguous="NaT").dt.tz_convert(
            "UTC"
        )

    def normalize(stamp):
        if pd.isna(stamp):
            return pd.NaT
        parsed = pd.Timestamp(stamp)
        if parsed.tzinfo is None:
            localized = parsed.tz_localize(tzinfo, nonexistent="NaT", ambiguous="NaT")
            return pd.NaT if pd.isna(localized) else pd.Timestamp(localized).tz_convert("UTC")
        return parsed.tz_convert("UTC")

    normalized = stamps.map(normalize)
    return pd.to_datetime(normalized, errors="coerce", utc=True)


def load_ohlcv(path: Path | str, tz: str = "UTC") -> tuple[pd.DataFrame, OhlcvReport]:
    try:
        frame = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        raise MappingError(f"{path}: file is empty") from None
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise MappingError(f"Could not read OHLCV CSV {path}: {exc}") from exc
    frame.columns = [str(c).strip() for c in frame.columns]
    columns = _detect_columns(list(frame.columns))
    # Compact YYYYMMDD integer dates would otherwise parse as epoch
    # NANOSECONDS (every bar lands on 1970-01-01 and dedupes to one row).
    raw_dates = frame[columns["datetime"]]
    if raw_dates.dtype.kind in "iu" and raw_dates.dropna().between(19000101, 21001231).all():
        frame[columns["datetime"]] = raw_dates.astype("Int64").astype(str)
    combined_display = _combine_split_date_time(frame, columns)
    # The report names user columns, never the internal scratch column.
    columns_used = dict(columns)
    if combined_display is not None:
        columns_used["datetime"] = combined_display
    report = OhlcvReport(rows_read=len(frame), columns_used=columns_used)

    try:
        tzinfo = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, TypeError) as exc:
        raise MappingError(f"Unknown OHLCV timezone {tz!r}") from exc
    out = pd.DataFrame()
    out["datetime"] = _normalize_stamps(frame[columns["datetime"]], tzinfo)
    for name in ("open", "high", "low", "close"):
        out[name] = pd.to_numeric(frame[columns[name]], errors="coerce")
    out["volume"] = (
        pd.to_numeric(frame[columns["volume"]], errors="coerce") if "volume" in columns else 0.0
    )

    bad_time = out["datetime"].isna()
    price_values = out[["open", "high", "low", "close"]]
    bad_price = (
        price_values.isna().any(axis=1)
        | price_values.isin([np.inf, -np.inf]).any(axis=1)  # NaN already via isna
        | (price_values <= 0).any(axis=1)
    )
    bad_volume = out["volume"].isna() | ~np.isfinite(out["volume"]) | (out["volume"] < 0)
    bad_ohlc = (out["high"] < out[["open", "close"]].max(axis=1)) | (
        out["low"] > out[["open", "close"]].min(axis=1)
    )
    for index in out.index[bad_time]:
        report.dropped.append(
            (int(index), "unparseable, ambiguous, or nonexistent local timestamp")
        )
    for index in out.index[~bad_time & bad_price]:
        report.dropped.append((int(index), "price must be numeric, finite, and positive"))
    for index in out.index[~bad_time & ~bad_price & bad_volume]:
        report.dropped.append((int(index), "invalid volume (must be finite and non-negative)"))
    for index in out.index[~bad_time & ~bad_price & ~bad_volume & bad_ohlc]:
        report.dropped.append((int(index), "inconsistent OHLC (high/low violate open/close)"))

    out = out[~(bad_time | bad_price | bad_volume | bad_ohlc)].sort_values(
        "datetime", kind="stable"
    )
    duplicate_rows = out.duplicated(subset="datetime", keep=False)
    value_columns = ["open", "high", "low", "close", "volume"]
    for stamp, group in out.loc[duplicate_rows].groupby("datetime", sort=False):
        if len(group[value_columns].drop_duplicates()) > 1:
            raise MappingError(
                f"Conflicting OHLCV bars in {path} at {stamp.isoformat()}; "
                "duplicate timestamps must have identical values"
            )
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
    out_path = prepared(out_path)  # missing parent dirs must not fail the write
    temporary = out_path.with_name(f".{out_path.name}.{secrets.token_hex(6)}.tmp")
    try:
        export = frame.copy()
        export["datetime"] = pd.DatetimeIndex(export["datetime"]).strftime("%Y-%m-%dT%H:%M:%SZ")
        export.to_csv(temporary, index=False)
        temporary.replace(out_path)
    except Exception as exc:
        raise MappingError(f"Could not write normalized OHLCV {out_path}: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return out_path
