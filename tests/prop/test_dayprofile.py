from __future__ import annotations

import numpy as np
import pytest

from quantlab.errors import QuantLabError
from quantlab.prop.dayprofile import DayProfile
from quantlab.schema.trade import FUTURES_DAY, TradeLog

from .conftest import day_trades


class TestDayProfile:
    def test_padded_arrays_hand_computed(self) -> None:
        # Day1: (+100, mae -30, mfe 120) then (-50, mae -60, mfe 10)
        # Day2: single (+40, mae -5, mfe 45)
        log = day_trades([[(100, -30, 120), (-50, -60, 10)], [(40, -5, 45)]])
        profile = DayProfile.from_log(log, FUTURES_DAY)
        assert profile.n_days == 2
        assert profile.max_trades == 2
        assert profile.n_trades.tolist() == [2, 1]

        # Trade 2 sits at cumulative base +100
        assert profile.high_rel[0].tolist() == [120.0, 110.0]
        assert profile.low_rel[0].tolist() == [-30.0, 40.0]
        assert profile.close_rel[0].tolist() == [100.0, 50.0]
        assert profile.day_pnl.tolist() == [50.0, 40.0]

        # Padding: no-op slots (low +inf never breaches, high -inf never
        # ratchets, close repeats the day's final cumulative)
        assert profile.low_rel[1, 1] == np.inf
        assert profile.high_rel[1, 1] == -np.inf
        assert profile.close_rel[1, 1] == 40.0

    def test_scaled(self) -> None:
        log = day_trades([[(100, -30, 120)]])
        profile = DayProfile.from_log(log, FUTURES_DAY)
        half = profile.scaled(0.5)
        assert half.day_pnl.tolist() == [50.0]
        assert half.low_rel[0, 0] == -15.0
        assert profile.scaled(1.0) is profile  # identity short-circuit

    def test_empty_log_raises(self) -> None:
        with pytest.raises(QuantLabError, match="no trading days"):
            DayProfile.from_log(TradeLog(trades=[]), FUTURES_DAY)
