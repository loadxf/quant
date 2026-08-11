"""Strict-JSON serialization shared by research artifacts."""

from __future__ import annotations

import json
import math
import numbers
import os
import secrets
from pathlib import Path


def sanitize(value):
    if isinstance(value, dict):
        return {str(key): sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        return value if math.isfinite(float(value)) else None
    return value


def dumps(value, **kwargs) -> str:
    return json.dumps(sanitize(value), allow_nan=False, default=str, **kwargs)


def atomic_write_text(path: Path, text: str) -> None:
    """Durably replace a text artifact without exposing a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        with temporary.open("x") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
