"""Regime analysis: classification, per-regime PnL, worst-regime stress (M10.d)."""

from __future__ import annotations

import numpy as np

from quantlab.metrics.regime import (
    REGIME_LABELS,
    classify_vol_regimes,
    compute_regimes,
)
from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.prop.registry import load_firm

from ..conftest import random_log
from ..prop.conftest import day_trades, simple


def _two_regime_log(days: int = 160, seed: int = 3):
    """Calm then violent halves, losses concentrated in the violent half."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(days):
        sigma, mean = (50.0, 40.0) if i < days // 2 else (400.0, -20.0)
        rows.append([simple(mean + sigma * rng.standard_normal())])
    return day_trades(rows)


class TestClassification:
    def test_two_regime_log_separates(self) -> None:
        log = _two_regime_log()
        from quantlab.schema.trade import FUTURES_DAY

        codes = classify_vol_regimes(log.daily_pnl(FUTURES_DAY))
        # Late (violent) days must classify overwhelmingly high-vol, early
        # classified days low/mid.
        late = codes[-40:]
        assert float(np.mean(late == 2)) > 0.8
        early = codes[25:60]
        assert float(np.mean(early <= 1)) > 0.8

    def test_burn_in_unclassified(self) -> None:
        log = _two_regime_log()
        from quantlab.schema.trade import FUTURES_DAY

        codes = classify_vol_regimes(log.daily_pnl(FUTURES_DAY), burn_in=20)
        assert (codes[:20] == -1).all()
        assert (codes[20:] >= 0).all()

    def test_terciles_roughly_balanced(self) -> None:
        log = random_log(n_days=120, seed=1)
        from quantlab.schema.trade import FUTURES_DAY

        codes = classify_vol_regimes(log.daily_pnl(FUTURES_DAY))
        counts = [int((codes == c).sum()) for c in range(3)]
        assert min(counts) > 15  # terciles cannot be wildly lopsided


class TestComputeRegimes:
    def test_worst_regime_and_concentration_on_synthetic(self) -> None:
        rg = compute_regimes(_two_regime_log())
        assert rg.tested
        assert rg.worst_regime == "high_vol"  # losses live in the violent half
        by_name = {r.regime: r for r in rg.regimes}
        assert by_name["high_vol"].day_expectancy < by_name["low_vol"].day_expectancy
        # The violent regime erases a material share of the calm-half profit.
        assert rg.regime_dependent

    def test_persistence_high_for_block_regimes(self) -> None:
        # Two long contiguous halves: persistence must be near 1.
        rg = compute_regimes(_two_regime_log())
        for r in rg.regimes:
            if r.n_days >= 30:
                assert r.persistence > 0.85

    def test_short_log_skipped_not_degraded(self) -> None:
        rg = compute_regimes(day_trades([[simple(100.0)]] * 25))
        assert not rg.tested
        assert rg.regimes == []
        assert any("skipped" in w for w in rg.warnings)

    def test_stress_present_with_firm_and_lower_than_baseline(self) -> None:
        log = _two_regime_log()
        firm = load_firm("topstep_50k")
        cfg = MCConfig(n_paths=300, seed=6)
        rg = compute_regimes(log, firm=firm, mc_cfg=cfg)
        assert rg.stress is not None
        assert rg.stress["regime"] == "high_vol"
        baseline = run_monte_carlo(log, firm, cfg).economics
        # Conditioning on the money-losing violent regime must not look
        # better than the whole-log baseline.
        assert rg.stress["expected_net"] <= baseline.expected_net

    def test_json_serializable(self) -> None:
        import json

        from quantlab.report.jsonout import sanitize

        rg = compute_regimes(_two_regime_log(), firm=load_firm("topstep_50k"))
        payload = rg.to_json_dict()
        json.dumps(sanitize(payload))
        assert set(REGIME_LABELS) == {r["regime"] for r in payload["regimes"]}


class TestMarketJoin:
    def _bars_csv(self, tmp_path, days: int = 80):
        import pandas as pd

        dates = pd.bdate_range("2026-01-05", periods=days, tz="UTC")
        rng = np.random.default_rng(2)
        close = 5000 + np.cumsum(rng.normal(0, 20, size=days))
        frame = pd.DataFrame(
            {
                "datetime": dates.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": close - 5,
                "high": close + 15,
                "low": close - 15,
                "close": close,
                "volume": 1000,
            }
        )
        path = tmp_path / "bars.csv"
        frame.to_csv(path, index=False)
        return path

    def test_market_regimes_join(self, tmp_path) -> None:
        from quantlab.ingest.ohlcv import load_ohlcv

        bars, _ = load_ohlcv(self._bars_csv(tmp_path))
        log = random_log(n_days=60, seed=4)
        rg = compute_regimes(log, ohlcv=bars)
        assert rg.market is not None
        # Every labeled bucket is one of the 6 trend x vol combinations.
        for m in rg.market:
            trend, vol = m.regime.split("_", 1)
            assert trend in ("up", "down") and vol in ("low_vol", "mid_vol", "high_vol")


class TestOverfitFlag:
    def test_regime_dependent_edge_triggers(self) -> None:
        from quantlab.metrics.core import compute_metrics
        from quantlab.metrics.overfit import overfit_flags

        log = _two_regime_log()
        flags = overfit_flags(log, compute_metrics(log))
        flag = next(f for f in flags if f.name == "regime_dependent_edge")
        assert flag.triggered

    def test_uniform_winner_does_not_trigger(self) -> None:
        from quantlab.metrics.core import compute_metrics
        from quantlab.metrics.overfit import overfit_flags

        log = random_log(n_days=120, mean=40.0, std=150.0, seed=8)
        flags = overfit_flags(log, compute_metrics(log))
        flag = next(f for f in flags if f.name == "regime_dependent_edge")
        assert not flag.triggered


class TestRealityIntegration:
    def test_regime_block_in_reality_json(self) -> None:
        from quantlab.metrics.reality import compute_reality_check

        log = random_log(n_days=70, mean=40.0, std=300.0, seed=7)
        rc = compute_reality_check(log, firm=load_firm("topstep_50k"), mc_paths=100, outer=0)
        payload = rc.to_json_dict()
        assert payload["regime"] is not None
        assert payload["regime"]["tested"]
