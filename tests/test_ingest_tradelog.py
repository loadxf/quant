from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

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

    def test_rejects_unknown_nested_and_wrong_type_fields(self) -> None:
        with pytest.raises(ValidationError, match="tzz"):
            ColumnMapping.model_validate(
                {"exit_time": "Exit", "pnl": "P/L", "tzz": "America/New_York"}
            )
        with pytest.raises(ValidationError, match="unexpected"):
            ColumnMapping.model_validate(
                {
                    "exit_time": "Exit",
                    "pnl": "P/L",
                    "side": {"column": "Side", "unexpected": "ignored before"},
                }
            )
        with pytest.raises(ValidationError, match="exit_time"):
            ColumnMapping.model_validate({"exit_time": 123, "pnl": "P/L"})

    def test_yaml_validation_is_wrapped_as_mapping_error(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("exit_time: Exit\npnl: P/L\ntzz: America/New_York\n")
        with pytest.raises(MappingError, match="Invalid mapping file") as exc_info:
            ColumnMapping.from_yaml(path)
        assert "tzz" in str(exc_info.value)

    def test_unreadable_trade_log_is_wrapped(self, tmp_path: Path) -> None:
        with pytest.raises(MappingError, match="Could not read trade-log CSV"):
            load_trade_log(tmp_path / "missing.csv")


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

    @pytest.mark.parametrize("reverse", [False, True])
    def test_mixed_full_and_time_only_rows_use_each_rows_companion_date(
        self, tmp_path: Path, reverse: bool
    ) -> None:
        rows = [
            "2024-01-02,2024-01-02 09:31,MNQ,100",
            "2024-01-03,09:32,MNQ,-50",
        ]
        if reverse:
            rows.reverse()
        csv = tmp_path / "mixed_split.csv"
        csv.write_text("Date,Exit Time,Symbol,Net P/L\n" + "\n".join(rows) + "\n")
        log, report = load_trade_log(csv)
        assert report.rows_dropped == 0
        assert [trade.exit_time.date().isoformat() for trade in log.trades] == [
            "2024-01-02",
            "2024-01-03",
        ]


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


class TestOutOfRangeSentinel:
    """Pass-4 regression: a year-9999 open-position sentinel crashed the
    load with OutOfBoundsDatetime; it must drop with a reason instead."""

    def test_sentinel_drops_instead_of_crashing(self, tmp_path: Path) -> None:
        csv = tmp_path / "sentinel.csv"
        csv.write_text(
            "Exit DateTime,Symbol,Net P/L\n"
            "2026-01-05 09:31:00,MNQ,100\n"
            "9999-12-31 00:00:00,MNQ,-50\n"
        )
        log, report = load_trade_log(csv)
        assert len(log) == 1
        assert report.rows_dropped == 1
        assert "timestamp" in report.dropped[0][1]


class TestMixedUtcOffsets:
    """Pass-4 regression: stragglers carrying different UTC offsets made
    pandas 3 raise 'Mixed timezones' from the rescue parse (despite
    errors='coerce'), crashing the load; they must all load."""

    def test_offset_rows_load(self, tmp_path: Path) -> None:
        csv = tmp_path / "mixedtz.csv"
        csv.write_text(
            "Exit DateTime,Symbol,Net P/L\n"
            "2026-01-05 09:31:00,MNQ,100\n"
            "2026-03-06 10:15:00-06:00,MNQ,-50\n"
            "2026-03-09 11:00:00-05:00,MNQ,25\n"
        )
        log, report = load_trade_log(csv)
        assert report.rows_dropped == 0
        assert len(log) == 3

    def test_all_aware_summer_and_winter_rows_load(self, tmp_path: Path) -> None:
        csv = tmp_path / "aware.csv"
        csv.write_text(
            "Entry DateTime,Exit DateTime,Symbol,Net P/L\n"
            "2024-07-01T09:30:00-04:00,2024-07-01T10:00:00-04:00,MNQ,100\n"
            "2024-12-01T09:30:00-05:00,2024-12-01T10:00:00-05:00,MNQ,-50\n"
        )
        log, report = load_trade_log(csv)
        assert report.rows_dropped == 0
        assert len(log) == 2
        assert [trade.entry_time.hour for trade in log.trades] == [13, 14]


class TestSentinelInScalarRescueBatch:
    """Pass-5 regression: a year-9999 sentinel sharing a rescue batch with
    mixed-UTC-offset rows slipped past the range mask via the scalar path
    and loaded as a fake trade."""

    def test_sentinel_drops_on_every_rescue_path(self, tmp_path: Path) -> None:
        csv = tmp_path / "mix9999.csv"
        csv.write_text(
            "Exit DateTime,Symbol,Net P/L\n"
            "2026-01-05 09:31:00,MNQ,100\n"
            "2026-03-06 10:15:00-06:00,MNQ,-50\n"
            "2026-03-09 11:00:00-05:00,MNQ,25\n"
            "9999-12-31 00:00:00,MNQ,-25\n"
        )
        log, report = load_trade_log(csv)
        assert len(log) == 3
        assert report.rows_dropped == 1
        assert report.dropped[0][0] == 3


class TestDecimalCommaFormats:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("1.234,56", 1234.56),  # EU grouping + decimal comma
            ("1 234,56", 1234.56),  # space grouping (French exports)
            ("1234,56", 1234.56),  # bare decimal comma
            ("1,23456", 1.23456),  # >2 decimals (FX rates)
            ("0,12345", 0.12345),
            ("-1234,5", -1234.5),
            ("1.234.567", 1234567.0),  # EU grouping, no decimals
            ("1,23,456.78", 123456.78),  # lakh grouping
            ("1,234", 1234.0),  # documented US-default ambiguity
            ("1.234", 1.234),  # mirror-image ambiguity stays US decimal
            ("0,500", 0.5),  # zero lead: only ever an EU decimal
            ("-0,125", -0.125),
            ("(0,500)", -0.5),
        ],
    )
    def test_parses(self, raw: str, expected: float) -> None:
        assert parse_money(raw) == pytest.approx(expected)

    @pytest.mark.parametrize("raw", ["inf", "-inf", "Infinity", float("inf"), float("nan")])
    def test_rejects_non_finite(self, raw: object) -> None:
        with pytest.raises(ValueError):
            parse_money(raw)


