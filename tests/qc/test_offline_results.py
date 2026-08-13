"""API-free QuantConnect Cloud browser workflow and project readiness."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import quantlab.cli.cloud_cmds as cloud_cmds
from quantlab.errors import QuantLabError
from quantlab.qc.results import (
    load_result_file,
    parse_closed_trades,
    parse_embedded_equity,
    parse_equity_marks,
)
from quantlab.schema.io import read_trade_log

PROJECTS = ["sma_cross_futures", "orb_equity", "custom_data_demo"]
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "backtest_result_sample.json"


def _pascalize(value):
    if isinstance(value, dict):
        return {key[:1].upper() + key[1:]: _pascalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_pascalize(item) for item in value]
    return value


def _strategy_path(project: str) -> Path:
    return ROOT / "cloud" / "strategies" / project / "main.py"


def _forbid_api(monkeypatch) -> None:
    class Exploding:
        def __init__(self) -> None:
            raise AssertionError("QCClient constructed in downloaded-results mode")

    monkeypatch.setattr(cloud_cmds, "QCClient", Exploding)
    monkeypatch.delenv("QC_USER_ID", raising=False)
    monkeypatch.delenv("QC_API_TOKEN", raising=False)


class TestCloudProjectReadiness:
    @pytest.mark.parametrize("project", PROJECTS)
    def test_main_is_standalone_cloud_project_within_free_file_limit(self, project: str) -> None:
        path = _strategy_path(project)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        algorithms = [
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and any(isinstance(base, ast.Name) and base.id == "QCAlgorithm" for base in node.bases)
        ]
        assert len(algorithms) == 1
        assert any(
            isinstance(node, ast.FunctionDef) and node.name == "initialize"
            for node in algorithms[0].body
        )
        assert "from AlgorithmImports import *" in source
        assert "from quantlab" not in source
        assert "import quantlab" not in source
        assert "QC_USER_ID" not in source
        assert "QC_API_TOKEN" not in source
        assert "QCClient" not in source
        assert path.stat().st_size < 32 * 1024

    @pytest.mark.parametrize("project", PROJECTS)
    def test_local_config_is_valid_but_not_required_by_browser_project(self, project: str) -> None:
        config = json.loads(
            (ROOT / "cloud" / "strategies" / project / "config.json").read_text(encoding="utf-8")
        )
        assert config["algorithm-language"] == "Python"
        assert isinstance(config["parameters"], dict)
        assert isinstance(config["description"], str) and config["description"].strip()

    @pytest.mark.parametrize("project", ["sma_cross_futures", "orb_equity"])
    def test_free_tier_projects_do_not_use_object_store(self, project: str) -> None:
        assert "object_store" not in _strategy_path(project).read_text(encoding="utf-8")


class TestDownloadedResultsCli:
    def test_imports_cloud_ui_download_without_credentials(self, monkeypatch, tmp_path) -> None:
        _forbid_api(monkeypatch)
        output = tmp_path / "trades.parquet"
        result = CliRunner().invoke(
            cloud_cmds.cloud_app,
            [
                "results",
                "--downloaded-results",
                str(FIXTURE),
                "--output",
                str(output),
                "--chart",
            ],
        )
        assert result.exit_code == 0, result.output
        log = read_trade_log(output)
        assert len(log.trades) == 3
        assert log.has_excursions
        assert (tmp_path / "trades.equity.csv").exists()
        assert "Download Results JSON" in " ".join(result.output.split())

    def test_from_json_alias_remains_supported(self, monkeypatch, tmp_path) -> None:
        _forbid_api(monkeypatch)
        output = tmp_path / "trades.parquet"
        result = CliRunner().invoke(
            cloud_cmds.cloud_app,
            ["results", "--from-json", str(FIXTURE), "--output", str(output)],
        )
        assert result.exit_code == 0, result.output
        assert output.exists()

    def test_chart_error_points_to_correct_ui_download(self, monkeypatch, tmp_path) -> None:
        _forbid_api(monkeypatch)
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        del payload["charts"]
        without_chart = tmp_path / "download.json"
        without_chart.write_text(json.dumps(payload), encoding="utf-8")
        result = CliRunner().invoke(
            cloud_cmds.cloud_app,
            [
                "results",
                "--downloaded-results",
                str(without_chart),
                "--chart",
                "--output",
                str(tmp_path / "trades.parquet"),
            ],
        )
        assert result.exit_code != 0
        assert "Overview > Download Results" in str(result.exception)

    def test_source_flags_are_mutually_exclusive(self, monkeypatch) -> None:
        _forbid_api(monkeypatch)
        result = CliRunner().invoke(
            cloud_cmds.cloud_app,
            [
                "results",
                "--downloaded-results",
                str(FIXTURE),
                "--project-id",
                "1",
            ],
        )
        assert result.exit_code != 0
        assert "one source" in str(result.exception)

    def test_missing_source_names_browser_and_optional_api_routes(self, monkeypatch) -> None:
        _forbid_api(monkeypatch)
        result = CliRunner().invoke(cloud_cmds.cloud_app, ["results"])
        assert result.exit_code != 0
        assert "--downloaded-results" in str(result.exception)

    def test_save_json_is_rejected_for_already_local_download(self, monkeypatch, tmp_path) -> None:
        _forbid_api(monkeypatch)
        result = CliRunner().invoke(
            cloud_cmds.cloud_app,
            [
                "results",
                "--downloaded-results",
                str(FIXTURE),
                "--save-json",
                str(tmp_path / "copy.json"),
            ],
        )
        assert result.exit_code != 0
        assert "already local" in str(result.exception)


class TestEmbeddedEquity:
    def test_reads_strategy_equity_from_download_results(self) -> None:
        curve = parse_embedded_equity(load_result_file(FIXTURE))
        assert curve is not None
        assert len(curve.points) == 3
        assert curve.points[-1].equity == pytest.approx(100_110.1)

    def test_rejects_invalid_charts_shape(self) -> None:
        with pytest.raises(QuantLabError, match="charts"):
            parse_embedded_equity({"charts": "not an object"})

    def test_accepts_pascal_case_ui_serializer_variant(self, tmp_path) -> None:
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        path = tmp_path / "pascal-download.json"
        path.write_text(json.dumps({"Backtest": _pascalize(raw)}), encoding="utf-8")
        backtest = load_result_file(path)
        log, skipped = parse_closed_trades(backtest)
        curve = parse_embedded_equity(backtest)
        assert len(log.trades) == 3
        assert skipped == []
        assert curve is not None and len(curve.points) == 3

    def test_legacy_equity_marks_remain_importable(self) -> None:
        curve = parse_equity_marks(
            {
                "equityMarks": [
                    ["2024-01-02T15:00:00Z", 50_000.0],
                    ["bad-time", 1.0],
                    ["2024-01-02T16:00:00Z", 50_250.0],
                ]
            }
        )
        assert curve is not None
        assert [point.equity for point in curve.points] == [50_000.0, 50_250.0]
