from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from edgelab.gates import signal_metadata
from edgelab.grammar import build_terminals, evaluate
from edgelab.market_calendar import nyse_sessions
from edgelab.signals import SECTOR_TO_ETF, _episode_log_return, compute_declared_signal
from pandas.testing import assert_frame_equal


def _fields(rows: int = 400, names: int = 24) -> dict[str, object]:
    rng = np.random.default_rng(17)
    index = pd.bdate_range("2017-01-03", periods=rows)
    columns = [f"S{i:02d}" for i in range(names)]
    close = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0, 0.015, (rows, names)), axis=0)),
        index=index,
        columns=columns,
    )
    open_ = close * np.exp(rng.normal(0, 0.003, close.shape))
    volume = pd.DataFrame(rng.lognormal(12, 0.8, close.shape), index=index, columns=columns)
    etf_columns = list(SECTOR_TO_ETF.values())
    etf = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0, 0.01, (rows, len(etf_columns))), axis=0)),
        index=index,
        columns=etf_columns,
    )
    return {
        "open": open_,
        "high": pd.DataFrame(np.maximum(open_, close) * 1.01, index=index, columns=columns),
        "low": pd.DataFrame(np.minimum(open_, close) * 0.99, index=index, columns=columns),
        "close": close,
        "adjclose": close,
        "volume": volume,
        "etf_adjclose": etf,
        "sectors": {ticker: "Materials" for ticker in columns},
    }


def _actual(candidate_id: str, fields: dict[str, object]) -> pd.DataFrame:
    return compute_declared_signal(fields, signal_metadata(candidate_id))


def _volz(fields: dict[str, object], window: int = 63) -> pd.DataFrame:
    logvol = np.log(fields["volume"].where(fields["volume"] > 0))
    return (logvol - logvol.rolling(window).mean()) / logvol.rolling(window).std()


def _recession(fields: dict[str, object]) -> pd.DataFrame:
    volz = _volz(fields)
    spike = volz.shift(5)
    post_mean = sum(volz.shift(k) for k in range(5)) / 5
    recession = (spike - post_mean).where(spike > 1.5)
    speed = recession.rolling(252, min_periods=3).mean()
    count = recession.notna().rolling(252, min_periods=1).sum()
    return speed.where(count >= 3)


def test_c003_episode_return_is_inclusive_and_uses_earliest_spike():
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    logret = pd.DataFrame(
        {
            "prior_day": [0.0, 0.01, 0.02, 0.03, 0.04, 0.05],
            "two_days": [0.0, 0.01, 0.02, 0.03, 0.04, 0.05],
            "earliest": [0.0, 0.01, 0.02, 0.03, 0.04, 0.05],
        },
        index=dates,
    )
    spike = pd.DataFrame(False, index=dates, columns=logret.columns)
    spike.loc[dates[4], "prior_day"] = True
    spike.loc[dates[3], "two_days"] = True
    spike.loc[dates[4], "earliest"] = True
    spike.loc[dates[2], "earliest"] = True

    result = _episode_log_return(logret, spike, lookback=5).loc[dates[5]]
    assert result["prior_day"] == 0.04
    assert result["two_days"] == 0.03 + 0.04
    assert result["earliest"] == 0.02 + 0.03 + 0.04


@pytest.mark.parametrize("candidate_id,window", [("B002", 1), ("C004", 5), ("C012", 21)])
def test_plain_reversal_handlers_match_declared_returns(candidate_id, window):
    fields = _fields()
    expected = -fields["adjclose"].pct_change(window, fill_method=None)
    assert_frame_equal(_actual(candidate_id, fields), expected)


def test_spike_reversal_matches_five_day_return_on_volume_spikes():
    fields = _fields()
    expected = (-fields["adjclose"].pct_change(5, fill_method=None)).where(_volz(fields) > 2.0)
    assert_frame_equal(_actual("B003", fields), expected)


@pytest.mark.parametrize("candidate_id,window", [("C001", 5), ("C013", 21)])
def test_volume_recession_handlers_match_exact_timing(candidate_id, window):
    fields = _fields()
    reversal = -fields["adjclose"].pct_change(window, fill_method=None)
    expected = reversal * _recession(fields).rank(axis=1, pct=True)
    assert_frame_equal(_actual(candidate_id, fields), expected)


