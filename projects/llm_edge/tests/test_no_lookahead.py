"""A signal equal to the next-day return must earn exactly what its
correctly-lagged application implies, never that next-day return itself.
Also pins the t+2 timing convention with a hand-built
case, and checks turnover-cost accounting.
"""

import edgelab.backtest as bt
import numpy as np
import pandas as pd
import pytest
from edgelab.backtest import quantile_weights, run_backtest
from edgelab.data import FieldBundle
from edgelab.gates import (
    _candidate_specific_gate2,
    _parameter_perturbations,
    _perturbations_pass,
    _signals_materially_differ,
    _validation_execution_differs,
    audit_signal_causality,
    compute_signal_isolated,
    evaluate_candidate,
)
from edgelab.market_calendar import nyse_sessions


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(bt, "LEDGER_PATH", tmp_path / "ledger.csv")


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

    result = run_backtest(foresight, prices, "test_foresight", "unit", cost_bps=0.0)

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
        signal, prices, "test_hand", "unit", cost_bps=0.0, quantile=0.5, min_names=2
    )
    # Position formed at close of day 2, earns day-3 return: +1 long A
    # gains 10% and -1 short B gains 10%, for a 20% gross-2 book return.
    ret_day3 = result.returns_gross.get(dates[3], 0.0)
    assert ret_day3 == pytest.approx(0.20, abs=1e-12)


def test_costs_charged_on_turnover():
    prices = make_prices(n_days=300)
    rng = np.random.default_rng(3)
    signal = pd.DataFrame(rng.normal(size=prices.shape), index=prices.index, columns=prices.columns)
    free = run_backtest(signal, prices, "test_cost0", "unit", cost_bps=0.0)
    paid = run_backtest(signal, prices, "test_cost25", "unit", cost_bps=25.0)
    implied = free.returns_gross - paid.returns_net
    expected = paid.turnover * 25.0 / 10_000.0
    assert np.allclose(implied, expected, atol=1e-14)
    assert paid.returns_net.mean() < free.returns_gross.mean()


def test_closing_cost_is_retained_when_position_returns_to_flat():
    dates = pd.bdate_range("2020-01-01", periods=7)
    prices = pd.DataFrame(100.0, index=dates, columns=["A", "B"])
    signal = pd.DataFrame(np.nan, index=dates, columns=["A", "B"])
    signal.loc[dates[1]] = [1.0, -1.0]
    result = run_backtest(
        signal, prices, "exit-cost", "unit", cost_bps=10, quantile=0.5, min_names=2
    )
    exit_day = dates[4]
    assert result.weights.loc[exit_day].abs().sum() == 0
    assert result.turnover.loc[exit_day] == pytest.approx(2.0)
    assert result.returns_net.loc[exit_day] == pytest.approx(-0.002)


def test_terminal_position_is_liquidated_and_charged():
    dates = pd.bdate_range("2020-01-01", periods=8)
    prices = pd.DataFrame(100.0, index=dates, columns=["A", "B"])
    signal = pd.DataFrame({"A": 1.0, "B": -1.0}, index=dates, columns=["A", "B"])
    result = run_backtest(
        signal, prices, "terminal-exit", "unit", cost_bps=10, quantile=0.5, min_names=2
    )
    assert result.turnover.sum() == pytest.approx(4.0)
    assert result.turnover.iloc[-1] == pytest.approx(2.0)
    assert result.returns_net.iloc[-1] == pytest.approx(-0.002)


def test_sparse_signal_retains_flat_calendar_days_after_first_trade():
    dates = pd.bdate_range("2020-01-01", periods=100)
    prices = pd.DataFrame(
        {"A": np.linspace(100, 120, 100), "B": np.linspace(100, 90, 100)},
        index=dates,
    )
    signal = pd.DataFrame(np.nan, index=dates, columns=["A", "B"])
    signal.iloc[::20] = [1.0, -1.0]
    result = run_backtest(signal, prices, "sparse", "unit", cost_bps=0, quantile=0.5, min_names=2)
    first_live = result.returns_net.index[0]
    assert result.returns_net.index.equals(dates[dates >= first_live])
    assert (result.returns_net == 0).sum() > 70


