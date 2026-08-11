from __future__ import annotations

from pathlib import Path

import pytest

from quantlab.errors import MappingError
from quantlab.ingest.ohlcv import load_ohlcv, write_normalized


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "bars.csv"
    path.write_text(text)
    return path


class TestLoadOhlcv:
    def test_normalizes_and_validates(self, tmp_path: Path) -> None:
        csv = _write(
            tmp_path,
            "Date,Open,High,Low,Close,Volume\n"
            "2026-01-05 09:30,100,101,99.5,100.5,1200\n"
            "2026-01-05 09:31,100.5,102,100,101.5,900\n"
            "2026-01-05 09:31,100.5,102,100,101.5,900\n"  # duplicate
            "2026-01-05 09:32,101.5,101.0,100,100.8,500\n"  # high < open: invalid
            "not-a-date,1,2,0,1,1\n",
        )
        frame, report = load_ohlcv(csv, tz="America/Chicago")
        assert report.rows_read == 5
        assert report.bars_kept == 2
        assert report.duplicate_timestamps == 1
        assert len(report.dropped) == 2
        assert str(frame["datetime"].iloc[0].tz) == "UTC"
        assert frame["datetime"].iloc[0].hour == 15  # 09:30 CT -> 15:30 UTC (winter)

    def test_gap_report(self, tmp_path: Path) -> None:
        csv = _write(
            tmp_path,
            "datetime,open,high,low,close\n"
            "2026-01-05,100,101,99,100\n"
            "2026-01-08,100,101,99,100\n",  # Tue+Wed missing
        )
        _, report = load_ohlcv(csv)
        assert report.weekday_gaps == 2

    def test_missing_columns(self, tmp_path: Path) -> None:
        csv = _write(tmp_path, "a,b\n1,2\n")
        with pytest.raises(MappingError, match="detect OHLCV"):
            load_ohlcv(csv)

    def test_write_normalized_round_trip(self, tmp_path: Path) -> None:
        csv = _write(
            tmp_path,
            "datetime,open,high,low,close,volume\n2026-01-05 09:30,1,2,0.5,1.5,10\n",
        )
        frame, _ = load_ohlcv(csv)
        out = write_normalized(frame, tmp_path / "norm.csv")
        text = out.read_text()
        assert text.splitlines()[0] == "datetime,open,high,low,close,volume"
        assert "2026-01-05T09:30:00Z" in text


class TestDstFallBack:
    """Pass-2 regression: ambiguous=True stamped both passes of the repeated
    fall-back hour with the SAME UTC offset, so the dedupe silently deleted
    the entire standard-time hour of real bars."""

    def test_fall_back_hour_bars_survive(self, tmp_path: Path) -> None:
        csv = _write(
            tmp_path,
            "Date,Open,High,Low,Close,Volume\n"
            "2025-11-02 01:15,100,101,99,100.5,10\n"  # CDT pass
            "2025-11-02 01:15,101,102,100,101.5,10\n"  # CST pass (real data)
            "2025-11-02 02:15,102,103,101,102.5,10\n",
        )
        frame, report = load_ohlcv(csv, tz="America/Chicago")
        assert report.bars_kept == 3
        assert report.duplicate_timestamps == 0
        stamps = sorted(frame["datetime"])
        assert len(set(stamps)) == 3  # distinct UTC instants


class TestNewestFirstExport:
    """Pass-3 regression: DST inference on a reverse-chronological export
    silently swapped the fall-back hour's UTC offsets (no error raised)."""

    def test_reversed_file_localizes_correctly(self, tmp_path: Path) -> None:
        csv = _write(
            tmp_path,
            "Date,Open,High,Low,Close,Volume\n"
            "2025-11-02 02:15,102,103,101,102.5,10\n"
            "2025-11-02 01:15,101,102,100,101.5,10\n"  # CST pass (second)
            "2025-11-02 01:15,100,101,99,100.5,10\n"  # CDT pass (first)
            "2025-11-02 00:15,99,100,98,99.5,10\n",
        )
        frame, report = load_ohlcv(csv, tz="America/Chicago")
        assert report.bars_kept == 4
        assert report.duplicate_timestamps == 0
        # Chronological output: opens must ascend 99 -> 100 (CDT) -> 101 (CST) -> 102
        assert list(frame["open"]) == [99.0, 100.0, 101.0, 102.0]


