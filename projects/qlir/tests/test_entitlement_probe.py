"""Round-12 hardening (Sol, finding 1-3 + item 6): the QC entitlement
probe must compile, request 2021 data only, make zero ObjectStore /
download / filesystem calls at runtime, classify ticks by positive
fields (never bare .notna()), and encode the four-way verdict with the
corrected branch requirements."""

from __future__ import annotations

import ast
from pathlib import Path

PROBE = Path(__file__).resolve().parents[1] / "qc" / "qlir_entitlement_probe.py"
SOURCE = PROBE.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


class TestCompilation:
    def test_probe_compiles(self) -> None:
        compile(SOURCE, str(PROBE), "exec")


class TestDateContainment:
    def test_every_date_constructor_is_2021(self) -> None:
        """Every dt.date/dt.datetime literal in the probe names 2021."""
        seen = 0
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call) and _call_name(node) in {"date", "datetime"}:
                seen += 1
                year = node.args[0]
                assert isinstance(year, ast.Constant) and year.value == 2021, (
                    f"non-2021 date constructor at line {node.lineno}"
                )
        assert seen >= 6  # session + windows + boundaries all checked

    def test_no_locked_period_literals(self) -> None:
        """No 2024-2026 literal anywhere in the AST (comments carry no
        runtime meaning; constants do)."""
        banned = {2024, 2025, 2026}
        for node in ast.walk(TREE):
            if isinstance(node, ast.Constant) and isinstance(node.value, int):
                assert node.value not in banned, f"locked-period literal at line {node.lineno}"


class TestRuntimeCalls:
    def test_no_object_store_download_or_file_io(self) -> None:
        forbidden = {"object_store", "objectstore", "download", "open", "read", "write", "save"}
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call):
                assert _call_name(node).lower() not in forbidden, (
                    f"forbidden runtime call at line {node.lineno}"
                )

    def test_no_dunder_file_reference(self) -> None:
        for node in ast.walk(TREE):
            if isinstance(node, ast.Name):
                assert node.id != "__file__"


class TestClassification:
    def test_no_bare_notna_masks(self) -> None:
        """Round-12 finding 1: QC uses zero, not NaN, for unused tick
        fields — .notna() masks would count trade rows as quotes. The
        check is on RUNTIME CALLS, not textual mentions (round 12,
        administrative correction)."""
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call):
                assert _call_name(node) != "notna", f"bare .notna() call at line {node.lineno}"

    def test_positive_field_helper_present(self) -> None:
        assert "fillna(0).gt(0)" in SOURCE

    def test_timezone_declared(self) -> None:
        assert "set_time_zone" in SOURCE and "TimeZones.NEW_YORK" in SOURCE


class TestVerdict:
    def test_four_way_branch_logic(self) -> None:
        """Round-12 finding 3: A needs trade ticks AND quote ticks AND a
        valid two-sided BBO; S/M are proxies; NONE is the floor."""
        assert "tick_trades_ok and tick_quotes_ok and bbo_valid_any" in SOURCE
        assert "sec_trades_ok and sec_quotes_ok" in SOURCE
        assert "min_trades_ok and min_quotes_ok" in SOURCE
        for label in ('branch = "A"', 'branch = "S"', 'branch = "M"', 'branch = "NONE"'):
            assert label in SOURCE, f"missing verdict arm {label}"

    def test_quote_bars_checked_for_usable_observations(self) -> None:
        assert "usable_two_sided" in SOURCE
        assert "sec_quotes_usable > 0" in SOURCE
        assert "min_quotes_usable > 0" in SOURCE

    def test_bar_layers_labeled_as_approximations(self) -> None:
        """Round-12 finding 2/3: bar closes are interval approximations,
        never the exact b+5s BBO."""
        assert SOURCE.count("NOT exact b+5s BBO") >= 2

    def test_independent_per_side_state(self) -> None:
        assert "bbo_state_at" in SOURCE
        assert "bid_age_s" in SOURCE and "ask_age_s" in SOURCE
