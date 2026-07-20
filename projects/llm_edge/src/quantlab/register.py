"""Pre-register candidate specs: hash spec.md into candidates/registry.json.

G1-originated candidates get holdout_end = 2026-01-31 (their generation window
is the post-cutoff slice; see research/debates/protocol_deviations.md D1).
The registration only becomes effective for the holdout gate once this file is
COMMITTED — holdout_gate refuses uncommitted registries.

Usage: python -m quantlab.register C001 C002 ...
"""

from __future__ import annotations

import datetime as _dt
import json
import sys

from . import CANDIDATES_DIR, REGISTRY_PATH
from .holdout_gate import spec_sha256

G1_CANDIDATES = {"C007", "C008", "C009"}
G1_HOLDOUT_END = "2026-01-31"


def register(candidate_ids: list[str]) -> dict:
    registry = json.loads(REGISTRY_PATH.read_text()) if REGISTRY_PATH.exists() else {}
    for cid in candidate_ids:
        spec_path = CANDIDATES_DIR / cid / "spec.md"
        if not spec_path.exists():
            raise FileNotFoundError(spec_path)
        if cid in registry:
            raise RuntimeError(f"{cid} already registered — registration is append-only")
        entry = {
            "spec_sha256": spec_sha256(spec_path),
            "registered_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        }
        if cid in G1_CANDIDATES:
            entry["holdout_end"] = G1_HOLDOUT_END
            entry["holdout_note"] = "G1 candidate: holdout excludes the post-cutoff generation window (D1)"
        registry[cid] = entry
    REGISTRY_PATH.write_text(json.dumps(registry, indent=1, sort_keys=True))
    return registry


if __name__ == "__main__":
    reg = register(sys.argv[1:])
    print(json.dumps(reg, indent=1, sort_keys=True))
