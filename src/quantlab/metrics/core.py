"""Standard strategy statistics from a trade log.

Sharpe/Sortino are annualized from the DAILY equity series (252 trading
days) — a documented assumption; trade-level ratios are not comparable
across strategies with different trade frequencies. That series contains
ACTIVE days only; annual_return and MAR annualize over the log's
calendar span instead, so a sparse trader's MAR is not inflated by the
flat days Sharpe never sees.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import numpy as np

from quantlab.errors import QuantLabError
from quantlab.schema.trade import FUTURES_DAY, DayBoundary, TradeLog

TRADING_DAYS_PER_YEAR = 252


@dataclass
class Metrics:
    trade_count: int
    net_profit: float
    win_rate: float
    avg_win: float
    avg_loss: float  # negative
    payoff_ratio: float  # avg_win / |avg_loss|
    expectancy: float  # mean pnl per trade
    expectancy_r: float  # expectancy / |avg_loss|
    expectancy_tstat: float
    expectancy_ci95: tuple[float, float]  # bootstrap CI of mean pnl
    profit_factor: float
    max_drawdown: float  # positive dollars
    max_drawdown_pct: float  # vs starting equity, 0..1
    sharpe: float
    sortino: float
    mar: float  # annualized return / max DD (both vs starting equity)
    longest_losing_streak: int
    best_day: float
    best_day_share: float  # best day / net profit (0 when net <= 0)
    top5_trade_share: float  # top-5 winners / gross profit
    trading_days: int
    daily_pnl_std: float
    per_trade_pnl_std: float
    starting_equity: float
    # P(mean pnl > 0) from the SAME bootstrap run as expectancy_ci95 —
    # the scorecard's robustness pillar consumes this instead of
    # re-resampling with its own (possibly different) count/seed. None
    # (a hand-built or deserialized pre-upgrade Metrics) means "unknown":
    # the scorecard recomputes rather than silently grading F on 0.0.
    bootstrap_p_positive: float | None = None


def _max_drawdown(equity: np.ndarray) -> float:
    peaks = np.maximum.accumulate(equity)
    return float(np.max(peaks - equity)) if equity.size else 0.0


def profit_factor(pnls: np.ndarray) -> float:
    """Gross wins / gross losses; inf for a no-loss winner, 0.0 for a
    no-win log — the single convention every surface shares."""
    wins = float(pnls[pnls > 0].sum())
    losses = float(-pnls[pnls < 0].sum())
    if losses > 0:
        return wins / losses
    return float("inf") if wins > 0 else 0.0


def bootstrap_means(pnls: np.ndarray, n_samples: int = 4000, seed: int = 7) -> np.ndarray:
    """Bootstrap distribution of the mean per-trade PnL.

    Single source for BOTH the expectancy CI (compute_metrics) and the
    robustness pillar's P(edge>0) (scorecard), so the two published
    statistics can never disagree about the same resampling question.
    """
    n = pnls.size
    if n < 2:
        return np.repeat(float(pnls.mean()) if n else 0.0, 2)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_samples, n))
    return pnls[idx].mean(axis=1)


def _annualized_ratio(daily_returns: np.ndarray, downside_only: bool) -> float:
    if daily_returns.size < 2:
        return 0.0
    mean = daily_returns.mean()
    if downside_only:
        # Target-downside deviation over ALL periods (sum of squared
        # below-zero returns / N) — the standard Sortino denominator.
        # Dividing by only the losing days understates the ratio ~16x for
        # rare-loss strategies.
        downside_sq = np.minimum(daily_returns, 0.0) ** 2
        denom = float(np.sqrt(downside_sq.mean()))
    else:
        # ptp==0 catches the whole constant-series class: float noise in
        # std of N identical values can leave a ~1e-14 denominator that
        # turns "the same loss every day" into Sharpe -7e16 instead of
        # the documented -inf convention.
        denom = 0.0 if np.ptp(daily_returns) == 0.0 else float(daily_returns.std(ddof=1))
    if denom == 0.0:
        # Degenerate zero-variance series: keep the sign of the edge —
        # a strategy losing the same amount every day is -inf, not flat.
        if mean > 0:
            return float("inf")
        return float("-inf") if mean < 0 else 0.0
    return float(mean / denom * math.sqrt(TRADING_DAYS_PER_YEAR))


def compute_metrics(
    log: TradeLog,
    starting_equity: float = 50_000.0,
    boundary: DayBoundary = FUTURES_DAY,
    bootstrap_samples: int = 4_000,
    seed: int = 7,
) -> Metrics:
    if starting_equity <= 0:
        raise QuantLabError(f"starting_equity must be positive (got {starting_equity})")
    pnls = np.array([t.pnl for t in log.trades], dtype=float)
    n = pnls.size
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    gross_profit = float(wins.sum())
    avg_win = float(wins.mean()) if wins.size else 0.0
    avg_loss = float(losses.mean()) if losses.size else 0.0
    expectancy = float(pnls.mean()) if n else 0.0
    per_trade_std = float(pnls.std(ddof=1)) if n > 1 else 0.0
    tstat = expectancy / (per_trade_std / math.sqrt(n)) if n > 1 and per_trade_std > 0 else 0.0

    if n > 1:
        means = bootstrap_means(pnls, n_samples=bootstrap_samples, seed=seed)
        ci = (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))
        p_positive = float(np.mean(means > 0))
    else:
        ci = (expectancy, expectancy)
        p_positive = 0.0

    equity = starting_equity + np.cumsum(pnls)
    max_dd = _max_drawdown(np.concatenate(([starting_equity], equity)))

    daily = log.daily_groups(boundary)
    daily_pnls = np.array([sum(t.pnl for t in trades) for _, trades in daily], dtype=float)
    daily_returns = daily_pnls / starting_equity
    # Annualization base for annual_return/MAR: the CALENDAR span of the
    # log (business days first->last session), never less than the active
    # day count (weekend sessions) or one day. Counting only days-with-
    # trades would inflate a once-a-week strategy's annual return ~5x.
    # Sharpe/Sortino keep the documented active-day daily series.
    if daily:
        span_busdays = int(np.busday_count(daily[0][0], daily[-1][0] + dt.timedelta(days=1)))
        years = max(span_busdays, len(daily), 1) / TRADING_DAYS_PER_YEAR
    else:
        years = 1e-9
    annual_return = (float(pnls.sum()) / starting_equity) / years

    streak = longest = 0
    for pnl in pnls:
        streak = streak + 1 if pnl < 0 else 0
        longest = max(longest, streak)

    net = float(pnls.sum())
    best_day = float(daily_pnls.max()) if daily_pnls.size else 0.0
    top5 = float(np.sort(wins)[-5:].sum()) if wins.size else 0.0

    return Metrics(
        trade_count=n,
        net_profit=net,
        win_rate=float(wins.size / n) if n else 0.0,
        avg_win=avg_win,
        avg_loss=avg_loss,
        # No losing trades: report inf (consistent with profit_factor) rather
        # than 0, which would make an all-winner log look edge-less.
        payoff_ratio=avg_win / abs(avg_loss)
        if avg_loss != 0
        else (float("inf") if wins.size else 0.0),
        expectancy=expectancy,
        expectancy_r=(
            expectancy / abs(avg_loss) if avg_loss != 0 else (float("inf") if wins.size else 0.0)
        ),
        expectancy_tstat=tstat,
        expectancy_ci95=ci,
        profit_factor=profit_factor(pnls),
        max_drawdown=max_dd,
        max_drawdown_pct=max_dd / starting_equity if starting_equity else 0.0,
        sharpe=_annualized_ratio(daily_returns, downside_only=False),
        sortino=_annualized_ratio(daily_returns, downside_only=True),
        # Zero drawdown with positive return is the BEST outcome, not the
        # worst — report inf, consistent with profit_factor's convention.
        mar=(
            annual_return / (max_dd / starting_equity)
            if max_dd > 0
            else (float("inf") if annual_return > 0 else 0.0)
        ),
        longest_losing_streak=longest,
        best_day=best_day,
        best_day_share=best_day / net if net > 0 else 0.0,
        top5_trade_share=top5 / gross_profit if gross_profit > 0 else 0.0,
        trading_days=len(daily),
        daily_pnl_std=float(daily_pnls.std(ddof=1)) if daily_pnls.size > 1 else 0.0,
        per_trade_pnl_std=per_trade_std,
        starting_equity=starting_equity,
        bootstrap_p_positive=p_positive,
    )
