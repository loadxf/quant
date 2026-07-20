"""Presentation-layer batch (M10.g): the same numbers on every surface.

One deterministic bundle (small log + topstep_50k, fixed seeds) rendered
to terminal, HTML, and JSON; the assertions pin the classic
display-disagreement bug: a headline number that appears on one surface
must appear, identically formatted, on the others.
"""

from __future__ import annotations

import json

import pytest
from rich.console import Console

from quantlab.metrics.core import compute_metrics
from quantlab.metrics.reality import compute_reality_check
from quantlab.metrics.scorecard import compute_scorecard
from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.prop.registry import load_firm
from quantlab.report.format import money, pct
from quantlab.report.html import build_html_report
from quantlab.report.jsonout import combined_json
from quantlab.report.terminal import render_reality, render_report
from quantlab.schema.io import write_trade_log

from ..conftest import random_log
from ..prop.conftest import day_trades, simple


def _render_text(*render_calls) -> str:
    console = Console(record=True, width=200, force_terminal=False)
    for fn, arg in render_calls:
        fn(arg, console)
    return console.export_text()


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    log = random_log(n_days=70, mean=40.0, std=300.0, seed=7, with_excursions=True)
    firm = load_firm("topstep_50k")
    metrics = compute_metrics(log, starting_equity=firm.account_size)
    mc = run_monte_carlo(log, firm, MCConfig(n_paths=200, seed=5))
    rc = compute_reality_check(
        log, firm=firm, mc_paths=100, seed=5, baseline_mc=mc, outer=6, inner_paths=50
    )
    verdict = compute_scorecard(
        log,
        metrics,
        decay=rc.decay,
        deflated=rc.deflated,
        clustering=rc.clustering,
        regime=rc.regime,
    )
    html_path = tmp_path_factory.mktemp("presentation") / "report.html"
    build_html_report(
        log, metrics, verdict, html_path, mc=mc, firm=firm, reality=rc, title="Presentation test"
    )
    return {
        "log": log,
        "firm": firm,
        "metrics": metrics,
        "mc": mc,
        "rc": rc,
        "verdict": verdict,
        "html": html_path.read_text(),
        "terminal": _render_text((render_report, mc), (render_reality, rc)),
        "json": combined_json(metrics, verdict, mc, reality=rc),
    }


class TestCrossSurfaceAgreement:
    def test_pass_prob_identical_everywhere(self, bundle) -> None:
        eco = bundle["mc"].economics
        shown = pct(eco.pass_prob)
        assert shown in bundle["terminal"]
        assert shown in bundle["html"]
        assert bundle["json"]["prop_simulation"]["economics"]["pass_prob"] == eco.pass_prob

    def test_expected_net_identical_everywhere(self, bundle) -> None:
        eco = bundle["mc"].economics
        shown = money(eco.expected_net, decimals=0)
        assert shown in bundle["terminal"]
        assert shown in bundle["html"]
        assert bundle["json"]["prop_simulation"]["economics"]["expected_net"] == eco.expected_net

    def test_grade_identical_everywhere(self, bundle) -> None:
        overall = bundle["verdict"].overall
        assert bundle["json"]["verdict"]["overall"] == overall
        assert f'class="g g-{overall}">{overall}<' in bundle["html"]

    def test_risk_of_ruin_identical(self, bundle) -> None:
        eco = bundle["mc"].economics
        assert pct(eco.risk_of_ruin_funded) in bundle["terminal"]
        assert (
            bundle["json"]["prop_simulation"]["economics"]["risk_of_ruin_funded"]
            == eco.risk_of_ruin_funded
        )


class TestNewSectionsRender:
    def test_regime_section_on_all_surfaces(self, bundle) -> None:
        assert "Vol regimes" in bundle["terminal"]
        assert "Volatility regimes" in bundle["html"]
        assert bundle["json"]["reality_check"]["regime"]["tested"] is True

    def test_sampling_band_on_all_surfaces(self, bundle) -> None:
        assert "Source-log sampling uncertainty" in bundle["terminal"]
        assert "Source-log sampling uncertainty" in bundle["html"]
        band = bundle["json"]["reality_check"]["sampling_uncertainty"]
        assert band["n_outer"] == 6
        shown = pct(bundle["rc"].sampling.pass_prob_quantiles["p50"])
        assert shown in bundle["terminal"]
        assert shown in bundle["html"]

    def test_reactivation_note_renders(self, bundle) -> None:
        # topstep presets define Back2Funded, so the note must appear.
        assert "reactivation option" in bundle["terminal"]
        assert bundle["json"]["prop_simulation"]["economics"]["reactivation"] is not None

    def test_clustering_and_voltarget_sections(self, bundle) -> None:
        assert "Volatility clustering" in bundle["html"]
        assert bundle["json"]["reality_check"]["clustering"] is not None

    def test_html_is_self_contained(self, bundle) -> None:
        head = bundle["html"].split("<head>")[1].split("</head>")[0]
        assert "http" not in head.replace("http://www.w3.org", "")