def test_first_day_entry_charges_turnover():
    """Entering the book from flat must be charged full turnover, not zero."""
    prices = make_prices(n_days=60)
    rng = np.random.default_rng(8)
    signal = pd.DataFrame(rng.normal(size=prices.shape), index=prices.index, columns=prices.columns)
    result = run_backtest(signal, prices, "test_entry", "unit", cost_bps=10.0)
    first_live = result.turnover.index[0]
    gross_book = result.weights.loc[first_live].abs().sum()
    assert gross_book > 0
    assert result.turnover.loc[first_live] == pytest.approx(gross_book)


def test_ledger_row_written(tmp_path, monkeypatch):
    prices = make_prices(n_days=120)
    signal = prices.pct_change(fill_method=None).rolling(5).mean()
    bt.run_backtest(signal, prices, 'test,"ledger"', "unit")
    ledger = pd.read_csv(bt.LEDGER_PATH)
    assert len(ledger) == 1
    assert ledger.loc[0, "candidate_id"] == 'test,"ledger"'
    assert ledger.loc[0, "n_obs"] > 0
    assert b"\r\n" not in bt.LEDGER_PATH.read_bytes()


def test_ledger_params_hash_binds_exact_signal_output():
    prices = make_prices(n_days=120)
    first = prices.pct_change(fill_method=None).rolling(5).mean()
    second = -first
    run_backtest(first, prices, "same-id", "unit")
    run_backtest(second, prices, "same-id", "unit")
    ledger = pd.read_csv(bt.LEDGER_PATH)
    assert ledger["params_hash"].nunique() == 2


def test_ledger_params_hash_binds_minimum_universe_size():
    prices = make_prices(n_days=120, n_names=20)
    signal = prices.pct_change(fill_method=None)
    run_backtest(signal, prices, "same-id", "unit", min_names=5)
    run_backtest(signal, prices, "same-id", "unit", min_names=10)
    ledger = pd.read_csv(bt.LEDGER_PATH)
    assert ledger["params_hash"].nunique() == 2


def test_ledger_uses_the_exact_bound_scoring_window_and_binds_it_in_hash():
    prices = make_prices(n_days=120, n_names=20)
    signal = prices.pct_change(fill_method=None)
    first_start, second_start, end = prices.index[40], prices.index[60], prices.index[99]

    first = run_backtest(
        signal,
        prices,
        "bounded-ledger",
        "val_perturb",
        start_date=prices.index[20],
        ledger_start_date=first_start,
        ledger_end_date=end,
    )
    run_backtest(
        signal,
        prices,
        "bounded-ledger",
        "val_perturb",
        start_date=prices.index[20],
        ledger_start_date=second_start,
        ledger_end_date=end,
    )

    ledger = pd.read_csv(bt.LEDGER_PATH)
    inspected = first.returns_net.loc[first_start:end]
    assert ledger.loc[0, "n_obs"] == len(inspected)
    assert ledger.loc[0, "sr_net"] == pytest.approx(round(bt.sharpe_ratio(inspected), 6))
    assert ledger["params_hash"].nunique() == 2


@pytest.mark.parametrize(
    "bounds",
    [
        {"ledger_end_date": "2014-12-31"},
        {"ledger_start_date": "2030-01-01"},
        {"ledger_end_date": "2015-02-01"},
    ],
)
def test_ledger_scoring_window_must_intersect_the_evaluated_panel(bounds):
    prices = make_prices(n_days=120, n_names=20)
    signal = prices.pct_change(fill_method=None)
    with pytest.raises(ValueError, match="evaluated price horizon"):
        run_backtest(
            signal,
            prices,
            "bad-ledger-bound",
            "unit",
            start_date="2015-02-01",
            **bounds,
        )


def test_missing_held_return_fails_instead_of_becoming_zero():
    prices = make_prices(n_days=60, n_names=4)
    signal = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    signal.loc[prices.index[10], ["S000", "S001", "S002", "S003"]] = [2, 1, -1, -2]
    prices.loc[prices.index[12], "S000"] = np.nan
    with pytest.raises(ValueError, match="no return"):
        run_backtest(signal, prices, "missing", "unit", quantile=0.25, min_names=4)
    ledger = pd.read_csv(bt.LEDGER_PATH)
    assert len(ledger) == 1
    assert ledger.loc[0, "candidate_id"] == "missing"
    assert ledger.loc[0, "sr_net"] == "error"


