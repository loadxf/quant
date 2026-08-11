import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import edgelab.data as qdata
import edgelab.gates as gates
import edgelab.holdout_gate as holdout_gate
import pandas as pd
import pytest
from edgelab.data import (
    _quarantine_invalid_envelopes,
    _session_publish_after,
    _validate_daily_frame,
    load_universe,
)


def test_yahoo_session_close_supports_exchange_half_day():
    new_york = ZoneInfo("America/New_York")
    close = datetime(2024, 11, 29, 13, 0, tzinfo=new_york)
    payload = {"meta": {"currentTradingPeriod": {"regular": {"end": close.timestamp()}}}}
    publish_after = _session_publish_after(payload, close.date())
    assert publish_after == datetime(2024, 11, 29, 13, 15, tzinfo=new_york)


def test_yahoo_session_close_rejects_mismatched_or_invalid_metadata():
    payload = {"meta": {"currentTradingPeriod": {"regular": {"end": float("nan")}}}}
    assert _session_publish_after(payload, datetime(2024, 11, 29).date()) is None


def _daily_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [10.0, 11.0],
            "high": [12.0, 13.0],
            "low": [9.0, 10.0],
            "close": [11.0, 12.0],
            "adjclose": [11.0, 12.0],
            "volume": [100.0, 200.0],
        },
        index=pd.date_range("2024-01-02", periods=2, freq="D"),
    )


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("open", 0.0, "non-positive"),
        ("adjclose", -1.0, "non-positive"),
        ("volume", -1.0, "negative volume"),
        ("high", 8.0, "OHLC envelope"),
        ("low", 14.0, "OHLC envelope"),
    ],
)
def test_daily_frame_rejects_invalid_observed_values(column, value, message):
    frame = _daily_frame()
    frame.loc[frame.index[0], column] = value
    with pytest.raises(ValueError, match=message):
        _validate_daily_frame(frame, "test frame")


def test_daily_frame_allows_missing_optional_yahoo_cells():
    frame = _daily_frame()
    frame.loc[frame.index[0], ["open", "high", "low", "adjclose", "volume"]] = None
    _validate_daily_frame(frame, "test frame")


def test_daily_frame_rejects_duplicate_or_intraday_index():
    frame = _daily_frame()
    frame.index = pd.DatetimeIndex([frame.index[0], frame.index[0]])
    with pytest.raises(ValueError, match="unique"):
        _validate_daily_frame(frame, "test frame")


def test_invalid_yahoo_envelope_is_quarantined_without_fabricating_prices():
    frame = _daily_frame()
    frame.loc[frame.index[0], "low"] = 11.5
    assert _quarantine_invalid_envelopes(frame) == 1
    assert frame.loc[frame.index[0], ["open", "high", "low"]].isna().all()
    assert frame.loc[frame.index[0], "close"] == 11.0
    _validate_daily_frame(frame, "quarantined frame")

    frame = _daily_frame()
    frame.index = frame.index + pd.Timedelta(hours=16)
    with pytest.raises(ValueError, match="session dates"):
        _validate_daily_frame(frame, "test frame")


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        '{"equities":null,"etfs":[],"sectors":{}}',
        '{"equities":["A","A"],"etfs":["SPY"],"sectors":{}}',
        '{"equities":[1],"etfs":["SPY"],"sectors":{}}',
        '{"equities":["SPY"],"etfs":["SPY"],"sectors":{"SPY":"Index"}}',
        '{"equities":["A"],"etfs":["SPY"],"sectors":{}}',
    ],
)
def test_universe_requires_valid_unique_ticker_lists(tmp_path, payload):
    path = tmp_path / "universe.json"
    path.write_text(payload)
    with pytest.raises(RuntimeError, match="invalid data universe"):
        load_universe(path)


def test_panel_calendar_comes_only_from_manifest_verified_bytes(monkeypatch, tmp_path):
    frame = _daily_frame()
    frame.index = pd.date_range("2023-01-03", periods=2, freq="D")
    cache = tmp_path / "cache"
    cache.mkdir()
    path = cache / "AAA.parquet"
    frame.to_parquet(path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "AAA": {
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "rows": 2,
                    "start": "2023-01-03",
                    "end": "2023-01-04",
                }
            }
        )
    )
    monkeypatch.setattr(qdata, "CACHE_DIR", cache)
    monkeypatch.setattr(qdata, "MANIFEST_PATH", manifest)

    # Simulate the former index-only path reopen seeing an attacker-controlled
    # replacement. Hardened loading never invokes this unverified read.
    real_read_parquet = qdata.pd.read_parquet
    injected = pd.DataFrame(index=pd.to_datetime(["2023-01-03", "2099-12-31"]))

    def swapped_index(source, *args, **kwargs):
        if kwargs.get("columns") == []:
            return injected
        return real_read_parquet(source, *args, **kwargs)

    monkeypatch.setattr(qdata.pd, "read_parquet", swapped_index)
    panels = qdata.load_panels(["AAA"])
    assert panels["close"].index.equals(frame.index.rename("date"))


