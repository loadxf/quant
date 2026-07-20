"""Cushion (buffer-aware) sizing (M11.a): kernel, golden equivalence,
and the ruin-cut acceptance criterion."""

from __future__ import annotations

import numpy as np
import pytest

from quantlab.prop.evaluator import evaluate
from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.prop.outcomes import OUTCOME_LABELS
from quantlab.prop.registry import load_firm
from quantlab.prop.voltarget import CushionParams, cushion_weight

from ..conftest import random_log
from .conftest import day_trades, simple
from .test_montecarlo import EQUIV_OUTCOME, LOG_SPECS, identity_phase_run

CLIP = (0.25, 1.5)


class TestKernel:
    def test_full_cushion_weight_is_one(self) -> None:
        p = CushionParams(cushion_0=2000.0)
        assert cushion_weight(2000.0, p) == 1.0

    def test_weight_scales_linearly_between_clips(self) -> None:
        p = CushionParams(cushion_0=2000.0, clip_lo=0.25, clip_hi=1.5)
        assert cushion_weight(1000.0, p) == pytest.approx(0.5)
        assert cushion_weight(4000.0, p) == 1.5  # capped
        assert cushion_weight(100.0, p) == 0.25  # floored
        assert cushion_weight(-50.0, p) == 0.25  # negative cushion -> floor

    def test_broadcasts_over_paths(self) -> None:
        p = CushionParams(cushion_0=2000.0)
        w = cushion_weight(np.array([2000.0, 1000.0, 0.0]), p)
        assert isinstance(w, np.ndarray)
        assert w.tolist() == [1.0, 0.5, 0.25]

    def test_validation(self) -> None:
        with pytest.raises(ValueError, match="clip"):
            CushionParams(cushion_0=1000.0, clip_lo=2.0, clip_hi=1.0)
        with pytest.raises(ValueError, match="cushion_0"):
            CushionParams(cushion_0=0.0)


class TestGoldenEquivalence:
    """The load-bearing invariant: identical scalar/vector semantics."""

    @pytest.mark.parametrize("preset", ["topstep_50k", "apex40_50k_intraday", "ftmo_2step_100k"])
    @pytest.mark.parametrize("spec_index", [0, 1, 2, 3])
    def test_identity_resample_matches_evaluator(self, preset: str, spec_index: int) -> None:
        firm = load_firm(preset)
        log = random_log(with_excursions=True, **LOG_SPECS[spec_index])
        for phase_cfg in [*firm.phases, firm.funded]:
            scalar = evaluate(log, firm, phase=phase_cfg.name, cushion_clip=CLIP)
            vector = identity_phase_run(log, firm, phase_cfg.name, cushion_clip=CLIP)
            v_outcome = OUTCOME_LABELS[int(vector.outcome[0])]
            assert OUTCOME_LABELS[EQUIV_OUTCOME[scalar.outcome]] == v_outcome, (
                f"{preset}/{phase_cfg.name}: scalar={scalar.outcome} vector={v_outcome}"
            )
            if scalar.outcome in ("passed", "breached"):
                expected_day = (
                    scalar.pass_day_index if scalar.outcome == "passed" else scalar.breach.day_index  # type: ignore[union-attr]
                )
                assert int(vector.end_day[0]) == expected_day
            if scalar.outcome in ("incomplete", "survived"):
                assert float(vector.final_balance[0]) == pytest.approx(scalar.final_balance)


class TestBehaviour:
    def test_derisks_after_losses(self) -> None:
        # After a big losing day the buffer shrinks, so the next day's
        # weight must drop below 1.
        firm = load_firm("topstep_50k")  # $2,000 trailing allowance
        log = day_trades([[simple(-1000.0)], [simple(10.0)], [simple(10.0)]])
        result = evaluate(log, firm, phase="challenge", cushion_clip=CLIP)
        # Day 2 weight = (2000-1000)/2000 = 0.5 -> day PnL 10 * 0.5 = 5.
        assert result.timeline.iloc[1]["day_pnl"] == pytest.approx(5.0)

    def test_needs_a_drawdown_rule(self) -> None:
        from quantlab.errors import ConfigError, QuantLabError

        from .test_montecarlo import make_firm

        firm = make_firm([{"type": "daily_loss_limit", "amount": 1000, "effect": "lockout"}])
        log = day_trades([[simple(100.0)]] * 10)
        with pytest.raises((ConfigError, QuantLabError), match="cushion"):
            evaluate(log, firm, phase="challenge", cushion_clip=CLIP)
        with pytest.raises((ConfigError, QuantLabError), match="cushion"):
            run_monte_carlo(log, firm, MCConfig(n_paths=10, seed=1, sizing="cushion"))

    def test_acceptance_cushion_cuts_funded_ruin(self) -> None:
        """The feature's honest claim: de-risking toward the floor must cut
        funded risk-of-ruin vs fixed sizing on a log that busts accounts."""
        firm = load_firm("topstep_50k")
        log = random_log(n_days=100, mean=20.0, std=400.0, seed=17)
        fixed = run_monte_carlo(log, firm, MCConfig(n_paths=1500, seed=3)).economics
        cush = run_monte_carlo(
            log, firm, MCConfig(n_paths=1500, seed=3, sizing="cushion")
        ).economics
        assert fixed.risk_of_ruin_funded > 0.05  # the stress is real
        assert cush.risk_of_ruin_funded < fixed.risk_of_ruin_funded

    def test_neutral_when_floor_never_approached(self) -> None:
        # A steady winner never nears the floor: cushion weight rides the
        # cap side, so outcomes stay pass-heavy in both modes.
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(300.0), simple(200.0)]] * 60)
        fixed = run_monte_carlo(log, firm, MCConfig(n_paths=300, seed=4)).economics
        cush = run_monte_carlo(log, firm, MCConfig(n_paths=300, seed=4, sizing="cushion")).economics
        assert fixed.pass_prob == 1.0 and cush.pass_prob == 1.0

    def test_sizing_block_in_json(self) -> None:
        firm = load_firm("topstep_50k")
        log = random_log(n_days=50, seed=5)
        report = run_monte_carlo(log, firm, MCConfig(n_paths=50, seed=1, sizing="cushion"))
        payload = report.to_json_dict()
        assert payload["sizing"] == {"mode": "cushion", "cushion_clip": [0.25, 1.5]}

    def test_unknown_mode_still_raises(self) -> None:
        from quantlab.errors import QuantLabError

        log = random_log(n_days=40, seed=6)
        with pytest.raises(QuantLabError, match="sizing mode"):
            run_monte_carlo(
                log, load_firm("topstep_50k"), MCConfig(n_paths=10, seed=1, sizing="typo")
            )
