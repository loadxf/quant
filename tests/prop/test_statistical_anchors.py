"""Statistical validation anchors — exact analytic results the engine must hit.

For zero-EV (martingale) trade sequences in the diffusion limit:

1. STATIC barriers (floor D below, target T above):
       P(pass) = D / (T + D)                    [gambler's ruin]
   independent of risk geometry (win rate / RR), up to jump overshoot.

2. PURE TRAILING drawdown D, target T (uncapped, any ratchet):
       P(pass) = exp(-T / D)                    [drawdown of driftless BM]
   ALSO independent of geometry — Brownian scale invariance: volatility
   rescales time, not probability. This refines the popular claim that
   low-RR/high-win-rate geometry passes trailing challenges more often:
   the effect does NOT come from the trailing barrier itself.

3. Geometry sensitivity appears only through rules with ABSOLUTE
   day-scale parameters. A binding daily loss limit punishes geometries
   whose daily loss distribution reaches it: at $250 risk/trade x 4
   trades, a 20%-win-rate strategy posts a -$1,000 day 41% of the time
   (0.8^4) while a 67%-win-rate one almost never does.
"""

from __future__ import annotations

import math

import pytest

from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.prop.registry import load_firm
from quantlab.prop.synthetic import synthetic_geometry_log

from .conftest import make_firm

# Zero-EV geometries: win_rate * rr = 1 - win_rate
GEOMETRIES = [
    dict(win_rate=0.2, rr=4.0),
    dict(win_rate=0.5, rr=1.0),
    dict(win_rate=2 / 3, rr=0.5),
]
IDS = ["rr4", "rr1", "rr0.5"]


def _pass_prob(firm, geometry, risk=100.0, paths=3000, horizon=900, seed=42) -> float:
    log = synthetic_geometry_log(
        win_rate=geometry["win_rate"],
        rr=geometry["rr"],
        trades_per_day=4,
        risk=risk,
        ev=0.0,
        days=300,
        seed=seed,
    )
    cfg = MCConfig(
        n_paths=paths,
        seed=seed,
        challenge_horizon_days=horizon,
        funded_horizon_days=10,  # funded phase irrelevant here
    )
    return run_monte_carlo(log, firm, cfg).economics.pass_prob


@pytest.mark.slow
class TestGamblersRuinAnchor:
    """Static $2,000 floor, $3,000 target: P ~ 2000/5000 = 0.40 for every
    geometry."""

    @pytest.mark.parametrize("geometry", GEOMETRIES, ids=IDS)
    def test_pass_prob_matches_theory(self, geometry) -> None:
        firm = make_firm([{"type": "static_max_loss", "amount": 2000}], target=3000)
        p = _pass_prob(firm, geometry)
        assert p == pytest.approx(0.40, abs=0.05), (
            f"geometry {geometry} gave {p:.3f}, expected ~0.40 (D/(T+D))"
        )


@pytest.mark.slow
class TestTrailingDrawdownAnchor:
    """Uncapped trailing $2,000, target $3,000: P ~ exp(-1.5) = 0.223 for
    every geometry (scale invariance)."""

    EXPECTED = math.exp(-1.5)

    @pytest.mark.parametrize("geometry", GEOMETRIES, ids=IDS)
    def test_pass_prob_matches_theory(self, geometry) -> None:
        firm = make_firm(
            [{"type": "trailing_drawdown", "amount": 2000, "ratchet": "intraday"}],
            target=3000,
        )
        p = _pass_prob(firm, geometry, horizon=600)
        assert p == pytest.approx(self.EXPECTED, abs=0.045), (
            f"geometry {geometry} gave {p:.3f}, expected ~{self.EXPECTED:.3f} (exp(-T/D))"
        )


@pytest.mark.slow
class TestDailyRuleGeometrySensitivity:
    """A binding daily loss limit breaks scale invariance: at $250 risk the
    rr4 geometry hits the -$1,000 DLL on 41% of days and must pass far less
    often than rr0.5, which almost never hits it."""

    def test_dll_punishes_fat_daily_left_tail(self) -> None:
        firm = make_firm(
            [
                {
                    "type": "trailing_drawdown",
                    "amount": 2000,
                    "ratchet": "eod",
                    "threshold_cap": 50_000,
                },
                {"type": "daily_loss_limit", "amount": 1000, "effect": "fail"},
            ],
            target=3000,
        )
        p_rr4 = _pass_prob(firm, GEOMETRIES[0], risk=250.0, horizon=600)
        p_rr05 = _pass_prob(firm, GEOMETRIES[2], risk=250.0, horizon=600)
        assert p_rr05 > p_rr4 + 0.05, f"expected clear gap, got rr4={p_rr4:.3f} rr0.5={p_rr05:.3f}"

    def test_current_topstep_rules_are_geometry_flat(self) -> None:
        """Today's Topstep Combine (no DLL since Aug 2024) shows no material
        geometry effect at small trade sizes — the scale-invariant regime."""
        firm = load_firm("topstep_50k")
        probs = [_pass_prob(firm, g, horizon=600) for g in GEOMETRIES]
        assert max(probs) - min(probs) < 0.05, f"unexpectedly geometry-sensitive: {probs}"
