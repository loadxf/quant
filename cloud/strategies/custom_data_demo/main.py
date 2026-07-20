# region imports
from AlgorithmImports import *  # noqa: F403

# endregion

# The Object Store key written by:
#   quant ingest ohlcv your_bars.csv --symbol demo --upload
OBJECT_STORE_KEY = "quantlab/demo.csv"


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
        parts = line.split(",")
        if len(parts) < 5:
            return None
        bar = ObjectStoreBars()
        bar.symbol = config.symbol
        bar.time = datetime.strptime(parts[0], "%Y-%m-%dT%H:%M:%SZ")  # noqa: F405
        bar.value = float(parts[4])
        bar["open"] = float(parts[1])
        bar["high"] = float(parts[2])
        bar["low"] = float(parts[3])
        bar["close"] = float(parts[4])
        bar["volume"] = float(parts[5]) if len(parts) > 5 else 0.0
        return bar


class CustomDataDemo(QCAlgorithm):  # noqa: F405
    """SMA cross on user-supplied bars uploaded to the Object Store."""

    def initialize(self):
        self.set_start_date(2026, 1, 1)
        self.set_end_date(2026, 6, 30)
        self.set_cash(100_000)
        self._symbol = self.add_data(ObjectStoreBars, "DEMO", Resolution.MINUTE).symbol  # noqa: F405
        self._fast = self.sma(self._symbol, 20)
        self._slow = self.sma(self._symbol, 60)

    def on_data(self, slice_):
        if self._symbol not in slice_ or not self._slow.is_ready:
            return
        holdings = self.portfolio[self._symbol].quantity
        if self._fast.current.value > self._slow.current.value and holdings <= 0:
            self.set_holdings(self._symbol, 0.5)
        elif self._fast.current.value < self._slow.current.value and holdings > 0:
            self.liquidate(self._symbol)
