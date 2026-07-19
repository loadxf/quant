from __future__ import annotations

from quantlab.metrics.core import compute_metrics
from quantlab.metrics.overfit import overfit_flags

from ..conftest import random_log, trades_from_daily


def _flags(log):
    m = compute_metrics(log)
    return {f.name: f for f in overfit_flags(log, m)}


class TestOverfitFlags:
    def test_smooth_curve_triggers_on_linear_equity(self) -> None:
        log = trades_from_daily([[50.0, 50.0]] * 50)  # 100 perfectly even trades
        flags = _flags(log)
        assert flags["suspiciously_smooth_equity"].triggered

    def test_smooth_curve_ok_for_noisy_or_large(self) -> None:
        noisy = random_log(n_days=60, mean=30, std=200, seed=31)
        assert not _flags(noisy)["suspiciously_smooth_equity"].triggered
        big_smooth = trades_from_daily([[50.0, 50.0]] * 150)  # n=300 >= 200
        assert not _flags(big_smooth)["suspiciously_smooth_equity"].triggered

    def test_zero_crossing(self) -> None:
        zero = random_log(n_days=100, mean=0.0, std=200.0, seed=32)
        assert _flags(zero)["expectancy_ci_straddles_zero"].triggered
        strong = random_log(n_days=100, mean=80.0, std=100.0, seed=33)
        assert not _flags(strong)["expectancy_ci_straddles_zero"].triggered

    def test_top5_concentration(self) -> None:
        # 95 tiny trades + 5 huge winners carrying nearly all profit
        daily = [[2.0]] * 95 + [[900.0]] * 5
        log = trades_from_daily(daily)
        assert _flags(log)["top5_trade_concentration"].triggered

    def test_breakeven_frontier(self) -> None:
        # exact win rate .5, payoff exactly 1.0 -> |0.5*2 - 1| = 0
        daily = [[100.0, -100.0, 100.0, -100.0] for _ in range(50)]
        log = trades_from_daily(daily)
        assert _flags(log)["hugging_breakeven_frontier"].triggered

    def test_symbol_month_dependency(self) -> None:
        # profit concentrated in one month, losses elsewhere: >50% of net
        daily = [[400.0, 300.0]] * 21 + [[-2.0, 1.0]] * 60
        log = trades_from_daily(daily)
        flags = _flags(log)
        assert flags["single_symbol_month_dependency"].triggered
