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
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

from . import CACHE_DIR, DATA_DIR, VALIDATION_END

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
FIELDS = ["open", "high", "low", "close", "adjclose", "volume"]
MANIFEST_PATH = DATA_DIR / "manifest.json"


def fetch_daily(ticker: str, retries: int = 3, throttle: float = 0.5) -> pd.DataFrame:
    """Fetch full daily history for one ticker. Returns OHLC+adjclose+volume."""
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
                index=pd.to_datetime(ts, unit="s", utc=True).tz_convert("America/New_York").normalize().tz_localize(None),
            )
            df.index.name = "date"
            df = df[~df.index.duplicated(keep="last")].dropna(subset=["close"])
            time.sleep(throttle)
            return df
        except Exception as err:  # noqa: BLE001 - retry any transport/parse failure
            last_err = err
            time.sleep(2**attempt)
    raise RuntimeError(f"failed to fetch {ticker}: {last_err}")


def _manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {}


def download_universe(tickers: list[str], force: bool = False) -> dict:
    """Download all tickers into the parquet cache; record hashes in the manifest."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _manifest()
    ok, failed = [], []
    for i, ticker in enumerate(tickers):
        path = CACHE_DIR / f"{ticker}.parquet"
        if path.exists() and not force:
            ok.append(ticker)
            continue
        try:
            df = fetch_daily(ticker)
        except RuntimeError as err:
            failed.append(ticker)
            print(f"  FAIL {ticker}: {err}", file=sys.stderr)
            continue
        df.to_parquet(path)
        manifest[ticker] = {
            "rows": len(df),
            "start": str(df.index[0].date()),
            "end": str(df.index[-1].date()),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        ok.append(ticker)
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(tickers)} done", file=sys.stderr)
            MANIFEST_PATH.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return {"ok": ok, "failed": failed}


def load_panel(
    field: str = "adjclose",
    tickers: list[str] | None = None,
    end: str | None = None,
    _holdout_token: str | None = None,
) -> pd.DataFrame:
    """Load a wide (date x ticker) panel for one field from the cache.

    Data after VALIDATION_END is refused unless a holdout token from
    holdout_gate.authorize() is presented.
    """
    if field not in FIELDS:
        raise ValueError(f"field must be one of {FIELDS}")
    end_ts = pd.Timestamp(end) if end is not None else pd.Timestamp(VALIDATION_END)
    if end_ts > pd.Timestamp(VALIDATION_END):
        from .holdout_gate import verify_token

        verify_token(_holdout_token)
    if tickers is None:
        tickers = sorted(p.stem for p in CACHE_DIR.glob("*.parquet"))
    cols = {}
    for ticker in tickers:
        path = CACHE_DIR / f"{ticker}.parquet"
        if not path.exists():
            continue
        cols[ticker] = pd.read_parquet(path, columns=[field])[field]
    panel = pd.DataFrame(cols)
    panel = panel.loc[panel.index <= end_ts]
    panel.index.name = "date"
    return panel


def load_g1_window(field: str = "adjclose", tickers: list[str] | None = None) -> pd.DataFrame:
    """G1 hypothesis-generation data: ONLY the post-knowledge-cutoff slice
    (POST_CUTOFF_START onward). Access is token-gated and logged; see
    research/debates/protocol_deviations.md D1."""
    from . import POST_CUTOFF_START
    from .holdout_gate import authorize_g1_generation

    token = authorize_g1_generation()
    panel = load_panel(field=field, tickers=tickers, end="2030-01-01", _holdout_token=token)
    return panel.loc[panel.index >= pd.Timestamp(POST_CUTOFF_START)]


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "download":
        universe = json.loads((DATA_DIR / "universe.json").read_text())
        tickers = universe["equities"] + universe["etfs"]
        result = download_universe(tickers)
        print(f"downloaded ok={len(result['ok'])} failed={len(result['failed'])}")
        if result["failed"]:
            print("failed:", ",".join(result["failed"]))
    else:
        print("usage: python -m quantlab.data download")


if __name__ == "__main__":
    main()
