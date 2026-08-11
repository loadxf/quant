from __future__ import annotations

import numpy as np
import pytest

from quantlab.metrics.core import compute_metrics
from quantlab.metrics.deflate import compute_deflated
from quantlab.metrics.scorecard import compute_scorecard

from ..conftest import random_log, trades_from_daily


class TestPillars:
    def test_strong_winner_grades_high(self) -> None:
        # 150 days x 4 trades, strong steady edge
        log = random_log(n_days=150, trades_per_day=4, mean=60.0, std=140.0, seed=21)
        verdict = compute_scorecard(log)
        assert verdict.edge.grade in ("A", "B")
        assert verdict.sample.grade in ("A", "B")
        assert verdict.overall in ("A", "B")
        assert not verdict.capped_by_sample

    def test_zero_edge_grades_f(self) -> None:
        log = random_log(n_days=150, mean=0.0, std=200.0, seed=22)
        verdict = compute_scorecard(log)
        assert verdict.edge.grade == "F"
        assert verdict.overall in ("D", "F")

    def test_small_sample_caps_overall(self) -> None:
        """A pristine 30-trade log cannot out-grade its sample pillar."""
        log = trades_from_daily([[300.0, -80.0]] * 15)  # 30 trades, strong PF
        verdict = compute_scorecard(log)
        assert verdict.sample.grade == "F"  # n=30 < 75
        assert verdict.overall == "F"
        assert verdict.capped_by_sample

    def test_json_shape(self) -> None:
        log = random_log(n_days=60, seed=23)
        payload = compute_scorecard(log).to_json_dict()
        assert set(payload) == {"overall", "points", "capped_by_sample", "pillars", "flags"}
        assert set(payload["pillars"]) == {"edge", "robustness", "risk", "sample"}
        assert len(payload["flags"]) == 10  # M10 adds regime_dependent_edge

    def test_supplied_deflated_stats_must_match_declared_trials(self) -> None:
        log = random_log(n_days=30, seed=25)
        stats = compute_deflated(np.array([trade.pnl for trade in log]), n_trials=2)
        with pytest.raises(ValueError, match="use 2 trials"):
            compute_scorecard(log, trials=3, deflated=stats)


class TestRiskPillar:
    def test_outsized_worst_loss_downgrades(self) -> None:
        # Same MAR-ish profile, one catastrophic loss 12x the average
        steady = trades_from_daily([[120.0, -60.0]] * 100)
        vs = compute_scorecard(steady, compute_metrics(steady, starting_equity=20_000))
        with_tail = trades_from_daily([[120.0, -60.0]] * 99 + [[120.0, -900.0]])
        vt = compute_scorecard(with_tail, compute_metrics(with_tail, starting_equity=20_000))
        order = "ABCDF"
        assert order.index(vt.risk.grade) >= order.index(vs.risk.grade)


class TestRobustnessSharesBootstrapRun:
    """Pass-2 regression: the robustness pillar re-ran the bootstrap with
    hard-coded (4000, seed 7), disagreeing with a caller-configured
    expectancy CI and doubling the most expensive computation."""

    def test_p_positive_comes_from_metrics(self) -> None:
        import pytest

        log = random_log(n_days=40, trades_per_day=2, mean=20.0, std=150.0, seed=99)
        metrics = compute_metrics(log, bootstrap_samples=500, seed=123)
        verdict = compute_scorecard(log, metrics)
        assert verdict.robustness.inputs["p_expectancy_positive"] == pytest.approx(
            metrics.bootstrap_p_positive
        )


class TestHandBuiltMetricsRecomputes:
    """Pass-3 regression: a Metrics without bootstrap_p_positive (hand-built
    or deserialized from a pre-upgrade report) must not silently grade
    robustness F — None means unknown, and the scorecard recomputes."""

    def test_none_sentinel_recomputes_instead_of_f(self) -> None:
        import dataclasses

        log = random_log(n_days=150, trades_per_day=4, mean=60.0, std=140.0, seed=21)
        metrics = compute_metrics(log)
        stripped = dataclasses.replace(metrics, bootstrap_p_positive=None)
        full = compute_scorecard(log, metrics)
        rebuilt = compute_scorecard(log, stripped)
        assert rebuilt.robustness.grade == full.robustness.grade
        assert rebuilt.robustness.inputs["p_expectancy_positive"] > 0.5
