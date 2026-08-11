"""User OHLCV CSV -> normalized canonical bars.

Canonical format (what the Object Store demo strategy reads):
    datetime,open,high,low,close,volume
with UTC ISO-8601 timestamps, strictly increasing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


def _find_companion(
    frame: pd.DataFrame, exclude: str, synonyms: tuple[str, ...]
) -> str | None:
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


def load_ohlcv(path: Path | str, tz: str = "UTC") -> tuple[pd.DataFrame, OhlcvReport]:
    try:
        frame = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        raise MappingError(f"{path}: file is empty") from None
    except pd.errors.ParserError as exc:
        raise MappingError(f"{path}: not a readable CSV ({exc})") from None
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
    except (KeyError, ValueError, ZoneInfoNotFoundError) as exc:
        raise MappingError(f"Unknown timezone {tz!r}: {exc}") from None
    out = pd.DataFrame()
    try:
        stamps = pd.to_datetime(frame[columns["datetime"]], errors="coerce")
    except (ValueError, TypeError):
        # pandas 3: "Mixed timezones detected" raises even with
        # errors="coerce" for DST-spanning ISO-offset exports; the offsets
        # are explicit so parsing straight to UTC is lossless.
        stamps = pd.to_datetime(frame[columns["datetime"]], errors="coerce", utc=True)
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
        # DST fall-back folds: bars in the repeated span are real data, and
        # a blanket ambiguous=True would stamp both passes with the same
        # UTC instant (the dedupe below silently deletes the second pass).
        # Label every fold daylight time, then relabel the SECOND
        # occurrence of each duplicated wall time as standard time — that
        # pass is the replay, and taking the ambiguous=False localization
        # (rather than adding a constant hour) yields the exact fold width
        # for any zone (Lord Howe folds 30 minutes, Troll 2 hours). This
        # is per-fold inference: lone fold stamps simply keep the DST
        # label (bar preserved), where pandas' ambiguous="infer" raises
        # for the whole column. Only the UTC instants are published, so
        # the offset label itself is moot. Nonexistent spring-forward
        # stamps shift forward instead of deleting an hour per transition.
        localized = stamps.dt.tz_localize(tzinfo, nonexistent="shift_forward", ambiguous=True)
        probe = stamps.dt.tz_localize(tzinfo, nonexistent="shift_forward", ambiguous="NaT")
        second_pass = probe.isna() & stamps.notna() & stamps.duplicated(keep="first")
        if second_pass.any():
            standard = stamps.dt.tz_localize(tzinfo, nonexistent="shift_forward", ambiguous=False)
            localized = localized.where(~second_pass, standard)
        stamps = localized
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
    export.to_csv(prepared(out_path), index=False)
    return out_path
