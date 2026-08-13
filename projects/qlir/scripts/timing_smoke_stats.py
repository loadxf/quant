"""Gate II statistics on the QC timing-smoke event export.

Consumes the qlir_events_<year>.csv files downloaded from the QC
research notebook (projects/qlir/qc/qlir_timing_smoke.py) and reports,
with DAY-CLUSTERED bootstrap confidence intervals:

  - quarter-hour vs five-minute-placebo forward |return| and volume;
  - the prespecified A(:00/:30) vs B(:15/:45) decomposition;
  - ES vs NQ separately; 60/120/300 s horizons;
  - development (2021-2023) vs validation (2024).

One common construction for every class — no class-specific tuning.
This is a MECHANISM SCREEN on trade-bar data with no aggressor side:
no strategy Sharpe is computed here, and a null does not falsify the
flow-conditioned Q-LIR hypothesis.

Usage:
    python projects/qlir/scripts/timing_smoke_stats.py qlir_events_*.csv
"""

from __future__ import annotations

import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

N_BOOT = 2000
SEED = 20260813
# Scheduled-release minutes excluded from the PRIMARY comparison (CT):
# 09:00 (US data cluster), 13:00 (FOMC statement days land here) — the
# exclusion list is deliberately coarse at smoke-test level and applies
# IDENTICALLY to quarter and placebo classes.
EXCLUDE_CT = {"09:00", "13:00"}


def day_clustered_ci(
    df: pd.DataFrame, col: str, rng: np.random.Generator
) -> tuple[float, float, float]:
    """Mean and 95% CI by resampling DAYS (clusters), not events."""
    grouped = df.groupby("date")[col].mean()
    days = grouped.to_numpy()
    if len(days) < 5:
        return float("nan"), float("nan"), float("nan")
    means = np.array([days[rng.integers(0, len(days), len(days))].mean() for _ in range(N_BOOT)])
    return float(days.mean()), float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def class_table(df: pd.DataFrame, label: str) -> None:
    rng = np.random.default_rng(SEED)
    print(f"\n### {label}  (events={len(df)}, days={df['date'].nunique()})")
    print(
        f"{'class':<10} {'horizon':<8} {'mean |r| bp':>12} {'95% CI':>22} "
        f"{'mean r bp':>10} {'events':>8}"
    )
    for cls in ("A_00_30", "B_15_45", "placebo"):
        sub = df[df["boundary_class"] == cls]
        if sub.empty:
            continue
        for s in (60, 120, 300):
            col = f"ret_fwd_{s}s"
            if col not in sub:
                continue
            absr = sub.assign(_a=sub[col].abs() * 1e4)
            mean_abs, lo, hi = day_clustered_ci(absr, "_a", rng)
            signed = float(sub[col].mean() * 1e4)
            print(
                f"{cls:<10} {s:<8} {mean_abs:>12.3f} "
                f"[{lo:>9.3f},{hi:>9.3f}] {signed:>10.3f} {len(sub):>8}"
            )
    # Quarter (A+B pooled) minus placebo, day-clustered on the difference.
    for s in (60, 120, 300):
        col = f"ret_fwd_{s}s"
        if col not in df:
            continue
        per_day = df.assign(_a=df[col].abs() * 1e4).pivot_table(
            index="date", columns="is_quarter", values="_a", aggfunc="mean"
        )
        if True not in per_day or False not in per_day:
            continue
        diff = (per_day[True] - per_day[False]).dropna().to_numpy()
        if len(diff) < 5:
            continue
        rng2 = np.random.default_rng(SEED + s)
        boots = np.array(
            [diff[rng2.integers(0, len(diff), len(diff))].mean() for _ in range(N_BOOT)]
        )
        print(
            f"quarter-minus-placebo |r| @{s}s: {diff.mean():+.3f} bp "
            f"[{np.quantile(boots, 0.025):+.3f}, {np.quantile(boots, 0.975):+.3f}] "
            f"({len(diff)} days)"
        )


def main(paths: list[str]) -> int:
    files = sorted({p for pat in paths for p in glob.glob(pat)})
    if not files:
        print(
            "No event files found. Run the QC research notebook "
            "(projects/qlir/qc/qlir_timing_smoke.py), download "
            "qlir_events_<year>.csv, and pass their paths."
        )
        return 2
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    print(f"loaded {len(df)} events from {len(files)} file(s): {[Path(f).name for f in files]}")
    if (df["resolution_used"] == "minute").any():
        share = (df["resolution_used"] == "minute").mean()
        print(
            f"WARNING: {share:.0%} of events extracted at MINUTE fallback resolution — "
            "sub-minute offsets are coarse there; interpret accordingly."
        )
    df = df[~df["boundary_ct"].isin(EXCLUDE_CT)]
    df["year"] = pd.to_datetime(df["date"]).dt.year

    for instrument in sorted(df["instrument"].unique()):
        sub = df[df["instrument"] == instrument]
        dev = sub[sub["year"] <= 2023]
        val = sub[sub["year"] == 2024]
        class_table(dev, f"{instrument} — development 2021-2023")
        class_table(val, f"{instrument} — validation 2024")
    print(
        "\nReminder: mechanism screen only — trade bars, no aggressor side, "
        "no execution model. No strategy conclusions from this table."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["qlir_events_*.csv"]))
