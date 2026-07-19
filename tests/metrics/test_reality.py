"""Reality-check orchestrator + report integration tests."""

from __future__ import annotations

import json

from quantlab.metrics.core import compute_metrics
from quantlab.metrics.reality import compute_reality_check
from quantlab.metrics.scorecard import compute_scorecard
from quantlab.prop.registry import load_firm
from quantlab.report.jsonout import combined_json, sanitize
from tests.prop.conftest import day_trades, simple


def _log():
    rows = []
    for i in range(60):
        rows.append([simple(-140.0 if i % 3 == 2 else 130.0)])
    return day_trades(rows)


class TestRealityCheck:
    def test_end_to_end_serializable(self) -> None:
        firm = load_firm("topstep_50k")
        rc = compute_reality_check(_log(), firm=firm, trials=3, mc_paths=200, seed=5)
        payload = sanitize(rc.to_json_dict())
        json.dumps(payload)  # must not raise (inf/nan sanitized)
        assert payload["deflated"]["dsr"] is not None
        assert len(payload["haircuts"]) == 4
        assert payload["costs"]["grid"]

    def test_trials_warning_at_default(self) -> None:
        rc = compute_reality_check(_log(), mc_paths=100, seed=5)
        assert any("n_trials=1" in w for w in rc.warnings)

    def test_combined_json_reality_key(self) -> None:
        log = _log()
        metrics = compute_metrics(log)
        verdict = compute_scorecard(log, metrics)
        rc = compute_reality_check(log, seed=5)
        payload = combined_json(metrics, verdict, reality=rc)
        assert payload["schema_version"] == 2
        assert "reality_check" in payload
        json.dumps(payload)
