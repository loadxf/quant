"""Yahoo Finance daily-bar downloader with local parquet cache and hash manifest.

Yahoo quirk discovered during setup: ``range=max&interval=1d`` silently returns
MONTHLY bars for long histories. Explicit ``period1``/``period2`` epoch params
return true daily bars, so that is the only request form used here.

Holdout discipline: ``load_panel`` truncates at VALIDATION_END by default.
Passing ``end`` beyond that raises unless ``_holdout_token`` is supplied — the
token is only ever created by ``holdout_gate.py``, which enforces spec
pre-registration before any holdout data can be seen.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import numbers
import re
import secrets
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from . import CACHE_DIR, DATA_DIR, VALIDATION_END
from .jsonutil import atomic_write_text, dumps

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
FIELDS = ["open", "high", "low", "close", "adjclose", "volume"]
MANIFEST_PATH = DATA_DIR / "manifest.json"
_TICKER_RE = re.compile(r"^[A-Za-z0-9.^=_-]+$")


class FieldBundle(dict[str, object]):
    """Panel mapping carrying the exact input snapshots used to build it."""

    def __init__(
        self,
        values: dict[str, object],
        *,
        input_identity: dict[str, str],
        universe: dict[str, object] | None = None,
    ) -> None:
        super().__init__(values)
        self.input_identity = dict(input_identity)
        self.universe = universe


def _session_publish_after(payload: dict, session_date) -> datetime | None:
    """Return Yahoo's regular-session close plus publication lag for a date."""
    try:
        raw_end = payload["meta"]["currentTradingPeriod"]["regular"]["end"]
        if isinstance(raw_end, bool) or not math.isfinite(float(raw_end)):
            return None
        close = datetime.fromtimestamp(float(raw_end), UTC).astimezone(ZoneInfo("America/New_York"))
    except (KeyError, TypeError, ValueError, OSError, OverflowError):
        return None
    return close + timedelta(minutes=15) if close.date() == session_date else None


def _validate_ticker(ticker: str) -> str:
    if not isinstance(ticker, str) or not _TICKER_RE.fullmatch(ticker):
        raise ValueError(f"invalid ticker {ticker!r}")
    return ticker


def load_universe_snapshot(path: Path | None = None) -> tuple[dict, str]:
    """Load, validate, and hash one exact universe byte snapshot."""
    universe_path = DATA_DIR / "universe.json" if path is None else path
    try:
        payload = universe_path.read_bytes()
        universe = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid data universe {universe_path}: {exc}") from exc
    if not isinstance(universe, dict):
        raise RuntimeError("invalid data universe: expected a JSON object")
    for group in ("equities", "etfs"):
        tickers = universe.get(group)
        if not isinstance(tickers, list) or not tickers:
            raise RuntimeError(f"invalid data universe: {group} must be a non-empty list")
        if len(tickers) != len(set(tickers)):
            raise RuntimeError(f"invalid data universe: {group} contains duplicates")
        try:
            for ticker in tickers:
                _validate_ticker(ticker)
        except ValueError as exc:
            raise RuntimeError(f"invalid data universe: {exc}") from exc
    if set(universe["equities"]) & set(universe["etfs"]):
        raise RuntimeError("invalid data universe: equities and etfs must be disjoint")
    sectors = universe.get("sectors")
    if not isinstance(sectors, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in sectors.items()
    ):
        raise RuntimeError("invalid data universe: sectors must map ticker strings to strings")
    if set(sectors) != set(universe["equities"]):
        raise RuntimeError("invalid data universe: sectors must cover exactly the equities")
    return universe, hashlib.sha256(payload).hexdigest()


def load_universe(path: Path | None = None) -> dict:
    """Load and validate the complete declared research universe."""
    universe, _ = load_universe_snapshot(path)
    return universe


