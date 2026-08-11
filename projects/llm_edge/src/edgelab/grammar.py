"""Signal-expression DSL for the G2 generation mechanism (protocol.md sec. 8).

Design intent: the LLM chooses this grammar ONCE (a prior over signal shapes);
the evolutionary search in search.py then explores it guided only by data
fitness. Novelty provenance of a surviving expression is therefore "P-derived"
at the selection level: the data, not the model, picked it.

Expressions are nested tuples, e.g.::

    ("cs_rank", ("roll_mean", ("mul", "ret1", "volz"), 10))

They serialize to a canonical string (used for dedupe and for spec files) and
evaluate against a dict of terminal panels (date x ticker DataFrames).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

WINDOWS = [3, 5, 10, 21, 63]
LAGS = [1, 2, 5, 10, 21]

TERMINALS = ["ret1", "ret5", "ret21", "gap", "intraday", "rng", "volz", "clv"]

UNARY = ["cs_rank", "sign", "neg", "abs_"]
ROLLING = ["roll_mean", "roll_std", "roll_skew", "ts_rank", "delta", "lag"]
BINARY = ["mul", "sub", "div"]

MAX_DEPTH = 5
MAX_NODES = 13


def build_terminals(
    open_: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    close: pd.DataFrame,
    adjclose: pd.DataFrame,
    volume: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Compute the terminal panels once; expressions only combine these."""
    ret1 = adjclose.pct_change(fill_method=None)
    logvol = np.log(volume.where(volume > 0))
    volz = (logvol - logvol.rolling(63).mean()) / logvol.rolling(63).std()
    span = high - low
    return {
        "ret1": ret1,
        "ret5": adjclose.pct_change(5, fill_method=None),
        "ret21": adjclose.pct_change(21, fill_method=None),
        "gap": open_ / close.shift(1) - 1.0,
        "intraday": close / open_ - 1.0,
        "rng": span / close,
        "volz": volz,
        "clv": ((close - low) - (high - close)) / span.where(span > 0),
    }


