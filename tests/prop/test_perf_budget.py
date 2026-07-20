from __future__ import annotations

import os
import time

import pytest

from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.prop.registry import load_firm

from ..conftest import random_log

# Shared CI runners can be several times slower than a dev machine; the
# budget stays strict locally while QUANTLAB_PERF_FACTOR grants headroom
# where the hardware, not the code, is the variable.
BUDGET_S = 10.0 * float(os.environ.get("QUANTLAB_PERF_FACTOR", "1"))


@pytest.mark.slow
def test_10k_paths_250_days_under_10s() -> None:
    log = random_log(n_days=250, trades_per_day=4, seed=99, with_excursions=True)
    firm = load_firm("topstep_50k")
    cfg = MCConfig(n_paths=10_000, seed=1, challenge_horizon_days=250, funded_horizon_days=250)
    start = time.perf_counter()
    run_monte_carlo(log, firm, cfg)
    elapsed = time.perf_counter() - start
    assert elapsed < BUDGET_S, f"{elapsed:.2f}s exceeds the {BUDGET_S:.0f}s budget"


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
    assert elapsed < BUDGET_S, f"{elapsed:.2f}s exceeds the {BUDGET_S:.0f}s budget with sizing"
