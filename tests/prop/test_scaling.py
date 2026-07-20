"""Contract scaling plans bound in-engine (M11.b)."""

from __future__ import annotations

import pytest

from quantlab.errors import ConfigError, QuantLabError
from quantlab.prop.config import ScalingPlanSpec, ScalingTier
from quantlab.prop.evaluator import evaluate
from quantlab.prop.montecarlo import MCConfig, run_monte_carlo
from quantlab.prop.outcomes import OUTCOME_LABELS
from quantlab.prop.registry import load_firm

from ..conftest import random_log
from .conftest import day_trades, simple
from .test_montecarlo import EQUIV_OUTCOME, identity_phase_run


class TestSpecValidation:
    def test_exactly_one_form(self) -> None:
        with pytest.raises(ConfigError, match="exactly one"):
            ScalingPlanSpec()
        with pytest.raises(ConfigError, match="exactly one"):
            ScalingPlanSpec(
                tiers=[ScalingTier(min_balance=0, max_contracts=2)], half_until_safety_net=True
            )

    def test_tiers_must_increase(self) -> None:
        with pytest.raises(ConfigError, match="increasing"):
            ScalingPlanSpec(
                tiers=[
                    ScalingTier(min_balance=1000, max_contracts=2),
                    ScalingTier(min_balance=0, max_contracts=3),
                ]
            )


class TestTopstepTiers:
    def test_tier_cap_binds_at_xfa_start(self) -> None:
        # XFA starts at $0 balance -> tier allows 2 of the log's 5-contract
        # base -> day-1 PnL scaled by 0.4.
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(500.0)], [simple(500.0)]], quantity=5)
        result = evaluate(log, firm, phase="funded")
        assert result.timeline.iloc[0]["day_pnl"] == pytest.approx(500.0 * 2 / 5)
        assert any("scaling plan capped" in a for a in result.advisories)

    def test_tier_grows_with_balance(self) -> None:
        # Climb the tiers: after banked profit crosses $2,000 the full 5
        # contracts unlock and the weight cap disappears (base = 5).
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(3000.0)]] * 4, quantity=5)
        result = evaluate(log, firm, phase="funded")
        # Day 1: 0.4 * 3000 = 1200 (balance 1200 -> still tier 1 -> 0.4)
        # Day 2: 1200 -> 0.4 * 3000 = 1200 (2400 -> tier 3: 5/5 = 1.0)
        # Day 3: full size.
        assert result.timeline.iloc[0]["day_pnl"] == pytest.approx(1200.0)
        assert result.timeline.iloc[1]["day_pnl"] == pytest.approx(1200.0)
        assert result.timeline.iloc[2]["day_pnl"] == pytest.approx(3000.0)

    def test_cap_never_scales_up(self) -> None:
        # A 1-contract log in a tier allowing 2: weight stays 1, never 2.
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(100.0)]] * 3, quantity=1)
        result = evaluate(log, firm, phase="funded")
        assert result.timeline.iloc[0]["day_pnl"] == pytest.approx(100.0)


class TestApexHalfUntilSafetyNet:
    def test_half_then_sticky_unlock(self) -> None:
        # Apex 50K EOD: safety net 52,100, firm max 10 contracts. A
        # full-allowance (10-lot) trader is halved until the close reaches
        # the net; the unlock survives a later dip.
        firm = load_firm("apex40_50k_eod")
        log = day_trades(
            [
                [simple(2000.0)],  # 0.5x -> +1000 (51,000)
                [simple(2400.0)],  # 0.5x -> +1200 (52,200 >= 52,100: unlock)
                [simple(-500.0)],  # full size -> -500 (51,700, below net)
                [simple(1000.0)],  # STILL full size (sticky)
            ],
            quantity=10,
        )
        result = evaluate(log, firm, phase="funded")
        assert result.timeline.iloc[0]["day_pnl"] == pytest.approx(1000.0)
        assert result.timeline.iloc[1]["day_pnl"] == pytest.approx(1200.0)
        assert result.timeline.iloc[2]["day_pnl"] == pytest.approx(-500.0)
        assert result.timeline.iloc[3]["day_pnl"] == pytest.approx(1000.0)

    def test_challenge_phase_unaffected(self) -> None:
        # The scaling plan lives on the PA only; the eval runs full size.
        firm = load_firm("apex40_50k_eod")
        log = day_trades([[simple(1000.0)]] * 2, quantity=10)
        result = evaluate(log, firm, phase="challenge")
        assert result.timeline.iloc[0]["day_pnl"] == pytest.approx(1000.0)


class TestGoldenEquivalence:
    @pytest.mark.parametrize("preset", ["topstep_50k", "apex40_50k_eod"])
    @pytest.mark.parametrize(
        "spec",
        [
            dict(n_days=90, mean=40.0, std=180.0, seed=11),
            dict(n_days=90, mean=15.0, std=350.0, seed=14),
        ],
    )
    def test_identity_resample_matches_evaluator(self, preset: str, spec: dict) -> None:
        firm = load_firm(preset)
        log = random_log(with_excursions=True, **spec)
        base = log.max_abs_quantity()
        for phase_cfg in [*firm.phases, firm.funded]:
            scalar = evaluate(log, firm, phase=phase_cfg.name)
            vector = identity_phase_run(log, firm, phase_cfg.name, base_contracts=base)
            v_outcome = OUTCOME_LABELS[int(vector.outcome[0])]
            assert OUTCOME_LABELS[EQUIV_OUTCOME[scalar.outcome]] == v_outcome, (
                f"{preset}/{phase_cfg.name}: scalar={scalar.outcome} vector={v_outcome}"
            )
            if scalar.outcome in ("incomplete", "survived"):
                assert float(vector.final_balance[0]) == pytest.approx(scalar.final_balance)


