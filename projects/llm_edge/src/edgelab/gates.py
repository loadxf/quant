"""Gate 1/2 evaluation driver (protocol.md section 7).

Runs a candidate's declaration-only signal.py through the trusted causal
registry against train+validation data, computes every
pre-registered gate quantity, and writes candidates/C###/results_validation.json.
Gate 3 (holdout) lives in holdout_eval.py and is NOT reachable from here.

Each signal.py declares SIGNAL_KIND, literal parameters, and a PERTURBATIONS
manifest. Gate 2 scales every declared
signal or backtest parameter by 0.75x and 1.25x and re-runs validation (integer
windows are rounded, minimum 1). All runs are ledgered by the engine.
"""

from __future__ import annotations

import ast
import ctypes
import ctypes.util
import errno
import hashlib
import json
import math
import multiprocessing as mp
import numbers
import os
import resource
import secrets
import sys
import time
from multiprocessing.connection import wait as wait_for_process

import numpy as np
import pandas as pd

from . import (
    CANDIDATES_DIR,
    REPO_ROOT,
    TRAIN_END,
    TRAIN_START,
    VALIDATION_END,
    VALIDATION_START,
)
from .backtest import record_failed_trial, run_backtest
from .costs import SWEEP_BPS, cost_rate
from .cpcv import cpcv_sharpe_distribution
from .data import FieldBundle, load_panels, load_universe_snapshot
from .jsonutil import atomic_write_text, dumps
from .signals import compute_declared_signal, validate_declaration
from .stats import newey_west_tstat, sharpe_ratio

GATE1 = {"min_val_sr": 0.5, "min_abs_t": 2.0, "min_stability_median": 0.0}
FAMILY_RETURNS_PATH = CANDIDATES_DIR / "family_returns_train_val.parquet"
FAMILY_META_PATH = CANDIDATES_DIR / "family_returns_train_val.meta.json"

try:
    _SECCOMP_LIBRARY = ctypes.CDLL(ctypes.util.find_library("seccomp") or "libseccomp.so.2")
except OSError:
    _SECCOMP_LIBRARY = None


def _parse_signal_declaration(source_text: str, filename: str) -> dict[str, object]:
    """Parse a declaration-only candidate and reject every executable form."""
    tree = ast.parse(source_text, filename=filename)
    values: dict[str, object] = {}
    for position, node in enumerate(tree.body):
        if (
            position == 0
            and isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            raise RuntimeError(
                "promotable signal.py must contain only a docstring and literal declarations"
            )
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not target.id.isupper():
            raise RuntimeError("signal declaration names must be uppercase constants")
        if target.id in values:
            raise RuntimeError(f"duplicate signal declaration {target.id}")
        try:
            values[target.id] = ast.literal_eval(node.value)
        except (ValueError, TypeError) as exc:
            raise RuntimeError(f"signal declaration {target.id} must be a literal value") from exc
    return validate_declaration(values)


def signal_metadata(candidate_id: str, source_text: str | None = None) -> dict[str, object]:
    """Read and validate a declaration-only promotable candidate."""
    path = CANDIDATES_DIR / candidate_id / "signal.py"
    if source_text is None:
        if not path.is_file():
            raise RuntimeError(f"candidate signal module not found: {path}")
        source_text = path.read_text()
    return _parse_signal_declaration(source_text, str(path))


def signal_declaration_snapshot(candidate_id: str) -> tuple[dict[str, object], str, str]:
    """Read, hash, and parse one exact candidate declaration snapshot."""
    path = CANDIDATES_DIR / candidate_id / "signal.py"
    try:
        payload = path.read_bytes()
        source = payload.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"could not read candidate declaration {path}: {exc}") from exc
    declaration = _parse_signal_declaration(source, str(path))
    return declaration, source, hashlib.sha256(payload).hexdigest()


def family_artifact_identity(candidate_ids: list[str]) -> dict[str, object]:
    """Identity of every executable/input component behind family returns."""
    from .holdout_gate import research_identity

    return research_identity(candidate_ids, candidates_dir=CANDIDATES_DIR)


def _publish_family_returns(panel: pd.DataFrame, identity: dict[str, object]) -> None:
    """Atomically publish one exact parquet snapshot and its bound metadata."""
    temporary = FAMILY_RETURNS_PATH.with_name(
        f".{FAMILY_RETURNS_PATH.name}.{secrets.token_hex(6)}.tmp"
    )
    try:
        panel.to_parquet(temporary)
        # Hash the exact bytes being published. Reopening the destination after
        # replace would let a concurrent same-path replacement get blessed by
        # otherwise-valid metadata.
        artifact_sha256 = hashlib.sha256(temporary.read_bytes()).hexdigest()
        os.replace(temporary, FAMILY_RETURNS_PATH)
    finally:
        temporary.unlink(missing_ok=True)
    metadata = dict(identity)
    metadata["artifact_sha256"] = artifact_sha256
    atomic_write_text(FAMILY_META_PATH, dumps(metadata, indent=1, sort_keys=True))


def _bound_research_identity(
    candidate_ids: list[str],
    fields: dict[str, object],
    declaration_hashes: dict[str, str],
) -> dict[str, object]:
    """Bind an artifact to the exact declarations and input snapshots used."""
    if not isinstance(fields, FieldBundle):
        raise RuntimeError("gate evaluation requires a bound field snapshot")
    identity = family_artifact_identity(candidate_ids)
    for candidate_id, digest in declaration_hashes.items():
        if identity["signal_sha256"].get(candidate_id) != digest:
            raise RuntimeError(f"{candidate_id} declaration changed during gate evaluation")
    for key in ("data_manifest_sha256", "universe_sha256"):
        if fields.input_identity.get(key) != identity.get(key):
            raise RuntimeError(f"gate fields were built from a different {key}")
    return identity


