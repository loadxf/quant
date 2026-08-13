"""Mapping-change validation: parse, change instants, window crossing,
and the roll-transition-session stratum."""

from __future__ import annotations

from typing import ClassVar

import pandas as pd
import pytest
from qlir import QlirError
from qlir.mapping import (
    change_instants,
    parse_resolution,
    roll_transition_sessions,
    window_crosses_mapping,
)

RESOLVE_RESULT = [
    {"d0": "2022-01-01", "d1": "2022-03-14", "s": "ESH2"},
    {"d0": "2022-03-14", "d1": "2022-06-13", "s": "ESM2"},
    {"d0": "2022-06-13", "d1": "2022-09-19", "s": "ESU2"},
]


class TestParse:
    def test_databento_style_result(self) -> None:
        intervals = parse_resolution("ES.v.0", RESOLVE_RESULT)
        assert [interval.raw_symbol for interval in intervals] == ["ESH2", "ESM2", "ESU2"]

    def test_malformed_interval_rejected(self) -> None:
        with pytest.raises(QlirError, match="malformed"):
            parse_resolution("ES.v.0", [{"d0": "2022-01-01"}])

    def test_inverted_interval_rejected(self) -> None:
        with pytest.raises(QlirError, match="d1 <= d0"):
            parse_resolution("ES.v.0", [{"d0": "2022-03-14", "d1": "2022-01-01", "s": "X"}])

    def test_overlap_rejected(self) -> None:
        with pytest.raises(QlirError, match="overlapping"):
            parse_resolution(
                "ES.v.0",
                [
                    {"d0": "2022-01-01", "d1": "2022-03-15", "s": "ESH2"},
                    {"d0": "2022-03-14", "d1": "2022-06-13", "s": "ESM2"},
                ],
            )


class TestChangeInstants:
    def test_interior_boundaries_only(self) -> None:
        intervals = parse_resolution("ES.v.0", RESOLVE_RESULT)
        instants = change_instants(intervals)
        assert instants == [
            pd.Timestamp("2022-03-14", tz="UTC"),
            pd.Timestamp("2022-06-13", tz="UTC"),
        ]

    def test_single_interval_has_no_changes(self) -> None:
        intervals = parse_resolution("ES.v.0", RESOLVE_RESULT[:1])
        assert change_instants(intervals) == []


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
        intervals = parse_resolution("ES.v.0", RESOLVE_RESULT)
        assert roll_transition_sessions(intervals) == {"2022-03-14", "2022-06-13"}
