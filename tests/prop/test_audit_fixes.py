"""Regression tests for the codebase-gaps audit (engine/config side).

Each class names the defect it pins down; the audit's finding numbers are
in the PR description, not repeated here.
"""

from __future__ import annotations

import dataclasses
from collections import Counter

import numpy as np
import pytest

from quantlab.errors import ConfigError, QuantLabError
from quantlab.prop.bootstrap import StationaryBlockBootstrap, resolve_sampler
from quantlab.prop.config import FirmConfig
from quantlab.prop.dayprofile import DayProfile
from quantlab.prop.equity_check import check_equity_curve
from quantlab.prop.frontier import compute_scale_frontier
from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.prop.synthetic import synthetic_geometry_log
from quantlab.schema.equity import EquityCurve
from quantlab.schema.trade import FUTURES_DAY
from tests.prop.conftest import day_trades, make_firm


class TestSyntheticDayStructure:
    def test_high_trades_per_day_stay_inside_session(self) -> None:
        """Trades must never spill past the 17:00 CT boundary into the
        next (possibly weekend) session, whatever trades_per_day is."""
        for tpd in (1, 32, 40, 100):
            log = synthetic_geometry_log(
                win_rate=0.5, rr=2.0, trades_per_day=tpd, risk=100, ev=10, days=20, seed=7
            )
            groups = log.daily_groups(FUTURES_DAY)
            assert len(groups) == 20, tpd
            assert Counter(len(ts) for _, ts in groups) == {tpd: 20}
            assert not any(d.weekday() >= 5 for d, _ in groups)

    def test_degenerate_parameters_rejected(self) -> None:
        with pytest.raises(QuantLabError):
            synthetic_geometry_log(0.5, 2.0, trades_per_day=0, risk=100, ev=0, days=5, seed=1)
        with pytest.raises(QuantLabError):
            synthetic_geometry_log(0.5, 2.0, trades_per_day=1, risk=-5, ev=0, days=5, seed=1)
        with pytest.raises(QuantLabError):
            synthetic_geometry_log(1.5, 2.0, trades_per_day=1, risk=100, ev=0, days=5, seed=1)


class TestConfigValidation:
    def test_consistency_pct_bounds(self) -> None:
        with pytest.raises((ConfigError, ValueError)):
            make_firm([{"type": "consistency", "max_best_day_pct": 0}])
        with pytest.raises((ConfigError, ValueError)):
            make_firm([{"type": "consistency", "max_best_day_pct": -50}])

    def test_contract_limit_requires_positive_max(self) -> None:
        with pytest.raises((ConfigError, ValueError)):
            make_firm([{"type": "contract_limit"}])

    def test_negative_rule_amounts_rejected_at_load(self, tmp_path) -> None:
        from quantlab.prop.registry import load_firm

        yaml_path = tmp_path / "bad.yaml"
        yaml_path.write_text(
            """
name: badfirm
account_size: 50000
phases:
  - name: challenge
    profit_target: 3000
    rules:
      - {type: trailing_drawdown, amount: -2000}
funded: {name: funded}
""",
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="greater than 0"):
            load_firm(yaml_path)

    def test_profit_split_fraction_enforced(self) -> None:
        with pytest.raises((ConfigError, ValueError), match="less than or equal to 1"):
            FirmConfig.model_validate(
                {
                    "name": "f",
                    "account_size": 50_000,
                    "phases": [{"name": "c", "profit_target": 3000}],
                    "funded": {"name": "funded"},
                    "payout": {"profit_split": 90},
                }
            )

    def test_negative_fees_rejected(self) -> None:
        with pytest.raises((ConfigError, ValueError)):
            FirmConfig.model_validate(
                {
                    "name": "f",
                    "account_size": 50_000,
                    "phases": [{"name": "c", "profit_target": 3000}],
                    "funded": {"name": "funded"},
                    "fees": {"one_time": -50},
                }
            )

    def test_bad_timezone_rejected(self) -> None:
        with pytest.raises((ConfigError, ValueError), match="unknown timezone"):
            make_firm(
                [{"type": "static_max_loss", "amount": 2000}],
                day_boundary={"tz": "Not/AZone"},
            )

    def test_account_size_positive(self) -> None:
        with pytest.raises((ConfigError, ValueError), match="greater than 0"):
            make_firm([{"type": "static_max_loss", "amount": 2000}], size=0)


