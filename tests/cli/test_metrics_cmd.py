"""CLI surface parity: the JSON branch must carry the same caveats the
table branch prints (M10.a honesty fix)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from quantlab.cli.app import app
from quantlab.schema.io import write_trade_log

from ..conftest import random_log


class TestMetricsJsonWarnings:
    def test_json_carries_fidelity_warning(self, tmp_path) -> None:
        parquet = tmp_path / "t.parquet"
        write_trade_log(random_log(n_days=10, with_excursions=False), parquet)
        result = CliRunner().invoke(app, ["metrics", str(parquet), "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["schema_version"] == 1
        assert any("MAE/MFE" in w for w in payload["warnings"])

    def test_json_warnings_empty_for_full_fidelity_log(self, tmp_path) -> None:
        parquet = tmp_path / "t.parquet"
        write_trade_log(random_log(n_days=10, with_excursions=True), parquet)
        result = CliRunner().invoke(app, ["metrics", str(parquet), "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert not any("MAE/MFE" in w for w in payload["warnings"])
