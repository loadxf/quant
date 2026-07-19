"""Stable JSON output combining metrics, verdict, and simulation."""

from __future__ import annotations

import dataclasses
from typing import Any

from quantlab.metrics.core import Metrics
from quantlab.metrics.scorecard import Verdict
from quantlab.prop.outcomes import MonteCarloReport

SCHEMA_VERSION = 1


def combined_json(
    metrics: Metrics,
    verdict: Verdict | None = None,
    mc: MonteCarloReport | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "metrics": dataclasses.asdict(metrics),
    }
    if verdict is not None:
        payload["verdict"] = verdict.to_json_dict()
    if mc is not None:
        payload["prop_simulation"] = mc.to_json_dict()
    return payload