class TestInsufficientDataBranches:
    def test_short_log_renders_skips_not_crashes(self) -> None:
        log = day_trades([[simple(100.0 + i)] for i in range(12)])
        rc = compute_reality_check(log, mc_paths=50, seed=1, outer=0)
        text = _render_text((render_reality, rc))
        assert "skipped" in text or "insufficient" in text
        assert rc.regime is not None and not rc.regime.tested

    def test_overhead_row_renders_when_set(self) -> None:
        from quantlab.prop.config import with_fee_overrides

        firm = with_fee_overrides(load_firm("topstep_50k"), extra_monthly=39.0, per_payout=30.0)
        log = random_log(n_days=40, mean=40.0, std=200.0, seed=3)
        mc = run_monte_carlo(log, firm, MCConfig(n_paths=50, seed=1))
        text = _render_text((render_report, mc))
        assert "overheads included" in text


class TestFrontierRenderers:
    def test_frontier_and_multiaccount_render(self) -> None:
        from quantlab.prop.frontier import compute_multiaccount, compute_scale_frontier
        from quantlab.report.terminal import render_frontier, render_multiaccount

        log = random_log(n_days=50, mean=40.0, std=250.0, seed=2)
        firm = load_firm("topstep_50k")
        fr = compute_scale_frontier(log, firm, MCConfig(n_paths=80, seed=1), scales=(0.5, 1.0))
        mc = run_monte_carlo(log, firm, MCConfig(n_paths=80, seed=1))
        ma = compute_multiaccount(mc, k_list=(2,))
        text = _render_text((render_frontier, fr), (render_multiaccount, ma))
        assert "Scale frontier" in text
        assert f"x{fr.best_ev_scale:g}" in text
        assert "Multi-account" in text


