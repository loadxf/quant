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
