"""Regime analysis: per-regime PnL diagnostic + worst-regime stress.

From the trade log alone, the identifiable regime is the strategy's own
PnL-volatility state: each trading day is labeled by the tercile of its
EWMA forecast sigma (the M9 path, strict t-1 inside the recursion; the
tercile CUTS use the full path — this is a DESCRIPTION of the log, not
a tradable signal, and is labeled as such). With optional user OHLCV,
days are additionally labeled by the market's character — trend sign
(close vs 20-day SMA) x ATR(14) tercile — a descriptive join only.

The actionable output is the STRESS, not a forecast (regime-switching
forecasts from one trade log are unidentifiable; cf. Hamilton 1989 for
what a real regime model needs): "if the worst-performing regime
persisted, would the campaign survive?" — a block bootstrap restricted
to the worst regime's days (Politis-White blocks within the subset),
run through the full prop-firm Monte Carlo. This is the honest version
of QuantPad-style regime-switching MC: a stress scenario with the
conditioning stated, never a probability-weighted prediction.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

import numpy as np

from quantlab.metrics.volforecast import DEFAULT_LAMBDA, ewma_sigma_path
from quantlab.prop.config import FirmConfig
from quantlab.schema.trade import FUTURES_DAY, TradeLog

REGIME_LABELS = ("low_vol", "mid_vol", "high_vol")
MIN_CLASSIFIED_DAYS = 30  # below this the analysis is skipped, not degraded
MIN_STRESS_DAYS = 20  # worst-regime subset floor for the conditioned MC


@dataclass(frozen=True, slots=True)
class RegimeStats:
    regime: str
    n_days: int
    n_trades: int
    net: float
    day_expectancy: float  # mean day PnL in the regime
    trade_win_rate: float
    persistence: float  # P(next classified day stays in this regime)


@dataclass(frozen=True, slots=True)
class MarketRegimeStats:
    regime: str  # e.g. "up_high_vol"
    n_days: int
    net: float
    day_expectancy: float


@dataclass
class RegimeAnalysis:
    method: str
    lam: float
    burn_in: int
    n_days: int
    n_classified: int
    tested: bool
    regimes: list[RegimeStats] = field(default_factory=list)
    worst_regime: str | None = None
    # Profitable overall, but the worst regime loses enough to erase a
    # material share (>=20%) of the net — the edge is regime-dependent.
    regime_dependent: bool = False
    stress: dict | None = None  # worst-regime-persists MC summary
    market: list[MarketRegimeStats] | None = None  # OHLCV join, when provided
    warnings: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict:
        return dataclasses.asdict(self)


def classify_vol_regimes(
    day_pnl: np.ndarray, lam: float = DEFAULT_LAMBDA, burn_in: int = 20
) -> np.ndarray:
    """Per-day regime codes: -1 unclassified (burn-in), else 0/1/2 for
    low/mid/high forecast-vol terciles."""
    sigma = np.array(ewma_sigma_path(day_pnl, lam=lam, burn_in=burn_in).sigma)
    codes = np.full(sigma.size, -1, dtype=np.int64)
    valid = ~np.isnan(sigma)
    if valid.sum() < 3:
        return codes
    lo, hi = np.quantile(sigma[valid], [1.0 / 3.0, 2.0 / 3.0])
    codes[valid] = np.where(sigma[valid] <= lo, 0, np.where(sigma[valid] <= hi, 1, 2))
    return codes


def _market_join(ohlcv, days: list, boundary) -> tuple[list[MarketRegimeStats], list[str]]:
    """Descriptive trend x vol labels for the trade days covered by the
    user's bars. `ohlcv` is the load_ohlcv normalized frame."""
    import pandas as pd

    frame = ohlcv.copy()
    stamps = pd.DatetimeIndex(frame["datetime"])
    session = [boundary.session_date(ts.to_pydatetime()) for ts in stamps]
    frame["session"] = session
    daily = frame.groupby("session").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")
    )
    prev_close = daily["close"].shift(1)
    tr = np.maximum(
        daily["high"] - daily["low"],
        np.maximum((daily["high"] - prev_close).abs(), (daily["low"] - prev_close).abs()),
    )
    atr = tr.rolling(14).mean()
    sma = daily["close"].rolling(20).mean()
    labeled = daily.assign(atr=atr, sma=sma).dropna(subset=["atr", "sma"])
    warnings: list[str] = []
    if labeled.empty:
        return [], ["--ohlcv: too few bars for ATR(14)/SMA(20) — market join skipped"]
    lo, hi = np.quantile(labeled["atr"], [1.0 / 3.0, 2.0 / 3.0])
    buckets: dict[str, list[float]] = {}
    matched = 0
    for date, trades in days:
        if date not in labeled.index:
            continue
        row = labeled.loc[date]
        trend = "up" if float(row["close"]) >= float(row["sma"]) else "down"
        vol = "low_vol" if row["atr"] <= lo else ("mid_vol" if row["atr"] <= hi else "high_vol")
        buckets.setdefault(f"{trend}_{vol}", []).append(sum(t.pnl for t in trades))
        matched += 1
    if matched < len(days):
        warnings.append(
            f"--ohlcv covers {matched}/{len(days)} trade days — market regimes "
            "describe the covered days only"
        )
    stats = [
        MarketRegimeStats(
            regime=name,
            n_days=len(pnls),
            net=float(np.sum(pnls)),
            day_expectancy=float(np.mean(pnls)),
        )
        for name, pnls in sorted(buckets.items())
    ]
    return stats, warnings