def _validate_daily_frame(df: pd.DataFrame, source: str) -> None:
    """Validate the complete cached/fetched daily-bar contract."""
    missing = set(FIELDS) - set(df.columns)
    if missing:
        raise ValueError(f"{source} is missing required columns: {sorted(missing)}")
    if df.empty:
        raise ValueError(f"{source} has no daily rows")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(f"{source} index must be a DatetimeIndex")
    if df.index.hasnans or df.index.has_duplicates:
        raise ValueError(f"{source} dates must be present and unique")
    if not df.index.is_monotonic_increasing:
        raise ValueError(f"{source} dates are not increasing")
    if df.index.tz is not None or not df.index.equals(df.index.normalize()):
        raise ValueError(f"{source} dates must be timezone-naive session dates")

    try:
        numeric = df[FIELDS].to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source} contains non-numeric OHLCV values") from exc
    if np.isinf(numeric).any():
        raise ValueError(f"{source} contains infinite OHLCV values")
    prices = df[["open", "high", "low", "close", "adjclose"]]
    if (prices.stack().astype(float) <= 0).any():
        raise ValueError(f"{source} contains non-positive observed prices")
    if df["close"].isna().any():
        raise ValueError(f"{source} contains missing closes")
    if (df["volume"].dropna().astype(float) < 0).any():
        raise ValueError(f"{source} contains negative volume")

    upper_members = df[["open", "low", "close"]].max(axis=1, skipna=True)
    lower_members = df[["open", "high", "close"]].min(axis=1, skipna=True)
    bad_high = df["high"].notna() & (df["high"] < upper_members)
    bad_low = df["low"].notna() & (df["low"] > lower_members)
    if bad_high.any() or bad_low.any():
        raise ValueError(f"{source} contains an invalid OHLC envelope")


def _quarantine_invalid_envelopes(df: pd.DataFrame) -> int:
    """Replace ambiguous Yahoo O/H/L rows with missing optional values."""
    upper_members = df[["open", "low", "close"]].max(axis=1, skipna=True)
    lower_members = df[["open", "high", "close"]].min(axis=1, skipna=True)
    invalid = (df["high"].notna() & (df["high"] < upper_members)) | (
        df["low"].notna() & (df["low"] > lower_members)
    )
    count = int(invalid.sum())
    if count:
        # Yahoo occasionally has one internally inconsistent raw OHLC row.
        # Which of O/H/L is wrong is unknowable, so retain close/adjusted
        # close/volume and mark all three optional price cells unavailable.
        df.loc[invalid, ["open", "high", "low"]] = np.nan
    return count


def fetch_daily(ticker: str, retries: int = 3, throttle: float = 0.5) -> pd.DataFrame:
    """Fetch full daily history for one ticker. Returns OHLC+adjclose+volume."""
    _validate_ticker(ticker)
    if (
        not isinstance(retries, int)
        or isinstance(retries, bool)
        or retries < 1
        or not isinstance(throttle, numbers.Real)
        or isinstance(throttle, bool)
        or not math.isfinite(float(throttle))
        or throttle < 0
    ):
        raise ValueError("retries must be >= 1 and throttle finite/non-negative")
    params = {
        "period1": 0,
        "period2": 9_999_999_999,
        "interval": "1d",
        "events": "div,split",
    }
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(
                CHART_URL.format(ticker=ticker), params=params, headers=HEADERS, timeout=30
            )
            resp.raise_for_status()
            payload = resp.json()["chart"]["result"][0]
            ts = payload["timestamp"]
            quote = payload["indicators"]["quote"][0]
            adj = payload["indicators"]["adjclose"][0]["adjclose"]
            df = pd.DataFrame(
                {
                    "open": quote["open"],
                    "high": quote["high"],
                    "low": quote["low"],
                    "close": quote["close"],
                    "adjclose": adj,
                    "volume": quote["volume"],
                },
                index=pd.to_datetime(ts, unit="s", utc=True)
                .tz_convert("America/New_York")
                .normalize()
                .tz_localize(None),
            )
            df.index.name = "date"
            # Duplicate Yahoo sessions are an input-integrity failure; never
            # resolve conflicting observations by response order.
            df = df.dropna(subset=["close"])
            # Yahoo can publish today's still-forming daily candle. Do not
            # persist it before the NYSE close plus a small publication lag.
            now_ny = datetime.now(UTC).astimezone(ZoneInfo("America/New_York"))
            if not df.empty and df.index[-1].date() >= now_ny.date():
                publish_after = _session_publish_after(payload, df.index[-1].date())
                # Without trustworthy session metadata, keep the conservative
                # invariant: never persist a candle dated today.
                if publish_after is None or now_ny < publish_after:
                    df = df.iloc[:-1]
            if df.empty:
                raise ValueError("Yahoo returned no daily rows")
            quarantined = _quarantine_invalid_envelopes(df)
            df.attrs["quarantined_ohlc_rows"] = quarantined
            _validate_daily_frame(df, "Yahoo response")
            time.sleep(throttle)
            return df
        except Exception as err:
            last_err = err
            time.sleep(2**attempt)
    raise RuntimeError(f"failed to fetch {ticker}: {last_err}")


