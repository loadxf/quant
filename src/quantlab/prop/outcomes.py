"""Result containers for the Monte Carlo simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

OUTCOME_ACTIVE = 0  # still running at horizon (eval: incomplete; funded: survived)
OUTCOME_PASSED = 1
OUTCOME_BREACHED = 2
OUTCOME_EXPIRED = 3
OUTCOME_RETIRED = 4  # funded account closed by lifetime payout cap (Apex 4.0)

OUTCOME_LABELS = {
    OUTCOME_ACTIVE: "active",
    OUTCOME_PASSED: "passed",
    OUTCOME_BREACHED: "breached",
    OUTCOME_EXPIRED: "expired",
    OUTCOME_RETIRED: "retired",
}


@dataclass
class PhaseOutcome:
    """Per-path arrays for one simulated phase (all shape (P,) unless noted)."""

    phase: str
    initial_balance: float
    horizon: int
    outcome: np.ndarray  # int8 codes above
    end_day: np.ndarray  # trading-day index when resolved; horizon-1 if active
    fail_rule: np.ndarray  # int16 index into rule_names; -1 = none
    rule_names: list[str]
    final_balance: np.ndarray
    max_drawdown: np.ndarray
    equity_samples: np.ndarray  # (S, H) day-close equity; NaN after resolution
    lockout_days: np.ndarray  # count of daily-loss lockout days per path
    # Funded-phase payout tracking (None for eval phases):
    total_withdrawn: np.ndarray | None = None
    payout_count: np.ndarray | None = None
    first_payout_day: np.ndarray | None = None  # -1 = never

    @property
    def passed(self) -> np.ndarray:
        return self.outcome == OUTCOME_PASSED

    def fail_breakdown(self) -> dict[str, float]:
        """Fraction of paths ended by each rule (and expiry)."""
        out: dict[str, float] = {}
        for code, name in enumerate(self.rule_names):
            out[name] = float(
                np.mean((self.outcome == OUTCOME_BREACHED) & (self.fail_rule == code))
            )
        expired = float(np.mean(self.outcome == OUTCOME_EXPIRED))
        if expired:
            out["time_limit"] = expired
        return {k: v for k, v in out.items() if v > 0}


@dataclass
class EconomicsSummary:
    pass_prob: float
    pass_prob_ci: tuple[float, float]  # Wilson 95%
    expected_fees_per_attempt: float
    expected_cost_to_funded: float  # E[eval fees spent until first pass, unlimited retries]
    expected_gross_payout: float  # E[withdrawn * split + refund | funded], per funded account
    expected_net: float  # single-attempt EV: -fees + pass * (funded value - activation)
    ev_with_resets: dict[int, float]  # campaign EV allowing k attempts, k=1..5
    p_net_positive: float
    var_95: float  # 5th percentile of single-attempt net
    cvar_95: float  # mean of the worst 5%
    p_payout: float  # P(>=1 payout | funded)
    risk_of_ruin_funded: float  # P(funded breached before any payout)
    payout_quantiles: dict[str, float]  # net received per funded account
    time_to_pass_quantiles: dict[str, float]  # trading days across eval phases
    days_to_first_payout_quantiles: dict[str, float]  # trading days incl. eval
    overhead: dict[str, float] | None = None  # extra_monthly / per_payout knobs, when set
    reactivation: dict[str, Any] | None = None  # Back2Funded option value, when firm defines it
    # (P,) single-attempt net per path — feeds the multi-account analysis;
    # deliberately NOT serialized (to_json_dict enumerates fields).
    net_per_path: np.ndarray | None = None


@dataclass
class MonteCarloReport:
    firm_name: str
    firm_display: str
    account_size: float
    n_paths: int
    seed: int | None
    bootstrap: str
    block_len: int | None
    fidelity: str
    scale_challenge: float
    scale_funded: float
    source_days: int
    source_trades: int
    phases: list[PhaseOutcome]  # eval phases in order
    funded: PhaseOutcome
    economics: EconomicsSummary
    warnings: list[str] = field(default_factory=list)
    sizing: dict[str, Any] = field(default_factory=lambda: {"mode": "fixed"})

    def to_json_dict(self) -> dict[str, Any]:
        """Stable numeric summary (no per-path arrays)."""
        eco = self.economics
        return {
            "schema_version": 3,  # v3: adds economics.overhead + economics.reactivation (M10)
            "firm": self.firm_name,
            "account_size": self.account_size,
            "n_paths": self.n_paths,
            "seed": self.seed,
            "bootstrap": self.bootstrap,
            "block_len": self.block_len,
            "sizing": self.sizing,
            "fidelity": self.fidelity,
            "scale_challenge": self.scale_challenge,
            "scale_funded": self.scale_funded,
            "source_days": self.source_days,
            "source_trades": self.source_trades,
            "warnings": self.warnings,
            "phases": [
                {
                    "phase": ph.phase,
                    "pass_prob": float(np.mean(ph.passed)),
                    "fail_breakdown": ph.fail_breakdown(),
                    "median_end_day": float(np.median(ph.end_day)),
                    "lockout_day_rate": float(np.mean(ph.lockout_days > 0)),
                }
                for ph in self.phases
            ],
            "funded": {
                "survive_rate": float(np.mean(self.funded.outcome == OUTCOME_ACTIVE)),
                "breach_rate": float(np.mean(self.funded.outcome == OUTCOME_BREACHED)),
                "retired_rate": float(np.mean(self.funded.outcome == OUTCOME_RETIRED)),
                "fail_breakdown": self.funded.fail_breakdown(),
                # Trading drawdown only — payout withdrawals rebase the peak.
                "max_drawdown_quantiles": {
                    f"p{q}": float(np.percentile(self.funded.max_drawdown, q)) for q in (50, 75, 95)
                },
            },
            "economics": {
                "pass_prob": eco.pass_prob,
                "pass_prob_ci": list(eco.pass_prob_ci),
                "expected_fees_per_attempt": eco.expected_fees_per_attempt,
                "expected_cost_to_funded": eco.expected_cost_to_funded,
                "expected_gross_payout": eco.expected_gross_payout,
                "expected_net": eco.expected_net,
                "ev_with_resets": {str(k): v for k, v in eco.ev_with_resets.items()},
                "p_net_positive": eco.p_net_positive,
                "var_95": eco.var_95,
                "cvar_95": eco.cvar_95,
                "p_payout": eco.p_payout,
                "risk_of_ruin_funded": eco.risk_of_ruin_funded,
                "payout_quantiles": eco.payout_quantiles,
                "time_to_pass_quantiles": eco.time_to_pass_quantiles,
                "days_to_first_payout_quantiles": eco.days_to_first_payout_quantiles,
                "overhead": eco.overhead,
                "reactivation": eco.reactivation,
            },
        }
