"""Artifact-write helpers shared by every output path.

Two failure modes these kill globally: a typo'd output directory raising
a raw FileNotFoundError AFTER minutes of Monte Carlo (parents are
created up front), and locale-default encoding corrupting or crashing
non-ASCII artifacts on cp1252/ASCII systems (UTF-8 always).
"""

from __future__ import annotations

from pathlib import Path


def prepared(path: Path | str) -> Path:
    """`path` with its parent directories guaranteed to exist."""
    p = Path(path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    return p


def write_text(path: Path | str, text: str) -> Path:
    p = prepared(path)
    p.write_text(text, encoding="utf-8")
    return p
