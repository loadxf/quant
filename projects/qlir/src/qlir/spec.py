"""The immutable acquisition specification (round 6, findings 1-2).

One frozen object names WHAT is being acquired — dataset, schema,
symbology types, requested symbols, half-open UTC time range — and every
boundary validates against it: the symbology response envelopes, the DBN
file metadata, the per-record binding, and the ledger receipt. Objects
that are independently valid but mutually contradictory (an XNAS/NQ file
under a GLBX/ES receipt) become unrepresentable as one acquisition.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from qlir import QlirError

SUPPORTED_SCHEMAS = ("trades", "tbbo", "mbp-1")


@dataclass(frozen=True)
class AcquisitionSpec:
    dataset: str
    schema: str
    symbols: tuple[str, ...]  # requested continuous symbols
    start_utc: dt.datetime  # inclusive
    end_utc: dt.datetime  # exclusive
    stype_in: str = "continuous"
    stype_out: str = "instrument_id"

    def __post_init__(self) -> None:
        if not self.dataset:
            raise QlirError("spec.dataset must be non-empty")
        if self.schema not in SUPPORTED_SCHEMAS:
            raise QlirError(f"spec.schema {self.schema!r} not in {SUPPORTED_SCHEMAS}")
        if not self.symbols:
            raise QlirError("spec.symbols must be non-empty")
        for value, name in ((self.start_utc, "start_utc"), (self.end_utc, "end_utc")):
            if value.tzinfo is None:
                raise QlirError(f"spec.{name} must be timezone-aware UTC")
        if self.end_utc <= self.start_utc:
            raise QlirError("spec.end_utc must be after spec.start_utc")

    @property
    def start_date(self) -> dt.date:
        return self.start_utc.astimezone(dt.UTC).date()

    @property
    def end_date_exclusive(self) -> dt.date:
        """First date NOT covered (half-open range semantics)."""
        end = self.end_utc.astimezone(dt.UTC)
        midnight = end.replace(hour=0, minute=0, second=0, microsecond=0)
        return end.date() if end == midnight else end.date() + dt.timedelta(days=1)


def _reject_escaping_path(value: str) -> None:
    """Round-7 finding 3: absolute, drive-qualified, UNC, and device
    paths must never masquerade as data_root-relative attestations —
    joining them to the root silently DISCARDS the root."""
    from pathlib import PurePosixPath, PureWindowsPath

    if not value or ".." in value:
        raise QlirError(f"unsafe acquired-file path {value!r}")
    windows = PureWindowsPath(value)
    posix = PurePosixPath(value)
    if (
        windows.is_absolute()
        or posix.is_absolute()
        or windows.drive  # C:..., //server/share, \\?\ device forms
        or value.startswith(("/", "\\"))
    ):
        raise QlirError(
            f"acquired-file path must be data_root-relative, got {value!r} "
            "(absolute/drive/UNC/device paths are refused)"
        )


@dataclass(frozen=True)
class AcquiredFile:
    """One immutable per-acquisition file attestation (round 6, finding
    1: `file_hashes` pointed at a MUTABLE cumulative manifest — a later
    raw write changed what old receipts appeared to reference).
    `server_filename` binds the stored file to the server batch-manifest
    entry it came from (round 7, finding 2)."""

    relative_path: str
    sha256: str
    size_bytes: int
    record_count: int
    server_filename: str = ""

    def __post_init__(self) -> None:
        _reject_escaping_path(self.relative_path)
        if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise QlirError(f"acquired-file sha256 is not 64 lowercase hex chars: {self.sha256!r}")
        if not isinstance(self.size_bytes, int) or self.size_bytes <= 0:
            raise QlirError(
                f"acquired-file size_bytes must be a positive int ({self.size_bytes!r})"
            )
        if not isinstance(self.record_count, int) or self.record_count < 0:
            raise QlirError(
                f"acquired-file record_count must be a non-negative int ({self.record_count!r})"
            )

    def to_dict(self) -> dict:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "record_count": self.record_count,
            "server_filename": self.server_filename,
        }

    @classmethod
    def from_dict(cls, item: object) -> AcquiredFile:
        if not isinstance(item, dict):
            raise QlirError(f"acquired-file entry is not a dict: {item!r}")
        try:
            return cls(
                relative_path=str(item["relative_path"]),
                sha256=str(item["sha256"]),
                size_bytes=int(item["size_bytes"]),
                record_count=int(item["record_count"]),
                server_filename=str(item.get("server_filename", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise QlirError(f"acquired-file entry malformed: {item!r}") from exc


@dataclass(frozen=True)
class EnvelopeCheck:
    """Fields a symbology response envelope must agree on when present."""

    stype_in: str
    stype_out: str
    symbols: tuple[str, ...] | None = None  # None = do not check (step two ids)
    extra: dict = field(default_factory=dict)


def validate_envelope(
    response: object,
    spec: AcquisitionSpec,
    check: EnvelopeCheck,
    step: str,
    allow_unverified: bool = False,
) -> dict:
    """Validate a symbology.resolve envelope against the spec and return
    the result payload. Bare payloads (no envelope fields) are refused
    unless `allow_unverified=True` (test fixtures only — the caller is
    explicitly accepting an unverified mapping)."""
    if not isinstance(response, dict):
        raise QlirError(f"{step}: response is not a dict")
    # Round-7 finding 4: `result` alone is NOT an envelope. Every field
    # the API contract documents is REQUIRED and type-checked; a
    # detached result-only wrapper is refused. (The response carries no
    # `dataset` field — dataset binding lives in the DBN metadata and
    # the persisted request, never in an invented envelope field.)
    required = (
        "result",
        "symbols",
        "stype_in",
        "stype_out",
        "start_date",
        "end_date",
        "partial",
        "not_found",
    )
    missing = [key for key in required if key not in response]
    if missing:
        if allow_unverified:
            return response.get("result", response)  # explicitly unverified
        raise QlirError(
            f"{step}: response envelope missing required fields {missing} — pass "
            "the FULL symbology.resolve response, or set allow_unverified=True "
            "for test fixtures (which marks the mapping unverified)"
        )
    payload = response["result"]
    if not isinstance(payload, dict) or not payload:
        raise QlirError(f"{step}: response has no usable result payload")
    for key in ("partial", "not_found"):
        if not isinstance(response[key], list):
            raise QlirError(f"{step}: envelope {key} must be a list")
        if response[key]:
            raise QlirError(
                f"{step}: response reports {key}={response[key]!r} — refusing an "
                "incomplete symbology resolution"
            )
    status = response.get("status")
    if status is not None and str(status) not in ("0", "ok", "OK", "200"):
        raise QlirError(f"{step}: response status {status!r} is not success")
    if not isinstance(response["symbols"], list) or not response["symbols"]:
        raise QlirError(f"{step}: envelope symbols must be a non-empty list")
    checks: list[tuple[str, object, object]] = [
        ("stype_in", response["stype_in"], check.stype_in),
        ("stype_out", response["stype_out"], check.stype_out),
        ("start_date", response["start_date"], spec.start_date.isoformat()),
        ("end_date", response["end_date"], spec.end_date_exclusive.isoformat()),
    ]
    for name, got, expected in checks:
        if str(got) != str(expected):
            raise QlirError(
                f"{step}: envelope {name}={got!r} does not match the acquisition "
                f"spec ({expected!r}) — refusing to bind unrelated responses"
            )
    if check.symbols is not None:
        got_symbols = set(map(str, response["symbols"]))
        if got_symbols != set(check.symbols):
            raise QlirError(
                f"{step}: envelope symbols {sorted(got_symbols)} do not match the "
                f"expected set {sorted(check.symbols)}"
            )
    return payload
