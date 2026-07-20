from __future__ import annotations

import pytest

from quantlab.metrics.core import compute_metrics

from ..conftest import random_log, trades_from_daily


class TestComputeMetrics:
    def test_hand_computed_basics(self) -> None:
        # Days: [+100, -50], [+200], [-30, +40, +5] -> net 265
        log = trades_from_daily([[100, -50], [200], [-30, 40, 5]])
        m = compute_metrics(log, starting_equity=10_000)

        assert m.trade_count == 6
        assert m.net_profit == pytest.approx(265.0)
        assert m.win_rate == pytest.approx(4 / 6)
        assert m.avg_win == pytest.approx((100 + 200 + 40 + 5) / 4)
        assert m.avg_loss == pytest.approx((-50 - 30) / 2)
        assert m.profit_factor == pytest.approx(345 / 80)
        assert m.trading_days == 3
        assert m.best_day == pytest.approx(200.0)
        assert m.best_day_share == pytest.approx(200 / 265)
        # equity path: 10100, 10050, 10250, 10220, 10260, 10265 -> max DD = 50
        assert m.max_drawdown == pytest.approx(50.0)
        assert m.longest_losing_streak == 1

    def test_losing_streak_and_expectancy_sign(self) -> None:
        log = trades_from_daily([[-10, -20, -30], [5], [-1, -1]])
        m = compute_metrics(log, starting_equity=1_000)
        assert m.longest_losing_streak == 3
        assert m.expectancy < 0
        assert m.expectancy_ci95[0] < m.expectancy_ci95[1]

    def test_winner_has_positive_sharpe_and_tstat(self, winner_log) -> None:
        m = compute_metrics(winner_log, starting_equity=50_000)
        assert m.sharpe > 1.0
        assert m.expectancy_tstat > 2.0
        assert 0 < m.max_drawdown_pct < 1

    def test_loser_mirrors(self, loser_log) -> None:
        m = compute_metrics(loser_log, starting_equity=50_000)
        assert m.net_profit < 0
        assert m.sharpe < 0
        assert m.best_day_share == 0.0  # undefined for net-negative, reported as 0

    def test_deterministic_ci(self) -> None:
        log = random_log(n_days=30, seed=9)
        a = compute_metrics(log)
        b = compute_metrics(log)
        assert a.expectancy_ci95 == b.expectancy_ci95

    def test_single_trade_edge_case(self) -> None:
        log = trades_from_daily([[50]])
        m = compute_metrics(log)
        assert m.trade_count == 1
        assert m.profit_factor == float("inf")
        assert m.payoff_ratio == float("inf")  # no losses -> inf, matching profit_factor
        assert m.expectancy_r == float("inf")
        assert m.sharpe == 0.0  # <2 daily points -> no ratio

    def test_rejects_nonpositive_equity(self) -> None:
        from quantlab.errors import QuantLabError

        log = trades_from_daily([[50]])
        with pytest.raises(QuantLabError, match="starting_equity"):
            compute_metrics(log, starting_equity=0)
