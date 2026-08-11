"""Pre-register candidate specs: hash spec.md into candidates/registry.json.

G1-originated candidates get holdout_end = 2026-01-31 (their generation window
is the post-cutoff slice; see research/debates/protocol_deviations.md D1).
The registration only becomes effective for the holdout gate once this file is
COMMITTED — holdout_gate refuses uncommitted registries.

Usage: python -m edgelab.register C001 C002 ...
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import sys

from . import CANDIDATES_DIR, LEDGER_PATH, REGISTRY_PATH
from .gates import signal_metadata
from .holdout_gate import (
    MANIFEST_PATH,
    UNIVERSE_PATH,
    engine_sha256,
    environment_sha256,
    git_head,
    spec_sha256,
    validation_result,
)
from .jsonutil import atomic_write_text, dumps

G1_HOLDOUT_END = "2026-01-31"
_CANDIDATE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def register(candidate_ids: list[str]) -> dict:
    try:
        registry = json.loads(REGISTRY_PATH.read_text()) if REGISTRY_PATH.exists() else {}
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid candidate registry: {exc}") from exc
    if not isinstance(registry, dict):
        raise RuntimeError("candidate registry must be a JSON object")
    for cid in candidate_ids:
        if not isinstance(cid, str) or not _CANDIDATE_RE.fullmatch(cid):
            raise RuntimeError(f"invalid candidate id {cid!r}")
        spec_path = CANDIDATES_DIR / cid / "spec.md"
        if not spec_path.exists():
            raise FileNotFoundError(spec_path)
        signal_path = CANDIDATES_DIR / cid / "signal.py"
        if not signal_path.exists():
            raise FileNotFoundError(signal_path)
        if not MANIFEST_PATH.exists():
            raise FileNotFoundError(MANIFEST_PATH)
        if not UNIVERSE_PATH.exists():
            raise FileNotFoundError(UNIVERSE_PATH)
        if not LEDGER_PATH.exists():
            raise FileNotFoundError(LEDGER_PATH)
        validation_path = CANDIDATES_DIR / cid / "results_validation.json"
        validation_result(validation_path, cid)
        declaration = signal_metadata(cid)
        origin = declaration["ORIGIN"]
        holdout_end = declaration.get("HOLDOUT_END")
        if not isinstance(holdout_end, str):
            raise RuntimeError(f"{cid} signal.py must declare a literal HOLDOUT_END")
        try:
            holdout_end_date = _dt.date.fromisoformat(holdout_end)
        except ValueError as exc:
            raise RuntimeError(f"{cid} has invalid HOLDOUT_END {holdout_end!r}") from exc
        if holdout_end_date <= _dt.date(2023, 12, 31):
            raise RuntimeError(f"{cid} HOLDOUT_END must be after validation")
        if origin == "G1" and holdout_end != G1_HOLDOUT_END:
            raise RuntimeError(f"{cid} G1 declaration must set HOLDOUT_END={G1_HOLDOUT_END}")
        if cid in registry:
            raise RuntimeError(f"{cid} already registered — registration is append-only")
        entry = {
            "spec_sha256": spec_sha256(spec_path),
            "signal_sha256": spec_sha256(signal_path),
            "engine_sha256": engine_sha256(),
            "engine_commit": git_head(),
            "environment_sha256": environment_sha256(),
            "data_manifest_sha256": spec_sha256(MANIFEST_PATH),
            "universe_sha256": spec_sha256(UNIVERSE_PATH),
            "validation_results_sha256": spec_sha256(validation_path),
            "ledger_sha256": spec_sha256(LEDGER_PATH),
            "ledger_bytes": LEDGER_PATH.stat().st_size,
            "registered_utc": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
            "holdout_end": holdout_end,
            "origin": origin,
        }
        if origin == "G1":
            entry["holdout_note"] = (
                "G1 candidate: holdout excludes the post-cutoff generation window (D1)"
            )
        registry[cid] = entry
    atomic_write_text(REGISTRY_PATH, dumps(registry, indent=1, sort_keys=True))
    return registry


if __name__ == "__main__":
    reg = register(sys.argv[1:])
    print(json.dumps(reg, indent=1, sort_keys=True))