def _literal_number(node: ast.AST | None) -> int | float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
    ):
        return -node.operand.value
    return None


def _validate_candidate_source(source: str, filename: str) -> None:
    """Reject common vectorized future-access forms before execution."""
    tree = ast.parse(source, filename=filename)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            name = node.func.attr
            periods = node.args[0] if node.args else None
            for keyword in node.keywords:
                if keyword.arg in {"periods", "shift"}:
                    periods = keyword.value
                if (
                    name == "rolling"
                    and keyword.arg == "center"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                ):
                    raise RuntimeError("candidate source uses forbidden centered rolling window")
            value = _literal_number(periods)
            if name in {"shift", "diff", "pct_change"} and value is not None and value < 0:
                raise RuntimeError(
                    f"candidate source uses forbidden future access: {name}({value})"
                )
            if name == "roll" and len(node.args) > 1:
                value = _literal_number(node.args[1])
                if value is not None and value < 0:
                    raise RuntimeError("candidate source uses forbidden negative array roll")
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            position = _literal_number(node.slice)
            if (
                node.value.attr in {"iat", "iloc", "index"}
                and position is not None
                and position < 0
            ):
                raise RuntimeError("candidate source uses forbidden negative positional access")


def _declares_signal_kind(source: str, filename: str) -> bool:
    tree = ast.parse(source, filename=filename)
    return any(
        isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "SIGNAL_KIND" for target in node.targets
        )
        for node in tree.body
    )


def _validate_signal_frame(signal: object, reference: pd.DataFrame) -> pd.DataFrame:
    if type(signal) is not pd.DataFrame or type(signal.index) is not pd.DatetimeIndex:
        raise TypeError("candidate signal must be a DataFrame with a DatetimeIndex")
    if signal.index.tz is not None:
        raise TypeError("candidate signal index must be timezone-naive like the price panel")
    if not signal.index.equals(reference.index) or not signal.columns.equals(reference.columns):
        raise RuntimeError("candidate signal must match the selected price panel")
    if not all(isinstance(column, str) for column in signal.columns):
        raise TypeError("candidate signal columns must be strings")
    values = signal.to_numpy(dtype=float, copy=True)
    if np.isinf(values).any():
        raise TypeError("candidate signal contains infinite values")
    return signal


def _install_seccomp() -> None:
    """Deny host I/O and process creation in the candidate worker at kernel level."""
    if _SECCOMP_LIBRARY is None:
        raise RuntimeError("libseccomp is required for isolated candidate execution")
    seccomp = _SECCOMP_LIBRARY
    seccomp.seccomp_init.argtypes = [ctypes.c_uint32]
    seccomp.seccomp_init.restype = ctypes.c_void_p
    seccomp.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    seccomp.seccomp_syscall_resolve_name.restype = ctypes.c_int
    seccomp.seccomp_rule_add.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    seccomp.seccomp_rule_add.restype = ctypes.c_int
    seccomp.seccomp_load.argtypes = [ctypes.c_void_p]
    seccomp.seccomp_load.restype = ctypes.c_int
    seccomp.seccomp_release.argtypes = [ctypes.c_void_p]

    allow = 0x7FFF0000
    deny = 0x00050000 | errno.EPERM
    context = seccomp.seccomp_init(allow)
    if not context:
        raise RuntimeError("could not initialize candidate seccomp filter")
    # The worker has already received its serialized inputs and loaded the
    # trusted numerical stack. It only needs memory/CPU plus its result pipe.
    # Deny both direct syscalls and Python wrappers so ctypes cannot bypass the
    # higher-level audit hook.
    denied = {
        "access",
        "acct",
        "bind",
        "bpf",
        "chdir",
        "chmod",
        "chown",
        "chroot",
        "clone",
        "clone3",
        "close_range",
        "connect",
        "creat",
        "execve",
        "execveat",
        "faccessat",
        "faccessat2",
        "fchmod",
        "fchmodat",
        "fchown",
        "fchownat",
        "fork",
        "fstatat64",
        "ftruncate",
        "futimesat",
        "getdents",
        "getdents64",
        "inotify_add_watch",
        "inotify_init",
        "inotify_init1",
        "io_uring_enter",
        "io_uring_register",
        "io_uring_setup",
        "kill",
        "lchown",
        "link",
        "linkat",
        "listen",
        "lookup_dcookie",
        "lsetxattr",
        "mknod",
        "mknodat",
        "mount",
        "move_mount",
        "name_to_handle_at",
        "newfstatat",
        "open",
        "open_by_handle_at",
        "open_tree",
        "openat",
        "openat2",
        "pivot_root",
        "process_vm_readv",
        "process_vm_writev",
        "ptrace",
        "readlink",
        "readlinkat",
        "removexattr",
        "rename",
        "renameat",
        "renameat2",
        "rmdir",
        "setns",
        "setxattr",
        "socket",
        "socketpair",
        "stat",
        "stat64",
        "statx",
        "symlink",
        "symlinkat",
        "tkill",
        "truncate",
        "umount2",
        "unlink",
        "unlinkat",
        "unshare",
        "uselib",
        "utime",
        "utimensat",
        "utimes",
        "vfork",
    }
    try:
        for name in sorted(denied):
            syscall = seccomp.seccomp_syscall_resolve_name(name.encode())
            if syscall < 0:  # syscall is not present on this architecture
                continue
            result = seccomp.seccomp_rule_add(context, deny, syscall, 0)
            if result != 0:
                raise RuntimeError(f"could not deny candidate syscall {name}: {-result}")
        result = seccomp.seccomp_load(context)
        if result != 0:
            raise RuntimeError(f"could not load candidate seccomp filter: {-result}")
    finally:
        seccomp.seccomp_release(context)


def _causality_positions(length: int) -> np.ndarray:
    # Every boundary must be checked.  A deterministic subset is not an audit:
    # candidate code can preserve only the sampled rows while using future data
    # everywhere else.  The final row has no future observation to expose.
    return np.arange(max(0, length - 1))


