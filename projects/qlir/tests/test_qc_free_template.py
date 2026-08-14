from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "qc" / "qlir_gate2_free_template.ipynb"
PASTE_TEMPLATE = ROOT / "qc" / "qlir_gate2_free_paste.py"


def test_free_template_is_compact_valid_and_output_free() -> None:
    serialized = TEMPLATE.read_text(encoding="utf-8")
    notebook = json.loads(serialized)

    assert len(serialized) < 64_000
    assert notebook["nbformat"] == 4
    assert len(notebook["cells"]) == 11
    assert all(cell.get("outputs", []) == [] for cell in notebook["cells"])
    assert all(cell.get("execution_count") is None for cell in notebook["cells"])


def test_every_template_code_cell_compiles() -> None:
    notebook = json.loads(TEMPLATE.read_text(encoding="utf-8"))

    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] == "code":
            compile(cell["source"], f"template-cell-{index}", "exec")


def test_template_contains_the_frozen_pipeline_without_download_workarounds() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "START_YEAR, END_YEAR = 2021, 2024" in source
    assert "EXPECTED_CALENDAR_SHA256" in source
    assert "locked_events_excluded" in source
    assert "Q-LIR GATE II FROZEN ANALYSIS" in source
    assert "FileLink" not in source
    assert "qlir_gate2_locked_2021_2024.csv.gz" not in source


def test_single_cell_paste_template_is_compact_and_self_contained() -> None:
    source = PASTE_TEMPLATE.read_text(encoding="utf-8")

    assert len(source) < 64_000
    assert "Paste this ENTIRE file into ONE fresh QuantConnect Research code cell" in source
    assert "START_YEAR, END_YEAR = 2021, 2024" in source
    assert "EXPECTED_CALENDAR_SHA256" in source
    assert "locked_events_excluded" in source
    assert "Q-LIR GATE II FROZEN ANALYSIS" in source
    assert "__file__" not in source
    compile(source, PASTE_TEMPLATE.name, "exec")
