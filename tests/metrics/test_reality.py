"""Reality-check orchestrator + report integration tests."""

from __future__ import annotations

import json

from quantlab.metrics.core import compute_metrics
from quantlab.metrics.reality import compute_reality_check
from quantlab.metrics.scorecard import compute_scorecard
from quantlab.prop.registry import load_firm
from quantlab.report.jsonout import combined_json, sanitize
from tests.prop.conftest import day_trades, simple


def _log():
    rows = []
    for i in range(60):
        rows.append([simple(-140.0 if i % 3 == 2 else 130.0)])
    return day_trades(rows)


class TestRealityCheck:
    def test_end_to_end_serializable(self) -> None:
        firm = load_firm("topstep_50k")
        rc = compute_reality_check(_log(), firm=firm, trials=3, mc_paths=200, seed=5)
        payload = sanitize(rc.to_json_dict())
        json.dumps(payload)  # must not raise (inf/nan sanitized)
        assert payload["deflated"]["dsr"] is not None
        assert len(payload["haircuts"]) == 4
        assert payload["costs"]["grid"]

    def test_trials_warning_at_default(self) -> None:
        rc = compute_reality_check(_log(), mc_paths=100, seed=5)
        assert any("n_trials=1" in w for w in rc.warnings)

    def test_combined_json_reality_key(self) -> None:
        log = _log()
        metrics = compute_metrics(log)
        verdict = compute_scorecard(log, metrics)
        rc = compute_reality_check(log, seed=5)
        payload = combined_json(metrics, verdict, reality=rc)
        assert payload["schema_version"] == 3
        assert "reality_check" in payload
        json.dumps(payload)


class TestM8ReviewFixes:
    """Regressions from the M8 adversarial review (pass 1)."""

    def test_iid_trade_bootstrap_still_runs(self) -> None:
        # Was: UnboundLocalError on block_len_used for every iid_trade run.
        from quantlab.prop.montecarlo import MCConfig, run_monte_carlo

        log = _log()
        report = run_monte_carlo(
            log, load_firm("topstep_50k"), MCConfig(n_paths=50, seed=1, bootstrap="iid_trade")
        )
        assert report.block_len is None  # not applicable to iid sampling

    def test_negative_sr_gets_no_haircut_sharpe(self) -> None:
        # Was: abs(t) sign-flipped a losing strategy to +0.22 adjusted SR.
        import numpy as np

        from quantlab.metrics.deflate import compute_deflated

        rng = np.random.default_rng(7)
        x = rng.standard_normal(100)
        x = (x - x.mean()) / x.std(ddof=1) - 0.30
        stats = compute_deflated(x, n_trials=10)
        assert stats.haircut_sharpe is None and stats.haircut_pct is None

    def test_baseline_mc_reused_verbatim(self) -> None:
        # One HTML must never show two different baseline pass probs.
        # Reuse applies to fees-RECORDED logs, where the baseline row is
        # truly zero-added (a gross log's baseline adds commission and is
        # legitimately a different quantity than the headline).
        import dataclasses

        from quantlab.prop.montecarlo import MCConfig, run_monte_carlo

        gross = _log()
        log = type(gross)(
            trades=[dataclasses.replace(t, fees=1.5) for t in gross.trades],
            source=gross.source,
        )
        firm = load_firm("topstep_50k")
        mc = run_monte_carlo(log, firm, MCConfig(n_paths=500, seed=3))
        rc = compute_reality_check(log, firm=firm, mc_paths=100, seed=3, baseline_mc=mc)
        baseline = next(p for p in rc.costs.grid if p.label == "0 tick/side, 1x commission")
        assert baseline.added_rt_per_contract == 0.0
        assert baseline.mc_pass_prob == mc.economics.pass_prob

    def test_tiny_log_raises_clean_error(self) -> None:
        import pytest

        from quantlab.errors import QuantLabError

        with pytest.raises(QuantLabError, match="3 trades"):
            compute_reality_check(day_trades([[simple(100.0)], [simple(-50.0)]]))

    def test_oos_start_reaches_wfe(self) -> None:
        log = _log()
        rc = compute_reality_check(log, oos_start=log.trades[30].entry_time, mc_paths=100)
        assert rc.decay.wfe is not None


class TestMannKendallFenwick:
    def test_fenwick_matches_matrix_path(self) -> None:
        # The O(n log n) large-n path must agree exactly with the small-n
        # matrix path (force both via the size threshold).
        import numpy as np

        from quantlab.metrics.decay import _kendall_s

        rng = np.random.default_rng(11)
        for trial in range(5):
            values = np.round(rng.standard_normal(300) * 10, 1)  # ties included
            signs = np.sign(values[None, :] - values[:, None])
            expected = int(np.triu(signs, k=1).sum())
            big = np.tile(values, 8)[:2401]  # pushes past the 2000 threshold
            signs_big = np.sign(big[None, :] - big[:, None])
            expected_big = int(np.triu(signs_big, k=1).sum())
            assert _kendall_s(big) == expected_big, trial
            assert _kendall_s(values) == expected


class TestChunkedPermutationStream:
    def test_chunking_matches_unchunked_reference(self) -> None:
        # Chunked generator consumption must be bit-identical to one batch.
        import numpy as np

        from quantlab.metrics.drawdown_mc import permutation_drawdown

        log = _log()
        pnls = np.array([t.pnl for t in log.trades])
        n_iter = 700  # crosses the 512 chunk boundary
        rng = np.random.default_rng(9)
        order = np.argsort(rng.random((n_iter, pnls.size)), axis=1)
        equity = np.cumsum(pnls[order], axis=1)
        peaks = np.maximum.accumulate(np.maximum(equity, 0.0), axis=1)
        expected_median = float(np.median(np.max(peaks - equity, axis=1)))
        got = permutation_drawdown(log, n_iter=n_iter, seed=9)
        assert got.median_max_dd == expected_median


class TestOosStartCliParse:
    def test_bad_iso_date_raises_quantlab_error(self, tmp_path) -> None:
        # Pass-2 finding: --oos-start garbage leaked a ValueError traceback.
        from quantlab.errors import QuantLabError
        from quantlab.schema.io import write_trade_log

        parquet = tmp_path / "t.parquet"
        write_trade_log(_log(), parquet)
        from typer.testing import CliRunner

        from quantlab.cli.app import app

        result = CliRunner().invoke(
            app, ["stress", str(parquet), "--oos-start", "junk"], catch_exceptions=True
        )
        assert isinstance(result.exception, QuantLabError)
        assert "not an ISO date" in str(result.exception)
