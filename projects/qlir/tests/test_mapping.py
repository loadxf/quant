"""Two-step mapping validation (round 4): continuous -> instrument_id
intervals composed with the instrument_id -> raw_symbol step, change
instants, window crossing, and the roll-transition-session stratum."""

from __future__ import annotations

from typing import ClassVar

import pandas as pd
import pytest
from qlir import QlirError
from qlir.mapping import (
    change_instants,
    parse_two_step,
    roll_transition_sessions,
    window_crosses_mapping,
)

# Step one (the ONLY supported continuous resolution): s = instrument id.
CONTINUOUS_TO_ID = [
    {"d0": "2022-01-01", "d1": "2022-03-14", "s": "4916"},
    {"d0": "2022-03-14", "d1": "2022-06-13", "s": "5203"},
    {"d0": "2022-06-13", "d1": "2022-09-19", "s": "5477"},
]
# Step two: instrument_id -> dated raw contract.
ID_TO_RAW = {"4916": "ESH2", "5203": "ESM2", "5477": "ESU2"}


def intervals():
    return parse_two_step("ES.v.0", CONTINUOUS_TO_ID, ID_TO_RAW)


class TestTwoStepParse:
    def test_composes_id_and_raw(self) -> None:
        parsed = intervals()
        assert [interval.instrument_id for interval in parsed] == [4916, 5203, 5477]
        assert [interval.raw_symbol for interval in parsed] == ["ESH2", "ESM2", "ESU2"]

    def test_int_keys_accepted_in_step_two(self) -> None:
        parsed = parse_two_step(
            "ES.v.0", CONTINUOUS_TO_ID, {4916: "ESH2", 5203: "ESM2", 5477: "ESU2"}
        )
        assert parsed[0].raw_symbol == "ESH2"

    def test_missing_raw_mapping_fails_closed(self) -> None:
        """Losing the raw-contract mapping is the round-4 failure mode."""
        incomplete = {"4916": "ESH2", "5203": "ESM2"}
        with pytest.raises(QlirError, match="no raw_symbol"):
            parse_two_step("ES.v.0", CONTINUOUS_TO_ID, incomplete)

    def test_non_id_step_one_output_rejected(self) -> None:
        """A raw symbol in step one means the invalid continuous->raw
        contract was used — refuse it."""
        bad = [{"d0": "2022-01-01", "d1": "2022-03-14", "s": "ESH2"}]
        with pytest.raises(QlirError, match="not an instrument id"):
            parse_two_step("ES.v.0", bad, ID_TO_RAW)

    def test_malformed_interval_rejected(self) -> None:
        with pytest.raises(QlirError, match="malformed"):
            parse_two_step("ES.v.0", [{"d0": "2022-01-01"}], ID_TO_RAW)

    def test_inverted_interval_rejected(self) -> None:
        with pytest.raises(QlirError, match="d1 <= d0"):
            parse_two_step(
                "ES.v.0", [{"d0": "2022-03-14", "d1": "2022-01-01", "s": "4916"}], ID_TO_RAW
            )

    def test_overlap_rejected(self) -> None:
        with pytest.raises(QlirError, match="overlapping"):
            parse_two_step(
                "ES.v.0",
                [
                    {"d0": "2022-01-01", "d1": "2022-03-15", "s": "4916"},
                    {"d0": "2022-03-14", "d1": "2022-06-13", "s": "5203"},
                ],
                ID_TO_RAW,
            )


class TestChangeInstants:
    def test_interior_boundaries_only(self) -> None:
        instants = change_instants(intervals())
        assert instants == [
            pd.Timestamp("2022-03-14", tz="UTC"),
            pd.Timestamp("2022-06-13", tz="UTC"),
        ]

    def test_single_interval_has_no_changes(self) -> None:
        parsed = parse_two_step("ES.v.0", CONTINUOUS_TO_ID[:1], ID_TO_RAW)
        assert change_instants(parsed) == []


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
        """Conservative closed-end convention: an end exactly at the
        instant counts as crossing."""
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
        assert roll_transition_sessions(intervals()) == {"2022-03-14", "2022-06-13"}
