"""Q-LIR data-integrity layer.

Raw DBN files are immutable; every byte is hash-manifested; every
acquisition is recorded in an append-only manifest; derived data may be
regenerated, never silently amended. See projects/qlir/README.md and
docs/sol-fable-edge-lab.md.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # projects/qlir
DATA_ROOT = PROJECT_ROOT / "data" / "q_lir"

SPLITS = ("development", "validation", "locked_test")


class QlirError(RuntimeError):
    """Data-integrity or configuration failure — always fail closed."""
