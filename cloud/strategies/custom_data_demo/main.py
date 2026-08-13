# region imports
import json
from datetime import datetime, timedelta
from math import isfinite

from AlgorithmImports import *  # noqa: F403

# endregion

# The Object Store key written by:
#   quant ingest ohlcv your_bars.csv --symbol demo --upload
# or uploaded by hand in the web IDE's Object Store panel (no API needed).
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
        self._quantlab_start_export()

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

    # --- quantlab export: API-free results retrieval ---------------------
    # Saves closed trades (with MAE/MFE) plus hourly equity marks to the
    # Object Store in the same JSON shape as the REST backtests/read
    # response. After the backtest, download the file in the web IDE
    # (Organization > Object Store) and run
    #   quant cloud results --from-json <downloaded file> -o trades.parquet
    # No API access or lean CLI needed - works on every account tier. To
    # instrument your own algorithm, copy these four methods plus the
    # _quantlab_start_export() call at the end of initialize().

    def _quantlab_start_export(self):
        self._quantlab_equity_marks = []
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.every(timedelta(minutes=60)),
            self._quantlab_sample_equity,
        )

    def _quantlab_sample_equity(self):
        self._quantlab_equity_marks.append(
            [
                self.utc_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                float(self.portfolio.total_portfolio_value),
            ]
        )

    def on_end_of_algorithm(self):
        self._quantlab_export()

    def _quantlab_export(self):
        trades = []
        for closed in self.trade_builder.closed_trades:
            symbol = getattr(closed, "symbol", None)
            if symbol is None:  # newer LEAN builds group symbols in a list
                grouped = list(getattr(closed, "symbols", None) or [])
                symbol = grouped[0] if grouped else None
            trades.append(
                {
                    "symbol": {"value": str(getattr(symbol, "value", symbol))},
                    "entryTime": closed.entry_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "entryPrice": float(closed.entry_price),
                    "exitTime": closed.exit_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "exitPrice": float(closed.exit_price),
                    "quantity": float(closed.quantity),
                    "direction": 1 if "short" in str(closed.direction).lower() else 0,
                    "profitLoss": float(closed.profit_loss),
                    "totalFees": float(closed.total_fees),
                    "mae": float(closed.mae),
                    "mfe": float(closed.mfe),
                }
            )
        payload = json.dumps(
            {
                "quantlabExport": 1,
                "algorithmId": str(self.algorithm_id),
                "totalPerformance": {"closedTrades": trades},
                "equityMarks": self._quantlab_equity_marks,
            }
        )
        key = "quantlab/results/" + str(self.algorithm_id) + ".json"
        try:
            # TradeBuilder times are fill.UtcTime, so the Z suffix above is
            # exact; Object Store writes from backtests are the documented
            # persistence pattern.
            self.object_store.save(key, payload)
        except Exception as error:  # quota/permissions must not fail the run
            self.log(
                "quantlab: Object Store save FAILED (" + str(error) + ") - "
                "free Object Store quota and re-run to export trades"
            )
            return
        self.log(
            "quantlab: exported " + str(len(trades)) + " closed trades to "
            "Object Store key " + key + " - download it and run: "
            "quant cloud results --from-json <downloaded file> -o trades.parquet"
        )
