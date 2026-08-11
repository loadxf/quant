from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from quantlab.errors import QuantLabError
from quantlab.schema.equity import EquityCurve, EquityPoint
from quantlab.schema.io import read_trade_log, write_trade_log
from quantlab.schema.trade import FTMO_DAY, FUTURES_DAY, Side, Trade, TradeLog

from .conftest import trades_from_daily

UTC = dt.UTC
CT = ZoneInfo("America/Chicago")


def _trade(exit_time: dt.datetime, pnl: float = 100.0) -> Trade:
    return Trade(
        entry_time=exit_time - dt.timedelta(minutes=10),
        exit_time=exit_time,
        symbol="MNQ",
        side=Side.LONG,
        quantity=1,
        pnl=pnl,
    )


class TestTradeValidation:
    def test_detects_overlapping_trade_intervals(self) -> None:
        start = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        first = Trade(start, start + dt.timedelta(hours=1), "MNQ", Side.LONG, 1, 0)
        overlapping = Trade(
            start + dt.timedelta(minutes=30),
            start + dt.timedelta(hours=2),
            "MNQ",
            Side.LONG,
            1,
            0,
        )
        touching = Trade(
            start + dt.timedelta(hours=1),
            start + dt.timedelta(hours=2),
            "MNQ",
            Side.LONG,
            1,
            0,
        )
        assert TradeLog([first, overlapping]).has_overlapping_trades
        assert not TradeLog([first, touching]).has_overlapping_trades

    def test_rejects_naive_datetimes(self) -> None:
        naive = dt.datetime(2026, 1, 5, 10, 0)
        with pytest.raises(QuantLabError, match="tz-aware"):
            Trade(naive, naive, "MNQ", Side.LONG, 1, 0.0)

    def test_rejects_exit_before_entry(self) -> None:
        t0 = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        with pytest.raises(QuantLabError, match="precedes"):
            Trade(t0, t0 - dt.timedelta(minutes=1), "MNQ", Side.LONG, 1, 0.0)

    def test_normalizes_to_utc(self) -> None:
        local = dt.datetime(2026, 1, 5, 9, 0, tzinfo=CT)  # 15:00 UTC in January
        trade = _trade(local)
        assert trade.exit_time.tzinfo == dt.UTC
        assert trade.exit_time.hour == 15
        assert trade.exit_time == local  # same instant

    def test_rejects_bad_quantity_and_excursions(self) -> None:
        t0 = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        with pytest.raises(QuantLabError, match="quantity"):
            Trade(t0, t0, "MNQ", Side.LONG, 0, 0.0)
        with pytest.raises(QuantLabError, match="mae"):
            Trade(t0, t0, "MNQ", Side.LONG, 1, 0.0, mae=5.0)
        with pytest.raises(QuantLabError, match="mfe"):
            Trade(t0, t0, "MNQ", Side.LONG, 1, 0.0, mfe=-5.0)

    @pytest.mark.parametrize("field", ["quantity", "pnl", "fees", "mae", "mfe"])
    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_rejects_nonfinite_numbers(self, field: str, value: float) -> None:
        t0 = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        values = {"quantity": 1.0, "pnl": 0.0, "fees": 0.0, "mae": None, "mfe": None}
        values[field] = value
        with pytest.raises(QuantLabError, match=field):
            Trade(t0, t0, "MNQ", Side.LONG, **values)

    @pytest.mark.parametrize("field", ["quantity", "pnl", "fees", "mae", "mfe"])
    @pytest.mark.parametrize("value", [True, "1.0"])
    def test_rejects_non_numeric_and_boolean_numbers(self, field: str, value) -> None:
        t0 = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        values = {"quantity": 1.0, "pnl": 0.0, "fees": 0.0, "mae": None, "mfe": None}
        values[field] = value
        with pytest.raises(QuantLabError, match=field):
            Trade(t0, t0, "MNQ", Side.LONG, **values)

    def test_rejects_blank_symbol_and_invalid_side(self) -> None:
        t0 = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        with pytest.raises(QuantLabError, match="symbol"):
            Trade(t0, t0, " ", Side.LONG, 1, 0.0)
        with pytest.raises(QuantLabError, match="side"):
            Trade(t0, t0, "MNQ", "flat", 1, 0.0)  # type: ignore[arg-type]


class TestDayBoundary:
    def test_rejects_bad_configuration(self) -> None:
        from quantlab.schema.trade import DayBoundary

        with pytest.raises(QuantLabError, match=r"0\.\.23"):
            DayBoundary("UTC", 24)
        with pytest.raises(QuantLabError, match=r"0\.\.23"):
            DayBoundary("UTC", True)
        with pytest.raises(QuantLabError, match="timezone"):
            DayBoundary("Not/A_Zone", 0)

    def test_futures_roll_at_5pm_chicago(self) -> None:
        # 16:00 CT Monday -> Monday's session; 18:00 CT Monday -> Tuesday's session
        monday = dt.date(2026, 1, 5)
        before = dt.datetime.combine(monday, dt.time(16, 0), tzinfo=CT)
        after = dt.datetime.combine(monday, dt.time(18, 0), tzinfo=CT)
        assert FUTURES_DAY.session_date(before) == monday
        assert FUTURES_DAY.session_date(after) == monday + dt.timedelta(days=1)

    def test_ftmo_midnight_prague(self) -> None:
        prague = ZoneInfo("Europe/Prague")
        stamp = dt.datetime(2026, 1, 5, 23, 30, tzinfo=prague)
        assert FTMO_DAY.session_date(stamp) == dt.date(2026, 1, 5)
        assert FTMO_DAY.session_date(stamp + dt.timedelta(hours=1)) == dt.date(2026, 1, 6)

    def test_daily_groups_ordering(self) -> None:
        log = trades_from_daily([[10, -5], [20], [-30, 40, 5]])
        groups = log.daily_groups()
        assert [len(trades) for _, trades in groups] == [2, 1, 3]
        assert [sum(t.pnl for t in trades) for _, trades in groups] == [5, 20, 15]


