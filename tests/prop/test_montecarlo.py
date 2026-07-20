"""Vectorized Monte Carlo: golden equivalence with the scalar evaluator,
determinism, and behavioral sanity."""

from __future__ import annotations

import json

import numpy as np
import pytest

from quantlab.prop.dayprofile import DayProfile
from quantlab.prop.evaluator import evaluate
from quantlab.prop.montecarlo import MCConfig, _simulate_phase, run_monte_carlo
from quantlab.prop.outcomes import (
    OUTCOME_ACTIVE,
    OUTCOME_BREACHED,
    OUTCOME_EXPIRED,
    OUTCOME_LABELS,
    OUTCOME_PASSED,
)
from quantlab.prop.registry import load_firm
from quantlab.schema.trade import DayBoundary

from ..conftest import random_log
from .conftest import day_trades, make_firm, simple

EQUIV_OUTCOME = {
    "incomplete": OUTCOME_ACTIVE,
    "survived": OUTCOME_ACTIVE,
    "passed": OUTCOME_PASSED,
    "breached": OUTCOME_BREACHED,
    "expired": OUTCOME_EXPIRED,
}


def identity_phase_run(log, firm, phase_name, sizing=None, cushion_clip=None):
    """Run the vectorized engine on ONE path that replays the log verbatim."""
    boundary = DayBoundary(firm.day_boundary.tz, firm.day_boundary.cutoff_hour)
    profile = DayProfile.from_log(log, boundary)
    idx = np.arange(profile.n_days, dtype=np.int64)[None, :]
    phase_cfg = next(
        (p for p in [*firm.phases, firm.funded] if p.name == phase_name), firm.phases[0]
    )
    return _simulate_phase(
        profile,
        idx,
        phase_cfg,
        firm,
        payout=None,
        sample_paths=1,
        sizing=sizing,
        cushion_clip=cushion_clip,
    )


PRESETS = [
    "topstep_50k",
    "apex40_50k_intraday",
    "apex40_50k_eod",
    "tpt_50k",
    "ftmo_2step_100k",
    "ftmo_1step_100k",
]
LOG_SPECS = [
    dict(n_days=90, mean=40.0, std=180.0, seed=11),  # winner
    dict(n_days=90, mean=-40.0, std=180.0, seed=12),  # loser
    dict(n_days=90, mean=0.0, std=260.0, seed=13),  # volatile zero-EV
    dict(n_days=90, mean=15.0, std=350.0, seed=14),  # wild
    dict(n_days=40, mean=60.0, std=120.0, seed=15),  # short strong
    dict(n_days=90, mean=5.0, std=60.0, seed=16),  # quiet grinder
]


class TestGoldenEquivalence:
    @pytest.mark.parametrize("preset", PRESETS)
    @pytest.mark.parametrize("spec_index", range(len(LOG_SPECS)))
    def test_identity_resample_matches_evaluator(self, preset: str, spec_index: int) -> None:
        firm = load_firm(preset)
        log = random_log(with_excursions=True, **LOG_SPECS[spec_index])

        for phase_cfg in [*firm.phases, firm.funded]:
            scalar = evaluate(log, firm, phase=phase_cfg.name)
            vector = identity_phase_run(log, firm, phase_cfg.name)

            v_outcome = OUTCOME_LABELS[int(vector.outcome[0])]
            s_outcome = EQUIV_OUTCOME[scalar.outcome]
            assert OUTCOME_LABELS[s_outcome] == v_outcome, (
                f"{preset}/{phase_cfg.name}: scalar={scalar.outcome} vector={v_outcome}"
            )
            if scalar.outcome in ("passed", "breached"):
                expected_day = (
                    scalar.pass_day_index if scalar.outcome == "passed" else scalar.breach.day_index  # type: ignore[union-attr]
                )
                assert int(vector.end_day[0]) == expected_day
            if scalar.outcome == "breached":
                assert scalar.breach is not None
                assert vector.rule_names[int(vector.fail_rule[0])] == scalar.breach.rule
            if scalar.outcome in ("incomplete", "survived"):
                assert float(vector.final_balance[0]) == pytest.approx(scalar.final_balance)
            if scalar.outcome == "expired":
                assert int(vector.end_day[0]) == scalar.days_consumed - 1

    def test_lockout_equivalence(self) -> None:
        """DLL lockout truncation must match exactly (Apex EOD-style)."""
        firm = make_firm(
            [
                {
                    "type": "trailing_drawdown",
                    "amount": 2000,
                    "ratchet": "eod",
                    "threshold_cap": 50_000,
                },
                {"type": "daily_loss_limit", "amount": 1000, "effect": "lockout"},
            ],
            target=100_000,
        )
        log = day_trades(
            [
                [simple(-600), simple(-600), simple(300)],  # locks mid-day
                [simple(400)],
                [simple(-700), simple(-500)],  # locks again
                [simple(200)],
            ]
        )
        scalar = evaluate(log, firm)
        vector = identity_phase_run(log, firm, "challenge")
        assert scalar.outcome == "incomplete"
        assert int(vector.outcome[0]) == OUTCOME_ACTIVE
        assert float(vector.final_balance[0]) == pytest.approx(scalar.final_balance)
        assert int(vector.lockout_days[0]) == scalar.lockout_days == 2