def test_load_panels_rejects_a_manifest_outside_the_capability_snapshot(monkeypatch, tmp_path):
    frame = _daily_frame().iloc[:1]
    frame.index = pd.DatetimeIndex(["2023-01-03"], name="date")
    cache = tmp_path / "cache"
    cache.mkdir()
    path = cache / "AAA.parquet"
    frame.to_parquet(path)
    manifest = tmp_path / "manifest.json"
    original = json.dumps(
        {
            "AAA": {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "rows": 1,
                "start": "2023-01-03",
                "end": "2023-01-03",
            }
        }
    ).encode()
    manifest.write_bytes(original)
    expected = {"data_manifest_sha256": hashlib.sha256(original).hexdigest()}
    monkeypatch.setattr(qdata, "CACHE_DIR", cache)
    monkeypatch.setattr(qdata, "MANIFEST_PATH", manifest)

    manifest.write_text("{}")
    with pytest.raises(RuntimeError, match="manifest changed"):
        qdata.load_panels(["AAA"], _expected_input_identity=expected)


def test_gate_loader_rejects_a_universe_outside_the_capability_snapshot(monkeypatch):
    universe = {
        "equities": ["AAA"],
        "etfs": ["SPY"],
        "sectors": {"AAA": "Industrials"},
    }
    monkeypatch.setattr(
        gates, "load_universe_snapshot", lambda path: (universe, "swapped-universe")
    )
    monkeypatch.setattr(
        holdout_gate,
        "authorized_input_identity",
        lambda token, candidate_id=None: {
            "data_manifest_sha256": "manifest",
            "universe_sha256": "authorized-universe",
        },
    )
    with pytest.raises(RuntimeError, match="universe changed"):
        gates.load_etf_fields(token="token", candidate_id="C016")


def test_force_refresh_preserves_prior_cache_when_provider_history_shrinks(monkeypatch, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    path = cache / "AAA.parquet"
    old = pd.concat([_daily_frame(), _daily_frame().iloc[[1]]])
    old.index = pd.date_range("2020-01-02", periods=3, freq="B", name="date")
    old.to_parquet(path)
    old_payload = path.read_bytes()
    manifest = tmp_path / "manifest.json"
    old_manifest = {
        "AAA": {
            "sha256": hashlib.sha256(old_payload).hexdigest(),
            "rows": 3,
            "start": "2020-01-02",
            "end": "2020-01-06",
        }
    }
    manifest.write_text(json.dumps(old_manifest))
    shortened = old.iloc[[-1]].copy()

    monkeypatch.setattr(qdata, "CACHE_DIR", cache)
    monkeypatch.setattr(qdata, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(qdata, "fetch_daily", lambda ticker: shortened)

    result = qdata.download_universe(["AAA"], force=True)

    assert result == {"ok": [], "failed": ["AAA"]}
    assert path.read_bytes() == old_payload
    assert json.loads(manifest.read_text()) == old_manifest


def test_download_hashes_the_exact_temporary_artifact_not_the_destination(monkeypatch, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    destination = cache / "AAA.parquet"
    manifest = tmp_path / "manifest.json"
    frame = _daily_frame()
    frame.index.name = "date"

    monkeypatch.setattr(qdata, "CACHE_DIR", cache)
    monkeypatch.setattr(qdata, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(qdata, "fetch_daily", lambda ticker: frame)

    real_read_bytes = qdata.Path.read_bytes

    def deny_destination_reopen(path):
        if path == destination:
            raise AssertionError("published destination must not be reopened for hashing")
        return real_read_bytes(path)

    monkeypatch.setattr(qdata.Path, "read_bytes", deny_destination_reopen)
    result = qdata.download_universe(["AAA"], force=True)

    assert result == {"ok": ["AAA"], "failed": []}
    entry = json.loads(manifest.read_text())["AAA"]
    assert entry["rows"] == len(frame)


def test_monotone_force_refresh_preserves_a_valid_history_revision(monkeypatch, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    path = cache / "AAA.parquet"
    old = _daily_frame()
    old.index = pd.date_range("2020-01-02", periods=2, freq="B", name="date")
    old.to_parquet(path)
    revision = {
        "accepted_on": "2026-08-11",
        "prior_end": "2019-12-31",
        "prior_rows": 100,
        "prior_sha256": "a" * 64,
        "prior_start": "2019-01-02",
        "reason": "independently confirmed provider rewrite",
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "AAA": {
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "rows": 2,
                    "start": "2020-01-02",
                    "end": "2020-01-03",
                    "upstream_history_revision": revision,
                }
            }
        )
    )
    extended = pd.concat([old, old.iloc[[-1]]])
    extended.index = pd.date_range("2020-01-02", periods=3, freq="B", name="date")

    monkeypatch.setattr(qdata, "CACHE_DIR", cache)
    monkeypatch.setattr(qdata, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(qdata, "fetch_daily", lambda ticker: extended)

    result = qdata.download_universe(["AAA"], force=True)

    assert result == {"ok": ["AAA"], "failed": []}
    assert json.loads(manifest.read_text())["AAA"]["upstream_history_revision"] == revision