class TestPercentColumnShadowing:
    """A percent column next to the money column must never win (F3)."""

    @pytest.mark.parametrize(
        "headers",
        [
            ["Exit Time", "Profit", "Profit %", "Qty"],
            ["Exit Time", "Profit %", "Profit", "Qty"],  # reversed column order
            ["Exit DateTime", "Net Profit", "Profit %", "Qty"],  # no normalization collision
        ],
    )
    def test_pnl_binds_to_money_column(self, headers: list[str]) -> None:
        mapping = autodetect_mapping(headers)
        assert mapping.pnl in ("Profit", "Net Profit")

    def test_true_ambiguity_refuses(self) -> None:
        with pytest.raises(MappingError, match="Ambiguous"):
            autodetect_mapping(["Exit Time", "Net P/L", "Net-P/L", "Qty"])

    def test_map_override_resolves_ambiguity(self, tmp_path: Path) -> None:
        csv = tmp_path / "amb.csv"
        csv.write_text(
            "Exit Time,Net P/L,Net-P/L,Qty\n2024-01-05 10:30:00,100,1.0,2\n", encoding="utf-8"
        )
        log, _report = load_trade_log(csv, overrides=["pnl=Net P/L"])
        assert log.trades[0].pnl == 100.0


class TestMapOverlayAutodetect:
    """--map without --mapping overlays auto-detection (F14)."""

    def test_partial_pairs_overlay(self, tmp_path: Path) -> None:
        csv = tmp_path / "t.csv"
        csv.write_text(
            "Exit Time,NetPL,Qty\n2024-01-05 10:30:00,150,1\n2024-01-05 11:00:00,-50,2\n",
            encoding="utf-8",
        )
        log, report = load_trade_log(csv, overrides=["pnl=NetPL", "tz=America/New_York"])
        assert report.autodetected
        assert len(log) == 2
        # tz was explicit: 10:30 New York == 15:30 UTC
        assert log.trades[0].exit_time.hour == 15
        assert not any("timezone" in w for w in report.warnings)

    def test_full_pairs_stay_authoritative(self, tmp_path: Path) -> None:
        # A fully-specified pairs-only mapping must NOT autodetect: a Type
        # column holding order types would otherwise be grabbed as side.
        csv = tmp_path / "t.csv"
        csv.write_text("Closed,NetPL,Type\n2024-01-05 10:30:00,150,market\n", encoding="utf-8")
        log, report = load_trade_log(csv, overrides=["exit_time=Closed", "pnl=NetPL"])
        assert not report.autodetected
        assert len(log) == 1 and log.trades[0].side == Side.LONG


class TestSignedQuantity:
    def test_negative_quantity_infers_short(self, tmp_path: Path) -> None:
        csv = tmp_path / "t.csv"
        csv.write_text(
            "Exit Time,PnL,Qty\n2024-01-05 10:30:00,100,-2\n2024-01-05 11:00:00,-40,3\n",
            encoding="utf-8",
        )
        log, report = load_trade_log(csv)
        assert [t.side for t in log.trades] == [Side.SHORT, Side.LONG]
        assert [t.quantity for t in log.trades] == [2.0, 3.0]
        assert any("side inferred" in w for w in report.warnings)

    def test_signed_quantity_with_side_column_is_clamped(self, tmp_path: Path) -> None:
        csv = tmp_path / "t.csv"
        csv.write_text(
            "Exit Time,PnL,Qty,Side\n2024-01-05 10:30:00,100,-2,sell\n", encoding="utf-8"
        )
        log, report = load_trade_log(csv)
        assert log.trades[0].side == Side.SHORT and log.trades[0].quantity == 2.0
        assert not any("side inferred" in w for w in report.warnings)