def _candidate_audit_hook(event, args) -> None:
    if event == "open":
        raw = args[0]
        if isinstance(raw, int):
            return
        mode = args[1] if len(args) > 1 else "r"
        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        if any(flag in str(mode) for flag in ("w", "a", "+", "x")) or flags & write_flags:
            raise PermissionError("candidate signal file writes are denied")
        raise PermissionError(f"candidate signal file access denied: {raw}")
    if event.startswith(("socket.", "subprocess.")) or event in {
        "mmap.__new__",
        "os.chmod",
        "os.chown",
        "os.fork",
        "os.forkpty",
        "os.kill",
        "os.link",
        "os.mkdir",
        "os.mknod",
        "os.remove",
        "os.removexattr",
        "os.rename",
        "os.rmdir",
        "os.system",
        "os.posix_spawn",
        "os.exec",
        "os.symlink",
        "os.setxattr",
        "os.truncate",
        "os.utime",
        "ctypes.dlopen",
    }:
        raise PermissionError(f"candidate signal operation denied: {event}")


def _configure_candidate_worker(cpu_seconds: float) -> None:
    # Candidate imports can only resolve modules loaded before the filesystem
    # sandbox. This is the one additional trusted utility used by a signal.
    __import__("edgelab.market_calendar")
    os.environ.clear()
    cpu_limit = max(1, math.ceil(cpu_seconds))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit + 1))
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    sys.addaudithook(_candidate_audit_hook)
    _install_seccomp()


def _execute_signal(code, filename, fields, overrides, frame_to_numpy):
    namespace = {"__builtins__": __builtins__, "__file__": filename, "__name__": "signal"}
    exec(code, namespace)
    namespace.update(overrides)
    compute = namespace.get("compute_signal")
    if not callable(compute):
        raise RuntimeError("candidate signal.py must define compute_signal(fields)")
    frame = compute(fields)
    if type(frame) is not pd.DataFrame or type(frame.index) is not pd.DatetimeIndex:
        raise TypeError("candidate signal must be a DataFrame with a DatetimeIndex")
    if frame.index.tz is not None:
        raise TypeError("candidate signal index must be timezone-naive like the price panel")
    if not all(isinstance(column, str) for column in frame.columns):
        raise TypeError("candidate signal columns must be strings")
    values = frame_to_numpy(frame, dtype=float, copy=True)
    if np.isinf(values).any():
        raise TypeError("candidate signal contains infinite values")
    return frame, values


def _signal_digest(values: np.ndarray) -> str:
    canonical = np.asarray(values, dtype="<f8").copy(order="C")
    canonical[np.isnan(canonical)] = np.nan
    canonical[canonical == 0] = 0
    shape = ",".join(str(size) for size in canonical.shape).encode()
    return hashlib.sha256(shape + b"\0" + canonical.tobytes()).hexdigest()


def _send_worker_error(connection, exc: BaseException) -> None:
    try:
        payload = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        connection.send_bytes(json.dumps(payload, separators=(",", ":")).encode())
    except BaseException:
        pass


def _candidate_worker(connection, source, filename, fields, overrides, cpu_seconds) -> None:
    """Run one untrusted signal computation in a clean, confined process."""
    try:
        code = compile(source, filename, "exec")
        _configure_candidate_worker(cpu_seconds)
        signal, values = _execute_signal(code, filename, fields, overrides, pd.DataFrame.to_numpy)
        reference = fields["adjclose"]
        if not signal.index.equals(reference.index) or not signal.columns.equals(reference.columns):
            raise RuntimeError("candidate signal must match the selected price panel")
        payload = {
            "status": "ok",
            "index_values": signal.index.asi8.tolist(),
            "index_unit": signal.index.unit,
            "columns": list(signal.columns),
            "values": values.tolist(),
        }
        connection.send_bytes(json.dumps(payload, separators=(",", ":")).encode())
    except BaseException as exc:
        _send_worker_error(connection, exc)
    finally:
        connection.close()


def _candidate_prefix_worker(connection, source, filename, overrides, cpu_seconds, steps) -> None:
    """Audit incrementally supplied prefixes; this process never receives future rows."""
    try:
        code = compile(source, filename, "exec")
        _configure_candidate_worker(cpu_seconds)
        frame_to_numpy = pd.DataFrame.to_numpy
        concatenate = pd.concat
        fields: dict[str, object] = {}
        for _ in range(steps):
            updates, metadata = connection.recv()
            fields.update(metadata)
            for name, value in updates.items():
                fields[name] = (
                    value if name not in fields else concatenate([fields[name], value], axis=0)
                )
            signal, values = _execute_signal(code, filename, fields, overrides, frame_to_numpy)
            reference = fields["adjclose"]
            if not signal.index.equals(reference.index) or not signal.columns.equals(
                reference.columns
            ):
                raise RuntimeError(
                    "candidate compute_signal must return the exact selected-universe prefix"
                )
            payload = {
                "status": "ok",
                "shape": list(values.shape),
                "digest": _signal_digest(values),
            }
            connection.send_bytes(json.dumps(payload, separators=(",", ":")).encode())
    except BaseException as exc:
        _send_worker_error(connection, exc)
    finally:
        connection.close()


