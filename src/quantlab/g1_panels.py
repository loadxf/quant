"""G1 mechanism, step 1: descriptive-statistics panels on the post-cutoff slice.

These tables are the raw material for LLM hypothesis generation: the model
reads the numbers (patterns it has provably never seen — the window postdates
its training cutoff) and articulates mechanisms, which are then formalized as
signals and validated on 2005-2023 data. With ~115 trading days the panels are
hypothesis GENERATORS, not evidence; power comes later from 19 years of
train/validation history.

Every panel uses next-day forward returns aligned as: condition measured at
close t, response = return over day t+1. (The eventual backtest applies the
stricter t+2 execution; the extra day of slippage is part of validation.)
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import REPO_ROOT
from .data import load_g1_window
from .grammar import build_terminals

SECTOR_ETFS = {
    "XLB": "Materials", "XLC": "Communication Services", "XLE": "Energy",
    "XLF": "Financials", "XLI": "Industrials", "XLK": "Information Technology",
    "XLP": "Consumer Staples", "XLRE": "Real Estate", "XLU": "Utilities",
    "XLV": "Health Care", "XLY": "Consumer Discretionary",
}


def _quintile_double_sort(
    cond_a: pd.DataFrame, cond_b: pd.DataFrame, fwd: pd.DataFrame, q: int = 5
) -> pd.DataFrame:
    """Mean forward return in bps for each (quintile of a, quintile of b) cell."""
    ra = cond_a.rank(axis=1, pct=True)
    rb = cond_b.rank(axis=1, pct=True)
    out = np.full((q, q), np.nan)
    counts = np.zeros((q, q))
    bins_a = np.ceil(ra * q).clip(1, q)
    bins_b = np.ceil(rb * q).clip(1, q)
    for i in range(1, q + 1):
        for j in range(1, q + 1):
            mask = (bins_a == i) & (bins_b == j)
            vals = fwd[mask]
            stacked = vals.stack().dropna()
            if len(stacked) > 30:
                out[i - 1, j - 1] = stacked.mean() * 1e4
                counts[i - 1, j - 1] = len(stacked)
    return pd.DataFrame(
        out,
        index=[f"a_q{i}" for i in range(1, q + 1)],
        columns=[f"b_q{j}" for j in range(1, q + 1)],
    )


def _single_sort(cond: pd.DataFrame, fwd: pd.DataFrame, q: int = 5) -> pd.Series:
    ranks = cond.rank(axis=1, pct=True)
    bins = np.ceil(ranks * q).clip(1, q)
    means = {}
    for i in range(1, q + 1):
        stacked = fwd[bins == i].stack().dropna()
        means[f"q{i}"] = stacked.mean() * 1e4 if len(stacked) > 30 else np.nan
    return pd.Series(means)


def compute_panels() -> dict:
    fields = {f: load_g1_window(field=f) for f in ["open", "high", "low", "close", "adjclose", "volume"]}
    universe = json.loads((REPO_ROOT / "data" / "universe.json").read_text())
    eq_cols = [t for t in universe["equities"] if t in fields["adjclose"].columns]
    eq = {k: v[eq_cols] for k, v in fields.items()}
    terms = build_terminals(eq["open"], eq["high"], eq["low"], eq["close"], eq["adjclose"], eq["volume"])
    ret1 = terms["ret1"]
    fwd1 = ret1.shift(-1)  # response: next-day return

    panels: dict = {"window": [str(ret1.index.min().date()), str(ret1.index.max().date())],
                    "n_days": int(len(ret1)), "n_names": int(ret1.shape[1])}

    # 1. Cross-sectional lag-response profile (Spearman, mean across days)
    lag_profile = {}
    for lag in range(1, 11):
        daily = ret1.shift(lag).corrwith(fwd1, axis=1, method="spearman")
        lag_profile[f"lag_{lag}"] = {
            "mean_ic": round(float(daily.mean()), 5),
            "t_stat": round(float(daily.mean() / daily.std() * np.sqrt(daily.notna().sum())), 2),
        }
    panels["cs_lag_response"] = lag_profile

    # 2. Overnight gap x intraday move -> next-day return (bps)
    panels["gap_x_intraday"] = _quintile_double_sort(terms["gap"], terms["intraday"], fwd1).round(1).to_dict()

    # 3. Volume z x prior return -> next-day return
    panels["volz_x_ret1"] = _quintile_double_sort(terms["volz"], ret1, fwd1).round(1).to_dict()

    # 4-6. Single sorts
    panels["clv_quintiles"] = _single_sort(terms["clv"], fwd1).round(1).to_dict()
    panels["range_quintiles"] = _single_sort(terms["rng"], fwd1).round(1).to_dict()
    panels["gap_quintiles"] = _single_sort(terms["gap"], fwd1).round(1).to_dict()
    panels["volz_quintiles"] = _single_sort(terms["volz"], fwd1).round(1).to_dict()

    # 7. Day-of-week mean cross-sectional return (bps) and reversal strength
    dow = {}
    rev_by_dow = {}
    for d, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
        mask = ret1.index.dayofweek == d
        dow[name] = round(float(ret1[mask].stack().mean() * 1e4), 1)
        daily_ic = ret1.shift(1).corrwith(fwd1, axis=1, method="spearman")
        rev_by_dow[name] = round(float(daily_ic[mask].mean()), 5)
    panels["day_of_week_ret_bps"] = dow
    panels["lag1_ic_by_dow"] = rev_by_dow

    # 8. Sector ETF lead-lag: ETF ret(t) -> own-sector stock mean ret(t+1)
    etf_ret = fields["adjclose"].reindex(columns=list(SECTOR_ETFS)).pct_change(fill_method=None)
    sector_map = universe["sectors"]
    lead_lag = {}
    for etf, sector in SECTOR_ETFS.items():
        members = [t for t in eq_cols if sector_map.get(t) == sector]
        if not members or etf not in etf_ret.columns:
            continue
        sector_fwd = ret1[members].mean(axis=1).shift(-1)
        own = etf_ret[etf]
        corr = own.corr(sector_fwd)
        lead_lag[etf] = {"n_members": len(members), "etf_to_members_next_day_corr": round(float(corr), 4)}
    panels["sector_etf_lead_lag"] = lead_lag

    # 9. Cross-sectional dispersion dynamics
    disp = ret1.std(axis=1)
    panels["dispersion"] = {
        "mean_daily_cs_std_bps": round(float(disp.mean() * 1e4), 1),
        "autocorr_lag1": round(float(disp.autocorr(1)), 4),
        "autocorr_lag5": round(float(disp.autocorr(5)), 4),
    }
    daily_ic = ret1.shift(1).corrwith(fwd1, axis=1, method="spearman")
    hi = disp > disp.median()
    panels["lag1_ic_by_dispersion"] = {
        "high_dispersion_days": round(float(daily_ic[hi].mean()), 5),
        "low_dispersion_days": round(float(daily_ic[~hi].mean()), 5),
    }

    # 10. Macro ETF -> equity next-day response (correlation of ETF ret t with
    # equal-weight equity ret t+1)
    macro = ["TLT", "GLD", "UUP", "HYG", "USO", "FXY"]
    ew = ret1.mean(axis=1)
    macro_lead = {}
    for etf in macro:
        if etf in fields["adjclose"].columns:
            r = fields["adjclose"][etf].pct_change(fill_method=None)
            macro_lead[etf] = round(float(r.corr(ew.shift(-1))), 4)
    panels["macro_etf_leads_equity"] = macro_lead

    return panels


def main() -> None:
    panels = compute_panels()
    out = REPO_ROOT / "report" / "g1_panels.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(panels, indent=1))
    print(json.dumps(panels, indent=1))


if __name__ == "__main__":
    main()
