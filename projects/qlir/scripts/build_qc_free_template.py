"""Build the compact free-tier Q-LIR QuantConnect notebook template."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QC = ROOT / "qc"
OUTPUT = QC / "qlir_gate2_free_template.ipynb"
PASTE_OUTPUT = QC / "qlir_gate2_free_paste.py"
MAX_QC_CHARACTERS = 64_000


def code_cell(source: str) -> dict[str, object]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.rstrip(),
    }


def markdown_cell(source: str) -> dict[str, object]:
    return {"cell_type": "markdown", "metadata": {}, "source": source.rstrip() + "\n"}


def split_core() -> list[str]:
    source = (QC / "qlir_free_template_core.py").read_text(encoding="utf-8")
    parts = re.split(r"(?m)^# %% CELL \d+[^\n]*\n", source)
    # Keep the short file preamble with setup instead of wasting a notebook cell.
    return [(parts[0] + parts[1]).strip(), *[part.strip() for part in parts[2:]]]


def main() -> int:
    instructions = """# Q-LIR Gate II free-tier template

Run every cell from top to bottom in one QuantConnect Research session.

- Frozen sample: 2021-2024 only. Never extend it to 2025+.
- Data: ES/NQ continuous futures, minute resolution, raw prices, open-interest mapping.
- The template removes non-cash and shortened sessions, applies the frozen dated
  macro calendar symmetrically, then runs the day-clustered Gate II analysis.
- No Object Store, file download, or paid feature is required.
- Do not restart the Research node after extraction; a restart clears the in-memory frame.
- If a yearly extraction is interrupted without a restart, rerun its cell;
  completed years are retained in `events_by_year`.
"""
    sources = split_core()
    sources[0] = re.sub(
        r"(?m)^# ruff: noqa: .*$",
        "# ruff: noqa: E402, F403, F405, F811 - sequential QC cells share one namespace.",
        sources[0],
        count=1,
    )
    sources.extend(
        [
            (QC / "macro_events_v2_embedded.py").read_text(encoding="utf-8"),
            (QC / "qlir_macro_exclusion_audit.py").read_text(encoding="utf-8"),
            (QC / "qlir_gate2_analysis.py").read_text(encoding="utf-8"),
        ]
    )
    notebook = {
        "cells": [markdown_cell(instructions), *[code_cell(source) for source in sources]],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    serialized = json.dumps(notebook, ensure_ascii=False, separators=(",", ":")) + "\n"
    if len(serialized) >= MAX_QC_CHARACTERS:
        raise RuntimeError(
            f"Template is {len(serialized):,} characters; QC limit is {MAX_QC_CHARACTERS:,}"
        )

    paste_header = """# Q-LIR Gate II free-tier template.
# Paste this ENTIRE file into ONE fresh QuantConnect Research code cell and run it.
# Do not paste build_qc_free_template.py into QuantConnect.
# Frozen sample: 2021-2024 only. No Object Store or file download is required.
"""
    paste_source = (
        paste_header.rstrip() + "\n\n" + "\n\n\n".join(source.rstrip() for source in sources) + "\n"
    )
    if len(paste_source) >= MAX_QC_CHARACTERS:
        raise RuntimeError(
            f"Paste template is {len(paste_source):,} characters; QC limit is {MAX_QC_CHARACTERS:,}"
        )
    if "__file__" in paste_source:
        raise RuntimeError("Paste template must not depend on __file__")

    OUTPUT.write_text(serialized, encoding="utf-8", newline="\n")
    PASTE_OUTPUT.write_text(paste_source, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT} with {len(notebook['cells'])} cells and {len(serialized):,} characters")
    print(f"wrote {PASTE_OUTPUT} with {len(paste_source):,} characters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
