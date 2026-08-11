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
        return stamps.dt.tz_localize(
            tzinfo, nonexistent="NaT", ambiguous="NaT"
        ).dt.tz_convert("UTC")

    def normalize(stamp):
        if pd.isna(stamp):
            return pd.NaT
        parsed = pd.Timestamp(stamp)
        if parsed.tzinfo is None:
            localized = parsed.tz_localize(
                tzinfo, nonexistent="NaT", ambiguous="NaT"
            )
            return pd.NaT if pd.isna(localized) else pd.Timestamp(localized).tz_convert("UTC")
        return parsed.tz_convert("UTC")

    normalized = stamps.map(normalize)
    return pd.to_datetime(normalized, errors="coerce", utc=True)


def load_ohlcv(path: Path | str, tz: str = "UTC") -> tuple[pd.DataFrame, OhlcvReport]:
    try:
        frame = pd.read_csv(path)
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise MappingError(f"Could not read OHLCV CSV {path}: {exc}") from exc
    frame.columns = [str(c).strip() for c in frame.columns]
    columns = _detect_columns(list(frame.columns))
    report = OhlcvReport(rows_read=len(frame), columns_used=columns)

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
        | ~np.isfinite(price_values).all(axis=1)
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
    temporary = out_path.with_name(f".{out_path.name}.{secrets.token_hex(6)}.tmp")
    try:
        export = frame.copy()
        export["datetime"] = pd.DatetimeIndex(export["datetime"]).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        export.to_csv(temporary, index=False)
        temporary.replace(out_path)
    except Exception as exc:
        raise MappingError(f"Could not write normalized OHLCV {out_path}: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return out_path
