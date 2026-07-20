# region imports
from AlgorithmImports import *  # noqa: F403

# endregion


class OpeningRangeBreakoutEquity(QCAlgorithm):  # noqa: F405
    """Opening-range breakout on SPY (QC built-in equity data).

    The low-RR/high-win-rate style discussed in the QuantPad methodology
    videos: enter on a break of the first 15 minutes' range, fixed
    stop/target brackets, flat by the close.

    Implementation notes (verified against LEAN semantics):
    - The range window counts BARS after the market open (scheduled reset
      fires before the first RTH bar) — never wall-clock arithmetic, which
      breaks across timezones/DST.
    - LEAN has no OCO orders: when one bracket leg fills, on_order_event
      cancels the sibling, otherwise the leftover order can flip the book.
    """

    RANGE_BARS = 15  # first 15 one-minute bars form the range

    def initialize(self):
        self.set_start_date(2024, 1, 1)
        self.set_end_date(2025, 12, 31)
        self.set_cash(100_000)
        self._spy = self.add_equity("SPY", Resolution.MINUTE).symbol  # noqa: F405
        self._range_high = None
        self._range_low = None
        self._bars_seen = 0
        self._traded_today = False
        self._exit_tickets = []
        self.schedule.on(
            self.date_rules.every_day(self._spy),
            self.time_rules.after_market_open(self._spy, 0),
            self._reset_day,
        )
        self.schedule.on(
            self.date_rules.every_day(self._spy),
            self.time_rules.before_market_close(self._spy, 5),
            self._flatten,
        )

    def _reset_day(self):
        self._range_high = None
        self._range_low = None
        self._bars_seen = 0
        self._traded_today = False

    def _flatten(self):
        self._cancel_exits()
        self.liquidate()

    def _cancel_exits(self):
        for ticket in self._exit_tickets:
            if ticket.status not in (OrderStatus.FILLED, OrderStatus.CANCELED):  # noqa: F405
                ticket.cancel()
        self._exit_tickets = []

    def on_order_event(self, order_event):
        # Manual OCO: one exit leg filling cancels the other.
        if order_event.status != OrderStatus.FILLED:  # noqa: F405
            return
        if any(t.order_id == order_event.order_id for t in self._exit_tickets):
            self._cancel_exits()
        # No true OCO in LEAN: a single wide bar can fill BOTH bracket legs
        # in one time slice (cancel arrives too late for an already-filled
        # sibling), flipping this long-only book short. The second fill's
        # event lands after the ticket list is cleared, so catch the
        # inversion here and flatten immediately.
        if not self._exit_tickets and self.portfolio[self._spy].quantity < 0:
            self.liquidate(self._spy)

    def on_data(self, slice_):
        bar = slice_.bars.get(self._spy)
        if bar is None:
            return
        self._bars_seen += 1

        if self._bars_seen <= self.RANGE_BARS:
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
            self._exit_tickets = [
                self.stop_market_order(self._spy, -quantity, bar.close - 0.5 * range_size),
                self.limit_order(self._spy, -quantity, bar.close + 0.5 * range_size),
            ]
