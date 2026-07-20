import numpy as np
import pandas as pd

from quantlab.grammar import (
    MAX_DEPTH,
    MAX_NODES,
    TERMINALS,
    build_terminals,
    count_nodes,
    crossover,
    depth,
    evaluate,
    mutate,
    random_expr,
    to_string,
)


def make_panels(n_days=300, n_names=30, seed=4):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2016-01-01", periods=n_days)
    cols = [f"S{i:02d}" for i in range(n_names)]
    close = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0, 0.02, (n_days, n_names)), axis=0)),
        index=dates, columns=cols,
    )
    open_ = close * (1 + rng.normal(0, 0.005, close.shape))
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.01, close.shape))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.01, close.shape))
    volume = pd.DataFrame(
        rng.integers(1e5, 1e7, close.shape).astype(float), index=dates, columns=cols
    )
    return build_terminals(open_, high, low, close, close, volume)


def test_terminals_shapes_and_sanity():
    terms = make_panels()
    for name, panel in terms.items():
        assert panel.shape == terms["ret1"].shape, name
    assert terms["clv"].abs().max().max() <= 1.0 + 1e-9


def test_random_exprs_respect_bounds_and_evaluate():
    terms = make_panels()
    rng = np.random.default_rng(0)
    for _ in range(200):
        expr = random_expr(rng)
        assert depth(expr) <= MAX_DEPTH
        result = evaluate(expr, terms)
        assert result.shape == terms["ret1"].shape


def test_serialization_roundtrip_dedupes():
    rng = np.random.default_rng(1)
    seen = {to_string(random_expr(rng)) for _ in range(300)}
    assert len(seen) > 100  # grammar generates diverse expressions


def test_mutation_crossover_respect_bounds():
    rng = np.random.default_rng(2)
    for _ in range(200):
        a, b = random_expr(rng), random_expr(rng)
        m = mutate(a, rng)
        c = crossover(a, b, rng)
        for e in (m, c):
            assert depth(e) <= MAX_DEPTH
            assert count_nodes(e) <= MAX_NODES
            # crossover/mutation must return a well-formed expression: either a
            # terminal string from the grammar or an operator tuple
            assert isinstance(e, tuple) or e in TERMINALS


def test_no_future_leak_in_operators():
    """Every operator must be causal: value at t unchanged when future rows
    are truncated."""
    terms = make_panels()
    rng = np.random.default_rng(3)
    cut = 200
    truncated = {k: v.iloc[:cut] for k, v in terms.items()}
    for _ in range(60):
        expr = random_expr(rng)
        full = evaluate(expr, terms).iloc[cut - 5 : cut]
        part = evaluate(expr, truncated).iloc[cut - 5 : cut]
        pd.testing.assert_frame_equal(full, part, check_exact=False, atol=1e-12)
