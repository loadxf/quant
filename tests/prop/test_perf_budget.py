from __future__ import annotations

import time

import pytest

from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.prop.registry import load_firm

from ..conftest import random_log


@pytest.mark.slow
def test_10k_paths_250_days_under_10s() -> None:
    log = random_log(n_days=250, trades_per_day=4, seed=99, with_excursions=True)
    firm = load_firm("topstep_50k")
    cfg = MCConfig(n_paths=10_000, seed=1, challenge_horizon_days=250, funded_horizon_days=250)
    start = time.perf_counter()
    run_monte_carlo(log, firm, cfg)
    elapsed = time.perf_counter() - start
    assert elapsed < 10.0, f"{elapsed:.2f}s exceeds the 10s budget"


@pytest.mark.slow
def test_vol_target_sizing_stays_in_budget() -> None:
    log = random_log(n_days=120, mean=30.0, std=200.0, seed=2)
    cfg = MCConfig(
        n_paths=10_000,
        seed=1,
        challenge_horizon_days=250,
        funded_horizon_days=250,
        sizing="vol_target",
    )
    start = time.perf_counter()
    run_monte_carlo(log, load_firm("topstep_50k"), cfg)
    elapsed = time.perf_counter() - start
    assert elapsed < 10.0, f"{elapsed:.2f}s exceeds the 10s budget with dynamic sizing"