def test_backtest_start_date_preserves_warmup_but_excludes_earlier_data_gaps():
    prices = make_prices(n_days=80, n_names=4)
    signal = pd.DataFrame(
        [[2.0, 1.0, -1.0, -2.0]] * len(prices),
        index=prices.index,
        columns=prices.columns,
    )
    prices.loc[prices.index[20], "S000"] = np.nan
    start = prices.index[30]

    result = run_backtest(
        signal,
        prices,
        "bounded",
        "unit",
        cost_bps=0,
        quantile=0.25,
        min_names=4,
        start_date=start,
    )

    assert result.returns_net.index.min() == start
    assert result.meta["start_date"] == str(start.date())
    assert result.weights.loc[start, "S000"] > 0


def test_backtest_start_date_still_rejects_a_later_held_return_gap():
    prices = make_prices(n_days=80, n_names=4)
    signal = pd.DataFrame(
        [[2.0, 1.0, -1.0, -2.0]] * len(prices),
        index=prices.index,
        columns=prices.columns,
    )
    start = prices.index[30]
    prices.loc[prices.index[40], "S000"] = np.nan

    with pytest.raises(ValueError, match="no return"):
        run_backtest(
            signal,
            prices,
            "bounded-gap",
            "unit",
            quantile=0.25,
            min_names=4,
            start_date=start,
        )


def test_explicit_start_retains_flat_days_before_delayed_first_trade():
    dates = pd.bdate_range("2020-01-01", periods=50)
    prices = pd.DataFrame(100.0, index=dates, columns=["A", "B"])
    signal = pd.DataFrame(np.nan, index=dates, columns=prices.columns)
    signal.loc[dates[20]] = [1.0, -1.0]
    start = dates[10]

    result = run_backtest(
        signal,
        prices,
        "delayed-event",
        "unit",
        cost_bps=0,
        quantile=0.5,
        min_names=2,
        start_date=start,
    )

    assert result.returns_net.index.equals(dates[dates >= start])
    assert (result.returns_net.loc[start : dates[21]] == 0).all()
    assert result.turnover.loc[dates[22]] == pytest.approx(2.0)


def test_finite_external_signal_cannot_trade_a_security_before_listing():
    dates = pd.bdate_range("2020-01-01", periods=60)
    prices = pd.DataFrame(
        {
            "A": np.linspace(100, 110, 60),
            "B": np.linspace(100, 105, 60),
            "C": np.linspace(100, 95, 60),
            "NEW": [np.nan] * 30 + list(np.linspace(20, 25, 30)),
        },
        index=dates,
    )
    external_signal = pd.DataFrame(
        {"A": 1.0, "B": 0.5, "C": -1.0, "NEW": 2.0},
        index=dates,
    )

    result = run_backtest(
        external_signal,
        prices,
        "listing-mask",
        "unit",
        cost_bps=0,
        quantile=0.5,
        min_names=3,
    )

    assert (result.weights.loc[: dates[31], "NEW"] == 0).all()
    assert result.weights.loc[dates[32] :, "NEW"].gt(0).any()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"holding_days": 1.5},
        {"holding_days": True},
        {"cost_bps": "free"},
        {"candidate_id": " "},
    ],
)
def test_backtest_rejects_invalid_runtime_types(kwargs):
    prices = make_prices(n_days=10, n_names=2)
    args = {"candidate_id": "X", "split": "test", "min_names": 2} | kwargs
    with pytest.raises(ValueError):
        run_backtest(prices, prices, **args)


