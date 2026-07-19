# region imports
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
        self.set_warm_up(60, Resolution.MINUTE)  # noqa: F405

    def on_data(self, slice_):
        mapped = self.securities[self._continuous].mapped
        if mapped is None or self.is_warming_up:
            return
        if not (self._fast.is_ready and self._slow.is_ready):
            return

        # Trade only 08:45-15:45 CT; flatten at/after 15:45 (time-object
        # comparisons — a naive `hour >= 15 and minute >= 45` check would
        # leak evening-session bars like 16:10 into the order logic).
        bar_time = self.time.time()
        session_start = time(8, 45)  # noqa: F405
        session_end = time(15, 45)  # noqa: F405
        if bar_time >= session_end:
            if self.portfolio.invested:
                self.liquidate()
            return
        if bar_time < session_start:
            return

        holdings = self.portfolio[mapped].quantity if mapped in self.portfolio else 0
        if self._fast.current.value > self._slow.current.value and holdings <= 0:
            self.market_order(mapped, 1 - holdings)
        elif self._fast.current.value < self._slow.current.value and holdings >= 0:
            self.market_order(mapped, -1 - holdings)
