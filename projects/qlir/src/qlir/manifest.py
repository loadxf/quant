"""Append-only acquisition manifest (acquisition.json).

One record per batch request, carrying everything needed to reproduce
or audit the acquisition. Records are validated on write; existing
records are never modified or removed — appends only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qlir import SPLITS, QlirError

REQUIRED_FIELDS: tuple[str, ...] = (
    "dataset",
    "schema",
    "requested_symbols",
    "stype_in",
    "stype_out",
    "resolved_contracts",
    "start_utc",
    "end_utc",
    "request_cost_usd",
    "record_count",
    "billable_size_bytes",
    "client_version",
    "file_hashes",
    "dataset_conditions",
    "derivation_code_commit",
    "split",
)


def validate_record(record: dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    if missing:
        raise QlirError(f"acquisition record missing required fields: {missing}")
    if record["split"] not in SPLITS:
        raise QlirError(f"split must be one of {SPLITS} (got {record['split']!r})")
    if not isinstance(record["requested_symbols"], list) or not record["requested_symbols"]:
        raise QlirError("requested_symbols must be a non-empty list")
    if record["split"] == "locked_test":
        raise QlirError(
            "locked_test acquisitions are prohibited until validation decisions "
            "are frozen (Sol/Fable protocol) — do not acquire 2025+ data"
        )


def load_manifest(path: Path) -> list[dict[str, Any]]:
    if not Path(path).exists():
        return []
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise QlirError(f"acquisition manifest {path} must be a JSON list")
    return raw


def append_acquisition(path: Path, record: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate and append one record; existing records are preserved
    verbatim and re-validated (tampering fails closed)."""
    validate_record(record)
    path = Path(path)
    existing = load_manifest(path)
    for i, prior in enumerate(existing):
        try:
            validate_record(prior)
        except QlirError as exc:
            raise QlirError(
                f"existing manifest record {i} is invalid ({exc}) — refusing "
                "to append to a corrupt manifest"
            ) from exc
    updated = [*existing, record]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(updated, indent=2, default=str) + "\n", encoding="utf-8")
    return updated