class TestPerLegSplitDateTime:
    def test_entry_and_exit_date_time_pairs(self, tmp_path: Path) -> None:
        csv = tmp_path / "t.csv"
        csv.write_text(
            "Entry Date,Entry Time,Exit Date,Exit Time,PnL\n"
            "2024-01-05,09:30:00,2024-01-05,10:45:00,125\n",
            encoding="utf-8",
        )
        log, _report = load_trade_log(csv)
        assert len(log) == 1
        trade = log.trades[0]
        assert (trade.entry_time.hour, trade.entry_time.minute) == (9, 30)
        assert (trade.exit_time.hour, trade.exit_time.minute) == (10, 45)


class TestMappingYamlStrictKeys:
    def test_unknown_key_rejected(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "map.yaml"
        yaml_path.write_text(
            "exit_time: When\npnl: Result\ndatetime_fmt: '%d/%m/%Y'\n", encoding="utf-8"
        )
        with pytest.raises(MappingError, match="datetime_fmt"):
            ColumnMapping.from_yaml(yaml_path)


class TestNaiveTzWarning:
    def test_autodetect_naive_warns(self, tmp_path: Path) -> None:
        csv = tmp_path / "t.csv"
        csv.write_text("Exit Time,PnL\n2024-01-05 10:30:00,100\n", encoding="utf-8")
        _, report = load_trade_log(csv)
        assert any("read as UTC" in w for w in report.warnings)

    def test_explicit_tz_no_warning(self, tmp_path: Path) -> None:
        csv = tmp_path / "t.csv"
        csv.write_text("Exit Time,PnL\n2024-01-05 10:30:00,100\n", encoding="utf-8")
        _, report = load_trade_log(csv, overrides=["tz=UTC"])
        assert not any("read as UTC" in w for w in report.warnings)


class TestCleanErrors:
    def test_zero_byte_file(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.csv"
        empty.write_bytes(b"")
        with pytest.raises(MappingError, match="empty"):
            load_trade_log(empty)

    def test_bad_timezone(self, tmp_path: Path) -> None:
        csv = tmp_path / "t.csv"
        csv.write_text("Exit Time,PnL\n2024-01-05 10:30:00,100\n", encoding="utf-8")
        with pytest.raises(MappingError, match="timezone"):
            load_trade_log(csv, overrides=["tz=Not/AZone"])


class TestWholeColumnMixedOffsets:
    def test_two_offsets_in_column_load(self, tmp_path: Path) -> None:
        """DST-spanning ISO export: the FIRST vectorized parse raises in
        pandas 3 — must fall back, not crash (F2)."""
        csv = tmp_path / "t.csv"
        csv.write_text(
            "exit_time,pnl\n2024-01-05T10:30:00-05:00,100\n2024-06-05T10:30:00-04:00,-50\n",
            encoding="utf-8",
        )
        log, report = load_trade_log(csv)
        assert len(log) == 2 and report.rows_dropped == 0
        assert log.trades[0].exit_time.hour == 15  # -05:00 -> UTC
        assert log.trades[1].exit_time.hour == 14  # -04:00 -> UTC


class TestMappingUsedCompleteness:
    def test_fees_and_prices_reported(self, tmp_path: Path) -> None:
        csv = tmp_path / "t.csv"
        csv.write_text(
            "Exit Time,PnL,Fees,Entry Price,Exit Price\n2024-01-05 10:30:00,100,2.5,5000,5010\n",
            encoding="utf-8",
        )
        _, report = load_trade_log(csv)
        assert report.mapping_used.get("fees") == "Fees"
        assert report.mapping_used.get("entry_price") == "Entry Price"
        assert report.mapping_used.get("exit_price") == "Exit Price"


class TestNaiveDstSafety:
    @pytest.mark.parametrize("stamp", ["2025-11-02 01:15:00", "2025-03-09 02:15:00"])
    def test_ambiguous_or_nonexistent_local_time_is_dropped(
        self, tmp_path: Path, stamp: str
    ) -> None:
        csv = tmp_path / "dst.csv"
        csv.write_text(
            f"Exit DateTime,Symbol,Net P/L\n2025-11-03 09:00:00,MNQ,10\n{stamp},MNQ,10\n"
        )
        log, report = load_trade_log(
            csv,
            ColumnMapping(
                exit_time="Exit DateTime",
                symbol="Symbol",
                pnl="Net P/L",
                tz="America/Chicago",
            ),
        )
        assert len(log) == 1
        assert report.rows_dropped == 1
        assert "ambiguous or nonexistent" in report.dropped[0][1]
