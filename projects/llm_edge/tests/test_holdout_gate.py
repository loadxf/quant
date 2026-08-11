"""The holdout gate must refuse: unregistered candidates, uncommitted
registries, tampered specs, and re-runs. load_panel must refuse post-validation
data without a token."""

import hashlib
import json
import os
import subprocess

import edgelab.backtest as edge_backtest
import edgelab.data as qdata
import edgelab.holdout_eval as holdout_eval
import edgelab.holdout_gate as gate
import edgelab.register as registration
import pandas as pd
import pytest
from edgelab.holdout_eval import _score_result


def _write_cache(monkeypatch, tmp_path, ticker, frame):
    frame = frame.copy()
    for column in ("open", "high", "low"):
        if column not in frame:
            frame[column] = frame["close"]
    if "volume" not in frame:
        frame["volume"] = 0.0
    frame = frame[qdata.FIELDS]
    monkeypatch.setattr(qdata, "CACHE_DIR", tmp_path)
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr(qdata, "MANIFEST_PATH", manifest_path)
    path = tmp_path / f"{ticker}.parquet"
    frame.to_parquet(path)
    manifest_path.write_text(
        json.dumps(
            {
                ticker: {
                    "rows": len(frame),
                    "start": str(frame.index[0].date()),
                    "end": str(frame.index[-1].date()),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            }
        )
    )
    return path


def test_load_panel_refuses_post_validation_without_token(monkeypatch, tmp_path):
    df = pd.DataFrame(
        {"close": [1.0, 2.0, 3.0], "adjclose": [1.0, 2.0, 3.0]},
        index=pd.to_datetime(["2023-12-29", "2024-06-03", "2026-03-02"]),
    )
    _write_cache(monkeypatch, tmp_path, "AAA", df)
    ok = qdata.load_panel()  # default end = validation end
    assert ok.index.max() <= pd.Timestamp("2023-12-31")
    with pytest.raises(RuntimeError, match="holdout token"):
        qdata.load_panel(end="2026-07-01")


def test_g1_token_grants_only_post_cutoff_slice(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "CANDIDATES_DIR", tmp_path)
    df = pd.DataFrame(
        {
            "close": [1.0, 2.0, 3.0, 4.0],
            "adjclose": [1.0, 2.0, 3.0, 4.0],
        },
        index=pd.to_datetime(["2023-06-01", "2024-06-03", "2026-01-05", "2026-03-02"]),
    )
    _write_cache(monkeypatch, tmp_path, "AAA", df)
    token = gate.authorize_g1_generation()
    panel = qdata.load_panel(end="2026-07-01", _holdout_token=token)
    # the 2024..2026-01 holdout rows must NOT be visible through a G1 token
    assert panel.index.min() >= pd.Timestamp("2026-02-01")
    assert len(panel) == 1


def test_g1_token_is_pinned_to_the_historical_generation_end(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "CANDIDATES_DIR", tmp_path)
    token = gate.authorize_g1_generation()
    assert (
        gate.verify_token(token, requested_end="2026-07-17", requested_field="adjclose")
        == "g1_generation"
    )
    with pytest.raises(RuntimeError, match="token scope ends"):
        gate.verify_token(token, requested_end="2026-07-18", requested_field="adjclose")


def test_gate_refuses_unregistered(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "REGISTRY_PATH", tmp_path / "registry.json")
    (tmp_path / "registry.json").write_text(json.dumps({"C001": {"spec_sha256": "ab"}}))
    with pytest.raises(RuntimeError, match="not registered"):
        gate.authorize("C999")


def test_gate_refuses_tampered_spec(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(gate, "CANDIDATES_DIR", tmp_path)
    monkeypatch.setattr(gate, "_registry_committed", lambda: True)
    monkeypatch.setattr(gate, "_path_committed", lambda path: True)
    spec_dir = tmp_path / "C001"
    spec_dir.mkdir()
    (spec_dir / "spec.md").write_text("original spec")
    signal = spec_dir / "signal.py"
    signal.write_text("def compute_signal(fields): return fields['close']\n")
    original_hash = gate.spec_sha256(spec_dir / "spec.md")
    (tmp_path / "registry.json").write_text(json.dumps({"C001": {"spec_sha256": original_hash}}))
    (spec_dir / "spec.md").write_text("tampered spec")
    with pytest.raises(RuntimeError, match="hash mismatch"):
        gate.authorize("C001")


def test_gate_single_shot(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(gate, "CANDIDATES_DIR", tmp_path)
    monkeypatch.setattr(gate, "_registry_committed", lambda: True)
    monkeypatch.setattr(gate, "_path_committed", lambda path: True)
    ledger = tmp_path / "ledger.csv"
    ledger.write_bytes(b"")
    monkeypatch.setattr(gate, "LEDGER_PATH", ledger)
    monkeypatch.setattr(
        gate,
        "_verify_research_seal",
        lambda *args: {"ledger_sha256": "test", "current_commit": "test"},
    )
    spec_dir = tmp_path / "C001"
    spec_dir.mkdir()
    (spec_dir / "spec.md").write_text("spec")
    signal = spec_dir / "signal.py"
    signal.write_text(
        'SIGNAL_KIND = "plain_reversal"\nORIGIN = "G3"\n'
        'HOLDOUT_END = "2030-01-01"\nRETURN_WINDOW = 1\n'
        'PERTURBATIONS = ("RETURN_WINDOW",)\n'
    )
    (tmp_path / "registry.json").write_text(
        json.dumps(
            {
                "C001": {
                    "spec_sha256": gate.spec_sha256(spec_dir / "spec.md"),
                    "signal_sha256": gate.spec_sha256(signal),
                    "engine_commit": "test",
                    "ledger_bytes": 0,
                    "ledger_sha256": hashlib.sha256(b"").hexdigest(),
                    "data_manifest_sha256": "manifest",
                    "universe_sha256": "universe",
                    "origin": "G3",
                    "holdout_end": "2030-01-01",
                }
            }
        )
    )
    token = gate.authorize("C001")
    assert gate.verify_token(token) == "holdout:C001"
    gate.record_results("C001", {"sr": 0.1}, token)
    with pytest.raises(RuntimeError, match="already consumed"):
        gate.authorize("C001")
    with pytest.raises(RuntimeError, match="immutable"):
        gate.record_results("C001", {"sr": 0.2}, token)
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
    signal = spec_dir / "signal.py"
    signal.write_text(
        'SIGNAL_KIND = "plain_reversal"\nORIGIN = "G3"\n'
        'HOLDOUT_END = "2026-06-30"\nRETURN_WINDOW = 1\n'
        'PERTURBATIONS = ("RETURN_WINDOW",)\n'
    )
    (tmp_path / "registry.json").write_text(
        json.dumps({"C001": {"spec_sha256": gate.spec_sha256(spec_dir / "spec.md")}})
    )
    with pytest.raises(RuntimeError, match="commit"):
        gate.authorize("C001")


def test_token_is_candidate_date_and_field_scoped(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(gate, "CANDIDATES_DIR", tmp_path)
    monkeypatch.setattr(gate, "_registry_committed", lambda: True)
    monkeypatch.setattr(gate, "_path_committed", lambda path: True)
    ledger = tmp_path / "ledger.csv"
    ledger.write_bytes(b"")
    monkeypatch.setattr(gate, "LEDGER_PATH", ledger)
    monkeypatch.setattr(
        gate,
        "_verify_research_seal",
        lambda *args: {"ledger_sha256": "test", "current_commit": "test"},
    )
    spec_dir = tmp_path / "C001"
    spec_dir.mkdir()
    (spec_dir / "spec.md").write_text("spec")
    signal = spec_dir / "signal.py"
    signal.write_text(
        'SIGNAL_KIND = "plain_reversal"\nORIGIN = "G3"\n'
        'HOLDOUT_END = "2026-06-30"\nRETURN_WINDOW = 1\n'
        'PERTURBATIONS = ("RETURN_WINDOW",)\n'
    )
    (tmp_path / "registry.json").write_text(
        json.dumps(
            {
                "C001": {
                    "spec_sha256": gate.spec_sha256(spec_dir / "spec.md"),
                    "signal_sha256": gate.spec_sha256(signal),
                    "engine_commit": "test",
                    "holdout_end": "2026-06-30",
                    "ledger_bytes": 0,
                    "ledger_sha256": hashlib.sha256(b"").hexdigest(),
                    "data_manifest_sha256": "manifest",
                    "universe_sha256": "universe",
                    "origin": "G3",
                }
            }
        )
    )
    token = gate.authorize("C001")
    with pytest.raises(RuntimeError, match="different candidate"):
        gate.verify_token(token, candidate_id="C002", requested_field="close")
    with pytest.raises(RuntimeError, match="scope ends"):
        gate.verify_token(token, candidate_id="C001", requested_end="2026-07-01")
    assert (
        gate.verify_token(
            token,
            candidate_id="C001",
            requested_end="2026-06-30",
            requested_field="close",
        )
        == "holdout:C001"
    )
    with pytest.raises(RuntimeError, match="already used"):
        gate.verify_token(token, candidate_id="C001", requested_field="close")


def test_holdout_uses_authorized_signal_snapshot_and_detects_later_edit(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(gate, "CANDIDATES_DIR", tmp_path)
    monkeypatch.setattr(gate, "_registry_committed", lambda: True)
    monkeypatch.setattr(gate, "_path_committed", lambda path: True)
    ledger = tmp_path / "ledger.csv"
    ledger.write_bytes(b"")
    monkeypatch.setattr(gate, "LEDGER_PATH", ledger)
    monkeypatch.setattr(
        gate,
        "_verify_research_seal",
        lambda *args: {"ledger_sha256": "test", "current_commit": "test"},
    )
    candidate = tmp_path / "C001"
    candidate.mkdir()
    spec = candidate / "spec.md"
    signal = candidate / "signal.py"
    spec.write_text("spec")
    original = (
        'SIGNAL_KIND = "plain_reversal"\nORIGIN = "G3"\n'
        'HOLDOUT_END = "2030-01-01"\nRETURN_WINDOW = 1\n'
        'PERTURBATIONS = ("RETURN_WINDOW",)\n'
    )
    signal.write_text(original)
    (tmp_path / "registry.json").write_text(
        json.dumps(
            {
                "C001": {
                    "spec_sha256": gate.spec_sha256(spec),
                    "signal_sha256": gate.spec_sha256(signal),
                    "engine_commit": "test",
                    "ledger_bytes": 0,
                    "ledger_sha256": hashlib.sha256(b"").hexdigest(),
                    "data_manifest_sha256": "manifest",
                    "universe_sha256": "universe",
                    "origin": "G3",
                    "holdout_end": "2030-01-01",
                }
            }
        )
    )

    token = gate.authorize("C001")
    signal.write_text(original.replace("RETURN_WINDOW = 1", "RETURN_WINDOW = 2"))
    assert gate.authorized_signal_source(token, "C001") == original
    with pytest.raises(RuntimeError, match="changed during holdout evaluation"):
        gate.reverify_authorized_state(token, "C001")


def test_successful_holdout_reverifies_before_its_single_ledger_append(monkeypatch, tmp_path):
    dates = pd.bdate_range("2024-01-02", periods=30)
    prices = pd.DataFrame(
        {"A": range(100, 130), "B": range(130, 100, -1)}, index=dates, dtype=float
    )
    signal = pd.DataFrame({"A": 1.0, "B": -1.0}, index=dates)
    ledger = tmp_path / "trials.csv"
    monkeypatch.setattr(edge_backtest, "LEDGER_PATH", ledger)
    monkeypatch.setattr(holdout_eval, "authorize", lambda candidate_id: "token")
    monkeypatch.setattr(
        holdout_eval, "authorized_signal_source", lambda token, candidate_id: "source"
    )
    monkeypatch.setattr(
        holdout_eval,
        "authorized_research_snapshot",
        lambda token, candidate_id: ({"holdout_end": "2030-01-01"}, b"ledger"),
    )
    monkeypatch.setattr(holdout_eval, "ledger_trial_stats", lambda **kwargs: (1, 0.0))
    monkeypatch.setattr(
        holdout_eval,
        "signal_metadata",
        lambda candidate_id, source_text=None: {
            "UNIVERSE": "equities",
            "HOLD": 1,
            "QUANTILE": 0.5,
            "MIN_NAMES": 2,
        },
    )
    monkeypatch.setattr(holdout_eval, "load_equity_fields", lambda **kwargs: {"adjclose": prices})
    monkeypatch.setattr(holdout_eval, "compute_declared_signal", lambda *args: signal)

    events = []

    def reverify(token, candidate_id):
        assert not ledger.exists()
        events.append("verified")

    real_run = edge_backtest.run_backtest

    def run(*args, **kwargs):
        events.append("backtest")
        return real_run(*args, **kwargs)

    recorded = {}
    monkeypatch.setattr(holdout_eval, "reverify_authorized_state", reverify)
    monkeypatch.setattr(holdout_eval, "run_backtest", run)
    monkeypatch.setattr(
        holdout_eval,
        "_score_result",
        lambda candidate_id, result, stats: {"candidate_id": candidate_id, "gate3": {"pass": True}},
    )
    monkeypatch.setattr(
        holdout_eval,
        "record_results",
        lambda candidate_id, result, token: recorded.update(result),
    )

    result = holdout_eval.evaluate_holdout("C001")
    assert result["gate3"]["pass"] is True
    assert recorded == result
    assert events == ["verified", "backtest"]
    assert len(ledger.read_text().splitlines()) == 2


def test_holdout_records_failure_even_when_trial_audit_append_fails(monkeypatch):
    monkeypatch.setattr(holdout_eval, "authorize", lambda candidate_id: "token")
    monkeypatch.setattr(
        holdout_eval,
        "authorized_signal_source",
        lambda token, candidate_id: (_ for _ in ()).throw(RuntimeError("primary")),
    )
    monkeypatch.setattr(
        holdout_eval,
        "record_failed_trial",
        lambda *args: (_ for _ in ()).throw(OSError("ledger unavailable")),
    )
    recorded = {}
    monkeypatch.setattr(
        holdout_eval,
        "record_results",
        lambda candidate_id, result, token: recorded.update(result),
    )

    result = holdout_eval.evaluate_holdout("C001")
    assert result["error"] == "RuntimeError: primary"
    assert result["ledger_audit_error"] == "OSError: ledger unavailable"
    assert recorded == result


def test_capability_returns_frozen_registry_and_ledger_snapshots():
    token = "snapshot-token"
    gate._ISSUED[token] = gate._Capability(
        "holdout",
        "C001",
        "2030-01-01",
        registered_entry={"holdout_end": "2030-01-01", "origin": "G3"},
        ledger_prefix=b"sealed-ledger",
    )
    entry, ledger = gate.authorized_research_snapshot(token, "C001")
    entry["holdout_end"] = "changed"
    assert ledger == b"sealed-ledger"
    assert gate._ISSUED[token].registered_entry["holdout_end"] == "2030-01-01"


def test_registration_seals_each_candidates_declared_holdout_boundary(monkeypatch, tmp_path):
    candidate = tmp_path / "C014"
    candidate.mkdir()
    for name in ("spec.md", "signal.py", "results_validation.json"):
        (candidate / name).write_text(name)
    manifest = tmp_path / "manifest.json"
    universe = tmp_path / "universe.json"
    ledger = tmp_path / "ledger.csv"
    registry = tmp_path / "registry.json"
    for path in (manifest, universe, ledger):
        path.write_text(path.name)
    monkeypatch.setattr(registration, "CANDIDATES_DIR", tmp_path)
    monkeypatch.setattr(registration, "REGISTRY_PATH", registry)
    monkeypatch.setattr(registration, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(registration, "UNIVERSE_PATH", universe)
    monkeypatch.setattr(registration, "LEDGER_PATH", ledger)
    monkeypatch.setattr(registration, "validation_result", lambda *args: {})
    monkeypatch.setattr(
        registration,
        "signal_metadata",
        lambda cid: {"HOLDOUT_END": "2026-01-31", "ORIGIN": "G1"},
    )
    monkeypatch.setattr(registration, "engine_sha256", lambda: "engine")
    monkeypatch.setattr(registration, "environment_sha256", lambda: "environment")
    monkeypatch.setattr(registration, "git_head", lambda: "commit")

    entry = registration.register(["C014"])["C014"]
    assert entry["holdout_end"] == "2026-01-31"
    assert entry["origin"] == "G1"
    assert "G1 candidate" in entry["holdout_note"]

    token = "c014-token"
    gate._ISSUED[token] = gate._Capability("holdout", "C014", entry["holdout_end"])
    with pytest.raises(RuntimeError, match="scope ends"):
        gate.verify_token(token, candidate_id="C014", requested_end="2026-02-01")

    candidate = tmp_path / "C017"
    candidate.mkdir()
    for name in ("spec.md", "signal.py", "results_validation.json"):
        (candidate / name).write_text(name)
    monkeypatch.setattr(
        registration,
        "signal_metadata",
        lambda cid: {"HOLDOUT_END": "2030-01-01", "ORIGIN": "G1"},
    )
    with pytest.raises(RuntimeError, match="G1 declaration"):
        registration.register(["C017"])


def test_registration_rejects_invalid_candidate_or_registry_shape(monkeypatch, tmp_path):
    monkeypatch.setattr(registration, "REGISTRY_PATH", tmp_path / "registry.json")
    with pytest.raises(RuntimeError, match="invalid candidate id"):
        registration.register(["../escape"])
    (tmp_path / "registry.json").write_text("[]")
    with pytest.raises(RuntimeError, match="JSON object"):
        registration.register(["C001"])


def test_gate_requires_committed_signal_code(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(gate, "CANDIDATES_DIR", tmp_path)
    monkeypatch.setattr(gate, "_registry_committed", lambda: True)
    spec_dir = tmp_path / "C001"
    spec_dir.mkdir()
    spec = spec_dir / "spec.md"
    signal = spec_dir / "signal.py"
    spec.write_text("spec")
    signal.write_text("uncommitted")
    monkeypatch.setattr(gate, "_path_committed", lambda path: path == spec)
    (tmp_path / "registry.json").write_text(
        json.dumps({"C001": {"spec_sha256": gate.spec_sha256(spec)}})
    )
    with pytest.raises(RuntimeError, match=r"signal\.py"):
        gate.authorize("C001")


def test_research_seal_binds_signal_engine_manifest_and_ledger(monkeypatch, tmp_path):
    candidates = tmp_path / "candidates"
    validation = candidates / "C001" / "results_validation.json"
    validation.parent.mkdir(parents=True)
    spec = validation.parent / "spec.md"
    signal = validation.parent / "signal.py"
    engine = tmp_path / "engine.py"
    manifest = tmp_path / "manifest.json"
    universe = tmp_path / "universe.json"
    ledger = tmp_path / "ledger.csv"
    spec.write_text("original spec")
    signal.write_text("original")
    engine.write_text("engine")
    manifest.write_text("{}")
    universe.write_text('{"equities":["A"],"etfs":["SPY"],"sectors":{"A":"Test"}}')
    ledger.write_text("header\n")
    monkeypatch.setattr(gate, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(gate, "UNIVERSE_PATH", universe)
    monkeypatch.setattr(gate, "LEDGER_PATH", ledger)
    monkeypatch.setattr(gate, "CANDIDATES_DIR", candidates)
    monkeypatch.setattr(gate, "ENGINE_PATHS", (engine,))
    monkeypatch.setattr(gate, "ENVIRONMENT_PATHS", (engine,))
    monkeypatch.setattr(gate, "_path_committed", lambda path: True)
    monkeypatch.setattr(gate, "git_head", lambda: "abc123")
    monkeypatch.setattr(gate, "_ledger_history_append_only", lambda commit: None)
    validation.write_text(
        json.dumps(
            {
                "candidate_id": "C001",
                "gate1": {"pass": True},
                "gate2": {"pass": True},
                "research_identity": gate.research_identity(["C001"]),
            }
        )
    )
    entry = {
        "signal_sha256": gate.spec_sha256(signal),
        "engine_sha256": gate.engine_sha256(),
        "engine_commit": "abc123",
        "environment_sha256": gate.environment_sha256(),
        "data_manifest_sha256": gate.spec_sha256(manifest),
        "universe_sha256": gate.spec_sha256(universe),
        "validation_results_sha256": gate.spec_sha256(validation),
        "ledger_sha256": gate.spec_sha256(ledger),
        "ledger_bytes": ledger.stat().st_size,
        "origin": "G3",
        "holdout_end": "2030-01-01",
    }
    seal = gate._verify_research_seal("C001", entry, signal)
    assert seal["ledger_sha256"] == gate.spec_sha256(ledger)
    signal.write_text("tampered")
    with pytest.raises(RuntimeError, match=r"different signal|signal_sha256 mismatch"):
        gate._verify_research_seal("C001", entry, signal)
    signal.write_text("original")
    spec.write_text("changed after validation")
    with pytest.raises(RuntimeError, match=r"different signal|engine|data input"):
        gate.validation_result(validation, "C001")


def test_research_seal_rejects_runtime_version_or_universe_change(monkeypatch, tmp_path):
    candidates = tmp_path / "candidates"
    validation = candidates / "C001" / "results_validation.json"
    validation.parent.mkdir(parents=True)
    spec = validation.parent / "spec.md"
    signal = validation.parent / "signal.py"
    engine = tmp_path / "engine.py"
    manifest = tmp_path / "manifest.json"
    universe = tmp_path / "universe.json"
    ledger = tmp_path / "ledger.csv"
    for path, content in (
        (spec, "spec"),
        (signal, "signal"),
        (engine, "engine"),
        (manifest, "{}"),
        (
            universe,
            '{"equities":["A"],"etfs":["SPY"],"sectors":{"A":"Test"}}',
        ),
        (ledger, "header\n"),
    ):
        path.write_text(content)
    monkeypatch.setattr(gate, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(gate, "UNIVERSE_PATH", universe)
    monkeypatch.setattr(gate, "LEDGER_PATH", ledger)
    monkeypatch.setattr(gate, "CANDIDATES_DIR", candidates)
    monkeypatch.setattr(gate, "ENGINE_PATHS", (engine,))
    monkeypatch.setattr(gate, "ENVIRONMENT_PATHS", (engine,))
    monkeypatch.setattr(gate, "RUNTIME_PACKAGES", ("numpy",))
    monkeypatch.setattr(gate, "_path_committed", lambda path: True)
    monkeypatch.setattr(gate, "git_head", lambda: "abc123")
    monkeypatch.setattr(gate, "_ledger_history_append_only", lambda commit: None)
    validation.write_text(
        json.dumps(
            {
                "candidate_id": "C001",
                "gate1": {"pass": True},
                "gate2": {"pass": True},
                "research_identity": gate.research_identity(["C001"]),
            }
        )
    )
    entry = {
        "signal_sha256": gate.spec_sha256(signal),
        "engine_sha256": gate.engine_sha256(),
        "engine_commit": "abc123",
        "environment_sha256": gate.environment_sha256(),
        "data_manifest_sha256": gate.spec_sha256(manifest),
        "universe_sha256": gate.spec_sha256(universe),
        "validation_results_sha256": gate.spec_sha256(validation),
        "ledger_sha256": gate.spec_sha256(ledger),
        "ledger_bytes": ledger.stat().st_size,
        "origin": "G3",
        "holdout_end": "2030-01-01",
    }
    real_version = gate.importlib.metadata.version
    monkeypatch.setattr(
        gate.importlib.metadata,
        "version",
        lambda package: "changed" if package == "numpy" else real_version(package),
    )
    with pytest.raises(RuntimeError, match=r"different signal|environment_sha256 mismatch"):
        gate._verify_research_seal("C001", entry, signal)
    monkeypatch.setattr(gate.importlib.metadata, "version", real_version)
    universe.write_text("tampered")
    with pytest.raises(RuntimeError, match=r"different signal|universe|data input"):
        gate._verify_research_seal("C001", entry, signal)


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"candidate_id": "C001", "gate1": {"pass": False}, "gate2": {"pass": True}}, "gate1"),
        ({"candidate_id": "C001", "gate1": {"pass": True}}, "gate2"),
        ({"candidate_id": "C999", "gate1": {"pass": True}, "gate2": {"pass": True}}, "identity"),
    ],
)
def test_validation_promotion_requires_identity_and_both_passes(tmp_path, payload, message):
    path = tmp_path / "results_validation.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(RuntimeError, match=message):
        gate.validation_result(path, "C001")


def test_validation_promotion_rejects_missing_or_nonfinite_artifact(tmp_path):
    path = tmp_path / "results_validation.json"
    with pytest.raises(RuntimeError, match="no results"):
        gate.validation_result(path, "C001")
    path.write_text(
        '{"candidate_id":"C001","gate1":{"pass":true},"gate2":{"pass":true},"metric":NaN}'
    )
    with pytest.raises(RuntimeError, match="non-finite"):
        gate.validation_result(path, "C001")


def test_ledger_git_history_must_be_byte_append_only(monkeypatch, tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    ledger = tmp_path / "ledger.csv"
    ledger.write_text("header\nrow1\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "ledger.csv"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "anchor"], check=True)
    anchor = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    ledger.write_text("header\nrow1\nrow2\n")
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qam", "append"], check=True)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gate, "LEDGER_PATH", ledger)
    gate._ledger_history_append_only(anchor)

    ledger.write_text("header\nrewritten\n")
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qam", "rewrite"], check=True)
    with pytest.raises(RuntimeError, match="not append-only"):
        gate._ledger_history_append_only(anchor)


def test_ledger_anchor_must_be_ancestor_of_head(monkeypatch, tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    ledger = tmp_path / "ledger.csv"
    ledger.write_text("header\n")
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gate, "LEDGER_PATH", ledger)
    real_run = subprocess.run

    def run(args, *pargs, **kwargs):
        if "merge-base" in args:
            return subprocess.CompletedProcess(args, 1)
        return real_run(args, *pargs, **kwargs)

    monkeypatch.setattr(gate.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="not an ancestor"):
        gate._ledger_history_append_only("deadbeef")


def test_record_results_rejects_nonfinite_json(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "CANDIDATES_DIR", tmp_path)
    token = "test-token"
    gate._ISSUED[token] = gate._Capability("holdout", "C001", "2026-12-31")
    with pytest.raises(RuntimeError, match="strict JSON"):
        gate.record_results("C001", {"sr": float("nan")}, token)


def test_g1_access_log_is_atomic_and_concurrency_safe(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(gate, "CANDIDATES_DIR", tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        tokens = list(pool.map(lambda _: gate.authorize_g1_generation(), range(16)))
    assert len(set(tokens)) == 16
    events = json.loads((tmp_path / "g1_access_log.json").read_text())
    assert len(events) == 16
    assert all(event["window_start"] == "2026-02-01" for event in events)

    (tmp_path / "g1_access_log.json").write_text("{}")
    with pytest.raises(RuntimeError, match="expected an event list"):
        gate.authorize_g1_generation()


def test_path_committed_requires_clean_head_blob(monkeypatch, tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    tracked = tmp_path / "spec.md"
    tracked.write_text("v1")
    subprocess.run(["git", "-C", str(tmp_path), "add", "spec.md"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "spec"], check=True)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    assert gate._path_committed(tracked)
    tracked.write_text("v2")
    assert not gate._path_committed(tracked)
    subprocess.run(["git", "-C", str(tmp_path), "add", "spec.md"], check=True)
    assert not gate._path_committed(tracked)  # staged-only is still not HEAD
    untracked = tmp_path / "new.md"
    untracked.write_text("new")
    assert not gate._path_committed(untracked)


def test_registry_history_is_append_only_and_deleted_markers_remain_spent(monkeypatch, tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    registry = tmp_path / "candidates" / "registry.json"
    marker = tmp_path / "candidates" / "C001" / "holdout_access.json"
    marker.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"C001": {"seal": "one"}}))
    marker.write_text("{}")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "register"], check=True)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gate, "REGISTRY_PATH", registry)
    gate._registry_history_append_only()

    marker.unlink()
    registry.write_text(json.dumps({"C001": {"seal": "one"}, "C002": {"seal": "two"}}))
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "append"], check=True)
    gate._registry_history_append_only()
    assert gate._path_ever_committed(marker)

    registry.write_text(json.dumps({"C001": {"seal": "rewritten"}, "C002": {"seal": "two"}}))
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "rewrite"], check=True)
    with pytest.raises(RuntimeError, match="rewrote existing entries"):
        gate._registry_history_append_only()


def test_cache_manifest_tampering_is_rejected(monkeypatch, tmp_path):
    frame = pd.DataFrame(
        {"close": [1.0, 2.0], "adjclose": [1.0, 2.0]},
        index=pd.to_datetime(["2023-01-03", "2023-01-04"]),
    )
    path = _write_cache(monkeypatch, tmp_path, "AAA", frame)
    assert len(qdata.load_panel(tickers=["AAA"])) == 2
    path.write_bytes(path.read_bytes() + b"tamper")
    with pytest.raises(RuntimeError, match=r"verification|unreadable"):
        qdata.load_panel(tickers=["AAA"])


def test_explicit_panel_tickers_require_complete_cache(monkeypatch, tmp_path):
    frame = pd.DataFrame(
        {"close": [1.0, 2.0], "adjclose": [1.0, 2.0]},
        index=pd.to_datetime(["2023-01-03", "2023-01-04"]),
    )
    _write_cache(monkeypatch, tmp_path, "AAA", frame)
    with pytest.raises(RuntimeError, match="missing 1 requested tickers: BBB"):
        qdata.load_panel(tickers=["AAA", "BBB"])


def test_same_size_restored_mtime_tampering_is_rehashed(monkeypatch, tmp_path):
    frame = pd.DataFrame(
        {"close": [1.0, 2.0], "adjclose": [1.0, 2.0]},
        index=pd.to_datetime(["2023-01-03", "2023-01-04"]),
    )
    path = _write_cache(monkeypatch, tmp_path, "AAA", frame)
    qdata.load_panel(tickers=["AAA"])
    original_stat = path.stat()
    payload = bytearray(path.read_bytes())
    payload[len(payload) // 2] ^= 1
    path.write_bytes(payload)
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    with pytest.raises(RuntimeError, match=r"verification|unreadable"):
        qdata.load_panel(tickers=["AAA"])


def test_gate3_pooled_statistic_excludes_pre_registered_train_history():
    from types import SimpleNamespace

    index = pd.to_datetime(["1990-01-02", "2005-01-03", "2010-01-04", "2024-01-02", "2024-01-03"])
    result = SimpleNamespace(returns_net=pd.Series([100.0, 0.01, -0.01, 0.02, 0.01], index=index))
    scored = _score_result("C000", result, (2, 0.1))
    assert scored["pooled"]["n_obs"] == 4
    assert scored["dsr"]["dsr"] is None
    assert "historical validation-labeled rows" in scored["dsr"]["unavailable_reason"]
    assert scored["gate3"]["dsr_gt_0.95"] is False
    assert scored["gate3"]["pass"] is False
