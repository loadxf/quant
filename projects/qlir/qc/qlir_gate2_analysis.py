# Q-LIR Gate II frozen analysis - paste as ONE QC Research notebook cell.
#
# Requires `locked_events_excluded` from the passed macro-exclusion audit.
# This is a mechanism screen on trade bars, not a strategy backtest.

from contextlib import redirect_stdout
from io import StringIO

import numpy as np
import pandas as pd

N_BOOT = 2_000
SEED = 20_260_813
HORIZONS = (60, 120, 300)
EXPECTED_ROWS = 135_252
EXPECTED_RETAINED = {
    (2021, "ES", "A_00_30"): 2_754,
    (2021, "ES", "B_15_45"): 3_227,
    (2021, "ES", "placebo"): 11_006,
    (2021, "NQ", "A_00_30"): 2_754,
    (2021, "NQ", "B_15_45"): 3_227,
    (2021, "NQ", "placebo"): 11_006,
    (2022, "ES", "A_00_30"): 2_751,
    (2022, "ES", "B_15_45"): 3_214,
    (2022, "ES", "placebo"): 10_986,
    (2022, "NQ", "A_00_30"): 2_751,
    (2022, "NQ", "B_15_45"): 3_214,
    (2022, "NQ", "placebo"): 10_986,
    (2023, "ES", "A_00_30"): 2_724,
    (2023, "ES", "B_15_45"): 3_190,
    (2023, "ES", "placebo"): 10_880,
    (2023, "NQ", "A_00_30"): 2_724,
    (2023, "NQ", "B_15_45"): 3_190,
    (2023, "NQ", "placebo"): 10_880,
    (2024, "ES", "A_00_30"): 2_740,
    (2024, "ES", "B_15_45"): 3_202,
    (2024, "ES", "placebo"): 10_952,
    (2024, "NQ", "A_00_30"): 2_740,
    (2024, "NQ", "B_15_45"): 3_202,
    (2024, "NQ", "placebo"): 10_952,
}
REQUIRED = {
    "date",
    "instrument",
    "boundary_ct",
    "boundary_class",
    "is_quarter",
    "resolution_used",
    "ret_fwd_60s",
    "ret_fwd_120s",
    "ret_fwd_300s",
    "vol_pre_60s",
    "vol_fwd_60s",
    "prevol_5m",
    "postvol_5m",
}


def boot_ci(
    days: np.ndarray, rng: np.random.Generator
) -> tuple[float, float, float]:
    """Mean and bootstrap 95% CI over per-day values."""
    days = days[np.isfinite(days)]
    if len(days) < 5:
        return float("nan"), float("nan"), float("nan")
    means = np.array(
        [days[rng.integers(0, len(days), len(days))].mean() for _ in range(N_BOOT)]
    )
    return (
        float(days.mean()),
        float(np.quantile(means, 0.025)),
        float(np.quantile(means, 0.975)),
    )


def two_sample_ci(
    a: np.ndarray, b: np.ndarray, rng: np.random.Generator
) -> tuple[float, float, float]:
    """Mean(a)-mean(b) with independent day-resample bootstrap CI."""
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 5 or len(b) < 5:
        return float("nan"), float("nan"), float("nan")
    diffs = np.array(
        [
            a[rng.integers(0, len(a), len(a))].mean()
            - b[rng.integers(0, len(b), len(b))].mean()
            for _ in range(N_BOOT)
        ]
    )
    return (
        float(a.mean() - b.mean()),
        float(np.quantile(diffs, 0.025)),
        float(np.quantile(diffs, 0.975)),
    )


def daily_mean(frame: pd.DataFrame, column: str) -> pd.Series:
    return frame.groupby("date")[column].mean()


def fmt(mean: float, low: float, high: float) -> str:
    if not np.isfinite(mean):
        return "n/a (too few days)"
    return f"{mean:+9.3f}  [{low:+8.3f}, {high:+8.3f}]"


