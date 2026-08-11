"""Regression tests for the codebase-gaps audit (metrics side)."""

from __future__ import annotations

import datetime as dt

import pytest

from quantlab.metrics.core import compute_metrics
from quantlab.metrics.decay import compute_decay
from quantlab.metrics.drawdown_mc import permutation_drawdown
from quantlab.schema.trade import Side, Trade, TradeLog

UTC = dt.UTC


def _log_on_dates(dates: list[dt.date], pnl: float = 100.0) -> TradeLog:
    trades = [
        Trade(
            entry_time=dt.datetime.combine(d, dt.time(15, 0), tzinfo=UTC),
            exit_time=dt.datetime.combine(d, dt.time(16, 0), tzinfo=UTC),
            symbol="T",
            side=Side.LONG,
            quantity=1,
            pnl=pnl,
        )
        for d in dates
    ]
    return TradeLog(trades=trades)


class TestCalendarSpanAnnualization:
    def test_weekly_trader_not_inflated(self) -> None:
        """A once-a-week trader's MAR must annualize over the calendar
        span, not the 12 active days (which would inflate it ~5x)."""
        mondays = [dt.date(2026, 1, 5) + dt.timedelta(weeks=k) for k in range(12)]
        dense = [dt.date(2026, 1, 5) + dt.timedelta(days=k) for k in range(80) if
                 (dt.date(2026, 1, 5) + dt.timedelta(days=k)).weekday() < 5][:12]
        sparse_m = compute_metrics(_log_on_dates(mondays, pnl=100.0), starting_equity=50_000)
        dense_m = compute_metrics(_log_on_dates(dense, pnl=100.0), starting_equity=50_000)
        # Same trades, same PnL; the sparse log spans ~5x the calendar and
        # must show a ~5x smaller MAR, not the same one.
        assert sparse_m.mar == pytest.approx(dense_m.mar / 4.83, rel=0.15)

    def test_dense_all_winner_log_unchanged(self) -> None:
        """Consecutive-weekday logs: span == active days, so the change is
        a no-op for the common case (all-winner: zero DD -> MAR inf)."""
        dense = [dt.date(2026, 1, 5) + dt.timedelta(days=k) for k in range(28) if
                 (dt.date(2026, 1, 5) + dt.timedelta(days=k)).weekday() < 5]
        m = compute_metrics(_log_on_dates(dense), starting_equity=50_000)
        assert m.mar == float("inf")  # zero drawdown, positive return


class TestZeroVarianceSharpeSign:
    def test_constant_loser_is_negative_infinity(self) -> None:
        days = [dt.date(2026, 1, 5) + dt.timedelta(days=k) for k in range(10) if
                (dt.date(2026, 1, 5) + dt.timedelta(days=k)).weekday() < 5]
        m = compute_metrics(_log_on_dates(days, pnl=-100.0), starting_equity=50_000)
        assert m.sharpe == float("-inf")
        assert m.sortino < 0

    def test_constant_winner_stays_positive_infinity(self) -> None:
        days = [dt.date(2026, 1, 5) + dt.timedelta(days=k) for k in range(10) if
                (dt.date(2026, 1, 5) + dt.timedelta(days=k)).weekday() < 5]
        m = compute_metrics(_log_on_dates(days, pnl=100.0), starting_equity=50_000)
        assert m.sharpe == float("inf")


class TestSingleTradeDrawdown:
    def test_single_ruinous_trade_is_certain_ruin(self) -> None:
        log = _log_on_dates([dt.date(2026, 1, 5)], pnl=-6000.0)
        mc = permutation_drawdown(log, ruin_capital=5000.0)
        assert mc.p_ruin == 1.0
        assert mc.median_max_dd == pytest.approx(6000.0)

    def test_single_winning_trade_no_ruin(self) -> None:
        log = _log_on_dates([dt.date(2026, 1, 5)], pnl=500.0)
        mc = permutation_drawdown(log, ruin_capital=5000.0)
        assert mc.p_ruin == 0.0 and mc.median_max_dd == 0.0

    def test_empty_log_no_estimate(self) -> None:
        mc = permutation_drawdown(TradeLog(trades=[]), ruin_capital=5000.0)
        assert mc.p_ruin is None


class TestWfeReason:
    def _log(self, n: int = 30) -> TradeLog:
        days = []
        d = dt.date(2026, 1, 5)
        while len(days) < n:
            if d.weekday() < 5:
                days.append(d)
            d += dt.timedelta(days=1)
        return _log_on_dates(days, pnl=50.0)

    def test_boundary_outside_log_gets_reason(self) -> None:
        panel = compute_decay(
            self._log(), oos_start=dt.datetime(2030, 1, 1, tzinfo=UTC)
        )
        assert panel.wfe is None
        assert panel.wfe_reason is not None and "out-of-sample side" in panel.wfe_reason

    def test_boundary_before_log_gets_reason(self) -> None:
        panel = compute_decay(
            self._log(), oos_start=dt.datetime(2020, 1, 1, tzinfo=UTC)
        )
        assert panel.wfe is None
        assert panel.wfe_reason is not None and "in-sample side" in panel.wfe_reason

    def test_valid_boundary_computes_wfe(self) -> None:
        panel = compute_decay(
            self._log(30), oos_start=dt.datetime(2026, 1, 26, tzinfo=UTC)
        )
        assert panel.wfe is not None and panel.wfe_reason is None

    def test_no_boundary_no_reason(self) -> None:
        panel = compute_decay(self._log())
        assert panel.wfe is None and panel.wfe_reason is None


class TestPostReviewRegressions:
    def test_float_noise_constant_series_still_degenerate(self) -> None:
        """A repeated loss whose float std is ~1e-14 (not exactly 0) must
        still hit the -inf convention, not report Sharpe -7e16 (P6)."""
        days = [dt.date(2026, 1, 5) + dt.timedelta(days=k) for k in range(14) if
                (dt.date(2026, 1, 5) + dt.timedelta(days=k)).weekday() < 5]
        # -100.1 is not exactly representable; sums accumulate float noise.
        m = compute_metrics(_log_on_dates(days, pnl=-100.1), starting_equity=50_000)
        assert m.sharpe == float("-inf")

    def test_partitions_beyond_sampler_range_clean_error(self) -> None:
        """--partitions 68 used to raise a raw OverflowError (P5)."""
        import numpy as np

        from quantlab.errors import QuantLabError
        from quantlab.metrics.pbo import compute_pbo

        m = np.random.default_rng(0).normal(size=(140, 3))
        with pytest.raises(QuantLabError, match="66 or fewer"):
            compute_pbo(m, partitions=68)
