"""Source-log sampling-uncertainty band (M10.b)."""

from __future__ import annotations

import numpy as np
import pytest

from quantlab.prop.montecarlo import MCConfig
from quantlab.prop.registry import load_firm
from quantlab.prop.uncertainty import source_uncertainty

from ..conftest import random_log
from .conftest import day_trades, simple


class TestSourceUncertainty:
    def test_deterministic_in_seed(self) -> None:
        log = random_log(n_days=80, mean=40.0, std=300.0, seed=3)
        firm = load_firm("topstep_50k")
        cfg = MCConfig(n_paths=2000, seed=11)
        a = source_uncertainty(log, firm, mc_cfg=cfg, n_outer=12, inner_paths=100)
        b = source_uncertainty(log, firm, mc_cfg=cfg, n_outer=12, inner_paths=100)
        assert a.pass_prob_quantiles == b.pass_prob_quantiles
        assert a.expected_net_quantiles == b.expected_net_quantiles

    def test_certain_loser_band_is_degenerate(self) -> None:
        # Every resample of an always-losing log still always loses: the
        # band must collapse to exactly zero pass prob at every quantile.
        log = day_trades([[simple(-500)]] * 40)
        su = source_uncertainty(
            log, load_firm("topstep_50k"), mc_cfg=MCConfig(seed=1), n_outer=10, inner_paths=50
        )
        assert all(v == 0.0 for v in su.pass_prob_quantiles.values())
        assert su.band_width_pp == 0.0

    def test_marginal_log_band_is_wide(self) -> None:
        # A marginal strategy's pass prob should genuinely move when the
        # source log is resampled — the whole point of the band.
        log = random_log(n_days=60, mean=30.0, std=350.0, seed=5)
        su = source_uncertainty(
            log, load_firm("topstep_50k"), mc_cfg=MCConfig(seed=2), n_outer=30, inner_paths=200
        )
        assert su.band_width_pp > 1.0
        assert su.pass_prob_quantiles["p5"] <= su.pass_prob_quantiles["p95"]

    def test_quantiles_ordered_and_json(self) -> None:
        import json

        from quantlab.report.jsonout import sanitize

        log = random_log(n_days=60, mean=30.0, std=350.0, seed=5)
        su = source_uncertainty(
            log, load_firm("topstep_50k"), mc_cfg=MCConfig(seed=2), n_outer=8, inner_paths=50
        )
        pq = su.pass_prob_quantiles
        assert pq["p5"] <= pq["p25"] <= pq["p50"] <= pq["p75"] <= pq["p95"]
        json.dumps(sanitize(su.to_json_dict()))

    def test_short_log_falls_back_to_iid_with_warning(self) -> None:
        log = day_trades([[simple(float(p))] for p in np.linspace(-300, 400, 20)])
        su = source_uncertainty(
            log, load_firm("topstep_50k"), mc_cfg=MCConfig(seed=3), n_outer=6, inner_paths=50
        )
        assert su.outer_bootstrap == "iid_day"
        assert any("low-confidence" in w for w in su.warnings)


class TestRealityIntegration:
    def test_band_present_with_firm_and_skippable(self) -> None:
        from quantlab.metrics.reality import compute_reality_check

        log = random_log(n_days=70, mean=40.0, std=300.0, seed=7, with_excursions=True)
        rc = compute_reality_check(
            log, firm=load_firm("topstep_50k"), mc_paths=100, outer=6, inner_paths=50
        )
        assert rc.sampling is not None
        assert rc.to_json_dict()["sampling_uncertainty"]["n_outer"] == 6
        rc_off = compute_reality_check(log, firm=load_firm("topstep_50k"), mc_paths=100, outer=0)
        assert rc_off.sampling is None
        assert rc_off.to_json_dict()["sampling_uncertainty"] is None

    def test_absent_without_firm(self) -> None:
        from quantlab.metrics.reality import compute_reality_check

        log = random_log(n_days=70, seed=7)
        rc = compute_reality_check(log, mc_paths=100)
        assert rc.sampling is None


@pytest.mark.slow
def test_default_band_stays_in_budget() -> None:
    import os
    import time

    budget = 30.0 * float(os.environ.get("QUANTLAB_PERF_FACTOR", "1"))
    log = random_log(n_days=250, trades_per_day=4, seed=9)
    start = time.perf_counter()
    source_uncertainty(log, load_firm("topstep_50k"), mc_cfg=MCConfig(seed=1))
    elapsed = time.perf_counter() - start
    assert elapsed < budget, f"{elapsed:.1f}s exceeds the {budget:.0f}s band budget"