def _receive_worker_payload(parent, process, timeout: float) -> dict:
    ready = wait_for_process([parent, process.sentinel], timeout)
    if not ready:
        raise RuntimeError(f"candidate signal timed out after {timeout:g}s")
    if parent not in ready:
        process.join(1)
        raise RuntimeError(
            f"isolated candidate signal exited with status {process.exitcode} without a response"
        )
    try:
        payload = json.loads(parent.recv_bytes(256 * 1024**2))
    except (EOFError, OSError) as exc:
        process.join(1)
        if process.exitcode in (0, None):
            raise RuntimeError(f"isolated candidate signal returned invalid data: {exc}") from None
        raise RuntimeError(
            f"isolated candidate signal exited with status {process.exitcode} without a response"
        ) from None
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"isolated candidate signal returned invalid data: {exc}") from None
    if not isinstance(payload, dict) or payload.get("status") not in {"ok", "error"}:
        raise RuntimeError("isolated candidate signal returned an invalid response")
    if payload["status"] == "error":
        raise RuntimeError(f"isolated candidate signal failed: {payload.get('error', 'unknown')}")
    return payload


def _audit_isolated_prefixes(
    source: str,
    filename: str,
    fields: dict[str, object],
    overrides: dict[str, object],
    full_signal: pd.DataFrame,
    timeout: float,
) -> None:
    """Stream only increasing prefixes to a separate confined audit worker."""
    reference = fields["adjclose"]
    positions = _causality_positions(len(reference))
    context = mp.get_context("spawn")
    parent, child = context.Pipe(duplex=True)
    process = context.Process(
        target=_candidate_prefix_worker,
        args=(child, source, filename, overrides, timeout, len(positions)),
        daemon=True,
    )
    process.start()
    child.close()
    deadline = time.monotonic() + timeout
    previous = -1
    metadata = {
        name: value.copy() if hasattr(value, "copy") else value
        for name, value in fields.items()
        if not (
            isinstance(value, (pd.DataFrame, pd.Series)) and value.index.equals(reference.index)
        )
    }
    try:
        for step, raw_position in enumerate(positions):
            position = int(raw_position)
            updates = {
                name: value.iloc[previous + 1 : position + 1].copy()
                for name, value in fields.items()
                if isinstance(value, (pd.DataFrame, pd.Series))
                and value.index.equals(reference.index)
            }
            parent.send((updates, metadata if step == 0 else {}))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"candidate signal timed out after {timeout:g}s")
            payload = _receive_worker_payload(parent, process, remaining)
            expected = full_signal.iloc[: position + 1].to_numpy(dtype=float)
            if payload.get("shape") != list(expected.shape) or payload.get(
                "digest"
            ) != _signal_digest(expected):
                raise RuntimeError(
                    f"candidate failed causality audit at "
                    f"{reference.index[position].date()}: earlier signal values changed"
                )
            previous = position
        process.join(5)
        if process.exitcode not in (0, None):
            raise RuntimeError(f"isolated candidate signal exited with status {process.exitcode}")
    finally:
        parent.close()
        if process.is_alive():
            process.terminate()
        process.join(5)


