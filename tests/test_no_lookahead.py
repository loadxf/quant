"""The engine must be immune to lookahead: a signal equal to the FUTURE return
must earn exactly what its correctly-lagged application implies, never the
future return itself. Also pins the t+2 timing convention with a hand-built
case, and checks turnover-cost accounting.
"""

import numpy as np
import pandas as pd
import pytest

from quantlab.backtest import quantile_weights, run_backtest


def make_prices(n_days=400, n_names=50, seed=11):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2015-01-01", periods=n_days)
    rets = rng.normal(0.0003, 0.02, size=(n_days, n_names))
    prices = 100 * np.exp(np.cumsum(rets, axis=0))
    return pd.DataFrame(prices, index=dates, columns=[f"S{i:03d}" for i in range(n_names)])


def test_future_return_signal_is_not_exploitable():
    """Signal_t = return over day t+1 (pure foresight). With correct t+2
    execution the realized alignment is: weights from signal at t apply to the
    return at t+2 — i.e. the foresight is stale by the time it is tradeable.
    The engine's mean daily return must match the hand-computed stale
    alignment, and must be far below the leaked (cheating) alignment."""
    prices = make_prices()
    returns = prices.pct_change(fill_method=None)
    foresight = returns.shift(-1)  # at t, knows the return of day t+1

    result = run_backtest(foresight, prices, "test_foresight", "unit", cost_bps=0.0, ledger=False)

    weights = quantile_weights(foresight.reindex_like(prices))
    hand_stale = (weights.shift(2) * returns).sum(axis=1)
    hand_stale = hand_stale[result.returns_gross.index]
    assert np.allclose(result.returns_gross, hand_stale, atol=1e-12)

    cheat = (weights.shift(1) * returns).sum(axis=1).dropna()
    # The cheating alignment holds tomorrow's winners DURING tomorrow: with a
    # 2% daily vol and decile spread its mean is enormous; the stale one is ~0.
    assert cheat.mean() > 10 * abs(result.returns_gross.mean())


def test_hand_built_timing_convention():
    """Three-day deterministic check of the t+2 rule on a two-asset panel."""
    dates = pd.bdate_range("2020-01-01", periods=6)
    prices = pd.DataFrame(
        {"A": [100, 100, 100, 110, 110, 110], "B": [100, 100, 100, 90, 90, 90]},
        index=dates,
        dtype=float,
    )
    # Signal on day 1 (index position 1): long A, short B.
    signal = pd.DataFrame(np.nan, index=dates, columns=["A", "B"])
    signal.loc[dates[1]] = [1.0, -1.0]

    result = run_backtest(
        signal, prices, "test_hand", "unit", cost_bps=0.0, quantile=0.5, min_names=2, ledger=False
    )
    # Position formed at close of day 2, earns day-3 return: A +10%, B -10% -> +10%.
    ret_day3 = result.returns_gross.get(dates[3], 0.0)
    assert ret_day3 == pytest.approx(0.10, abs=1e-12)


def test_costs_charged_on_turnover():
    prices = make_prices(n_days=300)
    rng = np.random.default_rng(3)
    signal = pd.DataFrame(
        rng.normal(size=prices.shape), index=prices.index, columns=prices.columns
    )
    free = run_backtest(signal, prices, "test_cost0", "unit", cost_bps=0.0, ledger=False)
    paid = run_backtest(signal, prices, "test_cost25", "unit", cost_bps=25.0, ledger=False)
    implied = free.returns_gross - paid.returns_net
    expected = paid.turnover * 25.0 / 10_000.0
    assert np.allclose(implied, expected, atol=1e-14)
    assert paid.returns_net.mean() < free.returns_gross.mean()


def test_ledger_row_written(tmp_path, monkeypatch):
    import quantlab.backtest as bt

    monkeypatch.setattr(bt, "LEDGER_PATH", tmp_path / "ledger.csv")
    prices = make_prices(n_days=120)
    signal = prices.pct_change(fill_method=None).rolling(5).mean()
    bt.run_backtest(signal, prices, "test_ledger", "unit", ledger=True)
    ledger = pd.read_csv(tmp_path / "ledger.csv")
    assert len(ledger) == 1
    assert ledger.loc[0, "candidate_id"] == "test_ledger"
    assert ledger.loc[0, "n_obs"] > 0
