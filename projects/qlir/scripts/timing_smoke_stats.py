"""Gate II statistics on the QC timing-smoke event export (round-3 spec).

Consumes qlir_events_<year>.csv files downloaded from the QC research
notebook (projects/qlir/qc/qlir_timing_smoke.py) and reports, with
DAY-CLUSTERED bootstrap confidence intervals:

  1. per-class forward |return|, signed return, VOLUME change
     (log vol_fwd_60s/vol_pre_60s) and VOLATILITY change
     (log postvol_5m/prevol_5m) for A(:00/:30), B(:15/:45), placebo;
  2. quarter-minus-placebo paired daily contrast per horizon;
  3. A-minus-B paired daily contrast (the prespecified mechanism split);
  4. ES-minus-NQ paired daily contrast of the quarter effect;
  5. development (2021-2023) minus validation (2024) two-sample contrast.

Exclusions are SYMMETRIC across classes: every boundary (quarter AND
placebo) within ±10 minutes of a dated release in the frozen v2 calendar
is dropped, so the quarter-vs-placebo comparison is not biased by
removing only quarter-hour observations. Coincident source rows are
preserved in the calendar but collapse to one mask timestamp. One common
construction for every class — no class-specific tuning.

This is a MECHANISM SCREEN on trade-bar data with no aggressor side: no
strategy Sharpe is computed here, and a null does not falsify the
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
HORIZONS = (60, 120, 300)
EXCLUDE_MINUTES = 10  # ±minutes around each DATED calendar event
DEFAULT_CALENDAR = (
    Path(__file__).resolve().parent.parent
    / "calendars"
    / "macro_events_v2.csv"
)


def load_calendar(path: Path) -> tuple[pd.DataFrame, list[str]]:
    """Dated macro-event calendar (round 5: a blanket time-of-day
    exclusion removed 09:00/13:00 CT on EVERY session — including
    non-event days — and unequal quarter/placebo counts; exclusions must
    be date-and-time events with a recorded source/version)."""
    if not path.exists():
        raise SystemExit(
            f"BLOCKED: macro-event calendar not found at {path} — Gate II "
            "statistics may not run without a dated, versioned exclusion "
            "calendar."
        )
    header: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            header.append(line.lstrip("# "))
        else:
            break
    calendar = pd.read_csv(path, comment="#")
    required = {
        "date",
        "time_ct",
        "event",
        "source",
        "source_url",
        "source_asof_utc",
    }
    if required - set(calendar.columns):
        raise SystemExit(
            f"BLOCKED: calendar lacks columns {sorted(required - set(calendar.columns))}"
        )
    if "coverage: complete" not in " ".join(header).lower():
        raise SystemExit(
            "BLOCKED: calendar does not declare complete frozen-taxonomy "
            "coverage. Gate II statistics may not run with an incomplete calendar."
        )
    if calendar.empty:
        raise SystemExit("BLOCKED: macro-event calendar is empty")
    try:
        dates = pd.to_datetime(calendar["date"], format="%Y-%m-%d", errors="raise")
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"BLOCKED: invalid calendar date: {exc}") from exc
    if set(dates.dt.year) != {2021, 2022, 2023, 2024}:
        raise SystemExit(
            "BLOCKED: calendar must contain only and all frozen years 2021-2024"
        )
    if not calendar["time_ct"].astype(str).str.fullmatch(r"\d{2}:\d{2}").all():
        raise SystemExit("BLOCKED: calendar time_ct values must use HH:MM")
    event_minutes = (
        calendar["time_ct"].str[:2].astype(int) * 60
        + calendar["time_ct"].str[3:5].astype(int)
    )
    if not event_minutes.between(8 * 60 + 45, 14 * 60 + 45).all():
        raise SystemExit("BLOCKED: calendar contains an out-of-window CT time")
    if not calendar["source_url"].astype(str).str.startswith("https://").all():
        raise SystemExit("BLOCKED: calendar contains a non-HTTPS source URL")
    if calendar[list(required)].isna().any().any():
        raise SystemExit("BLOCKED: calendar contains missing provenance fields")
    if calendar.duplicated(list(required)).any():
        raise SystemExit("BLOCKED: calendar contains exact duplicate source rows")
    return calendar, header


def release_excluded(df: pd.DataFrame, calendar: pd.DataFrame) -> pd.Series:
    """±EXCLUDE_MINUTES around each DATED event, on that DATE only,
    applied identically to every boundary class."""
    mask = pd.Series(False, index=df.index)
    boundary_minutes = df["boundary_ct"].str.slice(0, 2).astype(int) * 60 + df[
        "boundary_ct"
    ].str.slice(3, 5).astype(int)
    timestamps = calendar[["date", "time_ct"]].drop_duplicates()
    for _, event in timestamps.iterrows():
        event_time = str(event["time_ct"])
        event_minutes = int(event_time[:2]) * 60 + int(event_time[3:5])
        on_date = df["date"] == str(event["date"])
        near = (boundary_minutes - event_minutes).abs() <= EXCLUDE_MINUTES
        mask |= on_date & near
    return mask


def boot_ci(days: np.ndarray, rng: np.random.Generator) -> tuple[float, float, float]:
    """Mean and bootstrap 95% CI over an array of per-DAY values."""
    days = days[np.isfinite(days)]
    if len(days) < 5:
        return float("nan"), float("nan"), float("nan")
    means = np.array([days[rng.integers(0, len(days), len(days))].mean() for _ in range(N_BOOT)])
    return float(days.mean()), float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def two_sample_ci(
    a: np.ndarray, b: np.ndarray, rng: np.random.Generator
) -> tuple[float, float, float]:
    """Mean(a) - mean(b) with independent-resample bootstrap CI."""
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 5 or len(b) < 5:
        return float("nan"), float("nan"), float("nan")
    diffs = np.array(
        [
            a[rng.integers(0, len(a), len(a))].mean() - b[rng.integers(0, len(b), len(b))].mean()
            for _ in range(N_BOOT)
        ]
    )
    return (
        float(a.mean() - b.mean()),
        float(np.quantile(diffs, 0.025)),
        float(np.quantile(diffs, 0.975)),
    )


def daily_mean(df: pd.DataFrame, col: str) -> pd.Series:
    return df.groupby("date")[col].mean()


def fmt(mean: float, lo: float, hi: float) -> str:
    if not np.isfinite(mean):
        return "n/a (too few days)"
    return f"{mean:+9.3f}  [{lo:+8.3f}, {hi:+8.3f}]"


def with_derived(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for s in HORIZONS:
        out[f"absr_{s}"] = out[f"ret_fwd_{s}s"].abs() * 1e4  # bp
    with np.errstate(divide="ignore", invalid="ignore"):
        out["volume_change"] = np.log(out["vol_fwd_60s"].where(out["vol_fwd_60s"] > 0))
        out["volume_change"] -= np.log(out["vol_pre_60s"].where(out["vol_pre_60s"] > 0))
        out["vol_change"] = np.log(out["postvol_5m"].where(out["postvol_5m"] > 0)) - np.log(
            out["prevol_5m"].where(out["prevol_5m"] > 0)
        )
    return out


def class_table(df: pd.DataFrame, label: str, rng: np.random.Generator) -> None:
    print(f"\n### {label}  (events={len(df)}, days={df['date'].nunique()})")
    header = (
        f"{'class':<9} {'metric':<16} {'mean':>10} {'95% CI (day-clustered)':>24} {'events':>7}"
    )
    print(header)
    print("-" * len(header))
    for cls in ("A_00_30", "B_15_45", "placebo"):
        sub = df[df["boundary_class"] == cls]
        if sub.empty:
            continue
        rows: list[tuple[str, str]] = []
        for s in HORIZONS:
            mean, lo, hi = boot_ci(daily_mean(sub, f"absr_{s}").to_numpy(), rng)
            rows.append((f"|r| {s}s bp", fmt(mean, lo, hi)))
        for s in HORIZONS:
            # Signed returns get the SAME day-clustered interval as |r| —
            # bare event means were a round-4 defect.
            signed_daily = daily_mean(sub.assign(_s=sub[f"ret_fwd_{s}s"] * 1e4), "_s").to_numpy()
            mean, lo, hi = boot_ci(signed_daily, rng)
            rows.append((f"signed r {s}s bp", fmt(mean, lo, hi)))
        for metric, col in (("volume chg log", "volume_change"), ("vol chg log", "vol_change")):
            mean, lo, hi = boot_ci(daily_mean(sub.dropna(subset=[col]), col).to_numpy(), rng)
            rows.append((metric, fmt(mean, lo, hi)))
        for metric, value in rows:
            print(f"{cls:<9} {metric:<16} {value:>36} {len(sub):>7}")


def paired_daily_contrast(
    df: pd.DataFrame,
    col: str,
    split_col: str,
    positive: object,
    negative: object,
    rng: np.random.Generator,
) -> tuple[float, float, float, int]:
    per_day = df.pivot_table(index="date", columns=split_col, values=col, aggfunc="mean")
    if positive not in per_day or negative not in per_day:
        return float("nan"), float("nan"), float("nan"), 0
    diff = (per_day[positive] - per_day[negative]).dropna().to_numpy()
    mean, lo, hi = boot_ci(diff, rng)
    return mean, lo, hi, len(diff)


def quarter_effect_by_day(df: pd.DataFrame, col: str) -> pd.Series:
    """Per-day quarter-minus-placebo difference of daily means."""
    per_day = df.pivot_table(index="date", columns="is_quarter", values=col, aggfunc="mean")
    if True not in per_day or False not in per_day:
        return pd.Series(dtype=float)
    return (per_day[True] - per_day[False]).dropna()


def contrasts(df: pd.DataFrame, label: str, rng: np.random.Generator) -> None:
    print(f"\n### Contrasts — {label} (all day-clustered)")
    for s in HORIZONS:
        mean, lo, hi, n = paired_daily_contrast(df, f"absr_{s}", "is_quarter", True, False, rng)
        print(f"quarter - placebo   |r| {s}s bp: {fmt(mean, lo, hi)}  ({n} days)")
    for col, name in (("volume_change", "volume chg"), ("vol_change", "vol chg")):
        mean, lo, hi, n = paired_daily_contrast(
            df.dropna(subset=[col]), col, "is_quarter", True, False, rng
        )
        print(f"quarter - placebo   {name:<11}: {fmt(mean, lo, hi)}  ({n} days)")
    quarters = df[df["is_quarter"]]
    for s in HORIZONS:
        mean, lo, hi, n = paired_daily_contrast(
            quarters, f"absr_{s}", "boundary_class", "A_00_30", "B_15_45", rng
        )
        print(f"A(:00/:30) - B(:15/:45) |r| {s}s bp: {fmt(mean, lo, hi)}  ({n} days)")


def cross_instrument_contrast(df: pd.DataFrame, rng: np.random.Generator) -> None:
    instruments = sorted(df["instrument"].unique())
    if len(instruments) != 2:
        return
    first, second = instruments
    print(f"\n### {first} - {second} contrast of the quarter effect (paired by day)")
    for s in HORIZONS:
        effect_first = quarter_effect_by_day(df[df["instrument"] == first], f"absr_{s}")
        effect_second = quarter_effect_by_day(df[df["instrument"] == second], f"absr_{s}")
        joined = pd.concat([effect_first, effect_second], axis=1, join="inner").dropna()
        if joined.empty:
            print(f"|r| {s}s bp: n/a (no common days)")
            continue
        diff = (joined.iloc[:, 0] - joined.iloc[:, 1]).to_numpy()
        mean, lo, hi = boot_ci(diff, rng)
        print(f"|r| {s}s bp: {fmt(mean, lo, hi)}  ({len(diff)} common days)")


def dev_vs_val_contrast(df: pd.DataFrame, rng: np.random.Generator) -> None:
    print("\n### development (2021-2023) - validation (2024) quarter effect")
    for instrument in sorted(df["instrument"].unique()):
        sub = df[df["instrument"] == instrument]
        dev = sub[sub["year"] <= 2023]
        val = sub[sub["year"] == 2024]
        for s in HORIZONS:
            effect_dev = quarter_effect_by_day(dev, f"absr_{s}").to_numpy()
            effect_val = quarter_effect_by_day(val, f"absr_{s}").to_numpy()
            mean, lo, hi = two_sample_ci(effect_dev, effect_val, rng)
            print(
                f"{instrument} |r| {s}s bp (dev - val): {fmt(mean, lo, hi)}  "
                f"({len(effect_dev)} vs {len(effect_val)} days)"
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
    required = {"postvol_5m", "prevol_5m", "vol_pre_60s", "vol_fwd_60s"}
    missing = required - set(df.columns)
    if missing:
        print(
            f"BLOCKED: event files lack columns {sorted(missing)} — they were "
            "extracted with the pre-round-3 notebook; re-run the corrected "
            "extractor before any interpretation."
        )
        return 2
    if (df["resolution_used"] == "minute").any():
        share = (df["resolution_used"] == "minute").mean()
        print(
            f"WARNING: {share:.0%} of events extracted at MINUTE fallback resolution — "
            "sub-minute offsets are coarse there; interpret accordingly."
        )
    calendar, cal_header = load_calendar(DEFAULT_CALENDAR)
    unique_timestamps = len(calendar[["date", "time_ct"]].drop_duplicates())
    print(
        f"macro-event calendar: {DEFAULT_CALENDAR.name} — "
        f"{len(calendar)} source row(s), {unique_timestamps} unique timestamp(s)"
    )
    for line in cal_header:
        print(f"  calendar: {line}")
    excluded = release_excluded(df, calendar)
    print(
        f"dated release-window exclusion (±{EXCLUDE_MINUTES} min, event dates only, "
        f"all classes): dropped {int(excluded.sum())} events "
        f"({int((excluded & df['is_quarter']).sum())} quarter, "
        f"{int((excluded & ~df['is_quarter']).sum())} placebo)"
    )
    df = with_derived(df[~excluded].copy())
    df["year"] = pd.to_datetime(df["date"]).dt.year

    rng = np.random.default_rng(SEED)
    for instrument in sorted(df["instrument"].unique()):
        sub = df[df["instrument"] == instrument]
        dev = sub[sub["year"] <= 2023]
        val = sub[sub["year"] == 2024]
        class_table(dev, f"{instrument} — development 2021-2023", rng)
        contrasts(dev, f"{instrument} development", rng)
        class_table(val, f"{instrument} — validation 2024", rng)
        contrasts(val, f"{instrument} validation", rng)
    cross_instrument_contrast(df, rng)
    dev_vs_val_contrast(df, rng)
    print(
        "\nReminder: mechanism screen only — trade bars, no aggressor side, "
        "no execution model. No strategy conclusions from this table."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["qlir_events_*.csv"]))