class TestScaleAndHorizonValidation:
    def _log(self):
        return day_trades([[(200.0, -50.0, 250.0)] for _ in range(40)])

    def test_negative_scale_rejected(self) -> None:
        firm = make_firm([{"type": "static_max_loss", "amount": 2000}])
        with pytest.raises(QuantLabError, match="positive"):
            run_monte_carlo(self._log(), firm, MCConfig(n_paths=10, seed=1, scale=-1.0))
        with pytest.raises(QuantLabError, match="positive"):
            run_monte_carlo(self._log(), firm, MCConfig(n_paths=10, seed=1, scale=0.0))

    def test_zero_horizon_rejected(self) -> None:
        firm = make_firm([{"type": "static_max_loss", "amount": 2000}])
        with pytest.raises(QuantLabError, match="horizon"):
            run_monte_carlo(
                self._log(), firm, MCConfig(n_paths=10, seed=1, challenge_horizon_days=0)
            )

    def test_dayprofile_scaled_guards(self) -> None:
        profile = DayProfile.from_log(self._log(), FUTURES_DAY)
        with pytest.raises(QuantLabError, match="positive"):
            profile.scaled(-2.0)


class TestBlockLenValidation:
    def test_nonpositive_block_len_rejected(self) -> None:
        with pytest.raises(QuantLabError, match="block-len"):
            StationaryBlockBootstrap(0)
        with pytest.raises(QuantLabError, match="block-len"):
            StationaryBlockBootstrap(-3)

    def test_resolve_sampler_fallback_contract(self) -> None:
        short = np.random.default_rng(0).normal(size=10)
        _, name, block, fell_back = resolve_sampler("stationary", short)
        assert name == "iid_day" and fell_back and block is None
        long = np.random.default_rng(0).normal(size=60)
        _, name, block, fell_back = resolve_sampler("stationary", long)
        assert name == "stationary" and not fell_back and block is not None and block >= 1


class TestIidTradeProvenance:
    def test_source_days_is_the_logs_day_count(self) -> None:
        """iid_trade builds a 1000-day synthetic profile; the report must
        still state the log's REAL day count as source history."""
        log = day_trades([[(100.0, -20.0, 120.0)] for _ in range(35)])
        firm = make_firm([{"type": "static_max_loss", "amount": 2000}])
        report = run_monte_carlo(log, firm, MCConfig(n_paths=50, seed=3, bootstrap="iid_trade"))
        assert report.source_days == 35
        assert report.bootstrap == "iid_trade"

    def test_empty_log_clean_error(self) -> None:
        from quantlab.schema.trade import TradeLog

        firm = make_firm([{"type": "static_max_loss", "amount": 2000}])
        with pytest.raises(QuantLabError, match="at least one source trade"):
            run_monte_carlo(
                TradeLog(trades=[]), firm, MCConfig(n_paths=10, seed=1, bootstrap="iid_trade")
            )


