"""Half-open window primitives (round-4 defect: inclusive .loc slicing
double-counted the boundary bar and stretched minute-resolution windows
to two bars). These are the canonical implementations the QC notebook
mirrors verbatim."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from qlir.windows import half_open_slice, last_at_or_before, logret_std, window_sum

B = pd.Timestamp("2024-03-05 14:30:00", tz="UTC")


def minute_volumes() -> pd.Series:
    """Bars stamped on exact minutes around the boundary; volume equals
    the bar's minute-of-day so sums are diagnosable."""
    stamps = pd.date_range(B - pd.Timedelta(minutes=5), B + pd.Timedelta(minutes=5), freq="1min")
    return pd.Series([float(ts.minute) for ts in stamps], index=stamps)


def second_volumes() -> pd.Series:
    stamps = pd.date_range(B - pd.Timedelta(seconds=120), B + pd.Timedelta(seconds=120), freq="1s")
    return pd.Series(1.0, index=stamps)


class TestHalfOpenVolumes:
    def test_minute_pre_window_is_exactly_one_bar(self) -> None:
        """(b-60s, b] at minute resolution = ONLY the boundary bar —
        the round-4 defect counted two."""
        volumes = minute_volumes()
        window = half_open_slice(volumes, B - pd.Timedelta(seconds=60), B)
        assert len(window) == 1
        assert window.index[0] == B

    def test_minute_forward_window_is_exactly_one_bar(self) -> None:
        volumes = minute_volumes()
        window = half_open_slice(volumes, B, B + pd.Timedelta(seconds=60))
        assert len(window) == 1
        assert window.index[0] == B + pd.Timedelta(minutes=1)

    def test_boundary_bar_counted_on_exactly_one_side(self) -> None:
        volumes = minute_volumes()
        pre = window_sum(volumes, B - pd.Timedelta(seconds=60), B)
        fwd = window_sum(volumes, B, B + pd.Timedelta(seconds=60))
        assert pre == pytest.approx(30.0)  # the 14:30 bar
        assert fwd == pytest.approx(31.0)  # the 14:31 bar — no overlap
        # Disjointness: pre + fwd covers each bar at most once.
        both = window_sum(volumes, B - pd.Timedelta(seconds=60), B + pd.Timedelta(seconds=60))
        assert both == pytest.approx(pre + fwd)

    def test_second_resolution_60s_window_has_60_bars(self) -> None:
        volumes = second_volumes()
        assert window_sum(volumes, B - pd.Timedelta(seconds=60), B) == pytest.approx(60.0)
        assert window_sum(volumes, B, B + pd.Timedelta(seconds=60)) == pytest.approx(60.0)

    def test_forward_windows_nest(self) -> None:
        volumes = second_volumes()
        v60 = window_sum(volumes, B, B + pd.Timedelta(seconds=60))
        v120 = window_sum(volumes, B, B + pd.Timedelta(seconds=120))
        assert v120 == pytest.approx(v60 + 60.0)


class TestLastAtOrBefore:
    def test_exact_stamp_included(self) -> None:
        closes = second_volumes().cumsum()
        assert last_at_or_before(closes, B) == pytest.approx(float(closes.loc[B]))

    def test_before_first_stamp_is_none(self) -> None:
        closes = second_volumes()
        assert last_at_or_before(closes, B - pd.Timedelta(hours=1)) is None


class TestLogretStd:
    def test_uses_base_price_at_window_start(self) -> None:
        """The first in-window return is measured against the last price
        AT OR BEFORE the window start — not dropped."""
        stamps = pd.date_range(B - pd.Timedelta(minutes=6), B, freq="1min")
        closes = pd.Series(np.linspace(100.0, 106.0, len(stamps)), index=stamps)
        value = logret_std(closes, B - pd.Timedelta(minutes=5), B)
        window = closes.iloc[-5:]
        base = closes.iloc[-6]
        prices = np.concatenate([[base], window.to_numpy()])
        expected = float(np.std(np.diff(np.log(prices)), ddof=1))
        assert value == pytest.approx(expected)

    def test_too_few_prices_is_nan(self) -> None:
        stamps = pd.date_range(B, B + pd.Timedelta(minutes=1), freq="1min")
        closes = pd.Series([100.0, 101.0], index=stamps)
        assert np.isnan(logret_std(closes, B + pd.Timedelta(hours=1), B + pd.Timedelta(hours=2)))
