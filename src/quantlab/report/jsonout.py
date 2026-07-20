"""Stable JSON output combining metrics, verdict, and simulation.

All payloads pass through `sanitize`, which converts non-finite floats
(inf from profit_factor/MAR on flawless logs, expected_cost_to_funded on
zero-pass strategies; NaN) into strings/None — bare Infinity/NaN tokens
are invalid RFC 8259 JSON and break jq/JSON.parse consumers."""

from __future__ import annotations

import dataclasses
import math
from typing import Any

from quantlab.metrics.core import Metrics
from quantlab.metrics.scorecard import Verdict
from quantlab.prop.outcomes import MonteCarloReport

SCHEMA_VERSION = 4  # v4: prop_simulation v4 (policy block); moves with the MC schema


def sanitize(obj: Any) -> Any:
    """Recursively replace non-finite floats: inf -> "inf", nan -> None."""
    if isinstance(obj, float):
        if math.isinf(obj):
            return "inf" if obj > 0 else "-inf"
        if math.isnan(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {key: sanitize(value) for key, value in obj.items()}
    if isinstance(obj, list | tuple):
        return [sanitize(value) for value in obj]
    return obj


def combined_json(
    metrics: Metrics,
    verdict: Verdict | None = None,
    mc: MonteCarloReport | None = None,
    reality: Any | None = None,
    log: Any | None = None,
) -> dict[str, Any]:
    # The metrics block carries its own version marker AND the same
    # caveats list as the standalone `quant metrics --json`, so consumers
    # of the embedded and standalone forms parse one identical shape.
    metrics_block: dict[str, Any] = {"schema_version": 1, **dataclasses.asdict(metrics)}
    if log is not None:
        from quantlab.metrics.costs import log_caveats

        metrics_block["warnings"] = log_caveats(log)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "metrics": metrics_block,
    }
    if verdict is not None:
        payload["verdict"] = verdict.to_json_dict()
    if mc is not None:
        payload["prop_simulation"] = mc.to_json_dict()
    if reality is not None:
        payload["reality_check"] = reality.to_json_dict()
    return sanitize(payload)
