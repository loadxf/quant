"""Scale frontier + multi-account EV (M10.c)."""

from __future__ import annotations

import numpy as np
import pytest

from quantlab.errors import QuantLabError
from quantlab.prop.frontier import compute_multiaccount, compute_scale_frontier
from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.prop.registry import load_firm

from ..conftest import random_log
from .conftest import day_trades, simple


class TestScaleFrontier:
    def test_scale_one_matches_plain_run(self) -> None:
        # The frontier's x1.0 point must equal a plain run_monte_carlo at
        # the same cfg — same seed, same numbers.
        log = random_log(n_days=80, mean=40.0, std=300.0, seed=3)
        firm = load_firm("topstep_50k")
        cfg = MCConfig(n_paths=300, seed=8)
        fr = compute_scale_frontier(log, firm, mc_cfg=cfg, scales=(0.5, 1.0))
        plain = run_monte_carlo(log, firm, cfg).economics
        point = next(p for p in fr.points if p.scale == 1.0)
        assert point.pass_prob == plain.pass_prob
        assert point.expected_net == plain.expected_net

    def test_ruin_monotone_in_scale(self) -> None:
        # Bigger size can never make the funded account safer: with common
        # random numbers, funded ruin is non-decreasing in scale.
        log = random_log(n_days=80, mean=30.0, std=350.0, seed=5)
        fr = compute_scale_frontier(
            log,
            load_firm("topstep_50k"),
            mc_cfg=MCConfig(n_paths=400, seed=2),
            scales=(0.5, 1.0, 2.0),
        )
        ruins = [p.risk_of_ruin_funded for p in fr.points]
        assert ruins == sorted(ruins)

    def test_constrained_pick_at_most_best_grid_scale(self) -> None:
        log = random_log(n_days=80, mean=30.0, std=350.0, seed=5)
        fr = compute_scale_frontier(
            log,
            load_firm("topstep_50k"),
            mc_cfg=MCConfig(n_paths=200, seed=2),
            scales=(0.5, 1.0, 1.5),
            ruin_cap=0.5,
        )
        if fr.best_scale_within_ruin is not None:
            point = next(p for p in fr.points if p.scale == fr.best_scale_within_ruin)
            assert point.risk_of_ruin_funded <= 0.5

    def test_bad_scales_raise(self) -> None:
        log = day_trades([[simple(100.0)]] * 40)
        with pytest.raises(QuantLabError, match="scales"):
            compute_scale_frontier(log, load_firm("topstep_50k"), scales=(0.0, 1.0))

    def test_json_serializable(self) -> None:
        import json

        from quantlab.report.jsonout import sanitize

        log = random_log(n_days=60, seed=4)
        fr = compute_scale_frontier(
            log, load_firm("topstep_50k"), mc_cfg=MCConfig(n_paths=100, seed=1), scales=(1.0,)
        )
        json.dumps(sanitize(fr.to_json_dict()))


class TestMultiAccount:
    def _report(self):
        log = random_log(n_days=80, mean=30.0, std=350.0, seed=5)
        return run_monte_carlo(log, load_firm("topstep_50k"), MCConfig(n_paths=400, seed=2))

    def test_correlated_identities(self) -> None:
        # Perfect correlation: EV and CVaR scale by exactly k; P(all lose)
        # never moves.
        report = self._report()
        eco = report.economics
        ma = compute_multiaccount(report, k_list=(2, 5))
        assert eco.net_per_path is not None
        p_lose = float(np.mean(eco.net_per_path < 0))
        for row in ma.rows:
            assert row.expected_net == pytest.approx(row.k * eco.expected_net)
            assert row.correlated_p_all_lose == pytest.approx(p_lose)
            assert row.correlated_cvar_95 == pytest.approx(row.k * eco.cvar_95)

    def test_independence_illusion_is_rosier(self) -> None:
        # The imagined independent portfolio always shows a smaller
        # P(all lose) and a milder CVaR than the correlated reality.
        report = self._report()
        ma = compute_multiaccount(report, k_list=(3,))
        row = ma.rows[0]
        assert row.independent_p_all_lose < row.correlated_p_all_lose
        assert row.independent_cvar_95 > row.correlated_cvar_95  # less negative

    def test_bad_k_raises(self) -> None:
        with pytest.raises(QuantLabError, match="accounts"):
            compute_multiaccount(self._report(), k_list=(0, 2))

    def test_json_serializable(self) -> None:
        import json

        from quantlab.report.jsonout import sanitize

        ma = compute_multiaccount(self._report(), k_list=(2,))
        json.dumps(sanitize(ma.to_json_dict()))


class TestSemanticsReviewFixes:
    """Regressions from the M10 adversarial review (semantics pass)."""

    def test_unseeded_frontier_still_gets_common_random_numbers(self) -> None:
        # Was: seed=None pulled fresh OS entropy per grid point, silently
        # voiding the CRN guarantee (and ruin monotonicity) for API users.
        log = random_log(n_days=80, mean=30.0, std=350.0, seed=5)
        fr = compute_scale_frontier(
            log,
            load_firm("topstep_50k"),
            mc_cfg=MCConfig(n_paths=300, seed=None),
            scales=(0.5, 1.0, 2.0),
        )
        ruins = [p.risk_of_ruin_funded for p in fr.points]
        assert ruins == sorted(ruins)