class TestDeterminismAndScaling:
    def test_same_seed_identical_json(self, marginal_log) -> None:
        firm = load_firm("topstep_50k")
        cfg = MCConfig(n_paths=500, seed=7)
        a = run_monte_carlo(marginal_log, firm, cfg).to_json_dict()
        b = run_monte_carlo(marginal_log, firm, cfg).to_json_dict()
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_tighter_drawdown_never_raises_pass_prob(self, marginal_log) -> None:
        loose = make_firm(
            [{"type": "trailing_drawdown", "amount": 3000, "ratchet": "eod"}], target=3000
        )
        tight = make_firm(
            [{"type": "trailing_drawdown", "amount": 1500, "ratchet": "eod"}], target=3000
        )
        cfg = MCConfig(n_paths=2000, seed=5)
        p_loose = run_monte_carlo(marginal_log, loose, cfg).economics.pass_prob
        p_tight = run_monte_carlo(marginal_log, tight, cfg).economics.pass_prob
        assert p_tight <= p_loose

    def test_intraday_ratchet_never_easier_than_eod(self, marginal_log) -> None:
        eod = make_firm(
            [{"type": "trailing_drawdown", "amount": 2000, "ratchet": "eod"}], target=3000
        )
        intra = make_firm(
            [{"type": "trailing_drawdown", "amount": 2000, "ratchet": "intraday"}],
            target=3000,
        )
        cfg = MCConfig(n_paths=2000, seed=5)
        p_eod = run_monte_carlo(marginal_log, eod, cfg).economics.pass_prob
        p_intra = run_monte_carlo(marginal_log, intra, cfg).economics.pass_prob
        assert p_intra <= p_eod

    def test_small_sample_falls_back_to_iid(self) -> None:
        log = random_log(n_days=10, seed=3)
        report = run_monte_carlo(log, load_firm("topstep_50k"), MCConfig(n_paths=100, seed=1))
        assert report.bootstrap == "iid_day"
        assert any("low-confidence" in w for w in report.warnings)

    def test_scale_shifts_outcomes(self, winner_log) -> None:
        firm = load_firm("topstep_50k")
        base = run_monte_carlo(winner_log, firm, MCConfig(n_paths=1000, seed=9))
        tiny = run_monte_carlo(winner_log, firm, MCConfig(n_paths=1000, seed=9, scale=0.05))
        # At 5% size a winner can barely reach the target inside the horizon
        assert tiny.economics.pass_prob < base.economics.pass_prob


class TestPayoutMechanics:
    def test_xfa_payout_flow(self) -> None:
        """Topstep XFA: +200/day forever. Qualifying = 5 winning days >= $150.
        First payout on day 5: min(cap 2000, 50% x 1000, balance 1000) = 500."""
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(200)]] * 40)
        boundary = DayBoundary(firm.day_boundary.tz, firm.day_boundary.cutoff_hour)
        profile = DayProfile.from_log(log, boundary)
        idx = np.arange(profile.n_days, dtype=np.int64)[None, :]
        from quantlab.prop.montecarlo import _resolve_payout, _resolve_rules

        gates = _resolve_rules(firm.funded, firm, 0.0).payout_gate_pcts
        payout = _resolve_payout(firm, 0.0, gates)
        outcome = _simulate_phase(profile, idx, firm.funded, firm, payout, 1)
        assert outcome.first_payout_day is not None and outcome.first_payout_day[0] == 4
        assert outcome.total_withdrawn is not None
        # day5 balance 1000 -> withdraw 500; subsequent payouts every 5 days
        assert float(outcome.total_withdrawn[0]) > 0
        assert int(outcome.payout_count[0]) >= 5  # type: ignore[index]

    def test_apex_lifetime_cap_retires_account(self) -> None:
        firm = load_firm("apex40_50k_eod")
        # +700/day: reaches safety net 52,100 in ~3 days beyond start, then
        # 5 qualifying days per cycle -> 6 payouts -> retired.
        log = day_trades([[simple(700)]] * 120)
        boundary = DayBoundary(firm.day_boundary.tz, firm.day_boundary.cutoff_hour)
        profile = DayProfile.from_log(log, boundary)
        idx = np.arange(profile.n_days, dtype=np.int64)[None, :]
        from quantlab.prop.montecarlo import _resolve_payout, _resolve_rules
        from quantlab.prop.outcomes import OUTCOME_RETIRED

        gates = _resolve_rules(firm.funded, firm, 50_000.0).payout_gate_pcts
        payout = _resolve_payout(firm, 50_000.0, gates)
        outcome = _simulate_phase(profile, idx, firm.funded, firm, payout, 1)
        assert int(outcome.outcome[0]) == OUTCOME_RETIRED
        assert int(outcome.payout_count[0]) == 6  # type: ignore[index]
        assert float(outcome.total_withdrawn[0]) <= 13_000  # verified ladder total


