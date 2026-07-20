from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from quantlab.errors import QuantLabError
from quantlab.qc.results import load_result_file, parse_closed_trades, parse_equity_chart
from quantlab.schema.trade import Side

FIXTURE = Path(__file__).parent / "fixtures" / "backtest_result_sample.json"


class TestParseClosedTrades:
    def test_parses_fixture(self) -> None:
        backtest = load_result_file(FIXTURE)
        log, skipped = parse_closed_trades(backtest)
        assert len(log) == 3
        assert skipped == []
        assert log.source == "lean-cloud"
        assert log.has_excursions

        first = log.trades[0]
        assert first.symbol == "ES"  # dict-style symbol unwrapped
        assert first.side == Side.LONG
        # LEAN profitLoss is GROSS; canonical pnl is net of totalFees.
        assert first.pnl == 675.0 - 4.3
        assert first.fees == 4.3
        assert first.mae == -212.5 and first.mfe == 750.0
        assert first.entry_time == dt.datetime(2026, 1, 5, 9, 31, tzinfo=dt.UTC)

        short = log.trades[1]
        assert short.side == Side.SHORT
        assert short.quantity == 2
        assert short.pnl == -550.0 - 8.6

        spy = log.trades[2]
        assert spy.symbol == "SPY"  # plain-string symbol
        assert spy.exit_time.tzinfo == dt.UTC

    def test_malformed_trade_skipped_not_fatal(self) -> None:
        backtest = load_result_file(FIXTURE)
        bad = dict(backtest["totalPerformance"]["closedTrades"][0])
        bad["exitTime"] = "2026-01-04T09:00:00"  # exit before entry -> invalid
        backtest["totalPerformance"]["closedTrades"].append(bad)
        log, skipped = parse_closed_trades(backtest)
        assert len(log) == 3
        assert len(skipped) == 1
        assert "closedTrades[3]" in skipped[0]

    def test_empty_trades_raises(self) -> None:
        with pytest.raises(QuantLabError, match="closedTrades"):
            parse_closed_trades({"totalPerformance": {"closedTrades": []}})


class TestParseEquityChart:
    def test_candle_values(self) -> None:
        chart = {
            "name": "Strategy Equity",
            "series": {
                "Equity": {
                    "values": [
                        [1767600000, 100000, 100500, 99800, 100200],
                        [1767686400, 100200, 100900, 100100, 100750],
                    ]
                }
            },
        }
        curve = parse_equity_chart(chart)
        assert [p.equity for p in curve.points] == [100200.0, 100750.0]

    def test_pair_and_dict_values(self) -> None:
        chart = {
            "series": {
                "Equity": {"values": [[1767600000, 100000.0], {"x": 1767686400, "y": 100500.0}]}
            }
        }
        curve = parse_equity_chart(chart)
        assert [p.equity for p in curve.points] == [100000.0, 100500.0]

    def test_empty_raises(self) -> None:
        with pytest.raises(QuantLabError, match="no series"):
            parse_equity_chart({"name": "x", "series": {}})