def evaluate(expr, terminals: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if isinstance(expr, str):
        return terminals[expr]
    op = expr[0]
    if op in ("roll_mean", "roll_std", "roll_skew", "ts_rank", "delta", "lag"):
        x = evaluate(expr[1], terminals)
        w = expr[2]
        if op == "roll_mean":
            return x.rolling(w, min_periods=max(2, w // 2)).mean()
        if op == "roll_std":
            return x.rolling(w, min_periods=max(2, w // 2)).std()
        if op == "roll_skew":
            return x.rolling(max(w, 5), min_periods=max(3, w // 2)).skew()
        if op == "ts_rank":
            return x.rolling(w, min_periods=max(2, w // 2)).rank(pct=True)
        if op == "delta":
            return x - x.shift(w)
        if op == "lag":
            return x.shift(w)
    if op == "cs_rank":
        return evaluate(expr[1], terminals).rank(axis=1, pct=True) - 0.5
    if op == "sign":
        return np.sign(evaluate(expr[1], terminals))
    if op == "neg":
        return -evaluate(expr[1], terminals)
    if op == "abs_":
        return evaluate(expr[1], terminals).abs()
    if op in ("mul", "sub", "div"):
        x = evaluate(expr[1], terminals)
        y = evaluate(expr[2], terminals)
        if op == "mul":
            return x * y
        if op == "sub":
            return x - y
        denom = y.where(y.abs() > 1e-9)
        return x / denom
    raise ValueError(f"unknown op {op}")


def to_string(expr) -> str:
    if isinstance(expr, str):
        return expr
    return (
        "(" + " ".join(to_string(e) if isinstance(e, (tuple, str)) else str(e) for e in expr) + ")"
    )


def parse_expr(s: str):
    """Inverse of to_string: parse '(op child .. )' S-expressions back to tuples."""
    if not isinstance(s, str) or not s.strip():
        raise ValueError("expression must be a non-empty string")
    tokens = s.replace("(", " ( ").replace(")", " ) ").split()
    pos = 0

    def parse():
        nonlocal pos
        if pos >= len(tokens):
            raise ValueError(f"unterminated expression: {s}")
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            items = []
            while True:
                if pos >= len(tokens):
                    raise ValueError(f"unterminated expression: {s}")
                if tokens[pos] == ")":
                    break
                items.append(parse())
            pos += 1
            if not items:
                raise ValueError("empty expression is invalid")
            return tuple(items)
        if tok == ")":
            raise ValueError(f"unexpected ')' in expression: {s}")
        if tok.lstrip("-").isdigit():
            return int(tok)
        return tok

    result = parse()
    if pos != len(tokens):
        raise ValueError(f"trailing tokens in expression: {s}")
    _validate_expr(result)
    if depth(result) > MAX_DEPTH or count_nodes(result) > MAX_NODES:
        raise ValueError("expression exceeds the grammar complexity bounds")
    return result


def _validate_expr(expr) -> None:
    if isinstance(expr, str):
        if expr not in TERMINALS:
            raise ValueError(f"unknown terminal {expr!r}")
        return
    if not isinstance(expr, tuple) or not expr or not isinstance(expr[0], str):
        raise ValueError(f"invalid expression node {expr!r}")
    op = expr[0]
    if op in UNARY:
        if len(expr) != 2:
            raise ValueError(f"{op} expects one operand")
        _validate_expr(expr[1])
        return
    if op in ROLLING:
        allowed = LAGS if op in ("lag", "delta") else WINDOWS
        if len(expr) != 3 or type(expr[2]) is not int or expr[2] not in allowed:
            raise ValueError(f"{op} window must be one of {allowed}")
        _validate_expr(expr[1])
        return
    if op in BINARY:
        if len(expr) != 3:
            raise ValueError(f"{op} expects two operands")
        _validate_expr(expr[1])
        _validate_expr(expr[2])
        return
    raise ValueError(f"unknown op {op!r}")


def count_nodes(expr) -> int:
    if isinstance(expr, str):
        return 1
    return 1 + sum(count_nodes(e) for e in expr[1:] if isinstance(e, (tuple, str)))


def depth(expr) -> int:
    if isinstance(expr, str):
        return 1
    return 1 + max(depth(e) for e in expr[1:] if isinstance(e, (tuple, str)))


def random_expr(rng: np.random.Generator, max_depth: int = MAX_DEPTH):
    """Grow a random expression within depth AND node bounds."""
    for _ in range(50):
        expr = _grow(rng, max_depth)
        if count_nodes(expr) <= MAX_NODES:
            return expr
    return TERMINALS[rng.integers(len(TERMINALS))]


def _grow(rng: np.random.Generator, max_depth: int):
    if max_depth <= 1 or rng.random() < 0.3:
        return TERMINALS[rng.integers(len(TERMINALS))]
    roll = rng.random()
    if roll < 0.35:
        op = ROLLING[rng.integers(len(ROLLING))]
        w = (LAGS if op in ("lag", "delta") else WINDOWS)[rng.integers(5)]
        return (op, _grow(rng, max_depth - 1), int(w))
    if roll < 0.6:
        op = UNARY[rng.integers(len(UNARY))]
        return (op, _grow(rng, max_depth - 1))
    op = BINARY[rng.integers(len(BINARY))]
    return (op, _grow(rng, max_depth - 1), _grow(rng, max_depth - 1))


def _subtrees(expr, path=()):
    yield path, expr
    if not isinstance(expr, str):
        for i, child in enumerate(expr[1:], start=1):
            if isinstance(child, (tuple, str)):
                yield from _subtrees(child, (*path, i))


def _replace(expr, path, new):
    if not path:
        return new
    expr = list(expr)
    expr[path[0]] = _replace(expr[path[0]], path[1:], new)
    return tuple(expr)


def mutate(expr, rng: np.random.Generator):
    """Replace a random subtree with a fresh random expression."""
    nodes = list(_subtrees(expr))
    path, _ = nodes[rng.integers(len(nodes))]
    candidate = _replace(expr, path, random_expr(rng, max_depth=3)) if path else random_expr(rng)
    if depth(candidate) > MAX_DEPTH or count_nodes(candidate) > MAX_NODES:
        return expr
    return candidate


def crossover(a, b, rng: np.random.Generator):
    """Swap a random subtree of a with a random subtree of b."""
    nodes_a = list(_subtrees(a))
    nodes_b = list(_subtrees(b))
    path, _ = nodes_a[rng.integers(len(nodes_a))]
    _, donor = nodes_b[rng.integers(len(nodes_b))]
    child = _replace(a, path, donor) if path else donor
    if isinstance(child, str) or depth(child) > MAX_DEPTH or count_nodes(child) > MAX_NODES:
        return a
    return child