def with_derived(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for seconds in HORIZONS:
        out[f"absr_{seconds}"] = out[f"ret_fwd_{seconds}s"].abs() * 1e4
    with np.errstate(divide="ignore", invalid="ignore"):
        out["volume_change"] = np.log(
            out["vol_fwd_60s"].where(out["vol_fwd_60s"] > 0)
        ) - np.log(out["vol_pre_60s"].where(out["vol_pre_60s"] > 0))
        out["vol_change"] = np.log(
            out["postvol_5m"].where(out["postvol_5m"] > 0)
        ) - np.log(out["prevol_5m"].where(out["prevol_5m"] > 0))
    return out


def class_table(
    frame: pd.DataFrame, label: str, rng: np.random.Generator
) -> None:
    print(f"\n### {label} (events={len(frame)}, days={frame['date'].nunique()})")
    header = (
        f"{'class':<9} {'metric':<16} {'mean':>10} "
        f"{'95% CI (day-clustered)':>24} {'events':>7}"
    )
    print(header)
    print("-" * len(header))
    for boundary_class in ("A_00_30", "B_15_45", "placebo"):
        sub = frame[frame["boundary_class"] == boundary_class]
        for seconds in HORIZONS:
            mean, low, high = boot_ci(
                daily_mean(sub, f"absr_{seconds}").to_numpy(), rng
            )
            print(
                f"{boundary_class:<9} {f'|r| {seconds}s bp':<16} "
                f"{fmt(mean, low, high):>36} {len(sub):>7}"
            )
        for seconds in HORIZONS:
            signed = sub.assign(_signed=sub[f"ret_fwd_{seconds}s"] * 1e4)
            mean, low, high = boot_ci(daily_mean(signed, "_signed").to_numpy(), rng)
            print(
                f"{boundary_class:<9} {f'signed r {seconds}s bp':<16} "
                f"{fmt(mean, low, high):>36} {len(sub):>7}"
            )
        for metric, column in (
            ("volume chg log", "volume_change"),
            ("vol chg log", "vol_change"),
        ):
            usable = sub.dropna(subset=[column])
            mean, low, high = boot_ci(daily_mean(usable, column).to_numpy(), rng)
            print(
                f"{boundary_class:<9} {metric:<16} "
                f"{fmt(mean, low, high):>36} {len(sub):>7}"
            )


def paired_daily_contrast(
    frame: pd.DataFrame,
    column: str,
    split_column: str,
    positive: object,
    negative: object,
    rng: np.random.Generator,
) -> tuple[float, float, float, int]:
    per_day = frame.pivot_table(
        index="date", columns=split_column, values=column, aggfunc="mean"
    )
    if positive not in per_day or negative not in per_day:
        return float("nan"), float("nan"), float("nan"), 0
    difference = (per_day[positive] - per_day[negative]).dropna().to_numpy()
    mean, low, high = boot_ci(difference, rng)
    return mean, low, high, len(difference)


def quarter_effect_by_day(frame: pd.DataFrame, column: str) -> pd.Series:
    per_day = frame.pivot_table(
        index="date", columns="is_quarter", values=column, aggfunc="mean"
    )
    if True not in per_day or False not in per_day:
        return pd.Series(dtype=float)
    return (per_day[True] - per_day[False]).dropna()


def contrasts(frame: pd.DataFrame, label: str, rng: np.random.Generator) -> None:
    print(f"\n### Contrasts - {label} (all day-clustered)")
    for seconds in HORIZONS:
        mean, low, high, count = paired_daily_contrast(
            frame, f"absr_{seconds}", "is_quarter", True, False, rng
        )
        print(
            f"quarter - placebo |r| {seconds}s bp: "
            f"{fmt(mean, low, high)} ({count} days)"
        )
    for column, name in (
        ("volume_change", "volume chg"),
        ("vol_change", "vol chg"),
    ):
        mean, low, high, count = paired_daily_contrast(
            frame.dropna(subset=[column]), column, "is_quarter", True, False, rng
        )
        print(
            f"quarter - placebo {name:<10}: "
            f"{fmt(mean, low, high)} ({count} days)"
        )
    quarters = frame[frame["is_quarter"]]
    for seconds in HORIZONS:
        mean, low, high, count = paired_daily_contrast(
            quarters,
            f"absr_{seconds}",
            "boundary_class",
            "A_00_30",
            "B_15_45",
            rng,
        )
        print(
            f"A(:00/:30) - B(:15/:45) |r| {seconds}s bp: "
            f"{fmt(mean, low, high)} ({count} days)"
        )


def cross_instrument_contrast(
    frame: pd.DataFrame, rng: np.random.Generator
) -> None:
    print("\n### ES - NQ contrast of the quarter effect (paired by day)")
    for seconds in HORIZONS:
        es = quarter_effect_by_day(
            frame[frame["instrument"] == "ES"], f"absr_{seconds}"
        )
        nq = quarter_effect_by_day(
            frame[frame["instrument"] == "NQ"], f"absr_{seconds}"
        )
        joined = pd.concat([es, nq], axis=1, join="inner").dropna()
        difference = (joined.iloc[:, 0] - joined.iloc[:, 1]).to_numpy()
        mean, low, high = boot_ci(difference, rng)
        print(
            f"|r| {seconds}s bp: {fmt(mean, low, high)} "
            f"({len(difference)} common days)"
        )


def development_validation_contrast(
    frame: pd.DataFrame, rng: np.random.Generator
) -> None:
    print("\n### development (2021-2023) - validation (2024) quarter effect")
    for instrument in ("ES", "NQ"):
        sub = frame[frame["instrument"] == instrument]
        development = sub[sub["year"] <= 2023]
        validation = sub[sub["year"] == 2024]
        for seconds in HORIZONS:
            dev_effect = quarter_effect_by_day(
                development, f"absr_{seconds}"
            ).to_numpy()
            val_effect = quarter_effect_by_day(
                validation, f"absr_{seconds}"
            ).to_numpy()
            mean, low, high = two_sample_ci(dev_effect, val_effect, rng)
            print(
                f"{instrument} |r| {seconds}s bp (dev - val): "
                f"{fmt(mean, low, high)} "
                f"({len(dev_effect)} vs {len(val_effect)} days)"
            )


if "locked_events_excluded" not in globals():
    raise RuntimeError("Run the passed macro-exclusion audit first.")

analysis_frame = globals()["locked_events_excluded"].copy()
missing = REQUIRED - set(analysis_frame.columns)
if missing:
    raise RuntimeError(f"Filtered frame lacks columns: {sorted(missing)}")
if len(analysis_frame) != EXPECTED_ROWS:
    raise RuntimeError(
        f"Expected {EXPECTED_ROWS:,} retained rows, found {len(analysis_frame):,}"
    )

analysis_frame["date"] = analysis_frame["date"].astype(str)
analysis_frame["year"] = pd.to_datetime(
    analysis_frame["date"], format="%Y-%m-%d", errors="raise"
).dt.year
fingerprint = analysis_frame.groupby(
    ["year", "instrument", "boundary_class"]
).size().to_dict()
if fingerprint != EXPECTED_RETAINED:
    raise RuntimeError("Retained-count fingerprint changed; analysis refused")
if set(analysis_frame["resolution_used"]) - {"minute", "second"}:
    raise RuntimeError("Unexpected resolution label")
if not analysis_frame.loc[
    analysis_frame["boundary_class"].isin(["A_00_30", "B_15_45"]),
    "is_quarter",
].eq(True).all():
    raise RuntimeError("Quarter-class identity mismatch")
if not analysis_frame.loc[
    analysis_frame["boundary_class"] == "placebo", "is_quarter"
].eq(False).all():
    raise RuntimeError("Placebo identity mismatch")

analysis_frame = with_derived(analysis_frame)
rng = np.random.default_rng(SEED)
report_buffer = StringIO()
with redirect_stdout(report_buffer):
    print("--- Q-LIR GATE II FROZEN ANALYSIS ---")
    print("rows:", len(analysis_frame))
    print("sessions:", analysis_frame["date"].nunique())
    print("bootstrap replications:", N_BOOT)
    print("seed:", SEED)
    minute_share = analysis_frame["resolution_used"].eq("minute").mean()
    print(f"minute-resolution share: {minute_share:.1%}")
    if minute_share:
        print(
            "WARNING: minute bars make the 60s/120s offsets coarse; "
            "this is a mechanism screen only."
        )
    for instrument in ("ES", "NQ"):
        instrument_frame = analysis_frame[
            analysis_frame["instrument"] == instrument
        ]
        development = instrument_frame[instrument_frame["year"] <= 2023]
        validation = instrument_frame[instrument_frame["year"] == 2024]
        class_table(development, f"{instrument} - development 2021-2023", rng)
        contrasts(development, f"{instrument} development", rng)
        class_table(validation, f"{instrument} - validation 2024", rng)
        contrasts(validation, f"{instrument} validation", rng)
    cross_instrument_contrast(analysis_frame, rng)
    development_validation_contrast(analysis_frame, rng)
    print(
        "\nReminder: mechanism screen only - trade bars, no aggressor side, "
        "no execution model, and no strategy conclusion."
    )

gate2_report = report_buffer.getvalue()
print(gate2_report)
print("The complete report is also stored in the variable `gate2_report`.")
