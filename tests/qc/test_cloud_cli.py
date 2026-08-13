from __future__ import annotations

import math

from typer.testing import CliRunner

import quantlab.cli.cloud_cmds as cloud_cmds
from quantlab.qc.results import load_result_file


def test_saved_cloud_result_is_strict_and_reloadable(monkeypatch, tmp_path):
    backtest = {
        "metric": float("nan"),
        "totalPerformance": {
            "closedTrades": [
                {
                    "symbol": "ES",
                    "entryTime": "2024-01-02T15:00:00Z",
                    "exitTime": "2024-01-02T16:00:00Z",
                    "entryPrice": 4800,
                    "exitPrice": 4801,
                    "quantity": 1,
                    "direction": 0,
                    "profitLoss": 50,
                    "totalFees": 2,
                }
            ]
        },
    }

    class Client:
        def read_backtest(self, project_id, backtest_id):
            return backtest

    monkeypatch.setattr(cloud_cmds, "QCClient", Client)
    monkeypatch.setattr(cloud_cmds, "write_trade_log", lambda log, output: None)
    output = tmp_path / "trades.parquet"
    saved = tmp_path / "raw.json"
    result = CliRunner().invoke(
        cloud_cmds.cloud_app,
        [
            "results",
            "--project-id",
            "1",
            "--backtest-id",
            "abc",
            "--output",
            str(output),
            "--save-json",
            str(saved),
        ],
    )
    assert result.exit_code == 0, result.output
    loaded = load_result_file(saved)
    assert loaded["metric"] is None
    assert not any(token in saved.read_text(encoding="utf-8") for token in ("NaN", "Infinity"))
    assert math.isfinite(loaded["totalPerformance"]["closedTrades"][0]["profitLoss"])
