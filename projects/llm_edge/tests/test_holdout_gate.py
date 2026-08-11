"""The holdout gate must refuse: unregistered candidates, uncommitted
registries, tampered specs, and re-runs. load_panel must refuse post-validation
data without a token."""

import json

import edgelab.data as qdata
import edgelab.holdout_gate as gate
import pandas as pd
import pytest


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


def test_g1_token_grants_only_post_cutoff_slice(monkeypatch, tmp_path):
    monkeypatch.setattr(qdata, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gate, "CANDIDATES_DIR", tmp_path)
    df = pd.DataFrame(
        {"adjclose": [1.0, 2.0, 3.0, 4.0]},
        index=pd.to_datetime(["2023-06-01", "2024-06-03", "2026-01-05", "2026-03-02"]),
    )
    df.to_parquet(tmp_path / "AAA.parquet")
    token = gate.authorize_g1_generation()
    panel = qdata.load_panel(end="2026-07-01", _holdout_token=token)
    # the 2024..2026-01 holdout rows must NOT be visible through a G1 token
    assert panel.index.min() >= pd.Timestamp("2026-02-01")
    assert len(panel) == 1


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
    (tmp_path / "registry.json").write_text(json.dumps({"C001": {"spec_sha256": original_hash}}))
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
    assert gate.verify_token(token) == "holdout:C001"
    gate.record_results("C001", {"sr": 0.1})
    with pytest.raises(RuntimeError, match="already consumed"):
        gate.authorize("C001")
    with pytest.raises(RuntimeError, match="immutable"):
        gate.record_results("C001", {"sr": 0.2})
    # the issued token must be revoked once the shot is consumed
    with pytest.raises(RuntimeError, match="token"):
        gate.verify_token(token)


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


def test_degenerate_candidate_writes_failing_record(tmp_path, monkeypatch):
    """A no-live-days candidate must leave a failing results_validation.json,
    not a stale PASS record from an earlier run (P8)."""
    import json

    import numpy as np
    import pandas as pd
    from edgelab import backtest, gates

    # The real trials ledger is append-only research provenance — a unit
    # test must never write to it.
    monkeypatch.setattr(backtest, "LEDGER_PATH", tmp_path / "trials_ledger.csv")

    cand_dir = tmp_path / "CTEST"
    cand_dir.mkdir()
    (cand_dir / "signal.py").write_text(
        "import pandas as pd\nUNIVERSE='equities'\n"
        "def compute_signal(fields):\n"
        "    return fields['adjclose'] * float('nan')\n",
        encoding="utf-8",
    )
    (cand_dir / "results_validation.json").write_text(
        json.dumps({"gate1": {"pass": True}}), encoding="utf-8"
    )  # stale PASS from an earlier run
    monkeypatch.setattr(gates, "CANDIDATES_DIR", tmp_path)
    dates = pd.bdate_range("2015-01-02", periods=600)
    rng = np.random.default_rng(0)
    prices = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0, 0.01, size=(600, 30)), axis=0),
        index=dates,
        columns=[f"T{i}" for i in range(30)],
    )
    fields = {"adjclose": prices}
    result = gates.evaluate_candidate("CTEST", fields)
    assert result["gate1"]["pass"] is False
    on_disk = json.loads((cand_dir / "results_validation.json").read_text(encoding="utf-8"))
    assert on_disk["gate1"]["pass"] is False
    assert "_returns_net" not in on_disk