def compute_signal_isolated(
    candidate_id: str,
    fields: dict[str, object],
    overrides: dict[str, object] | None = None,
    timeout: float = 120.0,
    causality_audit: bool = False,
    source_text: str | None = None,
) -> pd.DataFrame:
    """Compute a signal through the trusted registry or confined dev executor.

    Promotable candidates must be declaration-only and are dispatched through
    :mod:`edgelab.signals`.  The arbitrary-source branch exists only for
    isolated development/adversarial tests; ``signal_metadata`` rejects it, so
    registration, gates, family artifacts, and holdout cannot reach it.
    """
    signal_path = CANDIDATES_DIR / candidate_id / "signal.py"
    if source_text is None:
        if not signal_path.is_file():
            raise RuntimeError(f"candidate signal module not found: {signal_path}")
        source = signal_path.read_text()
    else:
        source = source_text
    _validate_candidate_source(source, str(signal_path))
    reference = fields.get("adjclose")
    if not isinstance(reference, pd.DataFrame):
        raise RuntimeError("candidate fields must include an adjclose DataFrame")
    if causality_audit and len(reference) < 20:
        raise RuntimeError("candidate signal computation needs at least 20 dates")
    if _declares_signal_kind(source, str(signal_path)):
        declaration = _parse_signal_declaration(source, str(signal_path))
        signal = compute_declared_signal(fields, declaration, overrides or {})
        # Causality is enforced structurally here: candidates select only a
        # sealed trusted handler and literal, schema-checked parameters. Every
        # handler is exhaustively prefix-tested; no candidate Python executes.
        return _validate_signal_frame(signal, reference)

    context = mp.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_candidate_worker,
        args=(
            child,
            source,
            str(signal_path),
            fields,
            overrides or {},
            timeout,
        ),
        daemon=True,
    )
    process.start()
    child.close()
    try:
        payload = _receive_worker_payload(parent, process, timeout)
        process.join(5)
        if process.exitcode not in (0, None):
            raise RuntimeError(f"isolated candidate signal exited with status {process.exitcode}")
        try:
            values = np.asarray(payload["values"], dtype=float)
            unit = payload["index_unit"]
            if unit not in {"s", "ms", "us", "ns"}:
                raise ValueError(f"unsupported datetime unit {unit!r}")
            index = pd.DatetimeIndex(
                np.asarray(payload["index_values"], dtype=f"datetime64[{unit}]")
            )
            columns = pd.Index(payload["columns"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError(
                f"isolated candidate signal returned an invalid frame: {exc}"
            ) from None
        if values.ndim != 2 or values.shape != (len(index), len(columns)):
            raise RuntimeError("isolated candidate signal returned inconsistent frame dimensions")
        signal = pd.DataFrame(values, index=index, columns=columns)
        if causality_audit:
            _audit_isolated_prefixes(
                source,
                str(signal_path),
                fields,
                overrides or {},
                signal,
                timeout,
            )
        return signal
    finally:
        parent.close()
        if process.is_alive():
            process.terminate()
        process.join(5)


def load_equity_fields(
    end: str | None = None, token: str | None = None, candidate_id: str | None = None
) -> dict[str, object]:
    universe, universe_sha256 = load_universe_snapshot(REPO_ROOT / "data" / "universe.json")
    expected = None
    if token is not None:
        from .holdout_gate import authorized_input_identity

        expected = authorized_input_identity(token, candidate_id)
        if expected.get("universe_sha256") != universe_sha256:
            raise RuntimeError("data universe changed after the research capability was granted")
    equities = list(universe["equities"])
    etfs = list(universe["etfs"])
    panels = load_panels(
        tickers=equities,
        end=end,
        _holdout_token=token,
        _candidate_id=candidate_id,
        extra_adjclose_tickers=etfs,
        _expected_input_identity=expected,
    )
    fields = FieldBundle(
        {
            field_name: panel
            for field_name, panel in panels.items()
            if field_name != "extra_adjclose"
        },
        input_identity={
            **panels.input_identity,
            "universe_sha256": universe_sha256,
        },
        universe=universe,
    )
    fields["etf_adjclose"] = panels["extra_adjclose"]
    fields["sectors"] = dict(universe["sectors"])
    return fields


def _slice(series: pd.Series, start: str, end: str) -> pd.Series:
    return series[(series.index >= pd.Timestamp(start)) & (series.index <= pd.Timestamp(end))]


def load_etf_fields(
    end: str | None = None, token: str | None = None, candidate_id: str | None = None
) -> dict[str, pd.DataFrame]:
    universe, universe_sha256 = load_universe_snapshot(REPO_ROOT / "data" / "universe.json")
    expected = None
    if token is not None:
        from .holdout_gate import authorized_input_identity

        expected = authorized_input_identity(token, candidate_id)
        if expected.get("universe_sha256") != universe_sha256:
            raise RuntimeError("data universe changed after the research capability was granted")
    etfs = list(universe["etfs"])
    panels = load_panels(
        tickers=etfs,
        end=end,
        _holdout_token=token,
        _candidate_id=candidate_id,
        _expected_input_identity=expected,
    )
    panels.input_identity["universe_sha256"] = universe_sha256
    panels.universe = universe
    return panels


def audit_signal_causality(
    module,
    fields: dict[str, object],
    full_signal: pd.DataFrame | None = None,
    compute=None,
) -> None:
    """Future truncation must not change earlier signal values.

    Every boundary is checked. This helper and the seccomp-confined arbitrary
    executor are development/adversarial tools only. Promotable production
    candidates are declaration-only and use the trusted registry, whose every
    handler is exhaustively prefix-tested independently.
    """
    reference = fields["adjclose"]
    runner = compute or module.compute_signal
    signal = runner(fields) if full_signal is None else full_signal
    if not isinstance(signal, pd.DataFrame) or not signal.index.equals(reference.index):
        raise RuntimeError("candidate signal must be a DataFrame on the price-panel index")
    if not signal.columns.equals(reference.columns):
        raise RuntimeError("candidate signal columns must exactly match the selected universe")
    values = signal.to_numpy(dtype=float)
    if np.isinf(values).any():
        raise RuntimeError("candidate signal contains infinite values")
    if len(reference.index) < 20:
        raise RuntimeError("causality audit needs at least 20 dates")

    # A subset is gameable: candidate code can leak on every untested row.
    # Arbitrary development candidates therefore check every boundary.
    for position in _causality_positions(len(reference.index)):
        cutoff = reference.index[position]
        truncated = {
            name: (
                value.loc[:cutoff].copy()
                if isinstance(value, (pd.DataFrame, pd.Series))
                and value.index.equals(reference.index)
                else value.copy()
                if hasattr(value, "copy")
                else value
            )
            for name, value in fields.items()
        }
        check = runner(truncated)
        expected_index = reference.index[: position + 1]
        if (
            not isinstance(check, pd.DataFrame)
            or not check.index.equals(expected_index)
            or not check.columns.equals(signal.columns)
        ):
            raise RuntimeError(
                "candidate compute_signal must return the exact selected-universe prefix"
            )
        expected = signal.loc[:cutoff].to_numpy(dtype=float)
        observed = check.to_numpy(dtype=float)
        if not np.allclose(expected, observed, rtol=1e-12, atol=1e-14, equal_nan=True):
            mismatch = ~np.isclose(expected, observed, rtol=1e-12, atol=1e-14, equal_nan=True)
            raise RuntimeError(
                f"candidate failed causality audit at {cutoff.date()}: "
                f"{int(mismatch.sum())} earlier signal values changed when future data was removed"
            )


def _perturbations_pass(perturbations: dict[str, object]) -> bool:
    if not perturbations:
        return True  # no numeric signal parameter exists to perturb
    return all(
        isinstance(value, numbers.Real)
        and not isinstance(value, bool)
        and np.isfinite(float(value))
        and float(value) > 0
        for value in perturbations.values()
    )


def _signals_materially_differ(base: pd.DataFrame, perturbed: pd.DataFrame) -> bool:
    if base.shape != perturbed.shape:
        return True
    return not np.allclose(
        base.to_numpy(dtype=float),
        perturbed.to_numpy(dtype=float),
        rtol=1e-12,
        atol=1e-14,
        equal_nan=True,
    )


def _validation_execution_differs(base, perturbed) -> bool:
    """Return whether a perturbation changes the validation portfolio."""
    base_weights = base.weights.loc[VALIDATION_START:VALIDATION_END]
    perturbed_weights = perturbed.weights.loc[VALIDATION_START:VALIDATION_END]
    return not base_weights.equals(perturbed_weights)


def _scaled_parameter(value: int | float, factor: float):
    scaled = value * factor
    if isinstance(value, int):
        scaled = max(1, round(scaled))
        if scaled == value:
            if factor > 1:
                scaled = value + 1
            elif value > 1:
                scaled = value - 1
            else:
                return None
    return scaled


def _numeric_paths(value, prefix=()):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [(prefix, value)]
    paths = []
    if isinstance(value, tuple):
        for index, item in enumerate(value):
            paths.extend(_numeric_paths(item, (*prefix, index)))
    return paths


def _replace_tuple_path(value: tuple, path: tuple[int, ...], replacement):
    items = list(value)
    index = path[0]
    items[index] = (
        _replace_tuple_path(items[index], path[1:], replacement) if len(path) > 1 else replacement
    )
    return tuple(items)


def _parameter_perturbations(metadata: dict[str, object]):
    """Build variants from the candidate's explicit perturbation manifest."""
    declared = metadata.get("PERTURBATIONS")
    if not isinstance(declared, (tuple, list)) or not all(
        isinstance(name, str) and name for name in declared
    ):
        raise RuntimeError("candidate must declare PERTURBATIONS as a tuple of parameter names")
    if len(set(declared)) != len(declared):
        raise RuntimeError("candidate PERTURBATIONS contains duplicate names")
    variants: list[tuple[str, dict[str, object]]] = []
    for name in declared:
        if name == "EXPR":
            continue
        value = metadata.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise RuntimeError(
                f"declared perturbation parameter {name!r} is missing or non-numeric"
            )
        for factor in (0.75, 1.25):
            scaled = _scaled_parameter(value, factor)
            if scaled is None:
                continue
            # Cross-sectional tails cannot exceed half the universe. A
            # boundary value such as the B003/C003 median split therefore has
            # only one feasible ±25% variant; an impossible 0.625 quantile is
            # not evidence of failed robustness.
            if name == "QUANTILE" and not 0 < float(scaled) <= 0.5:
                continue
            if name in {"HOLD", "QUANTILE", "MIN_NAMES"}:
                key = {
                    "HOLD": "holding_days",
                    "QUANTILE": "quantile",
                    "MIN_NAMES": "min_names",
                }[name]
                overrides = {"__BACKTEST__": {key: scaled}}
            else:
                overrides = {name: scaled}
            variants.append((f"{name}x{factor}", overrides))

    expression = metadata.get("EXPR") if "EXPR" in declared else None
    if "EXPR" in declared:
        if not isinstance(expression, tuple):
            raise RuntimeError("declared EXPR must be a literal tuple")
        numeric_paths = _numeric_paths(expression)
        if not numeric_paths:
            raise RuntimeError("declared EXPR contains no numeric parameter to perturb")
        for path, value in numeric_paths:
            path_label = ".".join(map(str, path))
            for factor in (0.75, 1.25):
                scaled = _scaled_parameter(value, factor)
                if scaled is None:
                    continue
                changed = _replace_tuple_path(expression, path, scaled)
                variants.append((f"EXPR[{path_label}]x{factor}", {"EXPR": changed}))
    return variants


def _candidate_specific_gate2(
    candidate_id: str,
    fields: dict[str, object],
    candidate_validation: pd.Series,
    base_cost: float,
) -> dict[str, object]:
    """Exact candidate-specific comparisons declared in the frozen specs."""
    adjclose = fields["adjclose"]
    checks: dict[str, object] = {}
    required: list[bool] = []

    def baseline(
        label: str,
        signal: pd.DataFrame,
        *,
        holding_days: int = 1,
        quantile: float = 0.1,
        min_names: int = 20,
    ) -> pd.Series:
        result = run_backtest(
            signal,
            adjclose,
            candidate_id=f"gate2_{candidate_id}_{label}",
            split="val_baseline",
            cost_bps=base_cost,
            holding_days=holding_days,
            quantile=quantile,
            min_names=min_names,
            start_date=TRAIN_START,
            ledger_start_date=VALIDATION_START,
            ledger_end_date=VALIDATION_END,
        )
        return _slice(result.returns_net, VALIDATION_START, VALIDATION_END)

    def outperform(label: str, comparison: pd.Series) -> None:
        candidate_sr = sharpe_ratio(candidate_validation)
        baseline_sr = sharpe_ratio(comparison)
        passed = bool(
            np.isfinite(candidate_sr) and np.isfinite(baseline_sr) and candidate_sr > baseline_sr
        )
        checks[label] = {
            "candidate_sr": candidate_sr,
            "baseline_sr": baseline_sr,
            "pass": passed,
        }
        required.append(passed)

    def correlation(label: str, comparison: pd.Series, require_residual: bool = False) -> None:
        aligned = pd.concat(
            {"candidate": candidate_validation, "baseline": comparison}, axis=1
        ).dropna()
        corr = float(aligned["candidate"].corr(aligned["baseline"])) if len(aligned) > 2 else np.nan
        detail: dict[str, object] = {
            "daily_return_correlation": corr,
            "t1_reversal_ceiling": bool(np.isfinite(corr) and abs(corr) > 0.6),
            "n_obs": len(aligned),
        }
        if require_residual:
            variance = float(aligned["baseline"].var(ddof=0))
            if variance > 0:
                covariance = float(np.cov(aligned["candidate"], aligned["baseline"], ddof=0)[0, 1])
                residual = aligned["candidate"] - covariance / variance * aligned["baseline"]
                residual_sr = sharpe_ratio(residual)
            else:
                residual_sr = float("nan")
            passed = bool(np.isfinite(residual_sr) and residual_sr > 0)
            detail["orthogonalized_sr"] = residual_sr
            detail["pass"] = passed
            required.append(passed)
        checks[label] = detail

    reversal_5 = -adjclose.pct_change(5, fill_method=None)
    if candidate_id == "C001":
        outperform("outperform_C004", baseline("C004", reversal_5))
    elif candidate_id == "C002":
        reversal_1 = -adjclose.pct_change(fill_method=None)
        outperform(
            "outperform_ungated_ret1",
            baseline("ungated_ret1", reversal_1, holding_days=5),
        )
    elif candidate_id == "C003":
        log_volume = np.log(fields["volume"].where(fields["volume"] > 0))
        volz = (log_volume - log_volume.rolling(63).mean()) / log_volume.rolling(63).std()
        spike_entry = reversal_5.where(volz > 2)
        outperform(
            "outperform_spike_entry",
            baseline(
                "spike_entry",
                spike_entry,
                holding_days=10,
                quantile=0.5,
                min_names=4,
            ),
        )
        outperform(
            "outperform_plain_ret5",
            baseline("plain_ret5", reversal_5, holding_days=10),
        )
    elif candidate_id == "C013":
        reversal_21 = -adjclose.pct_change(21, fill_method=None)
        outperform(
            "outperform_C012_same_hold",
            baseline("C012_same_hold", reversal_21, holding_days=21),
        )

    if candidate_id in {"C007", "C008", "C009"}:
        c004 = baseline("C004_correlation", reversal_5)
        correlation(
            "correlation_C004",
            c004,
            require_residual=candidate_id == "C007",
        )
    if candidate_id == "C008":
        intraday = fields["close"] / fields["open"] - 1.0
        c006_signal = -intraday.rolling(5, min_periods=3).sum()
        correlation(
            "correlation_C006",
            baseline("C006_correlation", c006_signal),
        )

    checks["requirements_pass"] = all(required)
    return checks


def evaluate_candidate(
    candidate_id: str,
    fields: dict[str, object],
    declaration: dict[str, object] | None = None,
    declaration_sha256: str | None = None,
) -> dict:
    if declaration is None:
        metadata, _, declaration_sha256 = signal_declaration_snapshot(candidate_id)
    else:
        metadata = validate_declaration(declaration)
    if declaration_sha256 is None:
        raise RuntimeError("candidate declaration snapshot has no hash")
    hold = int(metadata.get("HOLD", 1))
    quantile = float(metadata.get("QUANTILE", 0.1))
    min_names = int(metadata.get("MIN_NAMES", 20))
    base_cost = cost_rate(str(metadata.get("UNIVERSE", "equities")))

    try:
        signal = _validate_signal_frame(
            compute_declared_signal(fields, metadata), fields["adjclose"]
        )
    except Exception as exc:
        record_failed_trial(candidate_id, "train_val", "registered signal", exc)
        raise

    identity = _bound_research_identity([candidate_id], fields, {candidate_id: declaration_sha256})

    def bt(
        split_name: str,
        cost_bps: float = base_cost,
        sig=None,
        cid=None,
        backtest_overrides: dict[str, object] | None = None,
        ledger_validation_only: bool = False,
    ):
        settings = {
            "quantile": quantile,
            "holding_days": hold,
            "min_names": min_names,
        }
        settings.update(backtest_overrides or {})
        return run_backtest(
            sig if sig is not None else signal,
            fields["adjclose"],
            candidate_id=cid or candidate_id,
            split=split_name,
            cost_bps=cost_bps,
            quantile=settings["quantile"],
            holding_days=settings["holding_days"],
            min_names=settings["min_names"],
            start_date=TRAIN_START,
            ledger_start_date=VALIDATION_START if ledger_validation_only else None,
            ledger_end_date=VALIDATION_END if ledger_validation_only else None,
        )

    full = bt("train_val")
    val_net = _slice(full.returns_net, VALIDATION_START, VALIDATION_END)
    train_net = _slice(full.returns_net, TRAIN_START, TRAIN_END)

    results: dict = {
        "candidate_id": candidate_id,
        "research_identity": identity,
        "params": {"hold": hold, "quantile": quantile, "min_names": min_names},
        "data": {
            "universe_size": len(fields["adjclose"].columns),
            "panel_start": str(fields["adjclose"].index.min().date()),
            "evaluation_start": TRAIN_START,
            "end": str(fields["adjclose"].index.max().date()),
        },
        "train": {
            "sr_net": sharpe_ratio(train_net),
            "nw_t": newey_west_tstat(train_net),
            "n_obs": len(train_net),
        },
        "validation": {
            "sr_net": sharpe_ratio(val_net),
            "sr_gross": sharpe_ratio(_slice(full.returns_gross, VALIDATION_START, VALIDATION_END)),
            "nw_t": newey_west_tstat(val_net),
            "n_obs": len(val_net),
            "mean_daily_turnover": float(
                _slice(full.turnover, VALIDATION_START, VALIDATION_END).mean()
            ),
        },
    }

    # Gate 1
    stability_returns = _slice(full.returns_net, TRAIN_START, VALIDATION_END)
    if len(stability_returns.dropna()) >= 8:
        stability = cpcv_sharpe_distribution(stability_returns)
    else:
        stability = {
            "interpretation": "combinatorial_subperiod_stability_not_oos",
            "n_paths": 0,
            "median_sr": float("nan"),
            "q25_sr": float("nan"),
            "min_sr": float("nan"),
            "frac_positive": float("nan"),
            "unavailable_reason": "fewer than eight non-missing return observations",
        }
    results["combinatorial_subperiod_stability"] = stability
    g1 = {
        "val_sr_gt_0.5": bool(results["validation"]["sr_net"] > GATE1["min_val_sr"]),
        "abs_t_gt_2": bool(abs(results["validation"]["nw_t"]) > GATE1["min_abs_t"]),
        "sign_positive": bool(results["validation"]["sr_net"] > 0),
        "stability_median_gt_0": bool(stability["median_sr"] > GATE1["min_stability_median"]),
    }
    g1["pass"] = all(g1.values())
    results["gate1"] = g1

    # Gate 2 (run regardless, for the record)
    if val_net.empty:
        half1 = half2 = val_net
    else:
        mid = val_net.index[len(val_net) // 2]
        half1, half2 = val_net[val_net.index <= mid], val_net[val_net.index > mid]

    ew_ret = fields["adjclose"].pct_change(fill_method=None).mean(axis=1)
    realized_vol = ew_ret.rolling(63).std()
    vol_at = realized_vol.reindex(val_net.index)
    hi_vol = val_net[vol_at > vol_at.median()]
    lo_vol = val_net[vol_at <= vol_at.median()]

    cost25 = bt("val_cost25", cost_bps=SWEEP_BPS[-1], ledger_validation_only=True)
    val25 = _slice(cost25.returns_net, VALIDATION_START, VALIDATION_END)
    (extra_cost,) = set(SWEEP_BPS[1:-1]) - {base_cost}
    extra_cost_result = bt(
        f"val_cost{int(extra_cost)}", cost_bps=extra_cost, ledger_validation_only=True
    )
    validation_cost_srs = {
        "0": results["validation"]["sr_gross"],
        str(int(base_cost)): results["validation"]["sr_net"],
        str(int(extra_cost)): sharpe_ratio(
            _slice(
                extra_cost_result.returns_net,
                VALIDATION_START,
                VALIDATION_END,
            )
        ),
        "25": sharpe_ratio(val25),
    }
    results["validation"]["cost_sweep_sr"] = {
        key: validation_cost_srs[key] for key in ("0", "5", "10", "25")
    }

    perturb_srs = {}
    perturbation_error = None
    try:
        perturbations = _parameter_perturbations(metadata)
    except RuntimeError as exc:
        perturbations = []
        perturbation_error = str(exc)
        perturb_srs["manifest"] = f"error: {exc}"
    for label, overrides in perturbations:
        try:
            backtest_overrides = overrides.get("__BACKTEST__", {})
            signal_overrides = {
                key: value for key, value in overrides.items() if key != "__BACKTEST__"
            }
            if signal_overrides:
                psig = _validate_signal_frame(
                    compute_declared_signal(fields, metadata, signal_overrides),
                    fields["adjclose"],
                )
                if not _signals_materially_differ(signal, psig):
                    raise RuntimeError(
                        "parameter perturbation did not change the signal; "
                        "the parameter is unused or captured before override"
                    )
            else:
                psig = signal
            pres = bt(
                "val_perturb",
                sig=psig,
                cid=f"{candidate_id}_p_{label}",
                backtest_overrides=backtest_overrides,
                ledger_validation_only=True,
            )
            if not _validation_execution_differs(full, pres):
                raise RuntimeError(
                    "parameter perturbation did not change validation portfolio weights"
                )
            perturb_srs[label] = sharpe_ratio(
                _slice(pres.returns_net, VALIDATION_START, VALIDATION_END)
            )
        except Exception as err:
            if not getattr(err, "_edgelab_trial_recorded", False):
                record_failed_trial(f"{candidate_id}_p_{label}", "val_perturb", str(overrides), err)
            perturb_srs[label] = f"error: {err}"

    g2 = {
        "subhalf1_sr": sharpe_ratio(half1),
        "subhalf2_sr": sharpe_ratio(half2),
        "hivol_sr": sharpe_ratio(hi_vol),
        "lovol_sr": sharpe_ratio(lo_vol),
        "cost25_sr": validation_cost_srs["25"],
        "perturbations": perturb_srs,
        "candidate_specific": _candidate_specific_gate2(candidate_id, fields, val_net, base_cost),
    }
    g2["pass"] = bool(
        g2["subhalf1_sr"] > 0
        and g2["subhalf2_sr"] > 0
        and g2["hivol_sr"] > 0
        and g2["lovol_sr"] > 0
        and g2["cost25_sr"] > 0
        and _perturbations_pass(perturb_srs)
        and perturbation_error is None
        and (not perturbations or bool(perturb_srs))
        and g2["candidate_specific"]["requirements_pass"]
    )
    results["gate2"] = g2

    out_path = CANDIDATES_DIR / candidate_id / "results_validation.json"
    atomic_write_text(out_path, dumps(results, indent=1))
    return results | {"_returns_net": full.returns_net}


def main() -> None:
    ids = sys.argv[1:]
    partial_run = bool(ids)
    if not ids:
        ids = sorted(p.name for p in CANDIDATES_DIR.iterdir() if (p / "signal.py").exists())
    eq_fields = load_equity_fields()
    etf_fields = None
    family_returns = {}
    declaration_hashes: dict[str, str] = {}
    for cid in ids:
        metadata, _, declaration_sha256 = signal_declaration_snapshot(cid)
        declaration_hashes[cid] = declaration_sha256
        if metadata.get("UNIVERSE", "equities") == "etfs":
            if etf_fields is None:
                etf_fields = load_etf_fields()
            fields = etf_fields
        else:
            fields = eq_fields
        res = evaluate_candidate(cid, fields, metadata, declaration_sha256)
        family_returns[cid] = res.pop("_returns_net")
        v = res["validation"]
        print(
            f"{cid}: val SR={v['sr_net']:.2f} t={v['nw_t']:.2f} "
            f"gate1={'PASS' if res['gate1']['pass'] else 'fail'} "
            f"gate2={'PASS' if res['gate2']['pass'] else 'fail'}"
        )
    if partial_run:
        print("partial run: family returns artifact was not modified")
        return
    # Recheck the complete family against both exact field snapshots before
    # publishing either the return panel or its metadata.
    family_identity = family_artifact_identity(ids)
    for candidate_id, digest in declaration_hashes.items():
        if family_identity["signal_sha256"].get(candidate_id) != digest:
            raise RuntimeError(f"{candidate_id} declaration changed during family replay")
    for fields in (eq_fields, etf_fields):
        if fields is None:
            continue
        for key in ("data_manifest_sha256", "universe_sha256"):
            if fields.input_identity.get(key) != family_identity.get(key):
                raise RuntimeError(f"family fields were built from a different {key}")

    _publish_family_returns(pd.DataFrame(family_returns), family_identity)


if __name__ == "__main__":
    main()
