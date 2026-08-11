import pandas as pd
import pytest
from edgelab.grammar import to_string
from edgelab.jsonutil import atomic_write_text
from edgelab.search import SearchResult, evolve, fitness_of


def test_search_rejects_corrupt_resume_checkpoint(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text('{"gen": 1, "pop":')
    with pytest.raises(RuntimeError, match="invalid search checkpoint"):
        evolve(
            {},
            pd.DataFrame(),
            population=2,
            generations=1,
            checkpoint_path=str(checkpoint),
        )


def test_atomic_text_replace_leaves_no_partial_artifact(tmp_path):
    path = tmp_path / "artifact.json"
    atomic_write_text(path, '{"complete":true}')
    assert path.read_text() == '{"complete":true}'
    assert list(tmp_path.glob(".*.tmp")) == []


def test_resume_checkpoint_is_bound_to_config_and_input_data(monkeypatch, tmp_path):
    import edgelab.search as search

    monkeypatch.setattr(search, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        search,
        "fitness_of",
        lambda expr, *args, **kwargs: SearchResult(expr, "ret1", 0.5, 0.48, 1),
    )
    index = pd.bdate_range("2020-01-01", periods=4)
    panel = pd.DataFrame({"A": [1.0, 2.0, 3.0, 4.0]}, index=index)
    evolve(
        {"ret1": panel},
        panel,
        population=2,
        generations=1,
        cost_bps=5,
        checkpoint_path="checkpoint.json",
    )
    with pytest.raises(RuntimeError, match="run identity"):
        evolve(
            {"ret1": panel},
            panel,
            population=2,
            generations=1,
            cost_bps=10,
            checkpoint_path="checkpoint.json",
        )
    with pytest.raises(RuntimeError, match="run identity"):
        evolve(
            {"ret1": panel},
            panel,
            population=2,
            generations=1,
            cost_bps=5,
            start_date="2020-01-02",
            checkpoint_path="checkpoint.json",
        )
    recovered = evolve(
        {"ret1": panel},
        panel,
        population=2,
        generations=1,
        cost_bps=5,
        checkpoint_path="checkpoint.json",
    )
    assert recovered
    changed = panel.copy()
    changed.iloc[-1, 0] = 99
    with pytest.raises(RuntimeError, match="run identity"):
        evolve(
            {"ret1": panel},
            changed,
            population=2,
            generations=1,
            cost_bps=5,
            checkpoint_path="checkpoint.json",
        )


def test_resume_reconstructs_rng_and_ignores_injected_expressions(monkeypatch, tmp_path):
    import json

    import edgelab.search as search

    monkeypatch.setattr(search, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(search, "random_expr", lambda rng: "ret1")
    monkeypatch.setattr(search, "mutate", lambda expr, rng: expr)
    monkeypatch.setattr(search, "crossover", lambda left, right, rng: left)
    seen = []

    def fake_fitness(expr, *args, **kwargs):
        key = to_string(expr)
        seen.append(key)
        return SearchResult(expr, key, 0.5, 0.48, 1)

    monkeypatch.setattr(search, "fitness_of", fake_fitness)
    index = pd.bdate_range("2020-01-01", periods=4)
    panel = pd.DataFrame({"A": [1.0, 2.0, 3.0, 4.0]}, index=index)
    kwargs = {
        "population": 2,
        "generations": 1,
        "checkpoint_path": "checkpoint.json",
    }
    evolve({"ret1": panel}, panel, **kwargs)
    state = json.loads((tmp_path / "checkpoint.json").read_text())
    state["pop"] = ["ret21", "ret21"]
    state["evaluated"] = ["ret21"]
    (tmp_path / "checkpoint.json").write_text(json.dumps(state))
    seen.clear()
    evolve({"ret1": panel}, panel, **kwargs)
    assert seen == ["ret1", "ret1"]


def test_search_fitness_preserves_warmup_and_uses_registered_start(monkeypatch):
    import types

    import edgelab.search as search

    dates = pd.bdate_range("2004-12-20", periods=20)
    prices = pd.DataFrame({"A": range(100, 120), "B": range(120, 100, -1)}, index=dates)
    terminal = prices.pct_change(fill_method=None).rolling(3).mean()
    captured = {}

    def fake_backtest(signal, adjclose, **kwargs):
        captured["signal_index"] = signal.index
        captured["start_date"] = kwargs["start_date"]
        return types.SimpleNamespace(
            sharpe_net=0.4,
            meta={"n_obs": 600},
        )

    monkeypatch.setattr(search, "run_backtest", fake_backtest)
    start = "2005-01-03"
    result = fitness_of(
        "ret1",
        {"ret1": terminal},
        prices,
        generation=0,
        cache={},
        start_date=start,
    )

    assert result.train_sharpe == 0.4
    assert captured["signal_index"].equals(dates)
    assert captured["signal_index"].min() < pd.Timestamp(start)
    assert captured["start_date"] == start