class TestMonteCarloIntegration:
    def test_base_derived_from_log_with_warning(self) -> None:
        firm = load_firm("apex40_50k_eod")
        log = random_log(n_days=60, mean=40.0, std=300.0, seed=7)
        report = run_monte_carlo(log, firm, MCConfig(n_paths=100, seed=1))
        assert any("scaling plan enforced" in w for w in report.warnings)

    def test_explicit_base_contracts_draws_no_assumption_warning(self) -> None:
        # An explicit --base-contracts is a user-supplied fact; the
        # "assuming the log's max position IS the full allowance" text
        # would misname the override as a log-derived guess.
        firm = load_firm("apex40_50k_eod")
        log = random_log(n_days=60, mean=40.0, std=300.0, seed=7)
        report = run_monte_carlo(log, firm, MCConfig(n_paths=100, seed=1, base_contracts=10.0))
        assert not any("scaling plan enforced" in w for w in report.warnings)

    def test_under_allowance_trader_not_halved(self) -> None:
        # M11 review fix: the real Apex rule is half of the FIRM max (10),
        # not half of the traded size. A 1-lot trader (well under the
        # pre-unlock allowance of 5) must match a firm with no scaling
        # rule exactly — the old ratio form spuriously halved everyone.
        firm = load_firm("apex40_50k_eod")
        bare = firm.model_copy(deep=True)
        bare.funded.rules = [r for r in bare.funded.rules if r.type != "scaling_plan"]
        log = random_log(n_days=60, mean=40.0, std=300.0, seed=7)  # quantity 1
        capped = run_monte_carlo(log, firm, MCConfig(n_paths=200, seed=2))
        uncapped = run_monte_carlo(log, bare, MCConfig(n_paths=200, seed=2))
        assert capped.economics.expected_net == uncapped.economics.expected_net

    def test_apex_half_cap_changes_funded_outcomes(self) -> None:
        # The cap must actually bite: funded economics differ from the
        # same firm with the scaling rule removed.
        firm = load_firm("apex40_50k_eod")
        bare = firm.model_copy(deep=True)
        bare.funded.rules = [r for r in bare.funded.rules if r.type != "scaling_plan"]
        log = random_log(n_days=80, mean=60.0, std=250.0, seed=9)
        # base_contracts=10 = the full allowance -> pre-unlock cap 0.5.
        capped = run_monte_carlo(log, firm, MCConfig(n_paths=300, seed=3, base_contracts=10))
        uncapped = run_monte_carlo(log, bare, MCConfig(n_paths=300, seed=3, base_contracts=10))
        assert capped.economics.expected_net != uncapped.economics.expected_net
        # Direction is log-dependent by design: half size slows early
        # growth but also protects paths from early ruin (payouts are
        # capped, losses are not) — no monotonicity to assert.

    def test_bad_base_override_raises(self) -> None:
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(100.0)]] * 40)
        with pytest.raises(QuantLabError, match="base"):
            run_monte_carlo(log, firm, MCConfig(n_paths=10, seed=1, base_contracts=-1))


class TestScaleTimesCapInteraction:
    """M11 review fix: a scale what-if multiplies the trader's contracts,
    so the plan's weight cap must divide by scale x base — otherwise
    --scale 2 quietly runs double the allowed size through an enforced
    plan (and --scale 0.5 over-restricts)."""

    def test_scale_two_still_respects_tier_contracts(self) -> None:
        # XFA day 1, tier allows 2 contracts, log base 5, scale 2:
        # effective contracts = 2 * w * 5 must cap at 2 -> w = 0.2, so the
        # day PnL (already 2x in the profile) caps at 2/5 of the raw log
        # day: 2 * 500 * 0.2 = 200 = tier_allowed/base * raw.
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(500.0)]] * 3, quantity=5)
        capped = run_monte_carlo(
            log, firm, MCConfig(n_paths=10, seed=1, scale=2.0, funded_horizon_days=1)
        )
        # One funded day at scale 2: balance change equals the capped day.
        assert float(capped.funded.final_balance[0]) == pytest.approx(200.0)

    def test_half_scale_not_over_restricted(self) -> None:
        # scale 0.5 with a 5-contract log = 2.5 effective contracts: the
        # day-1 tier (2 allowed) caps weight at 2/2.5 = 0.8, NOT 2/5.
        firm = load_firm("topstep_50k")
        log = day_trades([[simple(500.0)]] * 3, quantity=5)
        run = run_monte_carlo(
            log, firm, MCConfig(n_paths=10, seed=1, scale=0.5, funded_horizon_days=1)
        )
        # Raw day at scale 0.5 = 250; capped at 0.8 -> 200 (= tier cap in $).
        assert float(run.funded.final_balance[0]) == pytest.approx(200.0)
