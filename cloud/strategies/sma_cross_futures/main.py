# region imports
from datetime import time

from AlgorithmImports import *  # noqa: F403

# endregion


class SmaCrossFutures(QCAlgorithm):  # noqa: F405
    """SMA crossover on continuous ES futures (QC built-in data).

    Push + run with:
        quant cloud backtest cloud/strategies/sma_cross_futures --push
    then pull trades for the prop-firm simulator with `quant cloud results`.
    """

    def initialize(self):
        self.set_start_date(2024, 1, 1)
        self.set_end_date(2025, 12, 31)
        self.set_cash(100_000)
        self.set_time_zone(TimeZones.CHICAGO)  # noqa: F405

        future = self.add_future(
            Futures.Indices.SP_500_E_MINI,  # noqa: F405
            Resolution.MINUTE,  # noqa: F405
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,  # noqa: F405
            data_mapping_mode=DataMappingMode.OPEN_INTEREST,  # noqa: F405
            contract_depth_offset=0,
        )
        future.set_filter(0, 90)
        self._continuous = future.symbol
        self._fast = self.sma(self._continuous, 20, Resolution.MINUTE)  # noqa: F405
        self._slow = self.sma(self._continuous, 60, Resolution.MINUTE)  # noqa: F405
        self._contract = None
        self._retiring_contracts = set()
        self._flatten_tickets = {}
        self._startup_reconciled = False
        self._entry_locked_date = None
        self.schedule.on(
            self.date_rules.every_day(self._continuous),
            self.time_rules.before_market_close(self._continuous, 15),
            self._scheduled_flatten,
        )
        self.set_warm_up(60, Resolution.MINUTE)  # noqa: F405

    def on_data(self, slice_):
        changed = slice_.symbol_changed_events.get(self._continuous)
        if changed is not None:
            old_contract = changed.old_symbol
            self._retiring_contracts.add(old_contract)
            self._contract = changed.new_symbol
            self._reconcile_retiring("continuous-future rollover")
            return

        mapped = self.securities[self._continuous].mapped
        if mapped is None:
            return
        self._contract = mapped
        if not self._startup_reconciled:
            self._reconcile_startup(mapped)
        if self._retiring_contracts:
            self._reconcile_retiring("pending contract flatten")
            return
        if self._entries_locked():
            return
        if self.is_warming_up:
            return
        if mapped not in self.securities:
            return
        security = self.securities[mapped]
        if not security.is_tradable or security.price <= 0:
            return
        if not (self._fast.is_ready and self._slow.is_ready):
            return

        # Trade only 08:45-15:45 CT; flatten at/after 15:45 (time-object
        # comparisons — a naive `hour >= 15 and minute >= 45` check would
        # leak evening-session bars like 16:10 into the order logic).
        bar_time = self.time.time()
        session_start = time(8, 45)
        session_end = time(15, 45)
        if bar_time >= session_end:
            self._entry_locked_date = self.time.date()
            self._retiring_contracts.add(mapped)
            self._reconcile_retiring("scheduled session flatten")
            return
        if bar_time < session_start:
            return

        holdings = self.portfolio[mapped].quantity if mapped in self.portfolio else 0
        if self.transactions.get_open_orders(mapped):
            return
        # Never open the new mapped contract while the old rollover
        # liquidation is still unresolved.
        if self.portfolio.invested and holdings == 0:
            return
        if self._fast.current.value > self._slow.current.value and holdings <= 0:
            self.market_order(mapped, 1 - holdings)
        elif self._fast.current.value < self._slow.current.value and holdings >= 0:
            self.market_order(mapped, -1 - holdings)

    def _reconcile_startup(self, mapped):
        """Discover pre-restart exposure/orders and retire every stale contract."""
        for security in self.securities.values():
            symbol = security.symbol
            if symbol not in (self._continuous, mapped) and self.portfolio[symbol].invested:
                self._retiring_contracts.add(symbol)
        for order in self.transactions.get_open_orders():
            if order.symbol not in (self._continuous, mapped):
                self._retiring_contracts.add(order.symbol)
        self._startup_reconciled = True

    def _scheduled_flatten(self):
        """Calendar-aware close guard, including shortened exchange sessions."""
        self._entry_locked_date = self.time.date()
        mapped = self.securities[self._continuous].mapped
        if mapped is None:
            return
        self._contract = mapped
        self._retiring_contracts.add(mapped)
        self._reconcile_retiring("scheduled session flatten")

    def _entries_locked(self):
        """Keep the strategy flat after its close event until the next date."""
        if self._entry_locked_date is None:
            return False
        if self.time.date() != self._entry_locked_date:
            self._entry_locked_date = None
            return False
        return True

    def _reconcile_retiring(self, tag):
        """Cancel stale orders, then flatten; retry until orders and holdings are zero."""
        for symbol in list(self._retiring_contracts):
            flatten = self._flatten_tickets.get(symbol)
            flatten_id = flatten.order_id if flatten is not None else None
            open_orders = list(self.transactions.get_open_orders(symbol))
            for order in open_orders:
                if order.id != flatten_id:
                    self.transactions.cancel_order(order.id, tag="cancel before contract flatten")
            if any(order.id != flatten_id for order in open_orders):
                continue  # cancellation is asynchronous
            quantity = self.portfolio[symbol].quantity
            if quantity == 0:
                if not open_orders:
                    self._retiring_contracts.discard(symbol)
                    self._flatten_tickets.pop(symbol, None)
                continue
            if flatten_id is not None and any(order.id == flatten_id for order in open_orders):
                continue
            self._flatten_tickets[symbol] = self.market_order(
                symbol, -quantity, asynchronous=True, tag=tag
            )

    def on_order_event(self, order_event):
        # Invalid/canceled flatten orders are retried on the next data event.
        for symbol, ticket in list(self._flatten_tickets.items()):
            if order_event.order_id == ticket.order_id and order_event.status in (
                OrderStatus.INVALID,  # noqa: F405
                OrderStatus.CANCELED,  # noqa: F405
            ):
                self._flatten_tickets.pop(symbol, None)