class TestLoneFoldBar:
    """Pass-3 regression: with a feed that records the fall-back hour once,
    "infer" raises — the fallback must keep the bar (labeled DST), not NaT
    every ambiguous stamp in the file (or crash on pandas 2.x)."""

    def test_single_ambiguous_bar_is_kept(self, tmp_path: Path) -> None:
        csv = _write(
            tmp_path,
            "Date,Open,High,Low,Close,Volume\n"
            "2025-11-02 00:15,99,100,98,99.5,10\n"
            "2025-11-02 01:15,100,101,99,100.5,10\n"  # recorded once
            "2025-11-02 02:15,102,103,101,102.5,10\n",
        )
        _frame, report = load_ohlcv(csv, tz="America/Chicago")
        assert report.bars_kept == 3
        assert not report.dropped


class TestMultiTransitionFolds:
    """Pass-4 regression: one lone fold stamp anywhere in the file made the
    fallback relabel EVERY fold blanket-DST, and the dedupe silently
    deleted the real second-pass bars of properly-recorded transitions."""

    def test_duplicated_and_lone_folds_all_survive(self, tmp_path: Path) -> None:
        csv = _write(
            tmp_path,
            "Date,Open,High,Low,Close,Volume\n"
            "2024-11-03 00:15,1,2,0,1,1\n"
            "2024-11-03 01:15,2,3,1,2,1\n"  # CDT pass
            "2024-11-03 01:15,3,4,2,3,1\n"  # CST pass (real bar)
            "2024-11-03 02:15,4,5,3,4,1\n"
            "2025-11-02 00:15,5,6,4,5,1\n"
            "2025-11-02 01:15,6,7,5,6,1\n"  # lone fold stamp
            "2025-11-02 02:15,7,8,6,7,1\n",
        )
        frame, report = load_ohlcv(csv, tz="America/Chicago")
        assert report.bars_kept == 7
        assert report.duplicate_timestamps == 0
        assert list(frame["open"]) == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]


class TestNonHourFoldWidth:
    """Pass-5 regression: the second-pass shift hardcoded 1 hour, giving
    wrong UTC instants for zones with 30-minute folds (and colliding with
    real later bars, which the dedupe then deleted)."""

    def test_lord_howe_thirty_minute_fold(self, tmp_path: Path) -> None:
        csv = _write(
            tmp_path,
            "Date,Open,High,Low,Close,Volume\n"
            "2024-04-07 01:15,1,2,0,1,1\n"
            "2024-04-07 01:45,2,3,1,2,1\n"  # DST pass (+11:00)
            "2024-04-07 01:45,3,4,2,3,1\n"  # standard pass (+10:30)
            "2024-04-07 02:15,4,5,3,4,1\n",
        )
        frame, report = load_ohlcv(csv, tz="Australia/Lord_Howe")
        assert report.bars_kept == 4
        assert list(frame["open"]) == [1.0, 2.0, 3.0, 4.0]
        assert [t.strftime("%H:%M") for t in frame["datetime"]] == [
            "14:15",
            "14:45",
            "15:15",
            "15:45",
        ]


class TestSplitDateTimeColumns:
    def test_date_plus_time_columns_combine(self, tmp_path):
        """Split Date/Time exports must not collapse to one bar per day (F4)."""
        csv = tmp_path / "bars.csv"
        csv.write_text(
            "Date,Time,Open,High,Low,Close,Volume\n"
            "2024-01-05,09:30:00,100,101,99,100.5,1000\n"
            "2024-01-05,09:31:00,100.5,102,100,101.5,900\n"
            "2024-01-05,09:32:00,101.5,103,101,102.5,800\n",
            encoding="utf-8",
        )
        frame, report = load_ohlcv(csv)
        assert report.bars_kept == 3
        assert report.duplicate_timestamps == 0
        minutes = [ts.minute for ts in frame["datetime"]]
        assert minutes == [30, 31, 32]

    def test_time_only_without_date_refuses(self, tmp_path):
        csv = tmp_path / "bars.csv"
        csv.write_text(
            "Time,Open,High,Low,Close\n09:30:00,1,2,0.5,1.5\n09:31:00,1.5,2,1,1.8\n",
            encoding="utf-8",
        )
        with pytest.raises(MappingError, match="time-of-day"):
            load_ohlcv(csv)

    def test_zero_byte_file_clean_error(self, tmp_path):
        empty = tmp_path / "empty.csv"
        empty.write_bytes(b"")
        with pytest.raises(MappingError, match="empty"):
            load_ohlcv(empty)

    def test_bad_timezone_clean_error(self, tmp_path):
        csv = tmp_path / "bars.csv"
        csv.write_text(
            "datetime,Open,High,Low,Close\n2024-01-05 09:30:00,1,2,0.5,1.5\n", encoding="utf-8"
        )
        with pytest.raises(MappingError, match="timezone"):
            load_ohlcv(csv, tz="Not/AZone")

    def test_mixed_utc_offsets_load(self, tmp_path):
        csv = tmp_path / "bars.csv"
        csv.write_text(
            "datetime,Open,High,Low,Close\n"
            "2024-01-05T10:30:00-05:00,1,2,0.5,1.5\n"
            "2024-06-05T10:30:00-04:00,1.5,2,1,1.8\n",
            encoding="utf-8",
        )
        _, report = load_ohlcv(csv)
        assert report.bars_kept == 2


