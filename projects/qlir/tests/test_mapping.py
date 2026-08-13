"""Date-aware two-step mapping (round 5): the EXACT documented
interval-valued step-two response, daily-remap handling, coverage and
ambiguity enforcement, and the typed ledger round-trip."""

from __future__ import annotations

import datetime as dt
from typing import ClassVar

import pandas as pd
import pytest
from qlir import QlirError
from qlir.mapping import (
    ContractMap,
    change_instants,
    roll_transition_sessions,
    window_crosses_mapping,
)

# The exact documented response shapes: EVERY resolution is a list of
# dated {d0, d1, s} intervals — step two included.
STEP_ONE = {
    "ES.v.0": [
        {"d0": "2022-01-01", "d1": "2022-03-14", "s": "4916"},
        {"d0": "2022-03-14", "d1": "2022-06-13", "s": "5203"},
    ]
}
STEP_TWO = {
    "4916": [{"d0": "2022-01-01", "d1": "2022-03-14", "s": "ESH2"}],
    "5203": [{"d0": "2022-03-14", "d1": "2022-06-13", "s": "ESM2"}],
}


def composed() -> ContractMap:
    return ContractMap.compose_many(STEP_ONE, STEP_TWO)


class TestSolReproduction:
    def test_exact_round5_shapes_yield_esh2_not_a_serialized_list(self) -> None:
        """Sol's reproduction: the round-4 parser returned
        "[{'d0': …, 's': 'ESH2'}]" as the raw symbol. The composed map
        must return ESH2."""
        step_one = [{"d0": "2022-01-01", "d1": "2022-03-14", "s": "4916"}]
        step_two = {"4916": [{"d0": "2022-01-01", "d1": "2022-03-14", "s": "ESH2"}]}
        contract_map = ContractMap.compose("ES.v.0", step_one, step_two)
        raw = contract_map.raw_for(4916, dt.date(2022, 2, 1))
        assert raw == "ESH2"
        assert not raw.startswith("[")

    def test_flat_step_two_shape_is_refused(self) -> None:
        """The round-4 flat dict[id, str] shape does not exist in the
        API — offering it must raise, not silently stringify."""
        with pytest.raises(QlirError, match="LIST of"):
            ContractMap.compose(
                "ES.v.0",
                [{"d0": "2022-01-01", "d1": "2022-03-14", "s": "4916"}],
                {"4916": "ESH2"},  # type: ignore[dict-item]
            )


class TestDateAwareResolution:
    def test_raw_identity_is_a_function_of_id_and_date(self) -> None:
        contract_map = composed()
        assert contract_map.raw_for(4916, dt.date(2022, 2, 1)) == "ESH2"
        assert contract_map.raw_for(5203, dt.date(2022, 4, 1)) == "ESM2"

    def test_daily_remap_of_one_id(self) -> None:
        """Some publishers remap instrument ids daily: the SAME id can
        carry different raw symbols on different dates."""
        step_one = [{"d0": "2022-01-01", "d1": "2022-01-03", "s": "777"}]
        step_two = {
            "777": [
                {"d0": "2022-01-01", "d1": "2022-01-02", "s": "ESH2"},
                {"d0": "2022-01-02", "d1": "2022-01-03", "s": "ESM2"},
            ]
        }
        contract_map = ContractMap.compose("ES.v.0", step_one, step_two)
        assert contract_map.raw_for(777, dt.date(2022, 1, 1)) == "ESH2"
        assert contract_map.raw_for(777, dt.date(2022, 1, 2)) == "ESM2"

    def test_outside_coverage_fails_closed(self) -> None:
        with pytest.raises(QlirError, match="outside the composed mapping"):
            composed().raw_for(4916, dt.date(2023, 1, 1))

    def test_unknown_id_fails_closed(self) -> None:
        with pytest.raises(QlirError, match="no raw_symbol"):
            composed().raw_for(999, dt.date(2022, 2, 1))

    def test_flat_map_for_date(self) -> None:
        flat = composed().flat_map_for_date(dt.date(2022, 2, 1))
        assert flat == {4916: "ESH2"}

    def test_flat_map_empty_date_fails(self) -> None:
        with pytest.raises(QlirError, match="no instruments active"):
            composed().flat_map_for_date(dt.date(2023, 1, 1))


