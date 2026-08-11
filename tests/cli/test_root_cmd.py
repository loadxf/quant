"""Root callback surface: `--version` must terminate on its own, and a bare
`quant` must still print help rather than exiting silently."""

from __future__ import annotations

from typer.testing import CliRunner

from quantlab import __version__
from quantlab.cli.app import app


class TestRootCallback:
    def test_version_flag_prints_version(self) -> None:
        result = CliRunner().invoke(app, ["--version"])
        assert result.exit_code == 0, result.output
        assert result.output.strip() == __version__

    def test_no_args_shows_help(self) -> None:
        result = CliRunner().invoke(app, [])
        assert "Usage:" in result.output
        assert "prop" in result.output
