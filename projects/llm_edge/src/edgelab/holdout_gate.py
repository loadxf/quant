"""The only door to holdout data (protocol.md section 4).

A candidate may see post-2023 data only if its exact specification, signal,
research engine, and input-data manifest match its registration seal; the
registry, ledger and all sealed inputs must also be clean committed files.

``authorize`` returns a single-use token consumed by ``data.load_panel``;
``record_results`` writes the one-and-only holdout result file. Nothing else in
the codebase creates tokens, and load_panel refuses post-validation data
without one; token construction remains private to this module.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import importlib.metadata
import json
import platform
import re
import secrets
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import CANDIDATES_DIR, DATA_DIR, LEDGER_PATH, REGISTRY_PATH, REPO_ROOT
from .data import load_universe_snapshot
from .jsonutil import atomic_write_text, dumps

MANIFEST_PATH = DATA_DIR / "manifest.json"
UNIVERSE_PATH = DATA_DIR / "universe.json"
# Seal the complete executable package rather than a hand-maintained dependency
# list that silently becomes incomplete when a module is added or refactored.
ENGINE_PATHS = tuple(sorted((REPO_ROOT / "src" / "edgelab").glob("*.py")))
ENVIRONMENT_PATHS = (REPO_ROOT / "pyproject.toml", REPO_ROOT / "requirements.txt")
RUNTIME_PACKAGES = (
    "numpy",
    "pandas",
    "scipy",
    "pyarrow",
    "requests",
)


@dataclass
class _Capability:
    kind: str
    candidate_id: str | None
    max_end: str
    used_fields: set[str] = field(default_factory=set)
    signal_source: str | None = None
    authorization_identity: dict[str, object] = field(default_factory=dict)
    registered_entry: dict[str, object] = field(default_factory=dict)
    ledger_prefix: bytes | None = None
    input_identity: dict[str, str] = field(default_factory=dict)


_ISSUED: dict[str, _Capability] = {}
_CANDIDATE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def spec_sha256(spec_path: Path) -> str:
    return hashlib.sha256(spec_path.read_bytes()).hexdigest()


def validation_result(path: Path, candidate_id: str) -> dict:
    """Load a strict promotion artifact and require both pre-holdout gates."""
    if not path.is_file():
        raise RuntimeError(f"{candidate_id} has no results_validation.json")

    def reject_constant(value: str):
        raise ValueError(f"non-finite JSON constant {value}")

    try:
        result = json.loads(path.read_text(), parse_constant=reject_constant)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"{candidate_id} has invalid validation results: {exc}") from exc
    if not isinstance(result, dict) or result.get("candidate_id") != candidate_id:
        raise RuntimeError(f"{candidate_id} validation results have the wrong identity")
    for gate_name in ("gate1", "gate2"):
        gate = result.get(gate_name)
        if not isinstance(gate, dict) or gate.get("pass") is not True:
            raise RuntimeError(f"{candidate_id} did not pass {gate_name}; holdout promotion denied")
    if result.get("research_identity") != research_identity([candidate_id]):
        raise RuntimeError(
            f"{candidate_id} validation results were produced by a different "
            "signal, engine, environment, or data input"
        )
    return result


def engine_sha256() -> str:
    digest = hashlib.sha256()
    for path in ENGINE_PATHS:
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def environment_sha256() -> str:
    digest = hashlib.sha256()
    for path in ENVIRONMENT_PATHS:
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    try:
        versions = {package: importlib.metadata.version(package) for package in RUNTIME_PACKAGES}
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError(f"required runtime package is not installed: {exc.name}") from exc
    runtime = {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "packages": versions,
    }
    digest.update(json.dumps(runtime, sort_keys=True, separators=(",", ":")).encode())
    return digest.hexdigest()


def research_identity(
    candidate_ids: list[str], candidates_dir: Path | None = None
) -> dict[str, object]:
    root = CANDIDATES_DIR if candidates_dir is None else candidates_dir
    universe, universe_sha256 = load_universe_snapshot(UNIVERSE_PATH)
    return {
        "candidate_ids": candidate_ids,
        "spec_sha256": {
            candidate_id: spec_sha256(root / candidate_id / "spec.md")
            for candidate_id in candidate_ids
        },
        "signal_sha256": {
            candidate_id: spec_sha256(root / candidate_id / "signal.py")
            for candidate_id in candidate_ids
        },
        "engine_sha256": engine_sha256(),
        "environment_sha256": environment_sha256(),
        "data_manifest_sha256": spec_sha256(MANIFEST_PATH),
        "universe_sha256": universe_sha256,
        "universe_counts": {
            "equities": len(universe["equities"]),
            "etfs": len(universe["etfs"]),
        },
    }


def git_head() -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _registry() -> dict:
    if not REGISTRY_PATH.exists():
        raise RuntimeError("no candidates/registry.json — nothing is registered")
    try:
        registry = json.loads(REGISTRY_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid candidate registry: {exc}") from exc
    if not isinstance(registry, dict):
        raise RuntimeError("candidate registry must be a JSON object")
    return registry


def _path_committed(path: Path) -> bool:
    """The worktree file must be tracked, clean, and byte-identical to HEAD."""
    top = Path(
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    try:
        relative = path.resolve().relative_to(top.resolve()).as_posix()
    except ValueError:
        return False
    tracked = (
        subprocess.run(
            ["git", "-C", str(top), "ls-files", "--error-unmatch", "--", relative],
            capture_output=True,
        ).returncode
        == 0
    )
    clean = (
        subprocess.run(
            ["git", "-C", str(top), "diff", "--quiet", "HEAD", "--", relative]
        ).returncode
        == 0
    )
    head = subprocess.run(["git", "-C", str(top), "show", f"HEAD:{relative}"], capture_output=True)
    return tracked and clean and head.returncode == 0 and head.stdout == path.read_bytes()


def _registry_committed() -> bool:
    if not _path_committed(REGISTRY_PATH):
        return False
    _registry_history_append_only()
    return True


def _registry_history_append_only() -> None:
    """Require every committed registry transition to preserve old entries."""
    top = Path(
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    try:
        relative = REGISTRY_PATH.resolve().relative_to(top.resolve()).as_posix()
    except ValueError as exc:
        raise RuntimeError("candidate registry is outside the registered repository") from exc
    commits = subprocess.run(
        ["git", "-C", str(top), "log", "--format=%H", "--reverse", "--", relative],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    if not commits:
        raise RuntimeError("candidate registry has no committed history")
    previous: dict = {}
    for commit in commits:
        blob = subprocess.run(
            ["git", "-C", str(top), "show", f"{commit}:{relative}"],
            capture_output=True,
        )
        if blob.returncode != 0:
            raise RuntimeError(f"candidate registry was deleted at commit {commit[:12]}")
        try:
            current = json.loads(blob.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"candidate registry is invalid at commit {commit[:12]}: {exc}"
            ) from exc
        if not isinstance(current, dict) or not all(
            _CANDIDATE_RE.fullmatch(key) and isinstance(value, dict)
            for key, value in current.items()
        ):
            raise RuntimeError(f"candidate registry has invalid shape at {commit[:12]}")
        changed = [key for key, value in previous.items() if current.get(key) != value]
        if changed:
            raise RuntimeError(
                f"candidate registry history rewrote existing entries at {commit[:12]}: {changed}"
            )
        previous = current


def _path_ever_committed(path: Path) -> bool:
    """Return whether a one-shot marker exists anywhere in HEAD history."""
    top = Path(
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    try:
        relative = path.resolve().relative_to(top.resolve()).as_posix()
    except ValueError:
        return False
    result = subprocess.run(
        ["git", "-C", str(top), "log", "-1", "--format=%H", "--", relative],
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(result.stdout.strip())


def _ledger_history_append_only(start_commit: str) -> None:
    """Verify every committed ledger version since registration only appended bytes."""
    top = Path(
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    try:
        relative = LEDGER_PATH.resolve().relative_to(top.resolve()).as_posix()
    except ValueError as exc:
        raise RuntimeError("trials ledger is outside the registered repository") from exc

    ancestor = subprocess.run(
        ["git", "-C", str(top), "merge-base", "--is-ancestor", start_commit, "HEAD"]
    )
    if ancestor.returncode != 0:
        raise RuntimeError("registered engine commit is not an ancestor of HEAD")

    def blob(commit: str) -> bytes:
        result = subprocess.run(
            ["git", "-C", str(top), "show", f"{commit}:{relative}"], capture_output=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"trials ledger is absent from commit {commit[:12]}")
        return result.stdout

    previous = blob(start_commit)
    commits = subprocess.run(
        [
            "git",
            "-C",
            str(top),
            "rev-list",
            "--reverse",
            f"{start_commit}..HEAD",
            "--",
            relative,
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    for commit in commits:
        current = blob(commit)
        if not current.startswith(previous):
            raise RuntimeError(f"trials ledger history is not append-only at commit {commit[:12]}")
        previous = current
    if previous != LEDGER_PATH.read_bytes():
        raise RuntimeError("working trials ledger differs from its committed history")


def _verify_research_seal(candidate_id: str, entry: dict, signal_path: Path) -> dict[str, str]:
    required = {
        "signal_sha256",
        "engine_sha256",
        "engine_commit",
        "environment_sha256",
        "data_manifest_sha256",
        "universe_sha256",
        "validation_results_sha256",
        "ledger_sha256",
        "origin",
        "holdout_end",
    }
    if not all(isinstance(entry.get(key), str) and entry[key] for key in required):
        raise RuntimeError(
            f"{candidate_id} registration predates the integrity seal; re-register from a "
            "clean research state before holdout access"
        )
    if not isinstance(entry.get("ledger_bytes"), int) or entry["ledger_bytes"] < 0:
        raise RuntimeError(f"{candidate_id} registration has no valid ledger byte anchor")
    if not MANIFEST_PATH.is_file() or not _path_committed(MANIFEST_PATH):
        raise RuntimeError("data manifest is untracked or differs from git HEAD")
    if not UNIVERSE_PATH.is_file() or not _path_committed(UNIVERSE_PATH):
        raise RuntimeError("data universe is untracked or differs from git HEAD")
    if not LEDGER_PATH.is_file() or not _path_committed(LEDGER_PATH):
        raise RuntimeError("trials ledger must be committed and byte-identical to git HEAD")
    validation_path = CANDIDATES_DIR / candidate_id / "results_validation.json"
    if not validation_path.is_file() or not _path_committed(validation_path):
        raise RuntimeError(
            f"{candidate_id} results_validation.json is untracked or differs from git HEAD"
        )
    validation_result(validation_path, candidate_id)
    _ledger_history_append_only(entry["engine_commit"])
    registered_prefix = LEDGER_PATH.read_bytes()[: entry["ledger_bytes"]]
    if (
        len(registered_prefix) != entry["ledger_bytes"]
        or hashlib.sha256(registered_prefix).hexdigest() != entry["ledger_sha256"]
    ):
        raise RuntimeError("trials ledger no longer contains its registered byte anchor")
    dirty_engine = [path.name for path in ENGINE_PATHS if not _path_committed(path)]
    if dirty_engine:
        raise RuntimeError(f"research engine files are uncommitted: {dirty_engine}")
    dirty_environment = [path.name for path in ENVIRONMENT_PATHS if not _path_committed(path)]
    if dirty_environment:
        raise RuntimeError(f"research environment files are uncommitted: {dirty_environment}")
    actual = {
        "signal_sha256": spec_sha256(signal_path),
        "engine_sha256": engine_sha256(),
        "environment_sha256": environment_sha256(),
        "data_manifest_sha256": spec_sha256(MANIFEST_PATH),
        "universe_sha256": spec_sha256(UNIVERSE_PATH),
        "validation_results_sha256": spec_sha256(validation_path),
        "ledger_sha256": spec_sha256(LEDGER_PATH),
        "current_commit": git_head(),
    }
    for key in (
        "signal_sha256",
        "engine_sha256",
        "environment_sha256",
        "data_manifest_sha256",
        "universe_sha256",
        "validation_results_sha256",
    ):
        if actual[key] != entry[key]:
            raise RuntimeError(
                f"{candidate_id} {key} mismatch: registered {entry[key][:12]}, "
                f"actual {actual[key][:12]}"
            )
    return actual


def authorize(candidate_id: str) -> str:
    """Grant one holdout evaluation for a registered, committed candidate spec."""
    if not _CANDIDATE_RE.fullmatch(candidate_id):
        raise RuntimeError(f"invalid candidate id {candidate_id!r}")
    registry = _registry()
    if candidate_id not in registry:
        raise RuntimeError(f"{candidate_id} is not registered — holdout access denied")
    entry = registry[candidate_id]
    if not isinstance(entry, dict) or not isinstance(entry.get("spec_sha256"), str):
        raise RuntimeError(f"{candidate_id} has an invalid registry entry")
    if not _registry_committed():
        raise RuntimeError(
            "registry.json has uncommitted changes or is not in git HEAD — "
            "commit the registration first, then invoke the gate"
        )
    spec_path = CANDIDATES_DIR / candidate_id / "spec.md"
    if not spec_path.is_file() or not _path_committed(spec_path):
        raise RuntimeError(
            f"{candidate_id} spec.md is untracked, modified, or not byte-identical to git HEAD"
        )
    signal_path = CANDIDATES_DIR / candidate_id / "signal.py"
    if not signal_path.is_file() or not _path_committed(signal_path):
        raise RuntimeError(
            f"{candidate_id} signal.py is untracked, modified, or not byte-identical to git HEAD"
        )
    actual = spec_sha256(spec_path)
    expected = entry["spec_sha256"]
    if actual != expected:
        raise RuntimeError(
            f"{candidate_id} spec hash mismatch: registered {expected[:12]}, "
            f"actual {actual[:12]} — the spec was modified after registration"
        )
    seal = _verify_research_seal(candidate_id, entry, signal_path)
    results_path = CANDIDATES_DIR / candidate_id / "holdout_results.json"
    if results_path.exists() or _path_ever_committed(results_path):
        raise RuntimeError(f"{candidate_id} already consumed its holdout shot — refusing re-run")
    access_path = CANDIDATES_DIR / candidate_id / "holdout_access.json"
    if access_path.exists() or _path_ever_committed(access_path):
        raise RuntimeError(
            f"{candidate_id} already opened its holdout shot; access is single-use "
            "even after failure"
        )
    try:
        signal_bytes = signal_path.read_bytes()
        signal_source = signal_bytes.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"could not snapshot {candidate_id} signal.py: {exc}") from exc
    signal_digest = hashlib.sha256(signal_bytes).hexdigest()
    if signal_digest != entry["signal_sha256"]:
        raise RuntimeError(
            f"{candidate_id} signal changed while holdout access was being authorized"
        )
    from .gates import signal_metadata

    declaration = signal_metadata(candidate_id, source_text=signal_source)
    origin = declaration.get("ORIGIN")
    holdout_end = declaration.get("HOLDOUT_END")
    if entry.get("origin") != origin or entry.get("holdout_end") != holdout_end:
        raise RuntimeError(
            f"{candidate_id} registered origin/holdout boundary does not match its declaration"
        )
    if origin == "G1" and holdout_end != "2026-01-31":
        raise RuntimeError(f"{candidate_id} G1 holdout must end at 2026-01-31")
    try:
        invalid_end = pd.Timestamp(holdout_end) <= pd.Timestamp("2023-12-31")
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{candidate_id} has an invalid holdout_end {holdout_end!r}") from exc
    if invalid_end:
        raise RuntimeError(f"{candidate_id} has an invalid registered holdout_end {holdout_end!r}")
    authorization_identity = {
        "candidate_id": candidate_id,
        "spec_sha256": actual,
        **{
            key: value
            for key, value in seal.items()
            if isinstance(value, str) and key != "current_commit"
        },
    }
    authorization_identity["signal_sha256"] = signal_digest
    try:
        ledger_payload = LEDGER_PATH.read_bytes()[: entry["ledger_bytes"]]
    except OSError as exc:
        raise RuntimeError(f"could not snapshot the registered trials ledger: {exc}") from exc
    if (
        len(ledger_payload) != entry["ledger_bytes"]
        or hashlib.sha256(ledger_payload).hexdigest() != entry["ledger_sha256"]
    ):
        raise RuntimeError("trials ledger changed while holdout access was being authorized")
    token = secrets.token_urlsafe(32)
    _ISSUED[token] = _Capability(
        "holdout",
        candidate_id,
        holdout_end,
        signal_source=signal_source,
        authorization_identity=authorization_identity,
        registered_entry=dict(entry),
        ledger_prefix=ledger_payload,
        input_identity={
            "data_manifest_sha256": str(entry["data_manifest_sha256"]),
            "universe_sha256": str(entry["universe_sha256"]),
        },
    )
    try:
        with access_path.open("x") as handle:
            handle.write(
                json.dumps(
                    {
                        "candidate_id": candidate_id,
                        "granted_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                        "max_end": holdout_end,
                        "registration_engine_commit": entry["engine_commit"],
                        **seal,
                    },
                    indent=1,
                )
            )
    except FileExistsError as exc:
        del _ISSUED[token]
        raise RuntimeError(f"{candidate_id} holdout access was opened concurrently") from exc
    return token


def verify_token(
    token: str | None,
    candidate_id: str | None = None,
    requested_end: str | None = None,
    requested_field: str | None = None,
) -> str:
    """Validate a token and return its scope. Tokens are revoked once their
    candidate's holdout result is recorded, so a stale token cannot reopen
    the holdout after the single shot is consumed."""
    if token is None or token not in _ISSUED:
        raise RuntimeError(
            "post-validation data requested without a valid holdout token — "
            "use holdout_gate.authorize(candidate_id) (requires committed registration)"
        )
    capability = _ISSUED[token]
    if capability.kind == "holdout" and requested_field is not None and candidate_id is None:
        raise RuntimeError("holdout data access must identify the token's candidate")
    if candidate_id is not None and capability.candidate_id != candidate_id:
        raise RuntimeError("holdout token belongs to a different candidate")
    if requested_end is not None and pd.Timestamp(requested_end) > pd.Timestamp(capability.max_end):
        raise RuntimeError(f"token scope ends at {capability.max_end}; requested {requested_end}")
    if requested_field is not None:
        if requested_field in capability.used_fields:
            raise RuntimeError(f"token already used to load field {requested_field!r}")
        capability.used_fields.add(requested_field)
    return f"holdout:{capability.candidate_id}" if capability.kind == "holdout" else "g1_generation"


def authorized_signal_source(token: str, candidate_id: str) -> str:
    """Return the exact registered signal snapshot bound to a holdout grant."""
    verify_token(token, candidate_id=candidate_id)
    source = _ISSUED[token].signal_source
    if source is None:
        raise RuntimeError("holdout token has no authorized signal snapshot")
    return source


def authorized_input_identity(token: str, candidate_id: str | None = None) -> dict[str, str]:
    """Return the immutable manifest/universe hashes bound to a capability."""
    verify_token(token, candidate_id=candidate_id)
    identity = _ISSUED[token].input_identity
    if set(identity) != {"data_manifest_sha256", "universe_sha256"}:
        raise RuntimeError("research capability has no complete input identity")
    return dict(identity)


def authorized_research_snapshot(token: str, candidate_id: str) -> tuple[dict[str, object], bytes]:
    """Return the exact registered entry and ledger prefix captured at grant."""
    verify_token(token, candidate_id=candidate_id)
    capability = _ISSUED[token]
    if not capability.registered_entry or capability.ledger_prefix is None:
        raise RuntimeError("holdout capability has no registered research snapshot")
    return dict(capability.registered_entry), bytes(capability.ledger_prefix)


def reverify_authorized_state(token: str, candidate_id: str) -> None:
    """Fail if sealed research files changed while the one-shot run was executing."""
    verify_token(token, candidate_id=candidate_id)
    capability = _ISSUED[token]
    expected = capability.authorization_identity
    if not expected:
        raise RuntimeError("holdout token has no authorization identity")
    if not _registry_committed():
        raise RuntimeError("candidate registry changed during holdout evaluation")
    registry = _registry()
    entry = registry.get(candidate_id)
    if not isinstance(entry, dict):
        raise RuntimeError("candidate registration changed during holdout evaluation")
    spec_path = CANDIDATES_DIR / candidate_id / "spec.md"
    signal_path = CANDIDATES_DIR / candidate_id / "signal.py"
    if spec_sha256(spec_path) != expected["spec_sha256"]:
        raise RuntimeError("candidate spec changed during holdout evaluation")
    seal = _verify_research_seal(candidate_id, entry, signal_path)
    current = {
        key: value
        for key, value in seal.items()
        if isinstance(value, str) and key != "current_commit"
    }
    current["signal_sha256"] = spec_sha256(signal_path)
    for key, value in expected.items():
        if key in {"candidate_id", "spec_sha256"}:
            continue
        if current.get(key) != value:
            raise RuntimeError(f"{candidate_id} {key} changed during holdout evaluation")


def authorize_g1_generation() -> str:
    """Token for G1 hypothesis-generation access to the post-cutoff slice ONLY
    (POST_CUTOFF_START onward; see research/debates/protocol_deviations.md D1).
    Every grant is logged; G1 candidates' holdout ends at 2026-01-31.
    """
    from . import G1_GENERATION_END, POST_CUTOFF_START

    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    log_path = CANDIDATES_DIR / "g1_access_log.json"
    lock_path = CANDIDATES_DIR / ".g1_access_log.lock"
    max_end = G1_GENERATION_END
    input_identity = {
        "data_manifest_sha256": spec_sha256(MANIFEST_PATH),
        "universe_sha256": spec_sha256(UNIVERSE_PATH),
    }
    event = {
        "granted_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "window_start": POST_CUTOFF_START,
        "window_end": max_end,
        **input_identity,
    }
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            if log_path.exists():
                try:
                    log = json.loads(log_path.read_text())
                except (OSError, json.JSONDecodeError) as exc:
                    raise RuntimeError(f"invalid G1 access log: {exc}") from exc
                if not isinstance(log, list) or not all(isinstance(item, dict) for item in log):
                    raise RuntimeError("invalid G1 access log: expected an event list")
            else:
                log = []
            log.append(event)
            atomic_write_text(log_path, dumps(log, indent=1))
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    token = secrets.token_urlsafe(32)
    _ISSUED[token] = _Capability("g1_generation", None, max_end, input_identity=input_identity)
    return token


def record_results(candidate_id: str, results: dict, token: str) -> Path:
    """Write the candidate's single holdout result file. Fails if it exists."""
    if not _CANDIDATE_RE.fullmatch(candidate_id):
        raise RuntimeError(f"invalid candidate id {candidate_id!r}")
    if not isinstance(results, dict):
        raise RuntimeError("holdout results must be a JSON object")
    results_path = CANDIDATES_DIR / candidate_id / "holdout_results.json"
    if results_path.exists():
        raise RuntimeError(f"{candidate_id} holdout results already recorded — immutable")
    verify_token(token, candidate_id=candidate_id)
    capability = _ISSUED[token]
    results = dict(results)
    supplied_identity = results.get("authorization_identity")
    if supplied_identity is not None and supplied_identity != capability.authorization_identity:
        raise RuntimeError("holdout results have the wrong authorization identity")
    results["authorization_identity"] = capability.authorization_identity
    try:
        serialized = json.dumps(results, indent=1, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"holdout results are not strict JSON: {exc}") from exc
    results_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with results_path.open("x") as handle:
            handle.write(serialized)
    except FileExistsError as exc:
        raise RuntimeError(f"{candidate_id} holdout results already recorded — immutable") from exc
    # Revoke every token for this candidate: the single shot is consumed.
    for issued, capability in list(_ISSUED.items()):
        if capability.candidate_id == candidate_id:
            del _ISSUED[issued]
    return results_path
