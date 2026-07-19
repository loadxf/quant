# region imports
from AlgorithmImports import *  # noqa: F403

# endregion


class OpeningRangeBreakoutEquity(QCAlgorithm):  # noqa: F405
    """Opening-range breakout on SPY (QC built-in equity data).

    The low-RR/high-win-rate style discussed in the QuantPad methodology
    videos: enter on a break of the first 15 minutes' range, fixed
    stop/target brackets, flat by the close.
    """

    def initialize(self):
        self.set_start_date(2024, 1, 1)
        self.set_end_date(2025, 12, 31)
        self.set_cash(100_000)
        self._spy = self.add_equity("SPY", Resolution.MINUTE).symbol  # noqa: F405
        self._range_high = None
        self._range_low = None
        self._traded_today = False
        self.schedule.on(
            self.date_rules.every_day(self._spy),
            self.time_rules.after_market_open(self._spy, 0),
            self._reset_day,
        )
        self.schedule.on(
            self.date_rules.every_day(self._spy),
            self.time_rules.before_market_close(self._spy, 5),
            lambda: self.liquidate(),
        )

    def _reset_day(self):
        self._range_high = None
        self._range_low = None
        self._traded_today = False

    def on_data(self, slice_):
        bar = slice_.bars.get(self._spy)
        if bar is None:
            return
        minutes_in = (self.time - self.time.replace(hour=8, minute=30)).seconds // 60

        if minutes_in <= 15:
            self._range_high = max(self._range_high or bar.high, bar.high)
            self._range_low = min(self._range_low or bar.low, bar.low)
            return
        if self._traded_today or self._range_high is None or self.portfolio.invested:
            return

        range_size = self._range_high - self._range_low
        if range_size <= 0:
            return
        if bar.close > self._range_high:
            self._traded_today = True
            quantity = self.calculate_order_quantity(self._spy, 0.95)
            self.market_order(self._spy, quantity)
            self.stop_market_order(self._spy, -quantity, bar.close - 0.5 * range_size)
            self.limit_order(self._spy, -quantity, bar.close + 0.5 * range_size)