class TestCoverageAndAmbiguity:
    def test_step_two_gap_refused(self) -> None:
        step_two = {
            "4916": [{"d0": "2022-01-01", "d1": "2022-02-01", "s": "ESH2"}],  # gap after Feb 1
            "5203": STEP_TWO["5203"],
        }
        with pytest.raises(QlirError, match="coverage GAP"):
            ContractMap.compose_many(STEP_ONE, step_two)

    def test_missing_step_two_entry_refused(self) -> None:
        with pytest.raises(QlirError, match="no step-two entry"):
            ContractMap.compose_many(STEP_ONE, {"4916": STEP_TWO["4916"]})

    def test_non_id_step_one_output_rejected(self) -> None:
        bad = {"ES.v.0": [{"d0": "2022-01-01", "d1": "2022-03-14", "s": "ESH2"}]}
        with pytest.raises(QlirError, match="not an instrument id"):
            ContractMap.compose_many(bad, STEP_TWO)

    def test_ambiguous_overlapping_raw_refused(self) -> None:
        step_two = {
            "4916": [
                {"d0": "2022-01-01", "d1": "2022-03-14", "s": "ESH2"},
                {"d0": "2022-02-01", "d1": "2022-03-14", "s": "ESM2"},
            ],
            "5203": STEP_TWO["5203"],
        }
        with pytest.raises(QlirError, match="overlapping"):
            ContractMap.compose_many(STEP_ONE, step_two)

    def test_serialized_structure_as_symbol_refused(self) -> None:
        step_two = {
            "4916": [{"d0": "2022-01-01", "d1": "2022-03-14", "s": "[{'d0': 'x', 's': 'ESH2'}]"}],
            "5203": STEP_TWO["5203"],
        }
        with pytest.raises(QlirError, match="serialized structure"):
            ContractMap.compose_many(STEP_ONE, step_two)


class TestLedgerRoundTrip:
    def test_to_record_from_record(self) -> None:
        record = composed().to_record()
        assert record["ES.v.0"][0] == {
            "instrument_id": 4916,
            "raw_symbol": "ESH2",
            "d0": "2022-01-01",
            "d1": "2022-03-14",
        }
        rebuilt = ContractMap.from_record(record)
        assert rebuilt.raw_for(5203, dt.date(2022, 5, 1)) == "ESM2"

    @pytest.mark.parametrize("garbage", ["garbage", {}, {"ES.v.0": []}, {"ES.v.0": ["x"]}])
    def test_untyped_structures_refused(self, garbage: object) -> None:
        with pytest.raises(QlirError):
            ContractMap.from_record(garbage)


class TestChangeInstants:
    def test_id_changes_and_remaps_both_count(self) -> None:
        step_one = [{"d0": "2022-01-01", "d1": "2022-01-03", "s": "777"}]
        step_two = {
            "777": [
                {"d0": "2022-01-01", "d1": "2022-01-02", "s": "ESH2"},
                {"d0": "2022-01-02", "d1": "2022-01-03", "s": "ESM2"},
            ]
        }
        contract_map = ContractMap.compose("ES.v.0", step_one, step_two)
        assert change_instants(contract_map.intervals) == [pd.Timestamp("2022-01-02", tz="UTC")]

    def test_interior_boundaries_only(self) -> None:
        assert change_instants(composed().intervals) == [pd.Timestamp("2022-03-14", tz="UTC")]


class TestWindowCrossing:
    INSTANTS: ClassVar[list[pd.Timestamp]] = [pd.Timestamp("2022-03-14", tz="UTC")]

    def window(self, start: str, end: str) -> tuple[pd.Timestamp, pd.Timestamp]:
        return pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")

    def test_window_strictly_inside_one_mapping_valid(self) -> None:
        assert not window_crosses_mapping(
            *self.window("2022-03-13 10:00", "2022-03-13 10:02"), self.INSTANTS
        )

    def test_window_spanning_change_invalid(self) -> None:
        assert window_crosses_mapping(
            *self.window("2022-03-13 23:59", "2022-03-14 00:01"), self.INSTANTS
        )

    def test_window_ending_exactly_at_change_is_invalid(self) -> None:
        assert window_crosses_mapping(
            *self.window("2022-03-13 23:58", "2022-03-14 00:00"), self.INSTANTS
        )

    def test_window_starting_exactly_at_change_valid(self) -> None:
        assert not window_crosses_mapping(
            *self.window("2022-03-14 00:00", "2022-03-14 00:02"), self.INSTANTS
        )

    def test_degenerate_window_rejected(self) -> None:
        start, end = self.window("2022-03-14 00:00", "2022-03-14 00:00")
        with pytest.raises(QlirError):
            window_crosses_mapping(start, end, self.INSTANTS)


class TestRollStratum:
    def test_sessions_containing_changes(self) -> None:
        assert roll_transition_sessions(composed().intervals) == {"2022-03-14"}
