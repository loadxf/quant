"""The Verdict: A-F strategy scorecard.

Four pillars, each graded A-F against documented thresholds (rendered in
the report). Overall = weighted grade points (Edge 30 / Robustness 30 /
Risk 20 / Sample 20), CAPPED at the sample-size grade — no A-verdict
from 40 trades.

| Pillar      | A                  | B                  | C                | D                 |
|-------------|--------------------|--------------------|------------------|-------------------|
| Edge        | PF>=1.75 & Sh>=2.0 | PF>=1.5 & Sh>=1.5  | PF>=1.3 & Sh>=1  | PF>=1.15 & Sh>=.5 |
| Robustness  | P>=99% & PF-5>=1.3 | P>=95% & PF-5>=1.15| P>=90% & PF-5>=1 | P>=80%            |
| Risk        | MAR>=2 & WL/AL<=4  | MAR>=1 & <=6       | MAR>=.5 & <=8    | MAR>=.25          |
| Sample      | N>=500 & t>=3      | N>=300 & t>=2.5    | N>=150 & t>=2    | N>=75 & t>=1.5    |

(P = bootstrap P(expectancy > 0); PF-5 = profit factor after dropping the
top 5 winners; WL/AL = worst loss / average loss.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from quantlab.metrics.core import Metrics, bootstrap_means, compute_metrics
from quantlab.metrics.overfit import OverfitFlag, overfit_flags
from quantlab.schema.trade import TradeLog

GRADE_POINTS = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}
WEIGHTS = {"edge": 0.30, "robustness": 0.30, "risk": 0.20, "sample": 0.20}


@dataclass
class PillarScore:
    name: str
    grade: str
    detail: str
    inputs: dict[str, float] = field(default_factory=dict)


@dataclass
class Verdict:
    edge: PillarScore
    robustness: PillarScore
    risk: PillarScore
    sample: PillarScore
    overall: str
    points: float
    capped_by_sample: bool
    flags: list[OverfitFlag]

    @property
    def pillars(self) -> list[PillarScore]:
        return [self.edge, self.robustness, self.risk, self.sample]

    def to_json_dict(self) -> dict:
        return {
            "overall": self.overall,
            "points": round(self.points, 3),
            "capped_by_sample": self.capped_by_sample,
            "pillars": {
                p.name: {"grade": p.grade, "detail": p.detail, "inputs": p.inputs}
                for p in self.pillars
            },
            "flags": [
                {"name": f.name, "triggered": f.triggered, "explanation": f.explanation}
                for f in self.flags
            ],
        }


def _ladder(checks: list[tuple[str, bool]]) -> str:
    """First grade whose predicate holds; F otherwise."""
    for grade, passed in checks:
        if passed:
            return grade
    return "F"


def _grade_edge(m: Metrics) -> PillarScore:
    pf, sh = m.profit_factor, m.sharpe
    grade = _ladder(
        [
            ("A", pf >= 1.75 and sh >= 2.0),
            ("B", pf >= 1.5 and sh >= 1.5),
            ("C", pf >= 1.3 and sh >= 1.0),
            ("D", pf >= 1.15 and sh >= 0.5),
        ]
    )
    return PillarScore(
        "edge",
        grade,
        f"profit factor {pf:.2f}, Sharpe {sh:.2f}",
        {"profit_factor": pf, "sharpe": sh},
    )


def _grade_robustness(log: TradeLog, m: Metrics) -> PillarScore:
    pnls = np.array([t.pnl for t in log.trades])
    n = pnls.size
    # Computed inside compute_metrics from the SAME bootstrap run as the
    # expectancy CI (same count and seed, even caller-overridden ones), so
    # the two published statistics can never disagree — and the most
    # expensive metrics computation runs once, not twice. A Metrics built
    # outside compute_metrics carries None: recompute at defaults rather
    # than silently grading F.
    p_positive = m.bootstrap_p_positive
    if p_positive is None:
        p_positive = float(np.mean(bootstrap_means(pnls) > 0)) if n > 1 else 0.0
    trimmed = np.sort(pnls)[:-5] if n > 5 else pnls
    wins, losses = trimmed[trimmed > 0].sum(), -trimmed[trimmed < 0].sum()
    pf_trimmed = float(wins / losses) if losses > 0 else float("inf")

    if p_positive >= 0.99 and pf_trimmed >= 1.3:
        grade = "A"
    elif p_positive >= 0.95 and pf_trimmed >= 1.15:
        grade = "B"
    elif p_positive >= 0.90 and pf_trimmed >= 1.0:
        grade = "C"
    elif p_positive >= 0.80:
        grade = "D"
    else:
        grade = "F"
    return PillarScore(
        "robustness",
        grade,
        f"bootstrap P(edge>0) {p_positive:.0%}, PF without top-5 wins {pf_trimmed:.2f}",
        {"p_expectancy_positive": p_positive, "pf_minus_top5": pf_trimmed},
    )


def _grade_risk(log: TradeLog, m: Metrics) -> PillarScore:
    pnls = np.array([t.pnl for t in log.trades])
    losses = pnls[pnls < 0]
    wl_ratio = float(abs(losses.min()) / abs(losses.mean())) if losses.size else 0.0
    mar = m.mar
    if mar >= 2 and wl_ratio <= 4:
        grade = "A"
    elif mar >= 1 and wl_ratio <= 6:
        grade = "B"
    elif mar >= 0.5 and wl_ratio <= 8:
        grade = "C"
    elif mar >= 0.25:
        grade = "D"
    else:
        grade = "F"
    return PillarScore(
        "risk",
        grade,
        f"MAR {mar:.2f}, worst/avg loss {wl_ratio:.1f}x",
        {"mar": mar, "worst_over_avg_loss": wl_ratio},
    )


def _grade_sample(m: Metrics) -> PillarScore:
    n, t = m.trade_count, m.expectancy_tstat
    grade = _ladder(
        [
            ("A", n >= 500 and t >= 3.0),
            ("B", n >= 300 and t >= 2.5),
            ("C", n >= 150 and t >= 2.0),
            ("D", n >= 75 and t >= 1.5),
        ]
    )
    return PillarScore(
        "sample",
        grade,
        f"{n} trades, expectancy t-stat {t:.2f}",
        {"trade_count": float(n), "t_stat": t},
    )


def compute_scorecard(log: TradeLog, metrics: Metrics | None = None) -> Verdict:
    m = metrics or compute_metrics(log)
    edge = _grade_edge(m)
    robustness = _grade_robustness(log, m)
    risk = _grade_risk(log, m)
    sample = _grade_sample(m)

    points = sum(GRADE_POINTS[p.grade] * WEIGHTS[p.name] for p in (edge, robustness, risk, sample))
    uncapped_points = points
    points = min(points, GRADE_POINTS[sample.grade])
    capped = points < uncapped_points

    if points >= 3.5:
        overall = "A"
    elif points >= 2.5:
        overall = "B"
    elif points >= 1.5:
        overall = "C"
    elif points >= 0.5:
        overall = "D"
    else:
        overall = "F"

    return Verdict(
        edge=edge,
        robustness=robustness,
        risk=risk,
        sample=sample,
        overall=overall,
        points=points,
        capped_by_sample=capped,
        flags=overfit_flags(log, m),
    )