def _manifest_snapshot() -> tuple[dict, str]:
    if MANIFEST_PATH.exists():
        try:
            payload = MANIFEST_PATH.read_bytes()
            manifest = json.loads(payload)
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"invalid cache manifest {MANIFEST_PATH}: {exc}") from exc
        if not isinstance(manifest, dict):
            raise RuntimeError(f"cache manifest {MANIFEST_PATH} must be a JSON object")
        return manifest, hashlib.sha256(payload).hexdigest()
    return {}, hashlib.sha256(b"{}").hexdigest()


def _manifest() -> dict:
    manifest, _ = _manifest_snapshot()
    return manifest


def _validated_history_revision(entry: object, ticker: str) -> dict | None:
    if not isinstance(entry, dict) or "upstream_history_revision" not in entry:
        return None
    revision = entry["upstream_history_revision"]
    required = {
        "accepted_on",
        "prior_end",
        "prior_rows",
        "prior_sha256",
        "prior_start",
        "reason",
    }
    if not isinstance(revision, dict) or not required <= set(revision):
        raise RuntimeError(f"cached {ticker} has an invalid upstream history revision")
    string_fields = required - {"prior_rows"}
    if any(not isinstance(revision[key], str) or not revision[key] for key in string_fields):
        raise RuntimeError(f"cached {ticker} has an invalid upstream history revision")
    if (
        not isinstance(revision["prior_rows"], int)
        or isinstance(revision["prior_rows"], bool)
        or revision["prior_rows"] <= 0
        or re.fullmatch(r"[0-9a-f]{64}", revision["prior_sha256"]) is None
    ):
        raise RuntimeError(f"cached {ticker} has an invalid upstream history revision")
    try:
        for key in ("accepted_on", "prior_start", "prior_end"):
            datetime.strptime(revision[key], "%Y-%m-%d")
    except ValueError as exc:
        raise RuntimeError(f"cached {ticker} has an invalid upstream history revision") from exc
    if revision["prior_start"] > revision["prior_end"]:
        raise RuntimeError(f"cached {ticker} has an invalid upstream history revision")
    return dict(revision)


def _verify_cached_file(ticker: str, path: Path, manifest: dict) -> pd.DataFrame:
    entry = manifest.get(ticker)
    required = {"sha256", "rows", "start", "end"}
    if not isinstance(entry, dict) or not required <= set(entry):
        raise RuntimeError(f"cached {ticker} has no complete manifest entry")
    _validated_history_revision(entry, ticker)
    try:
        # Hash and parse one immutable byte snapshot. Hashing a path and then
        # reopening it lets a concurrent replacement pass the first check but
        # feed different bytes to parquet.
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        frame = pd.read_parquet(io.BytesIO(payload))
        _validate_daily_frame(frame, f"cached file {path}")
    except Exception as exc:
        raise RuntimeError(f"cached {ticker} parquet is unreadable: {exc}") from exc
    rows, start, end = len(frame), str(frame.index[0].date()), str(frame.index[-1].date())
    actual = {"sha256": digest, "rows": rows, "start": start, "end": end}
    expected = {key: entry[key] for key in required}
    if actual != expected:
        raise RuntimeError(
            f"cached {ticker} failed manifest verification; delete/re-download the cache"
        )
    return frame


