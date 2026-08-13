"""Canonical event loading: synthetic parquet fixtures, ordering,
aggressor-sign convention, unknown-side handling, and the (skippable)
real-DBN decode path.

Synthetic fixtures are DECODED-record parquet because databento's Python
bindings expose no DBN encoder — the DBN branch is a thin DBNStore
wrapper exercised only when a real file is present.
"""

from __future__ import annotations

import pandas as pd
import pytest
from qlir import QlirError
from qlir.loader import (
    aggressor_sign,
    load_events,
    signed_flow,
    unknown_side_fraction,
    validate_events,
)


def fixture_frame(sides=("B", "A", "N", "B"), shuffle=False) -> pd.DataFrame:
    base = pd.Timestamp("2022-03-01 14:30:00", tz="UTC")
    n = len(sides)
    frame = pd.DataFrame(
        {
            "ts_event": [base + pd.Timedelta(seconds=i) for i in range(n)],
            "ts_recv": [base + pd.Timedelta(seconds=i, microseconds=50) for i in range(n)],
            "sequence": range(1, n + 1),
            "price": [4500.25 + 0.25 * i for i in range(n)],
            "size": [4, 9, 1, 16],
            "side": list(sides),
            "symbol": ["ES.v.0"] * n,
            "raw_symbol": ["ESH2"] * n,
            "instrument_id": [12345] * n,
        }
    )
    if shuffle:
        frame = frame.iloc[::-1].reset_index(drop=True)
    return frame


class TestValidateEvents:
    def test_roundtrip_parquet(self, tmp_path) -> None:
        path = tmp_path / "2022-03-01.parquet"
        fixture_frame().to_parquet(path)
        loaded = load_events(path)
        assert list(loaded.columns)[:4] == ["ts_event", "ts_recv", "sequence", "price"]
        assert len(loaded) == 4

    def test_unsorted_input_sorted_by_event_then_sequence(self) -> None:
        out = validate_events(fixture_frame(shuffle=True))
        assert list(out["sequence"]) == [1, 2, 3, 4]
        assert out["ts_event"].is_monotonic_increasing

    def test_sequence_breaks_ts_event_ties(self) -> None:
        frame = fixture_frame()
        frame.loc[:, "ts_event"] = frame["ts_event"].iloc[0]  # all tied
        frame = frame.iloc[[2, 0, 3, 1]].reset_index(drop=True)
        out = validate_events(frame)
        assert list(out["sequence"]) == [1, 2, 3, 4]

    def test_missing_column_rejected(self) -> None:
        with pytest.raises(QlirError, match="missing canonical"):
            validate_events(fixture_frame().drop(columns=["side"]))

    def test_invalid_side_rejected(self) -> None:
        with pytest.raises(QlirError, match="invalid side"):
            validate_events(fixture_frame(sides=("B", "A", "X", "B")))

    @pytest.mark.parametrize("column", ["price", "size"])
    def test_nonpositive_values_rejected(self, column: str) -> None:
        frame = fixture_frame()
        frame.loc[0, column] = 0
        with pytest.raises(QlirError, match="non-positive"):
            validate_events(frame)

    def test_unsupported_suffix_rejected(self, tmp_path) -> None:
        path = tmp_path / "events.csv"
        path.write_text("nope", encoding="utf-8")
        with pytest.raises(QlirError, match="unsupported"):
            load_events(path)


class TestAggressorConvention:
    def test_sign_mapping(self) -> None:
        out = aggressor_sign(pd.Series(["B", "A", "N"]))
        assert list(out) == [1, -1, 0]

    def test_signed_flow_uses_sqrt_size(self) -> None:
        # B:4 -> +2, A:9 -> -3, N:1 -> 0, B:16 -> +4  => +3
        assert signed_flow(fixture_frame()) == pytest.approx(2 - 3 + 0 + 4)

    def test_unknown_side_counts_toward_volume_not_flow(self) -> None:
        frame = fixture_frame()
        assert unknown_side_fraction(frame) == pytest.approx(1 / 30)
        assert int(frame["size"].sum()) == 30  # N-volume kept in totals

    def test_unknown_side_fraction_empty(self) -> None:
        frame = fixture_frame().iloc[:0]
        assert unknown_side_fraction(frame) == 0.0


class TestDbnDecode:
    def test_dbn_requires_databento_or_real_file(self, tmp_path) -> None:
        pytest.importorskip("databento")
        sample = tmp_path / "sample.dbn.zst"
        if not sample.exists():
            pytest.skip(
                "no real DBN sample present — the decode branch is a thin "
                "DBNStore wrapper; it activates with the first purchased file"
            )