def test_registered_ledger_prefix_freezes_later_holdout_trials(monkeypatch, tmp_path):
    ledger = tmp_path / "ledger.csv"
    monkeypatch.setattr(bt, "LEDGER_PATH", ledger)
    ledger.write_text(
        "timestamp,candidate_id,params_hash,split,sr_net,n_obs\n"
        "t,C001,a,train,0.2,100\n"
        "t,C002,b,train,0.4,100\n"
    )
    registered_bytes = ledger.stat().st_size
    frozen = bt.ledger_trial_stats(prefix_bytes=registered_bytes)
    with ledger.open("a") as handle:
        handle.write("t,C001,c,holdout,9.9,100\n")
    assert bt.ledger_trial_stats(prefix_bytes=registered_bytes) == frozen
    assert bt.ledger_trial_stats()[0] == frozen[0] + 1


def test_quantile_leg_size_has_no_upper_off_by_one():
    signal = pd.DataFrame([range(10)], columns=list("abcdefghij"), dtype=float)
    weights = quantile_weights(signal, quantile=0.1, min_names=10)
    assert (weights.iloc[0] > 0).sum() == 1
    assert (weights.iloc[0] < 0).sum() == 1


def test_quantile_weights_are_dollar_neutral_for_small_and_median_books():
    rows = pd.DataFrame(
        [
            [1.0, 2.0, np.nan, np.nan, np.nan],
            [1.0, 2.0, 3.0, 4.0, np.nan],
            [1.0, 2.0, 3.0, 4.0, 5.0],
        ],
        columns=list("abcde"),
    )
    small = quantile_weights(rows.iloc[[0]], quantile=0.1, min_names=2)
    assert list(small.iloc[0, :2]) == [-1.0, 1.0]
    median = quantile_weights(rows.iloc[1:], quantile=0.5, min_names=2)
    assert np.allclose(median.sum(axis=1), 0.0)
    assert np.allclose(median.abs().sum(axis=1), 2.0)


def test_quantile_ties_never_create_a_one_sided_book():
    signal = pd.DataFrame(
        [
            [1.0] * 20,
            [1.0, 1.0, 1.0, 2.0] + [np.nan] * 16,
        ]
    )
    tied = quantile_weights(signal.iloc[[0]], quantile=0.5, min_names=2)
    boundary = quantile_weights(signal.iloc[[1]], quantile=0.1, min_names=2)
    assert not tied.to_numpy().any()
    assert not boundary.to_numpy().any()


def test_every_active_quantile_row_has_unit_long_and_short_legs():
    rng = np.random.default_rng(91)
    signal = pd.DataFrame(rng.normal(size=(40, 17)))
    weights = quantile_weights(signal, quantile=0.2, min_names=5)
    active = weights.abs().sum(axis=1) > 0
    assert np.allclose(weights.loc[active].sum(axis=1), 0.0)
    assert np.allclose(weights.loc[active].clip(lower=0).sum(axis=1), 1.0)
    assert np.allclose(-weights.loc[active].clip(upper=0).sum(axis=1), 1.0)


def test_flat_candidate_is_a_structured_gate_failure(monkeypatch, tmp_path):
    import edgelab.gates as gates

    candidate = tmp_path / "C000"
    candidate.mkdir()
    (candidate / "spec.md").write_text("test candidate")
    (candidate / "signal.py").write_text(
        'SIGNAL_KIND = "plain_reversal"\n'
        'ORIGIN = "G4"\n'
        "RETURN_WINDOW = 1\n"
        'PERTURBATIONS = ("RETURN_WINDOW",)\n'
    )
    prices = pd.DataFrame(
        100.0,
        index=pd.bdate_range("2019-01-01", periods=120),
        columns=["A", "B", "C", "D"],
    )
    monkeypatch.setattr(gates, "CANDIDATES_DIR", tmp_path)
    metadata, _, digest = gates.signal_declaration_snapshot("C000")
    identity = {
        "signal_sha256": {"C000": digest},
        "data_manifest_sha256": "manifest",
        "universe_sha256": "universe",
    }
    monkeypatch.setattr(gates, "family_artifact_identity", lambda ids: identity)
    fields = FieldBundle(
        {"adjclose": prices},
        input_identity={
            "data_manifest_sha256": "manifest",
            "universe_sha256": "universe",
        },
    )
    result = evaluate_candidate("C000", fields, metadata, digest)
    assert result["gate1"]["pass"] is False
    assert result["gate2"]["pass"] is False
    assert result["combinatorial_subperiod_stability"]["n_paths"] == 0
    assert set(result["validation"]["cost_sweep_sr"]) == {"0", "5", "10", "25"}
    assert result["data"]["panel_start"] == "2019-01-01"
    assert result["data"]["evaluation_start"] == "2005-01-01"


