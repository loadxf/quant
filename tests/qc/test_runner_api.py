from __future__ import annotations

import ast
import base64
import hashlib
from pathlib import Path

import pytest

from quantlab.errors import CloudUnavailableError
from quantlab.qc import runner
from quantlab.qc.api import QCClient, credentials_from_env


class TestPreflightDegradation:
    def test_missing_lean_cli(self, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda _: None)
        with pytest.raises(CloudUnavailableError, match=r"lean.*not installed"):
            runner.preflight()

    def test_missing_credentials(self, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/lean")
        monkeypatch.delenv("QC_USER_ID", raising=False)
        monkeypatch.delenv("QC_API_TOKEN", raising=False)
        with pytest.raises(CloudUnavailableError, match="QC_USER_ID"):
            runner.preflight()

    def test_error_message_points_to_simulator(self, monkeypatch) -> None:
        monkeypatch.delenv("QC_USER_ID", raising=False)
        monkeypatch.delenv("QC_API_TOKEN", raising=False)
        with pytest.raises(CloudUnavailableError, match="quant prop simulate"):
            credentials_from_env()


class TestParseIds:
    def test_url_pattern(self) -> None:
        out = (
            "Backtest complete: https://www.quantconnect.com/project/1234567/backtests/0a1b2c3d4e5f"
        )
        assert runner.parse_ids(out) == (1234567, "0a1b2c3d4e5f")

    def test_labelled_pattern(self) -> None:
        out = "Project id: 555\nStarted backtest\nbacktest id: deadbeef1234"
        assert runner.parse_ids(out) == (555, "deadbeef1234")

    def test_nothing_found(self) -> None:
        assert runner.parse_ids("no ids here") == (None, None)


class TestApiAuth:
    def test_hashed_timestamp_header(self, monkeypatch) -> None:
        monkeypatch.setattr("time.time", lambda: 1_750_000_000)
        client = QCClient(user_id="99999", api_token="secret-token")
        headers = client._headers()
        assert headers["Timestamp"] == "1750000000"
        expected_hash = hashlib.sha256(b"secret-token:1750000000").hexdigest()
        decoded = base64.b64decode(headers["Authorization"].split()[1]).decode()
        assert decoded == f"99999:{expected_hash}"

    def test_env_credentials_required(self, monkeypatch) -> None:
        monkeypatch.delenv("QC_USER_ID", raising=False)
        monkeypatch.delenv("QC_API_TOKEN", raising=False)
        with pytest.raises(CloudUnavailableError):
            QCClient()


class TestStrategiesParse:
    @pytest.mark.parametrize("project", ["sma_cross_futures", "orb_equity", "custom_data_demo"])
    def test_strategy_files_are_valid_python(self, project: str) -> None:
        root = Path(__file__).resolve().parents[2] / "cloud" / "strategies" / project
        source = (root / "main.py").read_text()
        ast.parse(source)  # LEAN imports aren't installed locally; syntax must hold
        assert (root / "config.json").exists()


class TestTokenRedaction:
    def test_failed_lean_login_never_echoes_token(self, monkeypatch):
        """A failed `lean login` must not print the API token (it lands in
        terminals, CI logs, and pasted GitHub issues)."""
        import subprocess

        from quantlab.errors import QuantLabError
        from quantlab.qc import runner

        def fake_run(args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="boom")

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setenv("QC_USER_ID", "123456")
        monkeypatch.setenv("QC_API_TOKEN", "super-secret-token")
        with pytest.raises(QuantLabError) as excinfo:
            runner.login()
        assert "super-secret-token" not in str(excinfo.value)
        assert "***" in str(excinfo.value)

    def test_timeout_never_echoes_token(self, monkeypatch):
        import subprocess

        from quantlab.errors import QuantLabError
        from quantlab.qc import runner

        def fake_run(args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=args, timeout=120)

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setenv("QC_USER_ID", "123456")
        monkeypatch.setenv("QC_API_TOKEN", "super-secret-token")
        with pytest.raises(QuantLabError) as excinfo:
            runner.login()
        assert "super-secret-token" not in str(excinfo.value)
