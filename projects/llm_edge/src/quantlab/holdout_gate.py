"""The only door to holdout data (protocol.md section 4).

A candidate may see post-2023 data only if:
  1. its spec SHA256 is registered in candidates/registry.json, and
  2. the registry entry was committed to git before the gate is invoked, and
  3. it has never consumed its holdout shot before (holdout_results.json absent).

``authorize`` returns a single-use token consumed by ``data.load_panel``;
``record_results`` writes the one-and-only holdout result file. Nothing else in
the codebase creates tokens, and load_panel refuses post-validation data
without one — grep for _HOLDOUT_SECRET to verify.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from . import CANDIDATES_DIR, REGISTRY_PATH, REPO_ROOT

_HOLDOUT_SECRET = "quantlab-holdout-gate-v1"
_ISSUED: dict[str, str] = {}  # token -> scope: "holdout:<candidate_id>" | "g1_generation"


def spec_sha256(spec_path: Path) -> str:
    return hashlib.sha256(spec_path.read_bytes()).hexdigest()


def _registry() -> dict:
    if not REGISTRY_PATH.exists():
        raise RuntimeError("no candidates/registry.json — nothing is registered")
    return json.loads(REGISTRY_PATH.read_text())


def _registry_committed() -> bool:
    """True if registry.json has no uncommitted modifications (it is in git HEAD)."""
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain", "--", "candidates/registry.json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    committed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "cat-file", "-e", "HEAD:candidates/registry.json"],
        capture_output=True,
    ).returncode == 0
    return committed and out == ""


def authorize(candidate_id: str) -> str:
    """Grant one holdout evaluation for a registered, committed candidate spec."""
    registry = _registry()
    if candidate_id not in registry:
        raise RuntimeError(f"{candidate_id} is not registered — holdout access denied")
    if not _registry_committed():
        raise RuntimeError(
            "registry.json has uncommitted changes or is not in git HEAD — "
            "commit the registration first, then invoke the gate"
        )
    spec_path = CANDIDATES_DIR / candidate_id / "spec.md"
    actual = spec_sha256(spec_path)
    expected = registry[candidate_id]["spec_sha256"]
    if actual != expected:
        raise RuntimeError(
            f"{candidate_id} spec hash mismatch: registered {expected[:12]}, actual {actual[:12]} — "
            "the spec was modified after registration"
        )
    results_path = CANDIDATES_DIR / candidate_id / "holdout_results.json"
    if results_path.exists():
        raise RuntimeError(f"{candidate_id} already consumed its holdout shot — refusing re-run")
    token = hashlib.sha256(f"{_HOLDOUT_SECRET}:{candidate_id}:{expected}".encode()).hexdigest()
    _ISSUED[token] = f"holdout:{candidate_id}"
    return token


def verify_token(token: str | None) -> str:
    """Validate a token and return its scope. Tokens are revoked once their
    candidate's holdout result is recorded, so a stale token cannot reopen
    the holdout after the single shot is consumed."""
    if token is None or token not in _ISSUED:
        raise RuntimeError(
            "post-validation data requested without a valid holdout token — "
            "use holdout_gate.authorize(candidate_id) (requires committed registration)"
        )
    return _ISSUED[token]


def authorize_g1_generation() -> str:
    """Token for G1 hypothesis-generation access to the post-cutoff slice ONLY
    (POST_CUTOFF_START onward; see research/debates/protocol_deviations.md D1).
    Every grant is logged; G1 candidates' holdout ends at 2026-01-31.
    """
    from . import POST_CUTOFF_START

    log_path = CANDIDATES_DIR / "g1_access_log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else []
    log.append(
        {
            "granted_utc": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(timespec="seconds"),
            "window_start": POST_CUTOFF_START,
        }
    )
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(log, indent=1))
    token = hashlib.sha256(f"{_HOLDOUT_SECRET}:g1_generation".encode()).hexdigest()
    _ISSUED[token] = "g1_generation"
    return token


def record_results(candidate_id: str, results: dict) -> Path:
    """Write the candidate's single holdout result file. Fails if it exists."""
    results_path = CANDIDATES_DIR / candidate_id / "holdout_results.json"
    if results_path.exists():
        raise RuntimeError(f"{candidate_id} holdout results already recorded — immutable")
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(results, indent=1, sort_keys=True))
    # Revoke every token for this candidate: the single shot is consumed.
    for token, scope in list(_ISSUED.items()):
        if scope == f"holdout:{candidate_id}":
            del _ISSUED[token]
    return results_path
