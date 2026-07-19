"""The holdout gate must refuse: unregistered candidates, uncommitted
registries, tampered specs, and re-runs. load_panel must refuse post-validation
data without a token."""

import json

import pandas as pd
import pytest

import quantlab.data as qdata
import quantlab.holdout_gate as gate


def test_load_panel_refuses_post_validation_without_token(monkeypatch, tmp_path):
    monkeypatch.setattr(qdata, "CACHE_DIR", tmp_path)
    df = pd.DataFrame(
        {"adjclose": [1.0, 2.0, 3.0]},
        index=pd.to_datetime(["2023-12-29", "2024-06-03", "2026-03-02"]),
    )
    df.to_parquet(tmp_path / "AAA.parquet")
    ok = qdata.load_panel()  # default end = validation end
    assert ok.index.max() <= pd.Timestamp("2023-12-31")
    with pytest.raises(RuntimeError, match="holdout token"):
        qdata.load_panel(end="2026-07-01")


def test_gate_refuses_unregistered(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "REGISTRY_PATH", tmp_path / "registry.json")
    (tmp_path / "registry.json").write_text(json.dumps({"C001": {"spec_sha256": "ab"}}))
    with pytest.raises(RuntimeError, match="not registered"):
        gate.authorize("C999")


def test_gate_refuses_tampered_spec(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(gate, "CANDIDATES_DIR", tmp_path)
    monkeypatch.setattr(gate, "_registry_committed", lambda: True)
    spec_dir = tmp_path / "C001"
    spec_dir.mkdir()
    (spec_dir / "spec.md").write_text("original spec")
    original_hash = gate.spec_sha256(spec_dir / "spec.md")
    (tmp_path / "registry.json").write_text(
        json.dumps({"C001": {"spec_sha256": original_hash}})
    )
    (spec_dir / "spec.md").write_text("tampered spec")
    with pytest.raises(RuntimeError, match="hash mismatch"):
        gate.authorize("C001")


def test_gate_single_shot(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(gate, "CANDIDATES_DIR", tmp_path)
    monkeypatch.setattr(gate, "_registry_committed", lambda: True)
    spec_dir = tmp_path / "C001"
    spec_dir.mkdir()
    (spec_dir / "spec.md").write_text("spec")
    (tmp_path / "registry.json").write_text(
        json.dumps({"C001": {"spec_sha256": gate.spec_sha256(spec_dir / "spec.md")}})
    )
    token = gate.authorize("C001")
    assert token
    gate.record_results("C001", {"sr": 0.1})
    with pytest.raises(RuntimeError, match="already consumed"):
        gate.authorize("C001")
    with pytest.raises(RuntimeError, match="immutable"):
        gate.record_results("C001", {"sr": 0.2})


def test_gate_requires_committed_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(gate, "CANDIDATES_DIR", tmp_path)
    monkeypatch.setattr(gate, "_registry_committed", lambda: False)
    spec_dir = tmp_path / "C001"
    spec_dir.mkdir()
    (spec_dir / "spec.md").write_text("spec")
    (tmp_path / "registry.json").write_text(
        json.dumps({"C001": {"spec_sha256": gate.spec_sha256(spec_dir / "spec.md")}})
    )
    with pytest.raises(RuntimeError, match="commit"):
        gate.authorize("C001")