def load_panels(
    tickers: list[str],
    end: str | None = None,
    _holdout_token: str | None = None,
    _candidate_id: str | None = None,
    extra_adjclose_tickers: list[str] | None = None,
    _expected_input_identity: dict[str, str] | None = None,
) -> FieldBundle:
    """Load OHLCV once/ticker; optionally retain adjclose for a second group."""
    try:
        end_ts = pd.Timestamp(end) if end is not None else pd.Timestamp(VALIDATION_END)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid panel end date {end!r}") from exc
    if end_ts.tz is not None:
        end_ts = end_ts.tz_convert("UTC").tz_localize(None)
    token_scope = None
    if end_ts > pd.Timestamp(VALIDATION_END):
        from .holdout_gate import verify_token

        for field_name in FIELDS:
            scope = verify_token(
                _holdout_token,
                candidate_id=_candidate_id,
                requested_end=str(end_ts.date()),
                requested_field=field_name,
            )
            if token_scope is not None and scope != token_scope:
                raise RuntimeError("holdout token scope changed while loading fields")
            token_scope = scope

    extra_adjclose_tickers = extra_adjclose_tickers or []
    all_tickers = tickers + extra_adjclose_tickers
    if len(all_tickers) != len(set(all_tickers)):
        raise RuntimeError("requested ticker list contains duplicates")
    manifest, manifest_sha256 = _manifest_snapshot()
    if (
        _expected_input_identity is not None
        and _expected_input_identity.get("data_manifest_sha256") != manifest_sha256
    ):
        raise RuntimeError("data manifest changed after the research capability was granted")
    paths: list[Path] = []
    missing_cache: list[str] = []
    for ticker in all_tickers:
        _validate_ticker(ticker)
        path = CACHE_DIR / f"{ticker}.parquet"
        if not path.exists():
            missing_cache.append(ticker)
            continue
        paths.append(path)
    if missing_cache:
        preview = ", ".join(missing_cache[:10])
        suffix = "..." if len(missing_cache) > 10 else ""
        raise RuntimeError(
            f"verified cache is missing {len(missing_cache)} requested tickers: {preview}{suffix}"
        )

    # Build the exact union calendar from manifest-verified snapshots, then
    # fill preallocated arrays from a second independently verified snapshot.
    # Reading an unverified index first would allow a concurrent same-path
    # replacement to inject dates (and potentially force a huge allocation)
    # even though the later full-file verification passed.
    date_values: set[int] = set()
    for ticker, path in zip(all_tickers, paths, strict=True):
        frame = _verify_cached_file(ticker, path, manifest)
        date_values.update(frame.index.as_unit("ns").asi8.tolist())
    calendar = pd.DatetimeIndex(pd.to_datetime(sorted(date_values), unit="ns"), name="date")
    calendar = calendar[calendar <= end_ts]
    if token_scope == "g1_generation":
        from . import POST_CUTOFF_START

        calendar = calendar[calendar >= pd.Timestamp(POST_CUTOFF_START)]
    if calendar.empty:
        raise RuntimeError(f"verified cache has no rows on or before {end_ts}")

    arrays = {
        field_name: np.full((len(calendar), len(tickers)), np.nan, dtype=float)
        for field_name in FIELDS
    }
    extra_adjclose = np.full((len(calendar), len(extra_adjclose_tickers)), np.nan, dtype=float)
    for column, (ticker, path) in enumerate(zip(all_tickers, paths, strict=True)):
        frame = _verify_cached_file(ticker, path, manifest)
        frame = frame.loc[frame.index.intersection(calendar)]
        positions = calendar.get_indexer(frame.index)
        if (positions < 0).any():
            raise RuntimeError(f"cached {ticker} dates do not align to the union calendar")
        if column < len(tickers):
            for field_name in FIELDS:
                arrays[field_name][positions, column] = frame[field_name].to_numpy(dtype=float)
        else:
            extra_column = column - len(tickers)
            extra_adjclose[positions, extra_column] = frame["adjclose"].to_numpy(dtype=float)
    panels = {
        field_name: pd.DataFrame(values, index=calendar, columns=tickers, copy=False)
        for field_name, values in arrays.items()
    }
    if extra_adjclose_tickers:
        panels["extra_adjclose"] = pd.DataFrame(
            extra_adjclose,
            index=calendar,
            columns=extra_adjclose_tickers,
            copy=False,
        )
    return FieldBundle(
        panels,
        input_identity={"data_manifest_sha256": manifest_sha256},
    )