def test_candidate_causality_audit_rejects_future_dependency():
    prices = make_prices(n_days=80, n_names=4)
    fields = {
        name: prices.copy() for name in ("open", "high", "low", "close", "adjclose", "volume")
    }

    class Causal:
        @staticmethod
        def compute_signal(data):
            return data["adjclose"].pct_change(fill_method=None)

    class Cheating:
        @staticmethod
        def compute_signal(data):
            return data["adjclose"].shift(-1)

    audit_signal_causality(Causal, fields)
    with pytest.raises(RuntimeError, match="causality audit"):
        audit_signal_causality(Cheating, fields)


def test_turn_of_month_uses_nyse_sessions_around_memorial_day():
    sessions = nyse_sessions("2021-04-01", "2021-05-31")
    prices = pd.DataFrame({"A": np.arange(100.0, 100.0 + len(sessions))}, index=sessions)
    fields = {
        name: prices.copy() for name in ("open", "high", "low", "close", "adjclose", "volume")
    }
    signal = compute_signal_isolated("C002", fields, causality_audit=True)
    assert signal.loc["2021-05-27", "A"] != 0
    assert signal.loc["2021-05-28", "A"] != 0
    assert signal.loc["2021-05-26", "A"] == 0


def test_nyse_is_open_friday_before_saturday_new_year():
    sessions = nyse_sessions("2021-12-27", "2021-12-31")
    assert pd.Timestamp("2021-12-31") in sessions


def test_causality_audit_catches_lookahead_localized_before_old_cutoffs():
    prices = make_prices(n_days=80, n_names=4)
    fields = {"adjclose": prices}

    class LocalizedCheat:
        @staticmethod
        def compute_signal(data):
            signal = data["adjclose"].pct_change(fill_method=None)
            signal.iloc[15:25] = data["adjclose"].shift(-1).iloc[15:25]
            return signal

    with pytest.raises(RuntimeError, match="causality audit"):
        audit_signal_causality(LocalizedCheat, fields)


def test_causality_audit_catches_single_row_leak_between_sampled_cutoffs():
    prices = make_prices(n_days=80, n_names=4)

    class OneRowCheat:
        @staticmethod
        def compute_signal(data):
            signal = data["adjclose"].pct_change(fill_method=None)
            if len(signal) > 2:
                signal.iloc[1] = data["adjclose"].shift(-1).iloc[1]
            return signal

    with pytest.raises(RuntimeError, match="causality audit"):
        audit_signal_causality(OneRowCheat, {"adjclose": prices})


def test_causality_audit_uses_true_prefix_and_catches_index_end_dependency():
    prices = make_prices(n_days=40, n_names=4)
    fields = {"adjclose": prices}

    class ShapeCheat:
        @staticmethod
        def compute_signal(data):
            value = float(data["adjclose"].index[-1].value)
            return data["adjclose"] * 0 + value

    with pytest.raises(RuntimeError, match="causality audit"):
        audit_signal_causality(ShapeCheat, fields)


def test_failed_or_nonfinite_perturbation_cannot_pass_gate2():
    assert _perturbations_pass({})
    assert _perturbations_pass({"WINDOWx0.75": 0.2})
    assert not _perturbations_pass({"WINDOWx0.75": "error: boom"})
    assert not _perturbations_pass({"WINDOWx0.75": float("nan")})
    assert not _perturbations_pass({"WINDOWx0.75": -0.1})


@pytest.mark.parametrize(
    "expression",
    [("roll_std", "rng", 63), ("roll_skew", ("abs_", ("cs_rank", "volz")), 63)],
)
def test_embedded_expression_windows_are_perturbed(expression):
    variants = _parameter_perturbations({"EXPR": expression, "HOLD": 5, "PERTURBATIONS": ("EXPR",)})
    assert [label for label, _ in variants] == ["EXPR[2]x0.75", "EXPR[2]x1.25"]
    assert all("EXPR" in overrides for _, overrides in variants)