def test_turn_of_month_handler_uses_first_three_and_last_two_nyse_sessions():
    fields = _fields(rows=80)
    ret = fields["adjclose"].pct_change(fill_method=None)
    selected = set()
    for period in ret.index.to_period("M").unique():
        sessions = nyse_sessions(period.start_time, period.end_time)
        selected.update(sessions[:3])
        selected.update(sessions[-2:])
    mask = pd.Series(ret.index.normalize().isin(selected).astype(float), index=ret.index)
    assert_frame_equal(_actual("C002", fields), (-ret).mul(mask, axis=0))


def test_episode_reversal_matches_inclusive_earliest_spike_and_breadth_tails():
    fields = _fields()
    volz = _volz(fields)
    ret = fields["adjclose"].pct_change(fill_method=None)
    spike = (volz > 2.0).fillna(False)
    live = spike.shift(1, fill_value=False).rolling(10, min_periods=1).max() == 1.0
    trigger = live & (volz < 0) & (volz.shift(1) >= 0)
    episode = pd.DataFrame(np.nan, index=ret.index, columns=ret.columns)
    logret = np.log1p(ret)
    for k in range(1, 11):
        inclusive = logret.shift(1).rolling(k, min_periods=k).sum()
        episode = episode.mask(spike.shift(k, fill_value=False), inclusive)
    raw = (-np.expm1(episode)).where(trigger)
    breadth = raw.notna().sum(axis=1)
    tail = pd.Series(np.where(breadth < 20, 1 / 3, 0.1), index=raw.index)
    ranks = raw.rank(axis=1, pct=True)
    expected = raw.where(ranks.le(tail, axis=0) | ranks.gt(1 - tail, axis=0))
    assert_frame_equal(_actual("C003", fields), expected)


def test_volume_weighted_reversal_matches_low_volume_rank_weight():
    fields = _fields()
    expected = -fields["adjclose"].pct_change(5, fill_method=None) * (
        1 - _volz(fields).rank(axis=1, pct=True)
    )
    assert_frame_equal(_actual("C005", fields), expected)


def test_intraday_reversal_matches_five_day_component_sum():
    fields = _fields()
    intraday = fields["close"] / fields["open"] - 1
    expected = -intraday.rolling(5, min_periods=3).sum()
    assert_frame_equal(_actual("C006", fields), expected)


def test_lag_band_reversal_matches_t_minus_8_through_t_minus_6_return():
    fields = _fields()
    expected = -fields["adjclose"].pct_change(2, fill_method=None).shift(6)
    assert_frame_equal(_actual("C007", fields), expected)


def test_gap_intraday_coherence_matches_terminal_product_smoothing():
    fields = _fields()
    terms = build_terminals(
        *(fields[name] for name in ("open", "high", "low", "close", "adjclose", "volume"))
    )
    expected = (terms["gap"] * terms["intraday"]).rolling(3, min_periods=2).mean()
    assert_frame_equal(_actual("C008", fields), expected)


def test_sector_etf_reversal_maps_each_member_to_its_sector_etf():
    fields = _fields()
    etf_ret = fields["etf_adjclose"].pct_change(fill_method=None)
    expected = pd.DataFrame({ticker: -etf_ret["XLB"] for ticker in fields["adjclose"].columns})
    assert_frame_equal(_actual("C009", fields), expected)


def test_expression_handlers_match_frozen_grammar_formulas():
    fields = _fields()
    terms = build_terminals(
        *(fields[name] for name in ("open", "high", "low", "close", "adjclose", "volume"))
    )
    c010 = evaluate(("roll_std", "rng", 63), terms)
    c011 = evaluate(("roll_std", "gap", 63), terms) - fields["adjclose"].pct_change(
        21, fill_method=None
    )
    assert_frame_equal(_actual("C010", fields), c010)
    assert_frame_equal(_actual("C011", fields), c011)


def test_smoothed_volume_and_range_volatility_match_declared_windows():
    fields = _fields()
    c014 = _volz(fields).rolling(5, min_periods=3).mean()
    fraction = (fields["high"] - fields["low"]) / fields["close"]
    c015 = fraction.rolling(63, min_periods=31).std()
    assert_frame_equal(_actual("C014", fields), c014)
    assert_frame_equal(_actual("C015", fields), c015)


def test_etf_volume_rank_skew_uses_the_declared_custom_volume_z():
    fields = _fields()
    terms = build_terminals(
        *(fields[name] for name in ("open", "high", "low", "close", "adjclose", "volume"))
    )
    terms["volz"] = _volz(fields)
    expected = evaluate(("roll_skew", ("abs_", ("cs_rank", "volz")), 63), terms)
    assert_frame_equal(_actual("C016", fields), expected)
