from __future__ import annotations

from pathlib import Path

import pytest

from quantlab.errors import MappingError
from quantlab.ingest.mapping import ColumnMapping, autodetect_mapping
from quantlab.ingest.tradelog import load_trade_log, parse_money
from quantlab.schema.trade import Side

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class TestParseMoney:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("$1,234.56", 1234.56),
            ("($500)", -500.0),
            ("(1,000.25)", -1000.25),
            ("-12.5", -12.5),
            ("\u221212.5", -12.5),  # unicode minus
            ("  3.5 ", 3.5),
            (7, 7.0),
            ("€2,000", 2000.0),
        ],
    )
    def test_parses(self, raw: object, expected: float) -> None:
        assert parse_money(raw) == pytest.approx(expected)

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError):
            parse_money("  ")


class TestAutodetect:
    def test_detects_sample_headers(self) -> None:
        headers = [
            "Entry DateTime",
            "Exit DateTime",
            "Symbol",
            "Type",
            "Qty",
            "Net P/L",
            "MAE",
            "MFE",
        ]
        mapping = autodetect_mapping(headers)
        assert mapping.exit_time == "Exit DateTime"
        assert mapping.pnl == "Net P/L"
        assert mapping.side is not None and mapping.side.column == "Type"
        assert mapping.mae == "MAE" and mapping.mfe == "MFE"

    def test_requires_core_columns(self) -> None:
        with pytest.raises(MappingError, match="auto-detect"):
            autodetect_mapping(["foo", "bar"])


class TestMappingConfig:
    def test_from_pairs_and_yaml(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "map.yaml"
        yaml_path.write_text("exit_time: When\npnl: Result\nside: Direction\n")
        base = ColumnMapping.from_yaml(yaml_path)
        assert base.side is not None and base.side.column == "Direction"
        override = ColumnMapping.from_pairs(["pnl=NetPL", "tz=America/New_York"], base=base)
        assert override.pnl == "NetPL"
        assert override.tz == "America/New_York"
        with pytest.raises(MappingError, match="Unknown field"):
            ColumnMapping.from_pairs(["nonsense=X"])

    def test_validate_against_missing_column(self) -> None:
        mapping = ColumnMapping(exit_time="When", pnl="Result")
        with pytest.raises(MappingError, match="not present"):
            mapping.validate_against(["When", "Other"])


class TestLoadSampleCsv:
    def test_loads_with_autodetect(self) -> None:
        log, report = load_trade_log(EXAMPLES / "trades_sample.csv")
        assert report.rows_read == 400
        assert report.trades_loaded == 400
        assert report.rows_dropped == 0
        assert report.autodetected
        assert log.has_excursions
        assert {t.side for t in log.trades} == {Side.LONG, Side.SHORT}
        assert all(t.mae is not None and t.mae <= 0 for t in log.trades)

    def test_loads_with_explicit_mapping(self) -> None:
        mapping = ColumnMapping.from_yaml(EXAMPLES / "trades_mapping.yaml")
        log, report = load_trade_log(EXAMPLES / "trades_sample.csv", mapping)
        assert not report.autodetected
        assert len(log) == 400
        # tz applied: sample entries are 08:30-13:30 America/Chicago -> UTC+6 in winter
        first = log.trades[0]
        assert first.exit_time.tzinfo is not None
        assert first.exit_time.hour >= 14  # 08:30 CT == 14:30 UTC in January

    def test_bad_rows_dropped_with_reason(self, tmp_path: Path) -> None:
        csv = tmp_path / "log.csv"
        csv.write_text(
            "Exit DateTime,Net P/L\n"
            "2026-01-05 10:00:00,$100\n"
            "not-a-date,$50\n"
            "2026-01-06 10:00:00,\n"
        )
        log, report = load_trade_log(csv)
        assert len(log) == 1
        assert report.rows_dropped == 2
        reasons = " ".join(reason for _, reason in report.dropped)
        assert "ValueError" in reasons

    def test_all_bad_raises(self, tmp_path: Path) -> None:
        csv = tmp_path / "log.csv"
        csv.write_text("Exit DateTime,Net P/L\nnope,\n")
        with pytest.raises(MappingError, match="No trades"):
            load_trade_log(csv)


class TestMixedFormatColumns:
    """Pass-2 regression: the vectorized parser infers ONE format from the
    first row and used to silently NaT (and drop) every other-format row."""

    def test_mixed_datetime_formats_all_load(self, tmp_path: Path) -> None:
        csv = tmp_path / "mixed.csv"
        csv.write_text(
            "Exit DateTime,Symbol,Net P/L\n"
            "2026-01-05 09:31:00,MNQ,100\n"
            "01/06/2026 10:15,MNQ,-50\n"  # minority format
            "2026-01-07 11:00:00.123,MNQ,25\n"  # fractional seconds
        )
        log, report = load_trade_log(csv)
        assert report.rows_dropped == 0
        assert len(log) == 3
        assert sorted(t.exit_time.day for t in log.trades) == [5, 6, 7]


class TestFallbackUnitMismatch:
    """Pass-3 regression: a finer-precision straggler (9-digit fractional
    seconds) crashed the per-row fallback with TypeError instead of loading
    (or at worst dropping) the row."""

    def test_nanosecond_straggler_loads(self, tmp_path: Path) -> None:
        csv = tmp_path / "ns.csv"
        csv.write_text(
            "Exit DateTime,Symbol,Net P/L\n"
            "2026-01-05 09:31:00,MNQ,100\n"
            "2026-01-06 10:15:00.123456789,MNQ,-50\n"
        )
        log, report = load_trade_log(csv)
        assert report.rows_dropped == 0
        assert len(log) == 2


class TestFirstRowMinorityFormat:
    """Pass-3 regression: rescue rounds must stay vectorized — a first row
    in the minority format made the old per-row fallback re-parse the
    entire rest of the file one scalar call at a time."""

    def test_minority_first_row_loads_everything(self, tmp_path: Path) -> None:
        rows = "\n".join(f"2026-01-05 09:{i:02d}:00,MNQ,10" for i in range(30, 59))
        csv = tmp_path / "minority_first.csv"
        csv.write_text("Exit DateTime,Symbol,Net P/L\n01/06/2026 10:15,MNQ,-50\n" + rows + "\n")
        log, report = load_trade_log(csv)
        assert report.rows_dropped == 0
        assert len(log) == 30