class TestPostReviewRegressions:
    def test_daily_file_with_empty_time_column_loads(self, tmp_path):
        """A vestigial empty Time column must not poison every stamp (P2)."""
        csv = tmp_path / "daily.csv"
        csv.write_text(
            "Date,Time,Open,High,Low,Close\n"
            "2024-01-03,,100,101,99,100.5\n"
            "2024-01-04,,100.5,102,100,101.5\n"
            "2024-01-05,,101.5,103,101,102.5\n",
            encoding="utf-8",
        )
        _frame, report = load_ohlcv(csv)
        assert report.bars_kept == 3 and not report.dropped

    def test_partial_time_column_keeps_dateonly_rows(self, tmp_path):
        csv = tmp_path / "partial.csv"
        csv.write_text(
            "Date,Time,Open,High,Low,Close\n"
            "2024-01-03,09:30:00,100,101,99,100.5\n"
            "2024-01-03,09:31:00,100.5,102,100,101.5\n"
            "2024-01-04,,101.5,103,101,102.5\n",
            encoding="utf-8",
        )
        _frame, report = load_ohlcv(csv)
        assert report.bars_kept == 3 and not report.dropped

    def test_yyyymmdd_integer_dates(self, tmp_path):
        """Compact int dates must not parse as epoch nanoseconds (P3)."""
        csv = tmp_path / "compact.csv"
        csv.write_text(
            "Date,Time,Open,High,Low,Close\n"
            "20240105,09:30:00,100,101,99,100.5\n"
            "20240105,09:31:00,100.5,102,100,101.5\n"
            "20240105,09:32:00,101.5,103,101,102.5\n",
            encoding="utf-8",
        )
        frame, report = load_ohlcv(csv)
        assert report.bars_kept == 3
        assert report.duplicate_timestamps == 0
        assert all(ts.year == 2024 for ts in frame["datetime"])

    def test_bar_time_synonym_combines(self, tmp_path):
        """'Bar Time' companions must be found by synonym, not exact 'time' (P10)."""
        csv = tmp_path / "bartime.csv"
        csv.write_text(
            "Date,Bar Time,Open,High,Low,Close\n"
            "2024-01-05,09:30:00,100,101,99,100.5\n"
            "2024-01-05,09:31:00,100.5,102,100,101.5\n",
            encoding="utf-8",
        )
        _frame, report = load_ohlcv(csv)
        assert report.bars_kept == 2 and report.duplicate_timestamps == 0

    def test_report_names_user_columns_not_scratch(self, tmp_path):
        csv = tmp_path / "named.csv"
        csv.write_text(
            "Date,Time,Open,High,Low,Close\n2024-01-05,09:30:00,100,101,99,100.5\n",
            encoding="utf-8",
        )
        _, report = load_ohlcv(csv)
        assert "__combined" not in report.columns_used["datetime"]
        assert report.columns_used["datetime"] == "Date + Time"


    def test_partial_time_column_with_hhmm_times(self, tmp_path):
        """Bare HH:MM times + injected midnights must share ONE format."""
        csv = tmp_path / "hhmm.csv"
        csv.write_text(
            "Date,Time,Open,High,Low,Close\n"
            "2024-01-03,09:30,100,101,99,100.5\n"
            "2024-01-03,09:31,100.5,102,100,101.5\n"
            "2024-01-04,,101.5,103,101,102.5\n",
            encoding="utf-8",
        )
        _frame, report = load_ohlcv(csv)
        assert report.bars_kept == 3 and not report.dropped
