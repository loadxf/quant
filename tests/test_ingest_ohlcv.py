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
    def test_unreadable_csv_is_wrapped(self, tmp_path: Path) -> None:
        with pytest.raises(MappingError, match="Could not read OHLCV CSV"):
            load_ohlcv(tmp_path / "missing.csv")

    def test_explicit_summer_and_winter_offsets_normalize_to_utc(
        self, tmp_path: Path
    ) -> None:
        csv = _write(
            tmp_path,
            "datetime,open,high,low,close,volume\n"
            "2024-07-01T09:30:00-04:00,1,2,0.5,1.5,10\n"
            "2024-12-01T09:30:00-05:00,1,2,0.5,1.5,10\n",
        )
        frame, report = load_ohlcv(csv, tz="America/New_York")
        assert report.bars_kept == 2
        assert [stamp.hour for stamp in frame["datetime"]] == [13, 14]

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

    @pytest.mark.parametrize("reverse", [False, True])
    def test_conflicting_duplicate_timestamp_is_rejected_independent_of_order(
        self, tmp_path: Path, reverse: bool
    ) -> None:
        rows = [
            "2026-01-05 09:30,100,101,99,100.5,1200",
            "2026-01-05 09:30,100,102,99,101.5,900",
        ]
        if reverse:
            rows.reverse()
        csv = _write(
            tmp_path,
            "datetime,open,high,low,close,volume\n" + "\n".join(rows) + "\n",
        )
        with pytest.raises(MappingError, match="Conflicting OHLCV bars"):
            load_ohlcv(csv)

    def test_missing_columns(self, tmp_path: Path) -> None:
        csv = _write(tmp_path, "a,b\n1,2\n")
        with pytest.raises(MappingError, match="detect OHLCV"):
            load_ohlcv(csv)

    def test_drops_nonfinite_prices_and_invalid_volume(self, tmp_path: Path) -> None:
        csv = _write(
            tmp_path,
            "datetime,open,high,low,close,volume\n"
            "2026-01-05 09:30,1,2,0.5,1.5,10\n"
            "2026-01-05 09:31,1,inf,0.5,1.5,10\n"
            "2026-01-05 09:32,1,2,0.5,1.5,-1\n"
            "2026-01-05 09:33,1,2,0.5,1.5,nan\n",
        )
        frame, report = load_ohlcv(csv)
        assert len(frame) == 1
        assert len(report.dropped) == 3
        assert any("volume" in reason for _, reason in report.dropped)

    def test_drops_nonpositive_prices(self, tmp_path: Path) -> None:
        csv = _write(
            tmp_path,
            "datetime,open,high,low,close,volume\n"
            "2026-01-05 09:30,1,2,0.5,1.5,10\n"
            "2026-01-05 09:31,-1,2,-2,1.5,10\n",
        )
        frame, report = load_ohlcv(csv)
        assert len(frame) == 1
        assert report.dropped == [(1, "price must be numeric, finite, and positive")]

    def test_unknown_timezone_is_domain_error(self, tmp_path: Path) -> None:
        csv = _write(
            tmp_path,
            "datetime,open,high,low,close\n2026-01-05,1,2,0.5,1.5\n",
        )
        with pytest.raises(MappingError, match="timezone"):
            load_ohlcv(csv, tz="Not/A_Zone")

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

    def test_write_normalized_failure_is_domain_error(self, tmp_path: Path) -> None:
        csv = _write(
            tmp_path,
            "datetime,open,high,low,close,volume\n"
            "2026-01-05 09:30,1,2,0.5,1.5,10\n",
        )
        frame, _ = load_ohlcv(csv)
        with pytest.raises(MappingError, match="Could not write normalized OHLCV"):
            write_normalized(frame, tmp_path / "missing" / "norm.csv")


class TestDstFallBack:
    """Naive fold/gap stamps are rejected because they do not identify an instant."""

    def test_fall_back_hour_bars_survive(self, tmp_path: Path) -> None:
        csv = _write(
            tmp_path,
            "Date,Open,High,Low,Close,Volume\n"
            "2025-11-02 01:15,100,101,99,100.5,10\n"  # CDT pass
            "2025-11-02 01:15,101,102,100,101.5,10\n"  # CST pass (real data)
            "2025-11-02 02:15,102,103,101,102.5,10\n",
        )
        frame, report = load_ohlcv(csv, tz="America/Chicago")
        assert report.bars_kept == 1
        assert len(report.dropped) == 2
        assert report.duplicate_timestamps == 0
        assert list(frame["open"]) == [102.0]


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
        assert report.bars_kept == 2
        assert report.duplicate_timestamps == 0
        assert list(frame["open"]) == [99.0, 102.0]


class TestLoneFoldBar:
    """A lone fold stamp is still ambiguous and must not be guessed."""

    def test_single_ambiguous_bar_is_kept(self, tmp_path: Path) -> None:
        csv = _write(
            tmp_path,
            "Date,Open,High,Low,Close,Volume\n"
            "2025-11-02 00:15,99,100,98,99.5,10\n"
            "2025-11-02 01:15,100,101,99,100.5,10\n"  # recorded once
            "2025-11-02 02:15,102,103,101,102.5,10\n",
        )
        _frame, report = load_ohlcv(csv, tz="America/Chicago")
        assert report.bars_kept == 2
        assert report.dropped == [(1, "unparseable, ambiguous, or nonexistent local timestamp")]


class TestMultiTransitionFolds:
    """Pass-4 regression: one lone fold stamp anywhere in the file made the
    fallback relabel EVERY fold blanket-DST, and the dedupe silently
    deleted the real second-pass bars of properly-recorded transitions."""

    def test_duplicated_and_lone_folds_all_survive(self, tmp_path: Path) -> None:
        csv = _write(
            tmp_path,
            "Date,Open,High,Low,Close,Volume\n"
            "2024-11-03 00:15,1,2,0.5,1,1\n"
            "2024-11-03 01:15,2,3,1,2,1\n"  # CDT pass
            "2024-11-03 01:15,3,4,2,3,1\n"  # CST pass (real bar)
            "2024-11-03 02:15,4,5,3,4,1\n"
            "2025-11-02 00:15,5,6,4,5,1\n"
            "2025-11-02 01:15,6,7,5,6,1\n"  # lone fold stamp
            "2025-11-02 02:15,7,8,6,7,1\n",
        )
        frame, report = load_ohlcv(csv, tz="America/Chicago")
        assert report.bars_kept == 4
        assert report.duplicate_timestamps == 0
        assert list(frame["open"]) == [1.0, 4.0, 5.0, 7.0]


class TestNonHourFoldWidth:
    """Pass-5 regression: the second-pass shift hardcoded 1 hour, giving
    wrong UTC instants for zones with 30-minute folds (and colliding with
    real later bars, which the dedupe then deleted)."""

    def test_lord_howe_thirty_minute_fold(self, tmp_path: Path) -> None:
        csv = _write(
            tmp_path,
            "Date,Open,High,Low,Close,Volume\n"
            "2024-04-07 01:15,1,2,0.5,1,1\n"
            "2024-04-07 01:45,2,3,1,2,1\n"  # DST pass (+11:00)
            "2024-04-07 01:45,3,4,2,3,1\n"  # standard pass (+10:30)
            "2024-04-07 02:15,4,5,3,4,1\n",
        )
        frame, report = load_ohlcv(csv, tz="Australia/Lord_Howe")
        assert report.bars_kept == 2
        assert list(frame["open"]) == [1.0, 4.0]
        assert [t.strftime("%H:%M") for t in frame["datetime"]] == [
            "14:15",
            "15:45",
        ]