class TestTradeLog:
    def test_sorts_by_exit_time(self) -> None:
        t1 = _trade(dt.datetime(2026, 1, 6, 15, 0, tzinfo=UTC))
        t2 = _trade(dt.datetime(2026, 1, 5, 15, 0, tzinfo=UTC))
        log = TradeLog(trades=[t1, t2])
        assert log.trades[0] is t2

    def test_has_excursions(self) -> None:
        assert trades_from_daily([[10]], with_excursions=True).has_excursions
        assert not trades_from_daily([[10]]).has_excursions

    @pytest.mark.parametrize("trades", ["bad", [object()]])
    def test_rejects_non_trade_collections(self, trades) -> None:
        with pytest.raises(QuantLabError, match="list of Trade"):
            TradeLog(trades)  # type: ignore[arg-type]


class TestEquityCurve:
    def test_from_series_and_daily(self) -> None:
        import pandas as pd

        times = [
            dt.datetime(2026, 1, 5, 15, 0, tzinfo=UTC),
            dt.datetime(2026, 1, 5, 16, 0, tzinfo=UTC),
            dt.datetime(2026, 1, 6, 15, 0, tzinfo=UTC),
        ]
        curve = EquityCurve.from_series(pd.Series([1_100.0, 1_050.0, 1_250.0], index=times))
        assert [p.equity for p in curve.points] == [1_100.0, 1_050.0, 1_250.0]
        daily = curve.daily()
        assert list(daily.values) == [1_050.0, 1_250.0]

    def test_rejects_naive_and_nonfinite_points(self) -> None:
        with pytest.raises(QuantLabError, match="timezone-aware"):
            EquityPoint(dt.datetime(2026, 1, 5), 1.0)
        with pytest.raises(QuantLabError, match="finite"):
            EquityPoint(dt.datetime(2026, 1, 5, tzinfo=UTC), float("nan"))
        with pytest.raises(QuantLabError, match="datetime"):
            EquityPoint("bad", 1.0)  # type: ignore[arg-type]
        with pytest.raises(QuantLabError, match="finite real"):
            EquityPoint(dt.datetime(2026, 1, 5, tzinfo=UTC), True)
        with pytest.raises(QuantLabError, match="finite real"):
            EquityPoint(dt.datetime(2026, 1, 5, tzinfo=UTC), "1.0")  # type: ignore[arg-type]


class TestParquetRoundTrip:
    def test_round_trip_preserves_everything(self, tmp_path) -> None:
        log = trades_from_daily([[100.5, -37.25], [12.0]], with_excursions=True)
        log.account_currency = "EUR"
        path = tmp_path / "trades.parquet"
        write_trade_log(log, path)
        loaded = read_trade_log(path)
        assert loaded.account_currency == "EUR"
        assert len(loaded) == 3
        assert [t.pnl for t in loaded.trades] == [t.pnl for t in log.trades]
        assert loaded.has_excursions
        assert loaded.trades[0].exit_time == log.trades[0].exit_time

    def test_missing_file_raises(self, tmp_path) -> None:
        with pytest.raises(QuantLabError, match="not found"):
            read_trade_log(tmp_path / "nope.parquet")

    def test_write_failure_is_domain_error_and_does_not_leave_temp(self, tmp_path) -> None:
        # Missing parents are auto-created, so the surviving failure mode is
        # a target occupied by a directory: replace() fails after the temp
        # write, which must surface as a domain error and clean the temp up.
        target = tmp_path / "log.parquet"
        target.mkdir()
        with pytest.raises(QuantLabError, match="Could not write trade log"):
            write_trade_log(trades_from_daily([[10.0]]), target)
        assert not list(tmp_path.glob(".*.tmp"))

    def test_missing_parent_dirs_are_created(self, tmp_path) -> None:
        path = tmp_path / "missing" / "log.parquet"
        write_trade_log(trades_from_daily([[10.0]]), path)
        assert read_trade_log(path).trades[0].pnl == 10.0

    def test_future_schema_version_rejected(self, tmp_path, monkeypatch) -> None:
        import quantlab.schema.io as io_mod

        log = trades_from_daily([[10.0]])
        path = tmp_path / "trades.parquet"
        monkeypatch.setattr(io_mod, "SCHEMA_VERSION", 99)
        write_trade_log(log, path)
        monkeypatch.undo()
        with pytest.raises(QuantLabError, match="schema v99"):
            read_trade_log(path)

    @pytest.mark.parametrize("version", [True, 1.5, 0, -1, "1"])
    def test_invalid_schema_versions_are_not_coerced(self, tmp_path, version) -> None:
        import json

        import pyarrow.parquet as pq

        from quantlab.schema import io as schema_io

        path = tmp_path / "trades.parquet"
        write_trade_log(trades_from_daily([[10.0]]), path)
        table = pq.read_table(path)
        metadata = dict(table.schema.metadata or {})
        payload = json.loads(metadata[schema_io._META_KEY].decode())
        payload["schema_version"] = version
        metadata[schema_io._META_KEY] = json.dumps(payload).encode()
        pq.write_table(table.replace_schema_metadata(metadata), path)
        with pytest.raises(QuantLabError, match=r"unreadable.*schema_version"):
            read_trade_log(path)
