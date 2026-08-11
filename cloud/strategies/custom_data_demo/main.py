# region imports
from datetime import datetime, timedelta
from math import isfinite

from AlgorithmImports import *  # noqa: F403

# endregion

# The Object Store key written by:
#   quant ingest ohlcv your_bars.csv --symbol demo --upload
OBJECT_STORE_KEY = "quantlab/demo.csv"
TRADE_SYMBOL = "SPY"


class ObjectStoreBars(PythonData):  # noqa: F405
    """Reads quantlab-normalized OHLCV CSV from the QC Cloud Object Store.

    Canonical line format (UTC): datetime,open,high,low,close,volume
    This is the officially documented cloud custom-data pattern:
    SubscriptionDataSource(key, SubscriptionTransportMedium.OBJECT_STORE).
    """

    def get_source(self, config, date, is_live):
        return SubscriptionDataSource(  # noqa: F405
            OBJECT_STORE_KEY,
            SubscriptionTransportMedium.OBJECT_STORE,  # noqa: F405
            FileFormat.CSV,  # noqa: F405
        )

    def reader(self, config, line, date, is_live):
        if not line or line[0].isalpha():  # skip the header row
            return None
        try:
            parts = line.split(",")
            if len(parts) < 5:
                return None
            open_, high, low, close = (float(value) for value in parts[1:5])
            volume = float(parts[5]) if len(parts) > 5 else 0.0
            values = (open_, high, low, close, volume)
            if not all(isfinite(value) for value in values):
                return None
            if (
                any(value <= 0 for value in (open_, high, low, close))
                or high < max(open_, close)
                or low > min(open_, close)
                or volume < 0
            ):
                return None
            stamp = datetime.strptime(parts[0], "%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, IndexError):
            return None
        bar = ObjectStoreBars()
        bar.symbol = config.symbol
        bar.time = stamp
        bar.end_time = stamp + timedelta(minutes=1)
        bar.value = close
        bar["open"] = open_
        bar["high"] = high
        bar["low"] = low
        bar["close"] = close
        bar["volume"] = volume
        return bar


class CustomDataDemo(QCAlgorithm):  # noqa: F405
    """SMA signal from Object Store bars, executed through liquid SPY."""

    def initialize(self):
        self.set_start_date(2026, 1, 1)
        self.set_end_date(2026, 6, 30)
        self.set_cash(100_000)
        self.set_time_zone(TimeZones.UTC)  # noqa: F405
        self._symbol = self.add_data(ObjectStoreBars, "DEMO", Resolution.MINUTE).symbol  # noqa: F405
        self._trade_symbol = self.add_equity(TRADE_SYMBOL, Resolution.MINUTE).symbol  # noqa: F405
        self._fast = self.sma(self._symbol, 20)
        self._slow = self.sma(self._symbol, 60)
        self.set_warm_up(60, Resolution.MINUTE)  # noqa: F405

    def on_data(self, slice_):
        if self._symbol not in slice_ or self.is_warming_up or not self._slow.is_ready:
            return
        security = self.securities[self._trade_symbol]
        if not security.is_tradable or not security.exchange.hours.is_open(
            self.time, extended_market_hours=False
        ):
            return
        if self.transactions.get_open_orders(self._trade_symbol):
            return
        holdings = self.portfolio[self._trade_symbol].quantity
        if holdings < 0:
            self.liquidate(self._trade_symbol)
            return
        if self._fast.current.value > self._slow.current.value and holdings == 0:
            self.set_holdings(self._trade_symbol, 0.5)
        elif self._fast.current.value < self._slow.current.value and holdings > 0:
            self.liquidate(self._trade_symbol)