def _atomic_json(path: Path, payload: dict) -> None:
    atomic_write_text(path, dumps(payload, indent=1, sort_keys=True))


def download_universe(tickers: list[str], force: bool = False) -> dict:
    """Download all tickers into the parquet cache; record hashes in the manifest."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _manifest()
    ok, failed = [], []
    for i, ticker in enumerate(tickers):
        _validate_ticker(ticker)
        path = CACHE_DIR / f"{ticker}.parquet"
        history_revision = _validated_history_revision(manifest.get(ticker), ticker)
        previous = None
        if path.exists():
            try:
                previous = _verify_cached_file(ticker, path, manifest)
            except RuntimeError:
                previous = None  # stale/corrupt caches are replaced below
            else:
                if not force:
                    ok.append(ticker)
                    continue
        try:
            df = fetch_daily(ticker)
            if previous is not None and not previous.index.isin(df.index).all():
                missing = previous.index[~previous.index.isin(df.index)]
                first_missing = str(missing[0].date())
                raise RuntimeError(
                    f"refreshed full history lost {len(missing)} previously verified "
                    f"session(s), first {first_missing}; prior cache preserved"
                )
        except RuntimeError as err:
            failed.append(ticker)
            print(f"  FAIL {ticker}: {err}", file=sys.stderr)
            continue
        temp = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
        try:
            df.to_parquet(temp)
            # Bind the manifest to the exact artifact being published. Reading
            # the destination after replace would let a concurrent replacement
            # be blessed by the new manifest instead of failing verification.
            artifact_sha256 = hashlib.sha256(temp.read_bytes()).hexdigest()
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
        entry = {
            "rows": len(df),
            "start": str(df.index[0].date()),
            "end": str(df.index[-1].date()),
            "sha256": artifact_sha256,
            "quarantined_ohlc_rows": int(df.attrs.get("quarantined_ohlc_rows", 0)),
        }
        if history_revision is not None:
            entry["upstream_history_revision"] = history_revision
        manifest[ticker] = entry
        ok.append(ticker)
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(tickers)} done", file=sys.stderr)
            _atomic_json(MANIFEST_PATH, manifest)
    _atomic_json(MANIFEST_PATH, manifest)
    return {"ok": ok, "failed": failed}


def load_panel(
    field: str = "adjclose",
    tickers: list[str] | None = None,
    end: str | None = None,
    _holdout_token: str | None = None,
    _candidate_id: str | None = None,
    _expected_input_identity: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Load a wide (date x ticker) panel for one field from the cache.

    Data after VALIDATION_END is refused unless a holdout token from
    holdout_gate.authorize() is presented.
    """
    if field not in FIELDS:
        raise ValueError(f"field must be one of {FIELDS}")
    try:
        end_ts = pd.Timestamp(end) if end is not None else pd.Timestamp(VALIDATION_END)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid panel end date {end!r}") from exc
    if end_ts.tz is not None:
        end_ts = end_ts.tz_convert("UTC").tz_localize(None)
    token_scope = None
    if end_ts > pd.Timestamp(VALIDATION_END):
        from .holdout_gate import verify_token

        token_scope = verify_token(
            _holdout_token,
            candidate_id=_candidate_id,
            requested_end=str(end_ts.date()),
            requested_field=field,
        )
    if tickers is None:
        tickers = sorted(p.stem for p in CACHE_DIR.glob("*.parquet"))
    manifest, manifest_sha256 = _manifest_snapshot()
    if (
        _expected_input_identity is not None
        and _expected_input_identity.get("data_manifest_sha256") != manifest_sha256
    ):
        raise RuntimeError("data manifest changed after the research capability was granted")
    cols = {}
    missing_cache: list[str] = []
    for ticker in tickers:
        _validate_ticker(ticker)
        path = CACHE_DIR / f"{ticker}.parquet"
        if not path.exists():
            missing_cache.append(ticker)
            continue
        frame = _verify_cached_file(ticker, path, manifest)
        cols[ticker] = frame[field]
    if missing_cache:
        preview = ", ".join(missing_cache[:10])
        suffix = "..." if len(missing_cache) > 10 else ""
        raise RuntimeError(
            f"verified cache is missing {len(missing_cache)} requested tickers: {preview}{suffix}"
        )
    if not cols:
        raise RuntimeError("no verified cached tickers were available for the requested panel")
    panel = pd.DataFrame(cols)
    panel = panel.loc[panel.index <= end_ts]
    if token_scope == "g1_generation":
        # G1 tokens grant ONLY the post-cutoff generation slice (deviation D1),
        # never the 2024..2026-01 holdout window.
        from . import POST_CUTOFF_START

        panel = panel.loc[panel.index >= pd.Timestamp(POST_CUTOFF_START)]
    if panel.empty:
        raise RuntimeError(f"verified cache has no rows on or before {end_ts}")
    panel.index.name = "date"
    return panel