class TestEquityCheckMultiRule:
    def _curve(self, values, start="2026-01-05T10:00:00+00:00"):
        import datetime as dt

        base = dt.datetime.fromisoformat(start)
        points = [(base + dt.timedelta(hours=6 * i), v) for i, v in enumerate(values)]
        import pandas as pd

        series = pd.Series([v for _, v in points], index=pd.DatetimeIndex([t for t, _ in points]))
        return EquityCurve.from_series(series)

    def test_second_rule_of_same_type_not_dropped(self) -> None:
        """Two trailing rules: the TIGHTER (capped) one breaches first and
        must be honored even though it is listed first."""
        firm = make_firm(
            [
                {"type": "trailing_drawdown", "amount": 1000, "threshold_cap": 50_000},
                {"type": "trailing_drawdown", "amount": 3000},
            ]
        )
        curve = self._curve([50_000, 48_800])  # breaches 1000-width floor only
        result = check_equity_curve(curve, firm)
        assert result.first_breach is not None
        assert result.first_breach.threshold == pytest.approx(49_000)

    def test_multi_floor_breach_attributed_to_highest(self) -> None:
        """One mark crossing both floors: the HIGHER threshold fired first."""
        firm = make_firm(
            [
                {"type": "trailing_drawdown", "amount": 2500},
                {"type": "static_max_loss", "amount": 2000},
            ]
        )
        curve = self._curve([50_000, 47_000])
        result = check_equity_curve(curve, firm)
        assert result.first_breach is not None
        assert result.first_breach.rule == "static_max_loss"
        assert result.first_breach.threshold == pytest.approx(48_000)

    def test_lockout_above_fail_level_suppresses_the_fail(self) -> None:
        """Descending equity reaches the HIGHER lockout level first: the
        account flattens there, so the lower fail floor is phantom."""
        firm = make_firm(
            [
                {"type": "daily_loss_limit", "amount": 1000, "effect": "lockout"},
                {"type": "daily_loss_limit", "amount": 1500, "effect": "fail"},
            ]
        )
        curve = self._curve([50_000, 48_300])  # crosses both widths
        result = check_equity_curve(curve, firm)
        # The account flattens at 49,000: the fail floor below is phantom
        # and never crossed, so only the lockout crossing is recorded.
        assert len(result.daily_loss_hits) == 1
        assert result.daily_loss_hits[0].rule == "daily_loss_limit[lockout]"
        assert result.first_breach is None

    def test_fail_above_lockout_level_ends_the_phase(self) -> None:
        firm = make_firm(
            [
                {"type": "daily_loss_limit", "amount": 1500, "effect": "lockout"},
                {"type": "daily_loss_limit", "amount": 1000, "effect": "fail"},
            ]
        )
        curve = self._curve([50_000, 48_300])
        result = check_equity_curve(curve, firm)
        assert result.first_breach is not None
        assert result.first_breach.threshold == pytest.approx(49_000)

    def test_daily_fail_joins_the_first_hit_pool(self) -> None:
        """A daily-fail floor ABOVE the trailing floor must win attribution."""
        firm = make_firm(
            [
                {"type": "trailing_drawdown", "amount": 2500},
                {"type": "daily_loss_limit", "amount": 1000, "effect": "fail"},
            ]
        )
        curve = self._curve([50_000, 47_400])  # crosses daily 49,000 and trailing 47,500
        result = check_equity_curve(curve, firm)
        assert result.first_breach is not None
        assert result.first_breach.rule == "daily_loss_limit[fail]"
        assert result.first_breach.threshold == pytest.approx(49_000)

    def test_next_session_breach_after_lockout_rebase(self) -> None:
        """The locked day closes AT the lockout level and the next session
        rebases onto it; a deep-enough rebased drop still breaches."""
        firm = make_firm(
            [
                {"type": "daily_loss_limit", "amount": 2000, "effect": "lockout"},
                {"type": "trailing_drawdown", "amount": 2500},
            ]
        )
        # Session 1: lockout at 48,000 on the 47,000 mark. Session 2 rebases
        # its first mark to 48,000 and re-arms the lockout at 46,000; the raw
        # 1,600 drop lands the balance at 46,400 — through the 47,500
        # trailing floor but above the day's lockout level, so the trailing
        # breach is the first hit.
        curve = self._curve([50_000, 48_800, 47_000, 47_200, 45_600])
        result = check_equity_curve(curve, firm)
        assert result.first_breach is not None
        assert result.first_breach.rule.startswith("trailing_drawdown")
        assert result.first_breach.threshold == pytest.approx(47_500)


class TestFrontierSinglePoint:
    def test_no_rising_trend_warning_on_one_point(self) -> None:
        log = day_trades([[(200.0, -50.0, 250.0)] for _ in range(40)])
        firm = make_firm([{"type": "static_max_loss", "amount": 2000}])
        frontier = compute_scale_frontier(
            log, firm, mc_cfg=MCConfig(n_paths=50, seed=5), scales=(1.0,)
        )
        assert not any("top of the grid" in w for w in frontier.warnings)


class TestReceivedPerPath:
    def test_haircut_flows_into_received_series(self) -> None:
        from quantlab.prop.config import with_fee_overrides
        from quantlab.prop.registry import load_firm

        log = day_trades([[(300.0, -50.0, 350.0)] for _ in range(40)])
        base_firm = load_firm("topstep_50k")
        cut_firm = with_fee_overrides(base_firm, payout_haircut=0.5)
        cfg = MCConfig(n_paths=300, seed=11, funded_horizon_days=120)
        base = run_monte_carlo(log, base_firm, cfg)
        cut = run_monte_carlo(log, cut_firm, dataclasses.replace(cfg))
        assert base.economics.received_per_path is not None
        assert cut.economics.received_per_path is not None
        # The histogram series and the payout_quantiles row must agree.
        assert float(np.percentile(cut.economics.received_per_path, 50)) == pytest.approx(
            cut.economics.payout_quantiles["p50"]
        )
        # And the haircut must actually shrink the plotted series.
        assert cut.economics.received_per_path.sum() < base.economics.received_per_path.sum()

    def test_not_serialized(self) -> None:
        log = day_trades([[(300.0, -50.0, 350.0)] for _ in range(35)])
        firm = make_firm([{"type": "static_max_loss", "amount": 2000}])
        report = run_monte_carlo(log, firm, MCConfig(n_paths=50, seed=2))
        payload = report.to_json_dict()
        assert "received_per_path" not in payload["economics"]
        assert "net_per_path" not in payload["economics"]