def test_holding_window_is_perturbed_in_backtest_settings():
    variants = _parameter_perturbations({"HOLD": 5, "PERTURBATIONS": ("HOLD",)})
    assert [label for label, _ in variants] == ["HOLDx0.75", "HOLDx1.25"]
    assert [variant["__BACKTEST__"]["holding_days"] for _, variant in variants] == [
        4,
        6,
    ]


def test_quantile_perturbations_skip_values_outside_the_valid_domain():
    variants = _parameter_perturbations({"QUANTILE": 0.5, "PERTURBATIONS": ("QUANTILE",)})
    assert variants == [
        ("QUANTILEx0.75", {"__BACKTEST__": {"quantile": 0.375}}),
    ]


def test_missing_perturbation_manifest_is_rejected():
    with pytest.raises(RuntimeError, match="must declare PERTURBATIONS"):
        _parameter_perturbations({"WINDOW": 20})


@pytest.mark.parametrize("expression", [None, "bad", ("neg", "ret1")])
def test_declared_expression_must_have_a_numeric_parameter(expression):
    with pytest.raises(RuntimeError, match="EXPR"):
        _parameter_perturbations({"PERTURBATIONS": ("EXPR",), "EXPR": expression})


def test_candidate_specific_comparisons_use_declared_baselines_and_holds(monkeypatch):
    import types

    import edgelab.gates as gates

    dates = pd.bdate_range("2019-01-01", periods=300)
    prices = make_prices(n_days=300, n_names=25)
    prices.index = dates
    fields = {
        name: prices.copy() for name in ("open", "high", "low", "close", "adjclose", "volume")
    }
    calls = []

    def fake_backtest(signal, adjclose, candidate_id, split, **kwargs):
        calls.append((candidate_id, signal.copy(), kwargs))
        values = pd.Series(np.sin(np.arange(len(dates))) + 0.01, index=dates)
        return types.SimpleNamespace(returns_net=values)

    monkeypatch.setattr(gates, "run_backtest", fake_backtest)
    candidate = pd.Series(np.cos(np.arange(len(dates))) + 0.02, index=dates)
    for candidate_id in ("C001", "C002", "C003", "C007", "C008", "C009", "C013"):
        result = _candidate_specific_gate2(candidate_id, fields, candidate, 10.0)
        assert "requirements_pass" in result

    call_map = {candidate_id: kwargs for candidate_id, _, kwargs in calls}
    signal_map = {candidate_id: signal for candidate_id, signal, _ in calls}
    assert call_map["gate2_C001_C004"]["holding_days"] == 1
    assert call_map["gate2_C002_ungated_ret1"]["holding_days"] == 5
    assert call_map["gate2_C003_spike_entry"]["holding_days"] == 10
    log_volume = np.log(fields["volume"].where(fields["volume"] > 0))
    volz = (log_volume - log_volume.rolling(63).mean()) / log_volume.rolling(63).std()
    expected_spike = (-prices.pct_change(5, fill_method=None)).where(volz > 2)
    pd.testing.assert_frame_equal(signal_map["gate2_C003_spike_entry"], expected_spike)
    assert call_map["gate2_C003_plain_ret5"]["holding_days"] == 10
    assert call_map["gate2_C013_C012_same_hold"]["holding_days"] == 21
    assert "gate2_C007_C004_correlation" in call_map
    assert "gate2_C008_C006_correlation" in call_map
    assert "gate2_C009_C004_correlation" in call_map


def test_vacuous_parameter_override_is_not_a_robustness_pass():
    prices = make_prices(n_days=30, n_names=2)
    base = prices.rolling(5).mean()
    assert not _signals_materially_differ(base, base.copy())
    assert _signals_materially_differ(base, prices.rolling(6).mean())