def load_g1_window(field: str = "adjclose", tickers: list[str] | None = None) -> pd.DataFrame:
    """G1 hypothesis-generation data: ONLY the post-knowledge-cutoff slice
    (POST_CUTOFF_START onward). Access is token-gated and logged; see
    research/debates/protocol_deviations.md D1."""
    from . import G1_GENERATION_END, POST_CUTOFF_START
    from .holdout_gate import authorize_g1_generation, authorized_input_identity

    universe, universe_sha256 = load_universe_snapshot()
    if tickers is None:
        tickers = universe["equities"] + universe["etfs"]
    token = authorize_g1_generation()
    expected = authorized_input_identity(token)
    if expected.get("universe_sha256") != universe_sha256:
        raise RuntimeError("data universe changed after the G1 capability was granted")
    end = G1_GENERATION_END
    panel = load_panel(
        field=field,
        tickers=tickers,
        end=end,
        _holdout_token=token,
        _expected_input_identity=expected,
    )
    return panel.loc[panel.index >= pd.Timestamp(POST_CUTOFF_START)]


def load_g1_panels(tickers: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """Load every G1 field under one logged, single-use capability."""
    from . import G1_GENERATION_END
    from .holdout_gate import authorize_g1_generation

    universe, universe_sha256 = load_universe_snapshot()
    if tickers is None:
        tickers = universe["equities"] + universe["etfs"]
    token = authorize_g1_generation()
    from .holdout_gate import authorized_input_identity

    expected = authorized_input_identity(token)
    if expected.get("universe_sha256") != universe_sha256:
        raise RuntimeError("data universe changed after the G1 capability was granted")
    panels = load_panels(
        tickers=tickers,
        end=G1_GENERATION_END,
        _holdout_token=token,
        _expected_input_identity=expected,
    )
    panels.input_identity["universe_sha256"] = universe_sha256
    panels.universe = universe
    return panels


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "download":
        unknown = set(sys.argv[2:]) - {"--force"}
        if unknown:
            raise SystemExit(f"unknown download options: {sorted(unknown)}")
        universe = load_universe()
        tickers = universe["equities"] + universe["etfs"]
        result = download_universe(tickers, force="--force" in sys.argv[2:])
        print(f"downloaded ok={len(result['ok'])} failed={len(result['failed'])}")
        if result["failed"]:
            print("failed:", ",".join(result["failed"]))
            raise SystemExit(1)
    else:
        print("usage: python -m edgelab.data download [--force]")


if __name__ == "__main__":
    main()