def compute_regimes(
    log: TradeLog,
    firm: FirmConfig | None = None,
    mc_cfg=None,
    lam: float = DEFAULT_LAMBDA,
    burn_in: int = 20,
    ohlcv=None,
    precomputed_days: list | None = None,
) -> RegimeAnalysis:
    """Per-regime PnL breakdown and, with a firm, the worst-regime-persists
    stress Monte Carlo."""
    boundary = firm.day_boundary.to_boundary() if firm is not None else FUTURES_DAY
    days = log.daily_groups(boundary) if precomputed_days is None else precomputed_days
    day_pnl = log.daily_pnl(boundary, days=days)
    codes = classify_vol_regimes(day_pnl, lam=lam, burn_in=burn_in)
    classified = codes >= 0
    n_classified = int(classified.sum())

    result = RegimeAnalysis(
        method="pnl_vol_terciles",
        lam=lam,
        burn_in=burn_in,
        n_days=len(days),
        n_classified=n_classified,
        tested=n_classified >= MIN_CLASSIFIED_DAYS,
    )
    if not result.tested:
        result.warnings.append(
            f"only {n_classified} classified days (<{MIN_CLASSIFIED_DAYS}) — "
            "regime analysis skipped (no verdict either way)"
        )
        return result

    for code, label in enumerate(REGIME_LABELS):
        mask = codes == code
        n_days_r = int(mask.sum())
        if n_days_r == 0:
            continue
        trades = [t for d in np.flatnonzero(mask) for t in days[d][1]]
        wins = sum(1 for t in trades if t.pnl > 0)
        # Persistence over consecutive classified pairs only.
        stay = same = 0
        for d in range(len(codes) - 1):
            if codes[d] == code and codes[d + 1] >= 0:
                stay += 1
                same += int(codes[d + 1] == code)
        result.regimes.append(
            RegimeStats(
                regime=label,
                n_days=n_days_r,
                n_trades=len(trades),
                net=float(day_pnl[mask].sum()),
                day_expectancy=float(day_pnl[mask].mean()),
                trade_win_rate=wins / len(trades) if trades else 0.0,
                persistence=same / stay if stay else 0.0,
            )
        )

    # The persistence stress conditions on the worst PER-DAY regime (the
    # damage-rate notion); the dependence trigger uses the most-eroding
    # regime BY NET (keying it to the stress regime would one-directionally
    # weaken the flag whenever tercile counts diverge). The overfit flag
    # names the eroding regime and cites the stress row only when the two
    # coincide — no misdirection, no lost sensitivity.
    worst = min(result.regimes, key=lambda r: r.day_expectancy)
    result.worst_regime = worst.regime
    total_net = float(day_pnl[classified].sum())
    if total_net > 0:
        worst_by_net = min(result.regimes, key=lambda r: r.net)
        result.regime_dependent = worst_by_net.net < 0 and -worst_by_net.net >= 0.2 * total_net

    if firm is not None:
        result.stress, stress_warnings = _worst_regime_stress(log, firm, mc_cfg, days, codes, worst)
        result.warnings.extend(stress_warnings)
    if ohlcv is not None:
        result.market, market_warnings = _market_join(ohlcv, days, boundary)
        result.warnings.extend(market_warnings)
    return result


def _worst_regime_stress(
    log: TradeLog, firm: FirmConfig, mc_cfg, days: list, codes: np.ndarray, worst: RegimeStats
) -> tuple[dict | None, list[str]]:
    from quantlab.prop.bootstrap import (
        BootstrapName,
        make_bootstrapper,
        optimal_block_length,
    )
    from quantlab.prop.dayprofile import DayProfile
    from quantlab.prop.montecarlo import (
        MIN_DAYS_FOR_BLOCKS,
        MCConfig,
        _run_from_profile,
        observed_sessions_per_week,
    )

    label = worst.regime
    subset = np.flatnonzero(codes == (REGIME_LABELS.index(label)))
    if subset.size < MIN_STRESS_DAYS:
        return None, [
            f"worst regime ({label}) has only {subset.size} days "
            f"(<{MIN_STRESS_DAYS}) — persistence stress skipped"
        ]
    if subset.size == int((codes >= 0).sum()):
        return None, ["all classified days share one regime — persistence stress is the baseline"]

    cfg = mc_cfg or MCConfig()
    boundary = firm.day_boundary.to_boundary()
    profile = DayProfile.from_log(log, boundary, days=days).gather(subset)
    name: BootstrapName
    if subset.size >= MIN_DAYS_FOR_BLOCKS:
        name = "stationary"
        block = optimal_block_length(profile.day_pnl)
    else:
        name, block = "iid_day", None
    report = _run_from_profile(
        profile,
        firm,
        cfg,
        rng=np.random.default_rng(cfg.seed),
        sampler=make_bootstrapper(name, block),
        bootstrap_name=name,
        block_len_used=block,
        sessions_per_week=observed_sessions_per_week(log, boundary, days=days),
        source_trades=len(log),
        warnings=[],
    )
    eco = report.economics
    return {
        "regime": label,
        "n_days": int(subset.size),
        "bootstrap": name,
        "pass_prob": eco.pass_prob,
        "expected_net": eco.expected_net,
        "risk_of_ruin_funded": eco.risk_of_ruin_funded,
    }, []
