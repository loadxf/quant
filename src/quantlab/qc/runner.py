"""Wrapper around the lean CLI's cloud commands.

Verified mechanics (lean-cli source, July 2026):
- `lean cloud push` / `lean cloud backtest` are Docker-free and need no
  `lean init` workspace — push resolves projects relative to the cwd.
- The CLI does NOT read credential env vars; non-interactive auth is
  `lean login -u <id> -t <token>` (stored in ~/.lean/credentials).
- No CLI command downloads the backtest result JSON (`lean cloud pull`
  fetches project files only) — results come from the REST API
  (qc/results.py); this module captures the project/backtest ids from
  the CLI output.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from quantlab.errors import CloudUnavailableError, QuantLabError
from quantlab.qc.api import credentials_from_env

_ID_PATTERNS = (
    re.compile(r"/project/(?P<project>\d+)(?:/backtests?/(?P<backtest>[0-9a-fA-F-]+))?"),
    re.compile(r"[Bb]acktest\s+id[:\s]+(?P<backtest>[0-9a-fA-F-]{8,})"),
    re.compile(r"[Pp]roject\s+id[:\s]+(?P<project>\d+)"),
)


@dataclass
class CloudBacktestRun:
    project: str
    name: str | None
    project_id: int | None
    backtest_id: str | None
    stdout: str


def preflight() -> None:
    """Fail fast with an actionable message when cloud runs can't work."""
    if shutil.which("lean") is None:
        raise CloudUnavailableError(
            "The `lean` CLI is not installed. Install with `pip install "
            "'loadx-quant[qc]'` (or `pip install lean`). Note: only the cloud "
            "commands are used — no Docker required. The prop-firm simulator "
            "works without it: `quant prop simulate trades.parquet --firm ...`"
        )
    credentials_from_env()  # raises CloudUnavailableError when unset


# argv flags whose VALUES are secrets: never echo them into error
# messages (which land in terminals, CI logs, and pasted GitHub issues).
_SENSITIVE_FLAGS = frozenset({"--api-token"})


def _redacted(args: list[str]) -> str:
    shown = list(args)
    for i, arg in enumerate(shown[:-1]):
        if arg in _SENSITIVE_FLAGS:
            shown[i + 1] = "***"
    return " ".join(shown)


def _run(args: list[str], timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        # TimeoutExpired's own message embeds the full argv (token included).
        raise QuantLabError(f"`{_redacted(args)}` timed out after {timeout}s") from None
    if result.returncode != 0:
        raise QuantLabError(
            f"`{_redacted(args)}` failed ({result.returncode}):\n"
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result


def login() -> None:
    """Non-interactive login using QC_USER_ID / QC_API_TOKEN (idempotent)."""
    user_id, token = credentials_from_env()
    _run(["lean", "login", "--user-id", user_id, "--api-token", token], timeout=120)


def push_project(project: Path) -> None:
    preflight()
    login()
    if not project.exists():
        raise QuantLabError(f"Project directory not found: {project}")
    _run(["lean", "cloud", "push", "--project", str(project)])


def parse_ids(output: str) -> tuple[int | None, str | None]:
    project_id: int | None = None
    backtest_id: str | None = None
    for pattern in _ID_PATTERNS:
        for match in pattern.finditer(output):
            groups = match.groupdict()
            if groups.get("project") and project_id is None:
                project_id = int(groups["project"])
            if groups.get("backtest") and backtest_id is None:
                backtest_id = groups["backtest"]
    return project_id, backtest_id


def run_cloud_backtest(
    project: Path | str, name: str | None = None, push: bool = False
) -> CloudBacktestRun:
    preflight()
    login()
    args = ["lean", "cloud", "backtest", str(project)]
    if name:
        args += ["--name", name]
    if push:
        args.append("--push")
    result = _run(args)
    combined = result.stdout + "\n" + result.stderr
    project_id, backtest_id = parse_ids(combined)
    return CloudBacktestRun(
        project=str(project),
        name=name,
        project_id=project_id,
        backtest_id=backtest_id,
        stdout=result.stdout,
    )


def object_store_upload(key: str, path: Path) -> None:
    """Upload a file to the CLOUD Object Store.

    Uses `lean cloud object-store set KEY PATH` (verified: this is the
    cloud upload command; plain `lean object-store set` only opens a
    local folder in current lean-cli).
    """
    preflight()
    login()
    _run(["lean", "cloud", "object-store", "set", key, str(path)])
