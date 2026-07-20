"""Evolutionary search over the signal grammar (G2 mechanism).

Fitness = cost-adjusted TRAIN Sharpe minus a complexity penalty. The search
never sees validation or holdout data; after the run, the top distinct
expressions are evaluated once on validation by the Phase B driver (also via
the ledgered engine). Every fitness evaluation writes a trials-ledger row —
that is the multiple-testing bill the Deflated Sharpe Ratio later pays.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import REPO_ROOT
from .backtest import run_backtest
from .grammar import (
    count_nodes,
    crossover,
    evaluate,
    mutate,
    parse_expr,
    random_expr,
    to_string,
)

COMPLEXITY_PENALTY = 0.02  # Sharpe points per grammar node


@dataclass
class SearchResult:
    expr: tuple | str
    expr_str: str
    train_sharpe: float
    fitness: float
    n_nodes: int


def fitness_of(
    expr,
    terminals: dict[str, pd.DataFrame],
    adjclose: pd.DataFrame,
    generation: int,
    cache: dict[str, float],
    holding_days: int = 1,
    cost_bps: float = 10.0,
    quantile: float = 0.1,
    split: str = "train_g2",
) -> SearchResult:
    key = to_string(expr)
    n_nodes = count_nodes(expr)
    if key in cache:
        sr = cache[key]
    else:
        try:
            signal = evaluate(expr, terminals)
            result = run_backtest(
                signal,
                adjclose,
                candidate_id=f"g2_gen{generation}",
                split=split,
                cost_bps=cost_bps,
                holding_days=holding_days,
                quantile=quantile,
            )
            sr = result.sharpe_net
            if result.meta["n_obs"] < 500:
                sr = float("nan")
        except Exception:  # noqa: BLE001 - degenerate expressions score nan
            sr = float("nan")
        cache[key] = sr
    fit = (sr if np.isfinite(sr) else -9.0) - COMPLEXITY_PENALTY * n_nodes
    return SearchResult(expr, key, sr, fit, n_nodes)


def evolve(
    terminals: dict[str, pd.DataFrame],
    adjclose: pd.DataFrame,
    population: int = 120,
    generations: int = 8,
    seed: int = 20260719,
    elite_frac: float = 0.15,
    log_path: str | None = None,
    holding_days: int = 1,
    cost_bps: float = 10.0,
    quantile: float = 0.1,
    split: str = "train_g2",
    checkpoint_path: str | None = None,
) -> list[SearchResult]:
    """Run the evolutionary search; returns all evaluated results sorted by
    fitness. Deterministic under the fixed seed. With ``checkpoint_path`` the
    state (population, fitness cache, history) is saved after every generation
    and a killed run resumes at the start of the interrupted generation —
    already-scored expressions replay from the cache without new ledger rows.
    Per-generation RNG streams (seeded by [seed, gen]) keep breeding
    deterministic across resumes.
    """
    ckpt = REPO_ROOT / checkpoint_path if checkpoint_path else None
    cache: dict[str, float] = {}
    history: list[dict] = []
    start_gen = 0
    if ckpt is not None and ckpt.exists():
        state = json.loads(ckpt.read_text())
        cache = {k: float(v) for k, v in state["cache"].items()}
        history = state["history"]
        start_gen = state["gen"]
        pop = [parse_expr(s) for s in state["pop"]]
    else:
        init_rng = np.random.default_rng([seed, 0])
        pop = [random_expr(init_rng) for _ in range(population)]
    all_results: dict[str, SearchResult] = {}

    for gen in range(start_gen, generations):
        scored = [
            fitness_of(
                e, terminals, adjclose, gen, cache,
                holding_days=holding_days, cost_bps=cost_bps,
                quantile=quantile, split=split,
            )
            for e in pop
        ]
        for s in scored:
            if s.expr_str not in all_results or s.fitness > all_results[s.expr_str].fitness:
                all_results[s.expr_str] = s
        scored.sort(key=lambda s: s.fitness, reverse=True)
        best = scored[0]
        history.append(
            {"generation": gen, "best_fitness": best.fitness, "best_train_sr": best.train_sharpe,
             "best_expr": best.expr_str, "evaluated": len(cache)}
        )
        rng = np.random.default_rng([seed, gen + 1])
        n_elite = max(2, int(population * elite_frac))
        elites = [s.expr for s in scored[:n_elite]]
        children = list(elites)
        while len(children) < population:
            roll = rng.random()
            if roll < 0.45:
                a, b = (elites[rng.integers(n_elite)] for _ in range(2))
                children.append(crossover(a, b, rng))
            elif roll < 0.85:
                children.append(mutate(elites[rng.integers(n_elite)], rng))
            else:
                children.append(random_expr(rng))
        pop = children
        if ckpt is not None:
            ckpt.write_text(json.dumps(
                {"gen": gen + 1, "pop": [to_string(e) for e in pop],
                 "cache": cache, "history": history}
            ))

    # On resume, earlier generations' bests live only in cache/history; rebuild
    # result objects for every cached expression so ranking sees the full run.
    for key, sr in cache.items():
        if key not in all_results:
            expr = parse_expr(key)
            fit = (sr if np.isfinite(sr) else -9.0) - COMPLEXITY_PENALTY * count_nodes(expr)
            all_results[key] = SearchResult(expr, key, sr, fit, count_nodes(expr))

    if log_path:
        (REPO_ROOT / log_path).write_text(json.dumps(history, indent=1))
    return sorted(all_results.values(), key=lambda s: s.fitness, reverse=True)
