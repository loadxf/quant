from __future__ import annotations

import edgelab.gates as gates
import numpy as np
import pandas as pd
import pytest
from edgelab.signals import compute_declared_signal


def _fields(rows: int = 80, names: int = 40) -> dict[str, object]:
    rng = np.random.default_rng(23)
    index = pd.bdate_range("2018-01-02", periods=rows)
    columns = [f"S{i:03d}" for i in range(names)]
    close = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0, 0.01, (rows, names)), axis=0)),
        index=index,
        columns=columns,
    )
    etf_columns = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
    etf = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0, 0.008, (rows, len(etf_columns))), axis=0)),
        index=index,
        columns=etf_columns,
    )
    return {
        "open": close * (1 + rng.normal(0, 0.001, close.shape)),
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "adjclose": close,
        "volume": pd.DataFrame(rng.lognormal(12, 0.5, close.shape), index=index, columns=columns),
        "etf_adjclose": etf,
        "sectors": {name: "Materials" for name in columns},
    }


def _candidate_ids() -> list[str]:
    return sorted(
        path.name for path in gates.CANDIDATES_DIR.iterdir() if (path / "signal.py").is_file()
    )


@pytest.mark.parametrize("candidate_id", _candidate_ids())
def test_every_trusted_handler_is_causal_at_every_boundary(candidate_id):
    fields = _fields()
    declaration = gates.signal_metadata(candidate_id)
    full = compute_declared_signal(fields, declaration)
    gates.audit_signal_causality(
        None,
        fields,
        full_signal=full,
        compute=lambda prefix: compute_declared_signal(prefix, declaration),
    )


def test_declaration_dispatches_by_kind_not_candidate_id(monkeypatch, tmp_path):
    candidate = tmp_path / "C999"
    candidate.mkdir()
    (candidate / "signal.py").write_text(
        'SIGNAL_KIND = "plain_reversal"\n'
        'ORIGIN = "G4"\n'
        "RETURN_WINDOW = 1\n"
        'PERTURBATIONS = ("RETURN_WINDOW",)\n'
    )
    monkeypatch.setattr(gates, "CANDIDATES_DIR", tmp_path)
    fields = _fields(rows=20, names=4)
    result = gates.compute_signal_isolated("C999", fields, causality_audit=True)
    expected = -fields["adjclose"].pct_change(fill_method=None)
    assert result.equals(expected)


@pytest.mark.parametrize(
    "source,error",
    [
        (
            'SIGNAL_KIND = "plain_reversal"\nORIGIN = "G4"\nRETURN_WINDOW = 1\n'
            'PERTURBATIONS = ("RETURN_WINDOW",)\nimport os\n',
            "only a docstring and literal declarations",
        ),
        (
            'SIGNAL_KIND = "plain_reversal"\nORIGIN = "G4"\nRETURN_WINDOW = 1\n'
            'UNUSED = 5\nPERTURBATIONS = ("RETURN_WINDOW",)\n',
            "unknown signal declaration constants",
        ),
        (
            "def compute_signal(fields):\n    return fields['adjclose']\n",
            "only a docstring and literal declarations",
        ),
    ],
)
def test_promotable_metadata_rejects_executable_or_unknown_source(
    monkeypatch, tmp_path, source, error
):
    candidate = tmp_path / "C999"
    candidate.mkdir()
    (candidate / "signal.py").write_text(source)
    monkeypatch.setattr(gates, "CANDIDATES_DIR", tmp_path)
    with pytest.raises(RuntimeError, match=error):
        gates.signal_metadata("C999")


def test_declaration_rejects_unused_perturbation_override():
    declaration = {
        "SIGNAL_KIND": "plain_reversal",
        "ORIGIN": "G4",
        "RETURN_WINDOW": 1,
        "PERTURBATIONS": ("RETURN_WINDOW",),
    }
    with pytest.raises(RuntimeError, match="undeclared, routing"):
        compute_declared_signal(_fields(rows=20, names=4), declaration, {"UNUSED": 2})


@pytest.mark.parametrize("name", ["SIGNAL_KIND", "ORIGIN", "UNIVERSE", "HOLDOUT_END"])
def test_declaration_overrides_cannot_change_identity_or_routing(name):
    declaration = {
        "SIGNAL_KIND": "plain_reversal",
        "ORIGIN": "G4",
        "RETURN_WINDOW": 1,
        "PERTURBATIONS": ("RETURN_WINDOW",),
    }
    with pytest.raises(RuntimeError, match="routing"):
        compute_declared_signal(_fields(rows=20, names=4), declaration, {name: "changed"})


def test_base_expression_must_belong_to_the_frozen_grammar(monkeypatch, tmp_path):
    candidate = tmp_path / "C999"
    candidate.mkdir()
    (candidate / "signal.py").write_text(
        'SIGNAL_KIND = "expression"\nORIGIN = "G2"\n'
        'EXPR = ("roll_std", "rng", 64)\nPERTURBATIONS = ("EXPR",)\n'
    )
    monkeypatch.setattr(gates, "CANDIDATES_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="outside the frozen grammar"):
        gates.signal_metadata("C999")


def test_expression_perturbations_allow_bounded_non_grammar_windows():
    declaration = {
        "SIGNAL_KIND": "expression",
        "ORIGIN": "G2",
        "EXPR": ("roll_std", "rng", 63),
        "PERTURBATIONS": ("EXPR",),
    }
    result = compute_declared_signal(
        _fields(rows=100, names=4), declaration, {"EXPR": ("roll_std", "rng", 79)}
    )
    assert result.notna().any().any()
    with pytest.raises(RuntimeError, match="too large"):
        compute_declared_signal(
            _fields(rows=100, names=4),
            declaration,
            {"EXPR": ("roll_std", "rng", 1000)},
        )
