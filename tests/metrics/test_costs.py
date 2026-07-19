"""Cost-sweep, haircut, and permutation-drawdown tests."""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from quantlab.errors import QuantLabError
from quantlab.metrics.costs import (
    apply_cost,
    gross_pnl_warning,
    haircut_log,
    run_cost_sweep,
    run_haircut_scenarios,
)
from quantlab.metrics.drawdown_mc import permutation_drawdown
from quantlab.prop.montecarlo import MCConfig
from quantlab.prop.registry import load_firm
from tests.prop.conftest import day_trades, simple


def _mnq_log(days: int = 60, pnl: float = 120.0, loss_every: int = 3):
    rows = []
    for i in range(days):
        rows.append([simple(-abs(pnl) if i % loss_every == 2 else pnl)])
    return day_trades(rows)


class TestApplyCost:
    def test_expectancy_drops_by_exact_amount(self) -> None:
        log = _mnq_log()
        base = np.mean([t.pnl for t in log.trades])
        stressed = apply_cost(log, 2.5)
        mean_qty = np.mean([t.quantity for t in log.trades])
        assert np.mean([t.pnl for t in stressed.trades]) == pytest.approx(base - 2.5 * mean_qty)
        assert all(
            s.fees == t.fees + 2.5 * t.quantity
            for s, t in zip(stressed.trades, log.trades, strict=True)
        )


class TestHaircut:
    def test_mean_shrinks_std_preserved(self) -> None:
        log = _mnq_log()
        pnls = np.array([t.pnl for t in log.trades])
        cut = haircut_log(log, 0.58)
        cut_pnls = np.array([t.pnl for t in cut.trades])
        assert cut_pnls.mean() == pytest.approx(pnls.mean() * (1 - 0.58))
        assert cut_pnls.std(ddof=1) == pytest.approx(pnls.std(ddof=1))

    def test_negative_ev_log_gets_no_scenarios(self) -> None:
        log = day_trades([[simple(-50.0)]] * 30)
        assert run_haircut_scenarios(log) == []

    def test_scenarios_carry_citation_labels(self) -> None:
        scenarios = run_haircut_scenarios(_mnq_log())
        assert [s.haircut for s in scenarios] == [0.26, 0.50, 0.58, 0.90]
        assert any("McLean-Pontiff" in s.label for s in scenarios)
        assert any("US-specific" in s.label for s in scenarios)


class TestCostSweep:
    def test_breakeven_equals_baseline_expectancy(self) -> None:
        log = _mnq_log()
        stress = run_cost_sweep(log)
        assert stress.breakeven_added_cost_per_trade == pytest.approx(
            np.mean([t.pnl for t in log.trades])
        )
        assert stress.tick_source == "resolved:MNQ"
        assert stress.tick_value == 0.50

    def test_grid_expectancy_declines_with_cost(self) -> None:
        stress = run_cost_sweep(_mnq_log())
        by_added = sorted(stress.grid, key=lambda p: p.added_rt_per_contract)
        expectancies = [p.expectancy for p in by_added]
        assert all(a >= b for a, b in itertools.pairwise(expectancies))

    def test_mc_pass_prob_non_increasing_and_seed_stable(self) -> None:
        firm = load_firm("apex40_50k_intraday")
        log = day_trades([[simple(400.0)], [simple(-150.0)]] * 40)
        cfg = MCConfig(n_paths=300, seed=9)
        s1 = run_cost_sweep(log, firm=firm, mc_cfg=cfg)
        s2 = run_cost_sweep(log, firm=firm, mc_cfg=cfg)
        mc = [p for p in s1.grid if p.mc_pass_prob is not None]
        assert len(mc) == 3
        ordered = sorted(mc, key=lambda p: p.added_rt_per_contract)
        assert ordered[0].mc_pass_prob >= ordered[-1].mc_pass_prob
        assert [p.mc_pass_prob for p in s1.grid] == [p.mc_pass_prob for p in s2.grid]

    def test_unresolvable_symbol_requires_tick_value(self) -> None:
        # Build a log with an unknown symbol directly.
        import datetime as dt
        from zoneinfo import ZoneInfo

        from quantlab.schema.trade import Side, Trade, TradeLog

        ct = ZoneInfo("America/Chicago")
        entry = dt.datetime(2026, 1, 5, 9, 0, tzinfo=ct)
        trades = [Trade(entry, entry, "CL", Side.LONG, 1, 100.0)]
        unknown = TradeLog(trades=trades, source="csv")
        with pytest.raises(QuantLabError, match="tick value"):
            run_cost_sweep(unknown)
        stress = run_cost_sweep(unknown, tick_value=10.0)
        assert stress.tick_source == "user"

    def test_gross_log_adds_baseline_commission_at_1x(self) -> None:
        log = _mnq_log()  # conftest trades carry fees=0 -> gross
        assert gross_pnl_warning(log) is not None
        stress = run_cost_sweep(log)
        assert not stress.commission_in_log
        zero_row = next(p for p in stress.grid if p.label == "0 tick/side, 1x commission")
        assert zero_row.added_rt_per_contract == pytest.approx(stress.commission_rt)


class TestPermutationDrawdown:
    def test_total_pnl_invariant_and_deterministic(self) -> None:
        log = _mnq_log()
        a = permutation_drawdown(log, n_iter=500, seed=1)
        b = permutation_drawdown(log, n_iter=500, seed=1)
        assert a == b
        assert a.p95_max_dd >= a.median_max_dd > 0

    def test_all_winner_log_zero_ruin(self) -> None:
        log = day_trades([[simple(100.0)]] * 40)
        res = permutation_drawdown(log, n_iter=200, seed=2, ruin_capital=1000.0)
        assert res.p_ruin == 0.0
        assert res.median_max_dd == 0.0

    def test_certain_ruin_detected(self) -> None:
        log = day_trades([[simple(-100.0)]] * 40)
        res = permutation_drawdown(log, n_iter=200, seed=3, ruin_capital=1000.0)
        assert res.p_ruin == 1.0
