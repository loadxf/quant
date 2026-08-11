from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import edgelab.diagnostics as diagnostics
import edgelab.gates as gates
import pandas as pd
import pytest
from edgelab.backtest import quantile_weights
from pandas.testing import assert_series_equal


def test_family_returns_parses_the_verified_byte_snapshot(monkeypatch, tmp_path):
    candidates = tmp_path / "candidates"
    candidate = candidates / "C001"
    candidate.mkdir(parents=True)
    (candidate / "signal.py").write_text("def compute_signal(fields): return None\n")
    artifact_path = tmp_path / "family.parquet"
    artifact = b"sealed parquet payload"
    artifact_path.write_bytes(artifact)
    metadata_path = tmp_path / "family.meta.json"
    identity = {"engine_sha256": "engine"}
    metadata_path.write_text(
        json.dumps(
            {
                **identity,
                "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
            }
        )
    )
    expected = pd.DataFrame({"C001": [0.1]}, index=pd.DatetimeIndex([pd.Timestamp("2020-01-02")]))

    monkeypatch.setattr(diagnostics, "CANDIDATES_DIR", candidates)
    monkeypatch.setattr(diagnostics, "FAMILY_RETURNS_PATH", artifact_path)
    monkeypatch.setattr(diagnostics, "FAMILY_META_PATH", metadata_path)
    monkeypatch.setattr(diagnostics, "family_artifact_identity", lambda ids: identity)

    def parse_snapshot(source):
        assert isinstance(source, io.BytesIO)
        assert source.getvalue() == artifact
        return expected

    monkeypatch.setattr(pd, "read_parquet", parse_snapshot)
    panel, metadata = diagnostics._verified_family_returns()
    assert panel.equals(expected)
    assert metadata["artifact_sha256"] == hashlib.sha256(artifact).hexdigest()


def test_diagnostics_reject_fields_from_a_different_input_snapshot():
    fields = type(
        "Fields",
        (),
        {
            "input_identity": {
                "data_manifest_sha256": "other",
                "universe_sha256": "universe",
            }
        },
    )()
    with pytest.raises(RuntimeError, match="different data_manifest_sha256"):
        diagnostics._require_matching_inputs(
            fields,
            {
                "data_manifest_sha256": "sealed",
                "universe_sha256": "universe",
            },
        )


def test_family_publish_hashes_the_exact_temporary_snapshot(monkeypatch, tmp_path):
    artifact_path = tmp_path / "family.parquet"
    metadata_path = tmp_path / "family.meta.json"
    monkeypatch.setattr(gates, "FAMILY_RETURNS_PATH", artifact_path)
    monkeypatch.setattr(gates, "FAMILY_META_PATH", metadata_path)

    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(path: Path) -> bytes:
        if path == artifact_path:
            raise AssertionError("the published destination must not be reopened for hashing")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    panel = pd.DataFrame(
        {"C001": [0.1, -0.2]},
        index=pd.DatetimeIndex(["2020-01-02", "2020-01-03"]),
    )
    gates._publish_family_returns(panel, {"engine_sha256": "engine"})

    payload = original_read_bytes(artifact_path)
    metadata = json.loads(metadata_path.read_text())
    assert metadata["artifact_sha256"] == hashlib.sha256(payload).hexdigest()
    assert metadata["engine_sha256"] == "engine"


def test_c015_leg_decomposition_uses_exact_overlapping_held_cohorts():
    dates = pd.date_range("2020-01-01", periods=9, freq="B")
    columns = [f"S{i:02d}" for i in range(10)]
    signal = pd.DataFrame(
        [[float((i + offset) % 10) for i in range(10)] for offset in range(9)],
        index=dates,
        columns=columns,
    )
    source_returns = pd.DataFrame(
        [[(i + 1) * (offset + 1) / 10_000 for i in range(10)] for offset in range(9)],
        index=dates,
        columns=columns,
    )
    adjclose = 100 * (1.0 + source_returns).cumprod()
    returns = adjclose.pct_change(fill_method=None)

    exact_held = (
        quantile_weights(signal.where(adjclose.notna()), quantile=0.2, min_names=10)
        .rolling(5, min_periods=1)
        .mean()
        .shift(2)
        .fillna(0.0)
    )
    long_leg, short_leg = diagnostics._held_leg_returns(
        exact_held,
        adjclose,
        start_date=str(dates[0].date()),
    )
    assert_series_equal(long_leg, (exact_held.clip(lower=0) * returns).sum(axis=1))
    assert_series_equal(short_leg, (-exact_held.clip(upper=0) * returns).sum(axis=1))


def test_leg_decomposition_fails_on_a_missing_return_for_a_held_asset():
    dates = pd.date_range("2020-01-01", periods=8, freq="B")
    adjclose = pd.DataFrame(
        {
            "A": range(100, 108),
            "B": range(108, 100, -1),
            "C": range(90, 98),
            "D": range(98, 90, -1),
        },
        index=dates,
        dtype=float,
    )
    held = pd.DataFrame(0.0, index=dates, columns=adjclose.columns)
    held.loc[dates[4] :, ["A", "D"]] = [1.0, -1.0]
    adjclose.loc[dates[4], "A"] = float("nan")

    with pytest.raises(ValueError, match="held asset A has no return"):
        diagnostics._held_leg_returns(
            held,
            adjclose,
            start_date=str(dates[0].date()),
        )


def test_leg_decomposition_ignores_missing_held_returns_before_registered_start():
    dates = pd.date_range("2004-12-27", periods=10, freq="B")
    adjclose = pd.DataFrame({"A": range(100, 110), "B": range(110, 100, -1)}, index=dates)
    held = pd.DataFrame({"A": 1.0, "B": -1.0}, index=dates)
    adjclose.loc[dates[2], "A"] = float("nan")

    long_leg, short_leg = diagnostics._held_leg_returns(
        held,
        adjclose,
        start_date="2005-01-03",
    )

    assert long_leg.index.min() == pd.Timestamp("2005-01-03")
    assert short_leg.index.min() == pd.Timestamp("2005-01-03")