class TestCliEndToEnd:
    def test_report_command_all_surfaces_agree(self, tmp_path) -> None:
        from typer.testing import CliRunner

        from quantlab.cli.app import app

        parquet = tmp_path / "t.parquet"
        write_trade_log(random_log(n_days=60, mean=40.0, std=300.0, seed=7), parquet)
        html_out = tmp_path / "r.html"
        json_out = tmp_path / "r.json"
        result = CliRunner().invoke(
            app,
            [
                "report",
                str(parquet),
                "--firm",
                "topstep_50k",
                "--paths",
                "150",
                "--seed",
                "5",
                "--outer",
                "4",
                "--inner-paths",
                "40",
                "-o",
                str(html_out),
                "--json",
                str(json_out),
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(json_out.read_text())
        html = html_out.read_text()
        assert payload["schema_version"] == 4
        assert pct(payload["prop_simulation"]["economics"]["pass_prob"]) in html
        assert payload["reality_check"]["regime"] is not None

    def test_stress_command_table_mode(self, tmp_path) -> None:
        from typer.testing import CliRunner

        from quantlab.cli.app import app

        parquet = tmp_path / "t.parquet"
        write_trade_log(random_log(n_days=65, mean=30.0, std=250.0, seed=9), parquet)
        result = CliRunner().invoke(
            app,
            ["stress", str(parquet), "--firm", "topstep_50k", "--paths", "80", "--outer", "0"],
        )
        assert result.exit_code == 0, result.output
        assert "Cost stress" in result.output
        assert "Vol regimes" in result.output

    def test_simulate_with_accounts_flag(self, tmp_path) -> None:
        from typer.testing import CliRunner

        from quantlab.cli.app import app

        parquet = tmp_path / "t.parquet"
        write_trade_log(random_log(n_days=45, mean=30.0, std=250.0, seed=9), parquet)
        result = CliRunner().invoke(
            app,
            [
                "prop",
                "simulate",
                str(parquet),
                "--firm",
                "topstep_50k",
                "--paths",
                "80",
                "--accounts",
                "2,3",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Multi-account" in result.output


class TestReviewLoopFixes:
    """Regressions from the M10 adversarial review (cross-file pass)."""

    def test_combined_json_metrics_warnings_parity(self, bundle) -> None:
        # Was: the embedded metrics block lacked the warnings key the
        # standalone `quant metrics --json` carries.
        payload = combined_json(
            bundle["metrics"], bundle["verdict"], bundle["mc"], log=bundle["log"]
        )
        from quantlab.metrics.costs import log_caveats

        assert payload["metrics"]["warnings"] == log_caveats(bundle["log"])

    def test_report_accepts_overhead_and_ohlcv_flags(self, tmp_path) -> None:
        # Was: quant report silently reverted to zero overhead while
        # simulate/stress honored the knobs — the deliverable disagreed
        # with the CLI numbers.
        import pandas as pd
        from typer.testing import CliRunner

        from quantlab.cli.app import app

        parquet = tmp_path / "t.parquet"
        write_trade_log(random_log(n_days=60, mean=40.0, std=300.0, seed=7), parquet)
        dates = pd.bdate_range("2026-01-05", periods=60, tz="UTC")
        bars = tmp_path / "bars.csv"
        pd.DataFrame(
            {
                "datetime": dates.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": 5000.0,
                "high": 5015.0,
                "low": 4990.0,
                "close": 5005.0,
                "volume": 1,
            }
        ).to_csv(bars, index=False)
        json_out = tmp_path / "r.json"
        result = CliRunner().invoke(
            app,
            [
                "report",
                str(parquet),
                "--firm",
                "topstep_50k",
                "--paths",
                "100",
                "--outer",
                "0",
                "--extra-monthly",
                "100",
                "--per-payout-fee",
                "30",
                "--ohlcv",
                str(bars),
                "-o",
                str(tmp_path / "r.html"),
                "--json",
                str(json_out),
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(json_out.read_text())
        overhead = payload["prop_simulation"]["economics"]["overhead"]
        assert overhead["extra_monthly"] == 100.0 and overhead["per_payout"] == 30.0

    def test_market_regimes_render_in_html(self, tmp_path) -> None:
        # Was: the --ohlcv market table existed on terminal + JSON but had
        # no HTML rendering path at all.
        import pandas as pd

        from quantlab.report.html import _reality_context

        log = random_log(n_days=60, mean=40.0, std=300.0, seed=7)
        dates = pd.bdate_range("2026-01-05", periods=60, tz="UTC")
        bars = tmp_path / "bars.csv"
        pd.DataFrame(
            {
                "datetime": dates.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": 5000.0,
                "high": 5015.0,
                "low": 4990.0,
                "close": 5005.0,
                "volume": 1,
            }
        ).to_csv(bars, index=False)
        from quantlab.ingest.ohlcv import load_ohlcv

        frame, _ = load_ohlcv(bars)
        rc = compute_reality_check(log, mc_paths=50, seed=1, outer=0, ohlcv=frame)
        assert rc.regime is not None and rc.regime.market
        ctx = _reality_context(rc)
        assert ctx["market_rows"]

    def test_frontier_reuses_its_base_report(self) -> None:
        # Was: --accounts re-simulated the identical x1.0 config the
        # frontier had just run and discarded.
        from quantlab.prop.frontier import compute_scale_frontier

        log = random_log(n_days=50, mean=40.0, std=250.0, seed=2)
        firm = load_firm("topstep_50k")
        fr = compute_scale_frontier(log, firm, MCConfig(n_paths=80, seed=1), scales=(0.5, 1.0))
        assert fr.base_report is not None
        point = next(p for p in fr.points if p.scale == 1.0)
        assert fr.base_report.economics.pass_prob == point.pass_prob
        assert "base_report" not in fr.to_json_dict()

    def test_flag_names_same_regime_as_stress(self) -> None:
        # Was: the flag named the net-worst regime while the stress row
        # conditioned on the day-expectancy-worst regime.
        from quantlab.metrics.overfit import _regime_dependence
        from quantlab.metrics.regime import compute_regimes
        from tests.metrics.test_regime import _two_regime_log

        rg = compute_regimes(_two_regime_log())
        flag = _regime_dependence(rg)
        assert flag.triggered
        assert rg.worst_regime is not None and rg.worst_regime in flag.explanation


class TestWaterfallDecomposition:
    """Regression from the M10 adversarial review (line-scan pass): the
    EV-waterfall bars must sum exactly to expected_net, overheads included."""

    def _waterfall_total(self, eco, activation: float) -> float:
        from quantlab.report.charts import fig_ev_waterfall

        fig = fig_ev_waterfall(eco, activation)
        ys = fig.data[0].y
        return float(sum(v for v in ys if v is not None))

    def test_sums_to_expected_net_without_knobs(self, bundle) -> None:
        eco = bundle["mc"].economics
        total = self._waterfall_total(eco, bundle["firm"].fees.activation)
        assert total == pytest.approx(eco.expected_net, abs=1e-6)

    def test_sums_to_expected_net_with_overheads(self) -> None:
        from quantlab.prop.config import with_fee_overrides

        firm = with_fee_overrides(load_firm("topstep_50k"), extra_monthly=100.0, per_payout=30.0)
        log = random_log(n_days=80, mean=40.0, std=300.0, seed=7)
        eco = run_monte_carlo(log, firm, MCConfig(n_paths=300, seed=5)).economics
        assert eco.pass_prob > 0  # otherwise the identity is trivially 0-fee only
        total = self._waterfall_total(eco, firm.fees.activation)
        assert total == pytest.approx(eco.expected_net, abs=1e-6)