def test_perturbation_must_change_validation_execution():
    import types

    dates = pd.bdate_range("2018-01-01", "2020-01-31")
    signal = pd.DataFrame({"A": 1.0, "B": -1.0}, index=dates)
    train_only_change = signal.copy()
    train_only_change.loc[:"2018-12-31"] *= -1
    positive_rescale = signal * 5.0
    base = quantile_weights(signal, quantile=0.5, min_names=2)
    base_result = types.SimpleNamespace(weights=base)
    assert not _validation_execution_differs(
        base_result,
        types.SimpleNamespace(
            weights=quantile_weights(positive_rescale, quantile=0.5, min_names=2)
        ),
    )
    assert not _validation_execution_differs(
        base_result,
        types.SimpleNamespace(
            weights=quantile_weights(train_only_change, quantile=0.5, min_names=2)
        ),
    )
    validation_change = signal.copy()
    validation_change.loc["2019-06-03", ["A", "B"]] = [-1.0, 1.0]
    assert _validation_execution_differs(
        base_result,
        types.SimpleNamespace(
            weights=quantile_weights(validation_change, quantile=0.5, min_names=2)
        ),
    )


def test_isolated_candidate_cannot_read_arbitrary_files(monkeypatch, tmp_path):
    import edgelab.gates as gates

    candidate = tmp_path / "C999"
    candidate.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("holdout")
    (candidate / "signal.py").write_text(
        f"def compute_signal(fields):\n    open({str(secret)!r}).read()\n"
        "    return fields['adjclose']\n"
    )
    monkeypatch.setattr(gates, "CANDIDATES_DIR", tmp_path)
    prices = make_prices(n_days=20, n_names=2)
    fields = {"adjclose": prices}
    with pytest.raises(RuntimeError, match="file access denied"):
        compute_signal_isolated("C999", fields)


def test_isolated_candidate_executes_benign_signal(monkeypatch, tmp_path):
    import edgelab.gates as gates

    candidate = tmp_path / "C997"
    candidate.mkdir()
    (candidate / "signal.py").write_text(
        "def compute_signal(fields):\n    return fields['adjclose'].pct_change()\n"
    )
    monkeypatch.setattr(gates, "CANDIDATES_DIR", tmp_path)
    prices = make_prices(n_days=20, n_names=2)
    result = compute_signal_isolated("C997", {"adjclose": prices}, causality_audit=True)
    assert result.equals(prices.pct_change())


