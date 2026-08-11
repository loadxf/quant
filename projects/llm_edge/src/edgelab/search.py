"""Evolutionary search over the signal grammar (G2 mechanism).

Fitness = cost-adjusted TRAIN Sharpe minus a complexity penalty. The search
never sees validation or holdout data; after the run, the top distinct
expressions are evaluated once on validation by the Phase B driver (also via
the ledgered engine). Every fitness evaluation writes a trials-ledger row —
that is the multiple-testing bill the Deflated Sharpe Ratio later pays.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import REPO_ROOT
from .backtest import record_failed_trial, run_backtest
from .costs import EQUITY_BPS
from .grammar import (
    count_nodes,
    crossover,
    evaluate,
    mutate,
    parse_expr,
    random_expr,
    to_string,
)
from .jsonutil import atomic_write_text, dumps

COMPLEXITY_PENALTY = 0.02  # Sharpe points per grammar node


def _frame_digest(frame: pd.DataFrame) -> str:
    values = frame.to_numpy(dtype="<f8", copy=True)
    values[np.isnan(values)] = np.nan
    values[values == 0] = 0
    digest = hashlib.sha256()
    digest.update(pd.util.hash_pandas_object(frame.index, index=False).values.tobytes())
    digest.update(json.dumps(list(map(str, frame.columns)), separators=(",", ":")).encode())
    digest.update(values.tobytes(order="C"))
    return digest.hexdigest()


def _run_identity(
    terminals: dict[str, pd.DataFrame],
    adjclose: pd.DataFrame,
    *,
    population: int,
    generations: int,
    seed: int,
    elite_frac: float,
    holding_days: int,
    cost_bps: float,
    quantile: float,
    split: str,
    start_date: str | None,
) -> str:
    from .holdout_gate import engine_sha256, environment_sha256

    payload = {
        "population": population,
        "generations": generations,
        "seed": seed,
        "elite_frac": elite_frac,
        "holding_days": holding_days,
        "cost_bps": cost_bps,
        "quantile": quantile,
        "split": split,
        "start_date": start_date,
        "engine_sha256": engine_sha256(),
        "environment_sha256": environment_sha256(),
        "adjclose": _frame_digest(adjclose),
        "terminals": {name: _frame_digest(frame) for name, frame in sorted(terminals.items())},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _checkpoint_state(path, population: int, generations: int, run_identity: str):
    try:
        state = json.loads(path.read_text())
        if not isinstance(state, dict):
            raise TypeError("root must be an object")
        gen = state["gen"]
        pop = state["pop"]
        evaluated = state["evaluated"]
        history = state["history"]
        if state.get("run_identity") != run_identity:
            raise ValueError("run identity does not match the requested config or input data")
        if not isinstance(gen, int) or isinstance(gen, bool) or not 0 <= gen <= generations:
            raise ValueError("gen is outside the requested run")
        if (
            not isinstance(pop, list)
            or len(pop) != population
            or not all(isinstance(item, str) for item in pop)
        ):
            raise ValueError("pop does not match the configured population")
        if not isinstance(history, list) or len(history) != gen:
            raise ValueError("history length does not match gen")
        parsed_pop = [parse_expr(expression) for expression in pop]
        if not isinstance(evaluated, list) or not all(isinstance(item, str) for item in evaluated):
            raise ValueError("evaluated expression list is invalid")
        if len(set(evaluated)) != len(evaluated):
            raise ValueError("evaluated expression list contains duplicates")
        parsed_evaluated = [parse_expr(expression) for expression in evaluated]
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"invalid search checkpoint {path}: {exc}") from None
    # State is syntactically checked here, but never trusted as evolutionary
    # provenance. The deterministic run is reconstructed from its seed.
    return gen, parsed_pop, parsed_evaluated, history


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
    cost_bps: float = EQUITY_BPS,
    quantile: float = 0.1,
    split: str = "train_g2",
    start_date: str | None = None,
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
                start_date=start_date,
            )
            sr = result.sharpe_net
            if result.meta["n_obs"] < 500:
                sr = float("nan")
        except Exception as exc:
            if not getattr(exc, "_edgelab_trial_recorded", False):
                record_failed_trial(f"g2_gen{generation}", split, key, exc)
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
    cost_bps: float = EQUITY_BPS,
    quantile: float = 0.1,
    split: str = "train_g2",
    checkpoint_path: str | None = None,
    start_date: str | None = None,
) -> list[SearchResult]:
    """Run the evolutionary search; returns all evaluated results sorted by
    fitness. Deterministic under the fixed seed. A checkpoint records progress
    and the bound run identity, but editable local state is not accepted as
    search provenance: recovery deterministically replays from generation 0
    and re-ledgers the work. This favors integrity over fast resume.
    """
    if population < 2 or generations < 1:
        raise ValueError("population must be >= 2 and generations >= 1")
    if not 0 < elite_frac <= 1 or max(2, int(population * elite_frac)) > population:
        raise ValueError("elite_frac must retain between 2 and population members")
    if holding_days < 1 or not 0 < quantile <= 0.5 or cost_bps < 0:
        raise ValueError("invalid holding_days, quantile, or cost_bps")
    canonical_start = None
    if start_date is not None:
        if not isinstance(start_date, str):
            raise ValueError("start_date must be an ISO date string")
        try:
            parsed_start = pd.Timestamp(start_date)
        except ValueError as exc:
            raise ValueError("start_date must be an ISO date string") from exc
        if pd.isna(parsed_start) or parsed_start.tz is not None:
            raise ValueError("start_date must be a finite timezone-naive date")
        canonical_start = str(parsed_start.normalize().date())
    ckpt = REPO_ROOT / checkpoint_path if checkpoint_path else None
    run_identity = _run_identity(
        terminals,
        adjclose,
        population=population,
        generations=generations,
        seed=seed,
        elite_frac=elite_frac,
        holding_days=holding_days,
        cost_bps=cost_bps,
        quantile=quantile,
        split=split,
        start_date=canonical_start,
    )
    cache: dict[str, float] = {}
    history: list[dict] = []
    if ckpt is not None and ckpt.exists():
        _checkpoint_state(ckpt, population, generations, run_identity)
    # A checkpoint is editable local input and therefore cannot authenticate
    # which expressions the registered RNG generated. Reconstruct from the
    # bound seed and conservatively re-score every generation. This still
    # recovers killed runs without allowing expression injection; the extra
    # ledger rows make multiple-testing correction more conservative.
    start_gen = 0
    init_rng = np.random.default_rng([seed, 0])
    pop = [random_expr(init_rng) for _ in range(population)]
    all_results: dict[str, SearchResult] = {}

    for gen in range(start_gen, generations):
        scored = [
            fitness_of(
                e,
                terminals,
                adjclose,
                gen,
                cache,
                holding_days=holding_days,
                cost_bps=cost_bps,
                quantile=quantile,
                split=split,
                start_date=canonical_start,
            )
            for e in pop
        ]
        for s in scored:
            if s.expr_str not in all_results or s.fitness > all_results[s.expr_str].fitness:
                all_results[s.expr_str] = s
        scored.sort(key=lambda s: s.fitness, reverse=True)
        best = scored[0]
        history.append(
            {
                "generation": gen,
                "best_fitness": best.fitness,
                "best_train_sr": best.train_sharpe,
                "best_expr": best.expr_str,
                "evaluated": len(cache),
            }
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
            atomic_write_text(
                ckpt,
                dumps(
                    {
                        "gen": gen + 1,
                        "run_identity": run_identity,
                        "pop": [to_string(e) for e in pop],
                        "evaluated": list(all_results),
                        "history": history,
                    }
                ),
            )

    # Current-run cache entries include every expression evaluated by the
    # deterministic run or recovery replay.
    for key, sr in cache.items():
        if key not in all_results:
            expr = parse_expr(key)
            fit = (sr if np.isfinite(sr) else -9.0) - COMPLEXITY_PENALTY * count_nodes(expr)
            all_results[key] = SearchResult(expr, key, sr, fit, count_nodes(expr))

    if log_path:
        atomic_write_text(REPO_ROOT / log_path, dumps(history, indent=1))
    return sorted(all_results.values(), key=lambda s: s.fitness, reverse=True)
