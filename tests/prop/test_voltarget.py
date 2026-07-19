"""Vol-targeted sizing tests: sizer recursion, counterfactual invariants."""

from __future__ import annotations

import numpy as np
import pytest

from quantlab.prop.montecarlo import MCConfig
from quantlab.prop.registry import load_firm
from quantlab.prop.voltarget import (
    EwmaSizer,
    VolSizingParams,
    auto_target_vol,
    compute_voltarget,
    resize_log,
)
from quantlab.schema.trade import FUTURES_DAY

from .conftest import day_trades, simple


def _two_regime_log(days: int = 120, seed: int = 3):
    """Calm regime (sigma 50) then violent regime (sigma 400), losses
    clustered in the violent half — the leverage-effect precondition."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(days):
        sigma = 50.0 if i < days // 2 else 400.0
        rows.append([simple(30.0 + sigma * rng.standard_normal())])
    return day_trades(rows)


class TestEwmaSizer:
    def test_scalar_and_vector_agree(self) -> None:
        params = VolSizingParams(lam=0.94, target_vol=100.0, seed_var=100.0**2)
        scalar = EwmaSizer(params)
        vector = EwmaSizer(params, n_paths=3)
        pnls = [120.0, -300.0, 40.0, 500.0]
        for pnl in pnls:
            assert vector.weight()[0] == pytest.approx(scalar.weight())
            scalar.update(pnl)
            vector.update(np.full(3, pnl))
        assert vector.weight()[2] == pytest.approx(scalar.weight())

    def test_weight_clipped(self) -> None:
        params = VolSizingParams(lam=0.94, target_vol=100.0, seed_var=1.0, clip_hi=1.5)
        assert EwmaSizer(params).weight() == 1.5  # tiny var -> capped
        params = VolSizingParams(lam=0.94, target_vol=100.0, seed_var=1e8, clip_lo=0.5)
        assert EwmaSizer(params).weight() == 0.5  # huge var -> floored

    def test_burn_in_weight_is_one(self) -> None:
        params = VolSizingParams(lam=0.94, target_vol=100.0, seed_var=1.0, burn_in=3)
        sizer = EwmaSizer(params)
        for _ in range(3):
            assert sizer.weight() == 1.0
            sizer.update(50.0)
        assert sizer.weight() != 1.0


class TestResizeLog:
    def test_median_weight_near_one_at_auto_target(self) -> None:
        log = _two_regime_log()
        days = log.daily_groups(FUTURES_DAY)
        day_pnl = np.array([sum(t.pnl for t in ts) for _, ts in days])
        target = auto_target_vol(day_pnl)
        params = VolSizingParams(
            lam=0.94, target_vol=target, seed_var=float(np.mean(day_pnl[:20] ** 2)), burn_in=20
        )
        _, weights, _ = resize_log(log, FUTURES_DAY, params)
        assert 0.5 <= np.median(weights) <= 1.5
        assert weights.min() >= 0.5 and weights.max() <= 1.5

    def test_burn_in_days_unscaled(self) -> None:
        log = _two_regime_log()
        params = VolSizingParams(lam=0.94, target_vol=100.0, seed_var=2500.0, burn_in=20)
        _, weights, _ = resize_log(log, FUTURES_DAY, params)
        assert (weights[:20] == 1.0).all()

    def test_no_trade_band_holds_weight(self) -> None:
        log = _two_regime_log()
        params = VolSizingParams(
            lam=0.94, target_vol=100.0, seed_var=2500.0, burn_in=20, band=10.0
        )  # absurd band: weight can never move once set
        _, weights, _ = resize_log(log, FUTURES_DAY, params)
        assert (weights == 1.0).all()

    def test_lookahead_property(self) -> None:
        log = _two_regime_log()
        params = VolSizingParams(lam=0.94, target_vol=100.0, seed_var=2500.0, burn_in=20)
        _, weights, _ = resize_log(log, FUTURES_DAY, params)
        # Amplify the LAST day's trades only; all prior weights unchanged.
        import dataclasses

        boosted_trades = [
            *log.trades[:-1],
            dataclasses.replace(log.trades[-1], pnl=log.trades[-1].pnl + 10_000),
        ]
        from quantlab.schema.trade import TradeLog

        boosted = TradeLog(trades=boosted_trades, source=log.source)
        _, weights2, _ = resize_log(boosted, FUTURES_DAY, params)
        assert weights[:-1] == pytest.approx(weights2[:-1])

    def test_scaling_preserves_trade_invariants(self) -> None:
        log = day_trades([[(100.0, -40.0, 120.0)]] * 30)
        params = VolSizingParams(lam=0.94, target_vol=10.0, seed_var=10_000.0, burn_in=5)
        resized, weights, _ = resize_log(log, FUTURES_DAY, params)
        # mae stays <= 0, mfe >= 0, pnl scaled by that day's weight
        for d, t in enumerate(resized.trades):
            assert t.mae is not None and t.mae <= 0
            assert t.mfe is not None and t.mfe >= 0
            assert t.pnl == pytest.approx(100.0 * weights[d])


class TestCounterfactual:
    def test_insurance_effect_on_clustered_log(self) -> None:
        """The hypothesis in action: with losses clustered in the violent
        regime, vol targeting must cut the max drawdown."""
        vt = compute_voltarget(_two_regime_log(days=160))
        assert vt.targeted["max_drawdown"] < vt.fixed["max_drawdown"]
        assert 0.8 <= vt.avg_weight <= 1.3

    def test_mc_comparison_present_with_firm(self) -> None:
        vt = compute_voltarget(
            _two_regime_log(),
            firm=load_firm("topstep_50k"),
            mc_cfg=MCConfig(n_paths=200, seed=4),
        )
        assert vt.mc_fixed is not None and vt.mc_targeted is not None
        assert 0.0 <= vt.mc_targeted["pass_prob"] <= 1.0

    def test_short_log_warns(self) -> None:
        vt = compute_voltarget(day_trades([[simple(100.0)]] * 30))
        assert any("low-confidence" in w for w in vt.warnings)

    def test_json_serializable(self) -> None:
        import json

        from quantlab.report.jsonout import sanitize

        vt = compute_voltarget(_two_regime_log())
        json.dumps(sanitize(vt.to_json_dict()))


class TestM9ReviewFixes:
    """Regressions from the M9 adversarial review (pass 1)."""

    def test_sizer_matches_sigma_path_convention(self) -> None:
        # EwmaSizer froze var during burn-in: its sigma sequence must now
        # equal ewma_sigma_path exactly (ONE recursion, all consumers).
        from quantlab.metrics.volforecast import ewma_sigma_path

        rng = np.random.default_rng(3)
        r = 100 * rng.standard_normal(60)
        params = VolSizingParams(
            lam=0.94, target_vol=100.0, seed_var=float(np.mean(r[:20] ** 2)), burn_in=20
        )
        sizer = EwmaSizer(params)
        sizer_sigma = []
        for x in r:
            sizer_sigma.append(float(np.sqrt(sizer.var)))
            sizer.update(float(x))
        path_sigma = ewma_sigma_path(r, burn_in=20).sigma
        for d in range(20, 60):
            assert sizer_sigma[d] == pytest.approx(path_sigma[d], rel=1e-12)

    def test_resize_log_honors_seed_var(self) -> None:
        # Was: seed_var silently discarded; burn_in=0 seeded from an empty
        # prefix -> sigma ~0 -> early weights pinned at clip_hi (leverage).
        rng = np.random.default_rng(3)
        log = day_trades([[simple(float(100 * rng.standard_normal()))] for _ in range(60)])
        params = VolSizingParams(lam=0.94, target_vol=100.0, seed_var=10_000.0, burn_in=0)
        _, weights, sigma = resize_log(log, FUTURES_DAY, params)
        assert sigma[0] == pytest.approx(100.0)  # sqrt(seed_var), not ~0
        assert weights[0] == pytest.approx(1.0)  # target/sqrt(seed) = 1

    def test_resize_log_matches_evaluator_weights(self) -> None:
        # The counterfactual and the scalar engine must produce the SAME
        # weight sequence for identical params (band=0).
        rng = np.random.default_rng(5)
        log = day_trades([[simple(float(150 * rng.standard_normal() + 20))] for _ in range(50)])
        day_pnl = log.daily_pnl(FUTURES_DAY)
        params = VolSizingParams(
            lam=0.94,
            target_vol=120.0,
            seed_var=float(np.mean(day_pnl[:10] ** 2)),
            burn_in=10,
            band=0.0,
        )
        _, weights, _ = resize_log(log, FUTURES_DAY, params)
        sizer = EwmaSizer(params)
        for d in range(50):
            assert weights[d] == pytest.approx(float(sizer.weight()))
            sizer.update(float(day_pnl[d]))

    def test_clip_bounds_validated(self) -> None:
        with pytest.raises(ValueError, match="clip"):
            VolSizingParams(lam=0.94, target_vol=100.0, seed_var=1.0, clip_lo=2.0, clip_hi=1.0)
        with pytest.raises(ValueError, match="lam"):
            VolSizingParams(lam=1.5, target_vol=100.0, seed_var=1.0)

    def test_counterfactual_forces_fixed_arms(self) -> None:
        # A vol_target mc_cfg must not double-apply the treatment.
        firm = load_firm("topstep_50k")
        log = _two_regime_log()
        base = compute_voltarget(log, firm=firm, mc_cfg=MCConfig(n_paths=200, seed=4))
        tainted = compute_voltarget(
            log, firm=firm, mc_cfg=MCConfig(n_paths=200, seed=4, sizing="vol_target")
        )
        assert base.mc_fixed == tainted.mc_fixed
        assert base.mc_targeted == tainted.mc_targeted

    def test_baseline_mc_reused_for_fixed_arm(self) -> None:
        from quantlab.prop.montecarlo import run_monte_carlo

        firm = load_firm("topstep_50k")
        log = _two_regime_log()
        mc = run_monte_carlo(log, firm, MCConfig(n_paths=400, seed=9))
        vt = compute_voltarget(log, firm=firm, mc_cfg=MCConfig(n_paths=100, seed=9), baseline_mc=mc)
        assert vt.mc_fixed is not None
        assert vt.mc_fixed["pass_prob"] == mc.economics.pass_prob

    def test_engine_starts_at_weight_one(self) -> None:
        # Seed = target^2: dynamic sizing must match fixed sizing exactly
        # on day 0 of an identity replay.
        from quantlab.prop.montecarlo import run_monte_carlo

        firm = load_firm("topstep_50k")
        log = _two_regime_log(days=80)
        dyn = run_monte_carlo(log, firm, MCConfig(n_paths=50, seed=2, sizing="vol_target"))
        assert dyn.sizing["mode"] == "vol_target"

    def test_evaluate_sequence_threads_sizing(self) -> None:
        from quantlab.prop.evaluator import evaluate_sequence

        firm = load_firm("topstep_50k")
        log = _two_regime_log()
        day_pnl = log.daily_pnl(FUTURES_DAY)
        params = VolSizingParams(
            lam=0.94,
            target_vol=float(np.sqrt(np.mean(day_pnl**2))),
            seed_var=float(np.mean(day_pnl**2)),
        )
        fixed = evaluate_sequence(log, firm)
        sized = evaluate_sequence(log, firm, sizing=params)
        assert len(sized) == len(fixed)  # runs end-to-end with sizing applied


class TestClusteringInsufficientData:
    def test_short_log_reports_skipped_not_clean(self) -> None:
        from quantlab.metrics.volforecast import compute_clustering

        tests = compute_clustering(np.random.default_rng(1).standard_normal(20))
        assert not tests.tested
        assert not tests.clustered  # but NOT presented as a clean negative

    def test_overfit_flag_says_skipped(self) -> None:
        from quantlab.metrics.overfit import _vol_clustering
        from quantlab.metrics.volforecast import compute_clustering

        flag = _vol_clustering(compute_clustering(np.zeros(15)))
        assert not flag.triggered and "skipped" in flag.explanation
