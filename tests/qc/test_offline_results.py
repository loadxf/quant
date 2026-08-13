"""The API-free results path: in-algorithm export block -> `results --from-json`.

The export block embedded in every example strategy serializes
TradeBuilder closed trades into the same JSON shape as the REST
backtests/read response. These tests execute that block (extracted by
AST, like TestStrategiesParse) against a fake algorithm and feed its
Object Store payload through the real CLI — proving the browser-only
flow round-trips without QC credentials or network.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import quantlab.cli.cloud_cmds as cloud_cmds
from quantlab.errors import QuantLabError
from quantlab.qc.results import parse_equity_marks
from quantlab.schema.io import read_trade_log
from quantlab.schema.trade import Side

PROJECTS = ["sma_cross_futures", "orb_equity", "custom_data_demo"]
EXPORT_MARKER = "# --- quantlab export: API-free results retrieval"
EXPORT_METHODS = [
    "_quantlab_start_export",
    "_quantlab_sample_equity",
    "on_end_of_algorithm",
    "_quantlab_export",
]


def _strategy_source(project: str) -> str:
    root = Path(__file__).resolve().parents[2] / "cloud" / "strategies" / project
    return (root / "main.py").read_text(encoding="utf-8")


def _strategy_method(project: str, method: str):
    tree = ast.parse(_strategy_source(project))
    function = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == method
    )
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace = {"json": json}  # the block's only external dependency
    exec(compile(module, f"<{project}:{method}>", "exec"), namespace)
    return namespace[method]


class FakeSymbol:
    def __init__(self, value: str) -> None:
        self.value = value


class FakeDirection:
    def __init__(self, name: str) -> None:
        self._name = name

    def __str__(self) -> str:
        return self._name


class FakeTrade:
    def __init__(self, *, short: bool = False) -> None:
        self.symbol = FakeSymbol("ES")
        self.entry_time = dt.datetime(2024, 1, 2, 15, 0)  # naive == fill.UtcTime
        self.exit_time = dt.datetime(2024, 1, 2, 16, 30)
        self.entry_price = 4800.25
        self.exit_price = 4805.25
        self.quantity = 2.0
        self.direction = FakeDirection("Short" if short else "Long")
        self.profit_loss = -250.0 if short else 500.0
        self.total_fees = 4.2
        self.mae = -120.0
        self.mfe = 260.0


class FakeObjectStore:
    def __init__(self, fail: bool = False) -> None:
        self.saved: list[tuple[str, str]] = []
        self._fail = fail

    def save(self, key: str, value: str) -> None:
        if self._fail:
            raise RuntimeError("quota exceeded")
        self.saved.append((key, value))


class FakeTradeBuilder:
    def __init__(self, trades) -> None:
        self.closed_trades = trades


class FakeAlgorithm:
    def __init__(self, trades, marks, fail_store: bool = False) -> None:
        self.trade_builder = FakeTradeBuilder(trades)
        self.algorithm_id = "BT123"
        self.object_store = FakeObjectStore(fail=fail_store)
        self._quantlab_equity_marks = marks
        self.logged: list[str] = []

    def log(self, message: str) -> None:
        self.logged.append(message)


def _exported_payload(marks=None) -> str:
    algorithm = FakeAlgorithm(
        [FakeTrade(), FakeTrade(short=True)],
        marks if marks is not None else [],
    )
    _strategy_method("sma_cross_futures", "_quantlab_export")(algorithm)
    assert algorithm.object_store.saved, algorithm.logged
    key, payload = algorithm.object_store.saved[0]
    assert key == "quantlab/results/BT123.json"
    return payload


class TestExportBlock:
    @pytest.mark.parametrize("project", PROJECTS)
    def test_every_strategy_carries_the_export_block(self, project: str) -> None:
        source = _strategy_source(project)
        assert EXPORT_MARKER in source
        tree = ast.parse(source)
        names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        assert set(EXPORT_METHODS) <= names

    @pytest.mark.parametrize("project", PROJECTS)
    def test_initialize_starts_the_export(self, project: str) -> None:
        tree = ast.parse(_strategy_source(project))
        initialize = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "initialize"
        )
        calls = {
            node.func.attr
            for node in ast.walk(initialize)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "_quantlab_start_export" in calls

    def test_block_is_identical_across_strategies(self) -> None:
        # One block, three copies: drift would silently fork the export
        # format. Compare from the marker to end-of-file byte for byte.
        blocks = {p: _strategy_source(p).split(EXPORT_MARKER, 1)[1] for p in PROJECTS}
        assert blocks["orb_equity"] == blocks["sma_cross_futures"]
        assert blocks["custom_data_demo"] == blocks["sma_cross_futures"]

    def test_store_failure_logs_and_never_raises(self) -> None:
        algorithm = FakeAlgorithm([FakeTrade()], [], fail_store=True)
        _strategy_method("sma_cross_futures", "_quantlab_export")(algorithm)
        assert not algorithm.object_store.saved
        assert any("FAILED" in line for line in algorithm.logged)

    def test_sample_equity_appends_utc_marks(self) -> None:
        class Portfolio:
            total_portfolio_value = 100_123.45

        algorithm = FakeAlgorithm([], [])
        algorithm.utc_time = dt.datetime(2024, 1, 2, 15, 0)
        algorithm.portfolio = Portfolio()
        _strategy_method("sma_cross_futures", "_quantlab_sample_equity")(algorithm)
        assert algorithm._quantlab_equity_marks == [["2024-01-02T15:00:00Z", 100_123.45]]


class TestFromJsonCli:
    def _forbid_api(self, monkeypatch) -> None:
        class Exploding:
            def __init__(self) -> None:
                raise AssertionError("QCClient constructed in offline mode")

        monkeypatch.setattr(cloud_cmds, "QCClient", Exploding)
        monkeypatch.delenv("QC_USER_ID", raising=False)
        monkeypatch.delenv("QC_API_TOKEN", raising=False)

    def test_round_trips_export_without_credentials(self, monkeypatch, tmp_path) -> None:
        self._forbid_api(monkeypatch)
        saved = tmp_path / "BT123.json"
        saved.write_text(_exported_payload(), encoding="utf-8")
        output = tmp_path / "trades.parquet"
        result = CliRunner().invoke(
            cloud_cmds.cloud_app,
            ["results", "--from-json", str(saved), "--output", str(output)],
        )
        assert result.exit_code == 0, result.output
        log = read_trade_log(output)
        assert len(log.trades) == 2
        assert log.has_excursions
        long_trade, short_trade = log.trades
        assert long_trade.side is Side.LONG and short_trade.side is Side.SHORT
        assert long_trade.pnl == pytest.approx(500.0 - 4.2)  # net of fees
        assert short_trade.pnl == pytest.approx(-250.0 - 4.2)
        assert long_trade.mae == pytest.approx(-120.0)
        assert long_trade.mfe == pytest.approx(260.0)
        assert long_trade.entry_time == dt.datetime(2024, 1, 2, 15, 0, tzinfo=dt.UTC)

    def test_firm_check_runs_on_equity_marks(self, monkeypatch, tmp_path) -> None:
        self._forbid_api(monkeypatch)
        marks = [
            [f"2024-01-{day:02d}T{hour:02d}:00:00Z", 50_000.0 + 10 * hour]
            for day in range(2, 6)
            for hour in range(14, 21)
        ]
        saved = tmp_path / "BT123.json"
        saved.write_text(_exported_payload(marks=marks), encoding="utf-8")
        output = tmp_path / "trades.parquet"
        result = CliRunner().invoke(
            cloud_cmds.cloud_app,
            ["results", "--from-json", str(saved), "-o", str(output), "--firm", "topstep_50k"],
        )
        assert result.exit_code == 0, result.output
        equity_csv = tmp_path / "trades.equity.csv"
        assert equity_csv.exists()
        assert "equityMarks" in result.output  # the coarseness caveat is stated

    def test_chart_without_marks_fails_with_guidance(self, monkeypatch, tmp_path) -> None:
        self._forbid_api(monkeypatch)
        saved = tmp_path / "api_download.json"
        payload = json.loads(_exported_payload())
        del payload["equityMarks"]
        saved.write_text(json.dumps(payload), encoding="utf-8")
        result = CliRunner().invoke(
            cloud_cmds.cloud_app,
            ["results", "--from-json", str(saved), "--chart", "-o", str(tmp_path / "t.parquet")],
        )
        assert result.exit_code != 0
        assert "equityMarks" in str(result.exception)

    def test_source_flags_are_mutually_exclusive(self, monkeypatch, tmp_path) -> None:
        self._forbid_api(monkeypatch)
        saved = tmp_path / "BT123.json"
        saved.write_text(_exported_payload(), encoding="utf-8")
        result = CliRunner().invoke(
            cloud_cmds.cloud_app,
            ["results", "--from-json", str(saved), "--project-id", "1"],
        )
        assert result.exit_code != 0
        assert "one source" in str(result.exception)

    def test_missing_source_names_both_routes(self, monkeypatch) -> None:
        self._forbid_api(monkeypatch)
        result = CliRunner().invoke(cloud_cmds.cloud_app, ["results"])
        assert result.exit_code != 0
        assert "--from-json" in str(result.exception)

    def test_save_json_rejected_offline(self, monkeypatch, tmp_path) -> None:
        self._forbid_api(monkeypatch)
        saved = tmp_path / "BT123.json"
        saved.write_text(_exported_payload(), encoding="utf-8")
        result = CliRunner().invoke(
            cloud_cmds.cloud_app,
            ["results", "--from-json", str(saved), "--save-json", str(tmp_path / "copy.json")],
        )
        assert result.exit_code != 0
        assert "--save-json" in str(result.exception)


class TestParseEquityMarks:
    def test_absent_returns_none(self) -> None:
        assert parse_equity_marks({}) is None
        assert parse_equity_marks({"equityMarks": None}) is None

    def test_reads_marks_and_skips_junk(self) -> None:
        curve = parse_equity_marks(
            {
                "equityMarks": [
                    ["2024-01-02T15:00:00Z", 50_000.0],
                    ["not a time", 1.0],
                    ["2024-01-02T16:00:00Z", "not a number"],
                    ["2024-01-02T17:00:00Z", float("nan")],
                    ["2024-01-02T18:00:00Z", 50_250.0],
                ]
            }
        )
        assert curve is not None
        assert len(curve.points) == 2

    def test_present_but_unreadable_raises(self) -> None:
        with pytest.raises(QuantLabError, match="no readable points"):
            parse_equity_marks({"equityMarks": []})
        with pytest.raises(QuantLabError, match="JSON array"):
            parse_equity_marks({"equityMarks": "nope"})