class TestVolTargetGoldenEquivalence:
    """M9: the dynamic-sizing mode must keep exact scalar<->vector parity —
    both engines consume the SAME EwmaSizer recursion with identical
    explicit parameters."""

    @pytest.mark.parametrize("preset", ["topstep_50k", "apex40_50k_intraday", "ftmo_1step_100k"])
    @pytest.mark.parametrize("spec_index", [0, 1, 2])
    def test_identity_resample_matches_evaluator(self, preset: str, spec_index: int) -> None:
        from quantlab.prop.voltarget import VolSizingParams

        firm = load_firm(preset)
        log = random_log(with_excursions=True, **LOG_SPECS[spec_index])
        sizing = VolSizingParams(
            lam=0.94, target_vol=150.0, seed_var=150.0**2, clip_lo=0.5, clip_hi=1.5
        )
        for phase_cfg in [*firm.phases, firm.funded]:
            scalar = evaluate(log, firm, phase=phase_cfg.name, sizing=sizing)
            vector = identity_phase_run(log, firm, phase_cfg.name, sizing=sizing)
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


class TestVolTargetHypothesis:
    """The feature's acceptance criterion: dynamic sizing must cut breach
    rates on vol-CLUSTERED synthetic data and stay ~neutral on iid data —
    the honest version of the video's claim."""

    @staticmethod
    def _clustered_log(days: int = 160, seed: int = 21):
        rng = np.random.default_rng(seed)
        rows = []
        sigma = 50.0
        for _ in range(days):
            # Persistent two-state regime chain: calm (50) <-> violent (250),
            # tuned so the fixed-mode funded breach rate sits mid-range
            # (~0.33) where the insurance effect is measurable.
            if rng.random() < 0.04:
                sigma = 250.0 if sigma == 50.0 else 50.0
            rows.append([simple(30.0 + sigma * rng.standard_normal())])
        return day_trades(rows)

    @staticmethod
    def _iid_log(days: int = 160, seed: int = 22):
        rng = np.random.default_rng(seed)
        return day_trades([[simple(30.0 + 130.0 * rng.standard_normal())] for _ in range(days)])

    def test_reduces_breach_on_clustered_log(self) -> None:
        """Insurance effect (Harvey et al. 2018): breach rate drops
        materially; pass probability pays at most a small premium."""
        firm = load_firm("topstep_50k")
        log = self._clustered_log()
        fixed = run_monte_carlo(log, firm, MCConfig(n_paths=1500, seed=5))
        dynamic = run_monte_carlo(log, firm, MCConfig(n_paths=1500, seed=5, sizing="vol_target"))
        breach_fixed = float(np.mean(fixed.funded.outcome == 2))
        breach_dyn = float(np.mean(dynamic.funded.outcome == 2))
        assert breach_dyn < breach_fixed - 0.05
        assert dynamic.economics.pass_prob > fixed.economics.pass_prob - 0.08

    def test_neutral_on_iid_log(self) -> None:
        firm = load_firm("topstep_50k")
        log = self._iid_log()
        fixed = run_monte_carlo(log, firm, MCConfig(n_paths=1500, seed=6))
        dynamic = run_monte_carlo(log, firm, MCConfig(n_paths=1500, seed=6, sizing="vol_target"))
        breach_fixed = float(np.mean(fixed.funded.outcome == 2))
        breach_dyn = float(np.mean(dynamic.funded.outcome == 2))
        assert abs(breach_dyn - breach_fixed) < 0.10

    def test_seed_deterministic_json(self) -> None:
        firm = load_firm("topstep_50k")
        log = self._clustered_log(days=80, seed=23)
        cfg = MCConfig(n_paths=300, seed=7, sizing="vol_target")
        a = run_monte_carlo(log, firm, cfg).to_json_dict()
        b = run_monte_carlo(log, firm, cfg).to_json_dict()
        assert a == b

    def test_unknown_sizing_mode_rejected(self) -> None:
        from quantlab.errors import QuantLabError

        firm = load_firm("topstep_50k")
        log = self._iid_log(days=60, seed=24)
        with pytest.raises(QuantLabError, match="sizing"):
            run_monte_carlo(log, firm, MCConfig(n_paths=10, seed=1, sizing="kelly"))
