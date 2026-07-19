from __future__ import annotations

import json

from quantlab.metrics.core import compute_metrics
from quantlab.metrics.scorecard import compute_scorecard
from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.prop.registry import load_firm
from quantlab.report.html import build_html_report
from quantlab.report.jsonout import combined_json

from ..conftest import random_log


class TestHtmlReport:
    def test_self_contained_html(self, tmp_path) -> None:
        log = random_log(n_days=60, seed=41, with_excursions=True)
        metrics = compute_metrics(log)
        verdict = compute_scorecard(log, metrics)
        firm = load_firm("topstep_50k")
        mc = run_monte_carlo(log, firm, MCConfig(n_paths=300, seed=1, sample_paths_kept=50))
        out = tmp_path / "report.html"
        build_html_report(log, metrics, verdict, out, mc=mc, firm=firm)

        html = out.read_text()
        assert html.startswith("<!doctype html>")
        assert html.count("window.PlotlyConfig") == 1  # plotly.js inlined exactly once
        assert "The Verdict" in html
        assert "Expected value per attempt" in html
        assert "Firm rules appendix" in html
        assert "help.topstep.com" in html  # sources present
        assert "http" not in html.split("<head>")[1].split("</head>")[0].replace(
            "http://www.w3.org", ""
        )  # no external loads in head

    def test_verdict_only_report(self, tmp_path) -> None:
        log = random_log(n_days=40, seed=42)
        metrics = compute_metrics(log)
        verdict = compute_scorecard(log, metrics)
        out = tmp_path / "verdict.html"
        build_html_report(log, metrics, verdict, out)
        html = out.read_text()
        assert "Prop-firm simulation" not in html
        assert "The Verdict" in html


class TestCombinedJson:
    def test_serializable_and_shaped(self) -> None:
        log = random_log(n_days=60, seed=43, with_excursions=True)
        metrics = compute_metrics(log)
        verdict = compute_scorecard(log, metrics)
        mc = run_monte_carlo(log, load_firm("apex40_50k_eod"), MCConfig(n_paths=200, seed=2))
        payload = combined_json(metrics, verdict, mc)
        text = json.dumps(payload, default=str)  # must not raise
        parsed = json.loads(text)
        assert parsed["schema_version"] == 2
        assert set(parsed) == {"schema_version", "metrics", "verdict", "prop_simulation"}
        assert parsed["prop_simulation"]["economics"]["pass_prob"] >= 0.0
        assert parsed["verdict"]["overall"] in "ABCDF"