def test_isolated_causality_audit_rejects_dynamic_future_shift(monkeypatch, tmp_path):
    import edgelab.gates as gates

    candidate = tmp_path / "C992"
    candidate.mkdir()
    (candidate / "signal.py").write_text(
        "PERIOD = -1\ndef compute_signal(fields):\n    return fields['adjclose'].shift(PERIOD)\n"
    )
    monkeypatch.setattr(gates, "CANDIDATES_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="causality audit"):
        compute_signal_isolated("C992", {"adjclose": make_prices(20, 2)}, causality_audit=True)


def test_isolated_causality_audit_cannot_be_gamed_at_known_cutoffs(monkeypatch, tmp_path):
    import edgelab.gates as gates

    candidate_dir = tmp_path / "C990"
    candidate_dir.mkdir()
    positions = np.unique(np.linspace(0, 598, num=64).astype(int)).tolist()
    (candidate_dir / "signal.py").write_text(
        "import pandas as pd\n"
        "FORWARD = 1\n"
        f"AUDITED = {positions!r}\n"
        "def compute_signal(fields):\n"
        "    adj = fields['adjclose']\n"
        "    out = adj.shift(-FORWARD)\n"
        "    for position in AUDITED:\n"
        "        if position < len(out):\n"
        "            out.iloc[position] = adj.iloc[position]\n"
        "    return out\n"
    )
    monkeypatch.setattr(gates, "CANDIDATES_DIR", tmp_path)

    with pytest.raises(RuntimeError, match="causality audit"):
        compute_signal_isolated("C990", {"adjclose": make_prices(600, 20)}, causality_audit=True)


def test_isolated_audit_does_not_share_full_signal_through_builtins(monkeypatch, tmp_path):
    import edgelab.gates as gates

    candidate = tmp_path / "C991"
    candidate.mkdir()
    (candidate / "signal.py").write_text(
        "import builtins\n"
        "PERIOD = -1\n"
        "def compute_signal(fields):\n"
        "    if not hasattr(builtins, '_edge_saved_signal'):\n"
        "        builtins._edge_saved_signal = fields['adjclose'].shift(PERIOD)\n"
        "    return builtins._edge_saved_signal.loc[fields['adjclose'].index]\n"
    )
    monkeypatch.setattr(gates, "CANDIDATES_DIR", tmp_path)
    with pytest.raises(RuntimeError, match=r"causality audit|isolated candidate signal failed"):
        compute_signal_isolated("C991", {"adjclose": make_prices(40, 2)}, causality_audit=True)


def test_isolated_candidate_denies_native_libc_file_read(monkeypatch, tmp_path):
    import edgelab.gates as gates

    candidate = tmp_path / "C996"
    candidate.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP_SECRET")
    (candidate / "signal.py").write_text(
        "import ctypes\n"
        "def compute_signal(fields):\n"
        f"    fd = ctypes.pythonapi.open({str(secret).encode()!r}, 0)\n"
        "    if fd < 0:\n"
        "        raise PermissionError('native open denied')\n"
        "    return fields['adjclose']\n"
    )
    monkeypatch.setattr(gates, "CANDIDATES_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="native open denied"):
        compute_signal_isolated("C996", {"adjclose": make_prices(20, 2)})


def test_candidate_source_rejects_negative_shift_before_execution(monkeypatch, tmp_path):
    import edgelab.gates as gates

    candidate = tmp_path / "C995"
    candidate.mkdir()
    (candidate / "signal.py").write_text(
        "def compute_signal(fields):\n    return fields['adjclose'].shift(-1)\n"
    )
    monkeypatch.setattr(gates, "CANDIDATES_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="forbidden future access"):
        compute_signal_isolated("C995", {"adjclose": make_prices(20, 2)})


def test_isolated_candidate_cannot_mutate_extended_attributes(monkeypatch, tmp_path):
    import edgelab.gates as gates

    candidate = tmp_path / "C994"
    candidate.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("unchanged")
    (candidate / "signal.py").write_text(
        "import os\n"
        "def compute_signal(fields):\n"
        f"    os.setxattr({str(secret)!r}, b'user.edgelab', b'mutated')\n"
        "    return fields['adjclose']\n"
    )
    monkeypatch.setattr(gates, "CANDIDATES_DIR", tmp_path)
    with pytest.raises(RuntimeError, match=r"operation denied: os\.setxattr"):
        compute_signal_isolated("C994", {"adjclose": make_prices(20, 2)})


def test_isolated_candidate_crash_is_reported_and_reaped(monkeypatch, tmp_path):
    import multiprocessing as mp

    import edgelab.gates as gates

    candidate = tmp_path / "C993"
    candidate.mkdir()
    (candidate / "signal.py").write_text(
        "import os\ndef compute_signal(fields):\n    os._exit(7)\n"
    )
    monkeypatch.setattr(gates, "CANDIDATES_DIR", tmp_path)
    children_before = {process.pid for process in mp.active_children()}
    with pytest.raises(RuntimeError, match="without a response"):
        compute_signal_isolated("C993", {"adjclose": make_prices(20, 2)}, timeout=5)
    assert {process.pid for process in mp.active_children()} <= children_before


def test_isolated_candidate_cannot_retarget_its_allowed_path(monkeypatch, tmp_path):
    import edgelab.gates as gates

    candidate = tmp_path / "C998"
    candidate.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("holdout")
    signal_path = candidate / "signal.py"
    signal_path.write_text(
        "import os\n"
        "def compute_signal(fields):\n"
        "    os.unlink(__file__)\n"
        f"    os.link({str(secret)!r}, __file__)\n"
        "    open(__file__).read()\n"
        "    return fields['adjclose']\n"
    )
    monkeypatch.setattr(gates, "CANDIDATES_DIR", tmp_path)
    prices = make_prices(n_days=20, n_names=2)
    with pytest.raises(RuntimeError, match=r"operation denied: os\.remove"):
        compute_signal_isolated("C998", {"adjclose": prices})
    assert signal_path.is_file()
