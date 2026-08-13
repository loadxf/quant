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
        # A mid-session live deployment has missed the scheduled open reset
        # and must not build a fake opening range from midday bars. Only the
        # exchange-calendar reset below unlocks entries.
        self._traded_today = True
        self._entry_ticket = None
        self._entry_range_size = None
        self._exit_tickets = []
        self._flattening = False
        self._flatten_ticket = None
        self._startup_reconciled = False
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
        self._entry_ticket = None
        self._entry_range_size = None
        if self.portfolio[self._spy].invested or self.transactions.get_open_orders(self._spy):
            self._begin_flatten("new-session reconciliation")
        else:
            # A final-bar asynchronous flatten may have filled without a
            # later OnData call to clear its state. Do not sacrifice the
            # next session's first opening-range bar to stale bookkeeping.
            self._flattening = False
            self._flatten_ticket = None
            self._exit_tickets = []

    def _flatten(self):
        self._begin_flatten("scheduled end-of-day flatten")

    def _begin_flatten(self, tag):
        # Once a flatten is requested, no later bar in this session may open
        # another position. The next scheduled session reset owns the unlock.
        self._traded_today = True
        self._flattening = True
        self._cancel_exits()
        self._reconcile_flatten(tag)

    def _reconcile_flatten(self, tag="order-state reconciliation"):
        """Retry asynchronous cancel/flatten work until no order or position remains."""
        flatten_id = self._flatten_ticket.order_id if self._flatten_ticket is not None else None
        open_orders = list(self.transactions.get_open_orders(self._spy))
        for order in open_orders:
            if order.id != flatten_id:
                self.transactions.cancel_order(order.id, tag="cancel before flatten")
        if any(order.id != flatten_id for order in open_orders):
            return
        quantity = self.portfolio[self._spy].quantity
        if quantity == 0:
            if not open_orders:
                self._flattening = False
                self._flatten_ticket = None
            return
        if flatten_id is not None and any(order.id == flatten_id for order in open_orders):
            return
        self._flatten_ticket = self.market_order(self._spy, -quantity, asynchronous=True, tag=tag)

    def _cancel_exits(self, except_order_id=None):
        for ticket in self._exit_tickets:
            if (
                ticket.order_id != except_order_id
                and ticket.status not in (OrderStatus.FILLED, OrderStatus.CANCELED)  # noqa: F405
            ):
                ticket.cancel()
        self._exit_tickets = []

    def on_order_event(self, order_event):
        entry_id = self._entry_ticket.order_id if self._entry_ticket is not None else None
        if order_event.order_id == entry_id:
            if order_event.status in (
                OrderStatus.PARTIALLY_FILLED,  # noqa: F405
                OrderStatus.FILLED,  # noqa: F405
            ):
                self._sync_brackets()
            elif order_event.status == OrderStatus.INVALID:  # noqa: F405
                self._begin_flatten("entry rejected after partial fill")
            return

        flatten_id = self._flatten_ticket.order_id if self._flatten_ticket is not None else None
        if order_event.order_id == flatten_id:
            if order_event.status == OrderStatus.FILLED:  # noqa: F405
                self._flatten_ticket = None
                self._reconcile_flatten("flatten fill reconciliation")
            elif order_event.status in (
                OrderStatus.INVALID,  # noqa: F405
                OrderStatus.CANCELED,  # noqa: F405
            ):
                self._flatten_ticket = None
            return

        exit_ids = {ticket.order_id for ticket in self._exit_tickets}
        if order_event.order_id in exit_ids:
            if order_event.status == OrderStatus.PARTIALLY_FILLED:  # noqa: F405
                self._resize_sibling(order_event.order_id)
            elif order_event.status == OrderStatus.FILLED:  # noqa: F405
                self._cancel_exits(except_order_id=order_event.order_id)
                self._begin_flatten("bracket fill reconciliation")
            elif order_event.status in (
                OrderStatus.INVALID,  # noqa: F405
                OrderStatus.CANCELED,  # noqa: F405
            ):
                self._begin_flatten("protective order unavailable")

        # No true OCO in LEAN: a single wide bar can fill BOTH bracket legs
        # in one time slice (cancel arrives too late for an already-filled
        # sibling), flipping this long-only book short. The second fill's
        # event lands after the ticket list is cleared, so catch the
        # inversion here and flatten immediately.
        if not self._exit_tickets and self.portfolio[self._spy].quantity < 0:
            self._begin_flatten("bracket double-fill reconciliation")

    def _sync_brackets(self):
        holding = self.portfolio[self._spy]
        quantity = holding.quantity
        if quantity <= 0 or self._entry_range_size is None:
            return
        half_range = 0.5 * self._entry_range_size
        stop_price = holding.average_price - half_range
        limit_price = holding.average_price + half_range
        if not self._exit_tickets:
            stop = self.stop_market_order(self._spy, -quantity, stop_price, tag="ORB stop")
            self._exit_tickets.append(stop)
            if (
                stop.status
                in (
                    OrderStatus.FILLED,  # noqa: F405
                    OrderStatus.INVALID,  # noqa: F405
                    OrderStatus.CANCELED,  # noqa: F405
                )
                or self.portfolio[self._spy].quantity <= 0
            ):
                self._begin_flatten("stop resolved during bracket submission")
                return
            # A synchronous partial stop fill may have fired its event before
            # this ticket was appended. Size the sibling from live holdings,
            # not the stale pre-submit quantity.
            quantity = self.portfolio[self._spy].quantity
            target = self.limit_order(self._spy, -quantity, limit_price, tag="ORB target")
            self._exit_tickets.append(target)
            if (
                target.status
                in (
                    OrderStatus.FILLED,  # noqa: F405
                    OrderStatus.INVALID,  # noqa: F405
                    OrderStatus.CANCELED,  # noqa: F405
                )
                or self.portfolio[self._spy].quantity <= 0
            ):
                self._begin_flatten("target resolved during bracket submission")
            elif target.status == OrderStatus.PARTIALLY_FILLED:  # noqa: F405
                self._resize_sibling(target.order_id)
            return
        if len(self._exit_tickets) != 2:
            self._begin_flatten("incomplete protective bracket state")
            return
        responses = (
            self._exit_tickets[0].update_quantity(
                self._exit_tickets[0].quantity_filled - quantity,
                "resize after entry fill",
            ),
            self._exit_tickets[0].update_stop_price(stop_price, "re-anchor to average fill"),
            self._exit_tickets[1].update_quantity(
                self._exit_tickets[1].quantity_filled - quantity,
                "resize after entry fill",
            ),
            self._exit_tickets[1].update_limit_price(limit_price, "re-anchor to average fill"),
        )
        if not all(response.is_success for response in responses):
            self._begin_flatten("protective order update failed")

    def _resize_sibling(self, filled_order_id):
        remaining = self.portfolio[self._spy].quantity
        if remaining <= 0:
            self._cancel_exits(except_order_id=filled_order_id)
            self._begin_flatten("partial exit exhausted or inverted position")
            return
        for ticket in self._exit_tickets:
            if ticket.order_id != filled_order_id:
                response = ticket.update_quantity(
                    ticket.quantity_filled - remaining,
                    "resize OCO sibling after partial exit",
                )
                if not response.is_success:
                    self._begin_flatten("OCO sibling update failed")
                    return

    def on_data(self, slice_):
        if not self._startup_reconciled:
            self._startup_reconciled = True
            if self.portfolio[self._spy].invested or self.transactions.get_open_orders(self._spy):
                self._begin_flatten("algorithm restart reconciliation")
                return
        if self._flattening:
            self._reconcile_flatten()
            return
        bar = slice_.bars.get(self._spy)
        if bar is None:
            return
        self._bars_seen += 1

        if self._bars_seen <= self.RANGE_BARS:
            self._range_high = max(self._range_high or bar.high, bar.high)
            self._range_low = min(self._range_low or bar.low, bar.low)
            return
        if (
            self._traded_today
            or self._range_high is None
            or self.portfolio.invested
            or self.transactions.get_open_orders(self._spy)
        ):
            return

        range_size = self._range_high - self._range_low
        if range_size <= 0:
            return
        if bar.close > self._range_high:
            self._traded_today = True
            quantity = self.calculate_order_quantity(self._spy, 0.95)
            if quantity <= 0:
                return
            self._entry_range_size = range_size
            self._entry_ticket = self.market_order(self._spy, quantity, tag="ORB entry")
            # Market orders are synchronous by default. A fill event can run
            # before the returned ticket is assigned, so reconcile once more
            # after assignment; the helper is idempotent for unfilled orders.
            self._sync_brackets()
