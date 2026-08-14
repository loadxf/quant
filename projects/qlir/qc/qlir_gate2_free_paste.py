# Q-LIR Gate II free-tier template.
# Paste this ENTIRE file into ONE fresh QuantConnect Research code cell and run it.
# Do not paste build_qc_free_template.py into QuantConnect.
# Frozen sample: 2021-2024 only. No Object Store or file download is required.

# Q-LIR Gate II free-tier QuantConnect Research template core.
# Run cells top to bottom. Do not extend the sample beyond 2024.
# ruff: noqa: E402, F403, F405, F811 - sequential QC cells share one namespace.

import datetime as dt

import numpy as np
import pandas as pd
from AlgorithmImports import *

START_YEAR, END_YEAR = 2021, 2024
EXPECTED_FULL_SESSIONS = {2021: 251, 2022: 250, 2023: 248, 2024: 249}

qb = QuantBook()
qb.set_time_zone("America/Chicago")
qb.set_start_date(START_YEAR, 1, 1)
qb.set_end_date(END_YEAR + 1, 1, 1)

future_tickers = {
    "ES": Futures.Indices.SP_500_E_MINI,
    "NQ": Futures.Indices.NASDAQ_100_E_MINI,
}
continuous = {}
for name, ticker in future_tickers.items():
    subscription = qb.add_future(
        ticker,
        Resolution.MINUTE,
        extended_market_hours=True,
        data_mapping_mode=DataMappingMode.OPEN_INTEREST,
        data_normalization_mode=DataNormalizationMode.RAW,
        contract_depth_offset=0,
    )
    continuous[name] = subscription.symbol

spy = qb.add_equity("SPY", Resolution.DAILY, extended_market_hours=False).symbol
print("QuantBook timezone:", qb.time_zone)
print("continuous symbols:", continuous)


def flatten_history(history):
    if history.empty:
        return history
    bars = history.copy()
    if isinstance(bars.index, pd.MultiIndex):
        bars.index = bars.index.get_level_values(-1)
    bars.index = pd.DatetimeIndex(bars.index)
    bars = bars.sort_index()
    return bars[~bars.index.duplicated(keep="last")]


def request_month(symbol, start, end):
    history = qb.history(
        symbol,
        start=start,
        end=end,
        resolution=Resolution.MINUTE,
        fill_forward=False,
        extended_market_hours=True,
        data_mapping_mode=DataMappingMode.OPEN_INTEREST,
        data_normalization_mode=DataNormalizationMode.RAW,
        contract_depth_offset=0,
    )
    if history.empty:
        raise RuntimeError(f"Empty minute history from {start} through {end}")
    return flatten_history(history)


def half_open_slice(series, start, end):
    low = series.index.searchsorted(start, side="right")
    high = series.index.searchsorted(end, side="right")
    return series.iloc[low:high]


def last_at_or_before(series, when):
    position = series.index.searchsorted(when, side="right") - 1
    return float(series.iloc[position]) if position >= 0 else None


def window_sum(series, start, end):
    return float(half_open_slice(series, start, end).sum())


def logret_std(closes, start, end):
    window = half_open_slice(closes, start, end)
    base = last_at_or_before(closes, start)
    if base is None or len(window) < 1:
        return float("nan")
    prices = np.concatenate([[base], window.to_numpy(dtype="float64")])
    if len(prices) < 3 or (prices <= 0).any():
        return float("nan")
    return float(np.std(np.diff(np.log(prices)), ddof=1))


boundaries = [
    dt.time(hour, minute)
    for hour in range(8, 15)
    for minute in range(0, 60, 5)
    if (hour, minute) >= (8, 45) and (hour, minute) <= (14, 45)
]
assert len(boundaries) == 73


probe = request_month(continuous["ES"], dt.datetime(2024, 3, 5), dt.datetime(2024, 3, 6))
cash_open_window = probe.between_time("09:25", "09:35")
if cash_open_window.empty:
    raise RuntimeError("No ES bars around the expected 09:30 New York cash open")
spike = cash_open_window["volume"].idxmax()
if not (spike.hour == 9 and 25 <= spike.minute <= 35):
    raise RuntimeError(f"Unexpected timestamp alignment; volume spike was {spike}")
print("PASS: ES history index is New York exchange time; cash-open spike:", spike)


def extract_year(year):
    rows = []
    for month in range(1, 13):
        month_start = dt.datetime(year, month, 1)
        month_end = dt.datetime(year + (month == 12), month % 12 + 1, 1)
        for instrument, symbol in continuous.items():
            bars = request_month(symbol, month_start, month_end)
            closes = bars["close"].astype(float)
            volumes = bars["volume"].astype(float)
            for session in sorted({timestamp.date() for timestamp in closes.index}):
                for boundary_ct in boundaries:
                    # QC continuous-futures history is indexed in New York time.
                    boundary = pd.Timestamp(
                        dt.datetime.combine(session, boundary_ct) + dt.timedelta(hours=1)
                    )
                    price_at_boundary = last_at_or_before(closes, boundary)
                    price_pre = last_at_or_before(closes, boundary - pd.Timedelta(seconds=60))
                    if (
                        price_at_boundary is None
                        or price_pre is None
                        or price_at_boundary <= 0
                        or price_pre <= 0
                    ):
                        continue
                    prevol = logret_std(closes, boundary - pd.Timedelta(minutes=5), boundary)
                    postvol = logret_std(closes, boundary, boundary + pd.Timedelta(minutes=5))
                    if not (np.isfinite(prevol) and np.isfinite(postvol)):
                        continue
                    minute = boundary_ct.minute
                    row = {
                        "date": session.isoformat(),
                        "instrument": instrument,
                        "boundary_ct": boundary_ct.strftime("%H:%M"),
                        "minute": minute,
                        "is_quarter": minute % 15 == 0,
                        "boundary_class": (
                            "A_00_30"
                            if minute % 30 == 0
                            else ("B_15_45" if minute % 15 == 0 else "placebo")
                        ),
                        "resolution_used": "minute",
                        "price_b": price_at_boundary,
                        "ret_pre_60s": np.log(price_at_boundary / price_pre),
                        "prevol_5m": prevol,
                        "postvol_5m": postvol,
                        "vol_pre_60s": window_sum(
                            volumes,
                            boundary - pd.Timedelta(seconds=60),
                            boundary,
                        ),
                    }
                    complete = True
                    for seconds in (60, 120, 300):
                        future_price = last_at_or_before(
                            closes, boundary + pd.Timedelta(seconds=seconds)
                        )
                        if future_price is None or future_price <= 0:
                            complete = False
                            break
                        row[f"ret_fwd_{seconds}s"] = np.log(future_price / price_at_boundary)
                        row[f"vol_fwd_{seconds}s"] = window_sum(
                            volumes,
                            boundary,
                            boundary + pd.Timedelta(seconds=seconds),
                        )
                    if complete:
                        rows.append(row)
        print(f"{year}-{month:02d}: {len(rows):,} cumulative event rows")
    return pd.DataFrame(rows)


if "events_by_year" not in globals():
    events_by_year = {}

for extraction_year in range(START_YEAR, END_YEAR + 1):
    if extraction_year not in events_by_year:
        events_by_year[extraction_year] = extract_year(extraction_year)
    print(extraction_year, len(events_by_year[extraction_year]))


cleaned_by_year = {}
for audit_year in range(START_YEAR, END_YEAR + 1):
    spy_history = qb.history(
        spy,
        start=dt.datetime(audit_year, 1, 1),
        end=dt.datetime(audit_year + 1, 1, 1),
        resolution=Resolution.DAILY,
        fill_forward=False,
        extended_market_hours=False,
    )
    spy_bars = flatten_history(spy_history)
    cash_dates = {timestamp.date().isoformat() for timestamp in spy_bars.index}
    raw = events_by_year[audit_year].copy()
    raw["date"] = raw["date"].astype(str)
    counts = raw.groupby(["date", "instrument"]).size().unstack(fill_value=0).fillna(0)
    for instrument in ("ES", "NQ"):
        if instrument not in counts:
            counts[instrument] = 0
    full_dates = set(counts[(counts["ES"] == 73) & (counts["NQ"] == 73)].index) & cash_dates
    if len(full_dates) != EXPECTED_FULL_SESSIONS[audit_year]:
        raise RuntimeError(
            f"{audit_year}: expected {EXPECTED_FULL_SESSIONS[audit_year]} "
            f"full cash sessions, found {len(full_dates)}"
        )
    cleaned = raw[raw["date"].isin(full_dates)].copy()
    cleaned_by_year[audit_year] = cleaned
    print(
        f"{audit_year}: cash={len(cash_dates)}, full={len(full_dates)}, "
        f"retained rows={len(cleaned):,}"
    )


locked_events = pd.concat(
    [cleaned_by_year[year] for year in range(START_YEAR, END_YEAR + 1)],
    ignore_index=True,
)
locked_events["_audit_year"] = pd.to_datetime(
    locked_events["date"], format="%Y-%m-%d", errors="raise"
).dt.year
expected_counts = {
    (2021, "ES"): 18_323,
    (2021, "NQ"): 18_323,
    (2022, "ES"): 18_250,
    (2022, "NQ"): 18_250,
    (2023, "ES"): 18_104,
    (2023, "NQ"): 18_104,
    (2024, "ES"): 18_177,
    (2024, "NQ"): 18_177,
}
actual_counts = locked_events.groupby(["_audit_year", "instrument"]).size().to_dict()
if actual_counts != expected_counts:
    raise RuntimeError(f"Locked sample fingerprint mismatch: {actual_counts}")
if len(locked_events) != 145_708 or locked_events["date"].nunique() != 998:
    raise RuntimeError("Locked sample totals changed")
identity = ["date", "instrument", "boundary_ct", "boundary_class"]
if locked_events.duplicated(identity).any():
    raise RuntimeError("Locked sample contains duplicate event identities")
numeric = locked_events.select_dtypes(include=[np.number])
if not np.isfinite(numeric.to_numpy(dtype="float64")).all():
    raise RuntimeError("Locked sample contains non-finite numeric values")
if (locked_events.filter(regex=r"^vol_").select_dtypes(include=[np.number]) < 0).any().any():
    raise RuntimeError("Locked sample contains negative volume")
locked_events = locked_events.drop(columns="_audit_year")
print("--- PRE-ANALYSIS INTEGRITY AUDIT ---")
print("rows:", len(locked_events))
print("sessions:", locked_events["date"].nunique())
print("instrument-sessions:", locked_events.groupby(["date", "instrument"]).ngroups)
print("PASS: market-data frame is ready for frozen exclusions")


"""Generated Q-LIR macro calendar for free-tier QC Research.

Do not edit this file by hand. Rebuild it with scripts/embed_macro_calendar.py.
"""

from base64 import b64decode
from zlib import decompress

MACRO_CALENDAR_SHA256 = "db16c107e06903e4731323a3ed71256d1314fa96275a8197349aac5d5a1c3c37"

_PAYLOAD = (
    "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"
)


def macro_calendar_csv_text():
    """Return the frozen calendar as UTF-8 CSV text."""
    return decompress(b64decode(_PAYLOAD)).decode("utf-8")


# Q-LIR macro exclusion audit - paste as ONE QuantConnect Research cell.
#
# 1. Paste and run macro_events_v2_embedded.py as its own notebook cell.
#    This works on free accounts; no Object Store or Research restart is needed.
# 2. Keep the locked 2021-2024 event frame in memory as `locked_events`
#    (the code also accepts `all_events`).
# 3. Run this cell BEFORE any return/effect calculation.
#
# This cell deliberately selects only date/time/class/identity columns. It
# does not read price, return, volume, or volatility values.

from hashlib import sha256
from io import StringIO
from pathlib import Path

import pandas as pd

CALENDAR_FILE = "macro_events_v2.csv"
EXPECTED_CALENDAR_SHA256 = "db16c107e06903e4731323a3ed71256d1314fa96275a8197349aac5d5a1c3c37"
EXCLUDE_MINUTES = 10
ALLOWED_YEARS = {2021, 2022, 2023, 2024}


def load_calendar():
    """Read locally or from the free-tier-compatible embedded QC module."""
    local_file = Path(CALENDAR_FILE)
    if local_file.exists():
        calendar_text = local_file.read_text(encoding="utf-8")
    elif "macro_calendar_csv_text" in globals():
        calendar_text = globals()["macro_calendar_csv_text"]()
    else:
        try:
            from macro_events_v2_embedded import macro_calendar_csv_text
        except ImportError as exc:
            raise RuntimeError(
                "Paste and run macro_events_v2_embedded.py as a notebook cell, "
                "then rerun this audit cell. No Object Store is required."
            ) from exc
        calendar_text = macro_calendar_csv_text()

    calendar_text = calendar_text.replace("\r\n", "\n")
    actual_digest = sha256(calendar_text.encode("utf-8")).hexdigest()
    if actual_digest != EXPECTED_CALENDAR_SHA256:
        raise RuntimeError(
            "Macro calendar checksum mismatch: "
            f"expected {EXPECTED_CALENDAR_SHA256}, found {actual_digest}"
        )
    return pd.read_csv(StringIO(calendar_text), comment="#", dtype=str)


if "locked_events" in globals():
    _source_events = globals()["locked_events"]
elif "all_events" in globals():
    _source_events = globals()["all_events"]
else:
    raise RuntimeError("Expected the locked frame in `locked_events` or `all_events`.")

identity_columns = ["date", "instrument", "boundary_ct", "boundary_class"]
missing_event_columns = set(identity_columns) - set(_source_events.columns)
if missing_event_columns:
    raise RuntimeError(f"Locked frame lacks columns: {sorted(missing_event_columns)}")

calendar = load_calendar()
required_calendar = {
    "date",
    "time_ct",
    "event",
    "source",
    "source_url",
    "source_asof_utc",
}
missing_calendar = required_calendar - set(calendar.columns)
if missing_calendar:
    raise RuntimeError(f"Calendar lacks columns: {sorted(missing_calendar)}")
if len(calendar) != 1_482:
    raise RuntimeError(f"Expected 1,482 v2 source rows, found {len(calendar):,}")
if calendar.duplicated(list(required_calendar)).any():
    raise RuntimeError("Calendar contains an exact duplicate provenance row")
calendar_years = set(pd.to_datetime(calendar["date"], format="%Y-%m-%d").dt.year)
if calendar_years != ALLOWED_YEARS:
    raise RuntimeError(f"Calendar years are not locked 2021-2024: {calendar_years}")

# Work on an identity-only copy. This makes accidental outcome inspection
# impossible in the exclusion-audit cell even if those columns exist upstream.
audit = _source_events.loc[:, identity_columns].copy()
audit["date"] = audit["date"].astype(str)
audit["year"] = pd.to_datetime(audit["date"], format="%Y-%m-%d").dt.year
if set(audit["year"]) - ALLOWED_YEARS:
    raise RuntimeError("Locked frame contains a 2025+ or pre-2021 observation")
if audit.duplicated(identity_columns).any():
    raise RuntimeError("Locked frame contains a duplicate instrument-boundary row")

unique_releases = calendar[["date", "time_ct"]].drop_duplicates().copy()
if len(unique_releases) != 1_156:
    raise RuntimeError(
        f"Expected 1,156 unique v2 release timestamps, found {len(unique_releases):,}"
    )
unique_releases["event_minute"] = unique_releases["time_ct"].str[:2].astype(
    int
) * 60 + unique_releases["time_ct"].str[3:5].astype(int)
release_minutes_by_date = unique_releases.groupby("date")["event_minute"].apply(
    lambda values: tuple(values)
)

boundary_minutes = audit["boundary_ct"].str[:2].astype(int) * 60 + audit["boundary_ct"].str[
    3:5
].astype(int)
audit["release_excluded"] = [
    any(
        abs(int(boundary) - int(event)) <= EXCLUDE_MINUTES
        for event in release_minutes_by_date.get(date, ())
    )
    for date, boundary in zip(audit["date"], boundary_minutes, strict=True)
]

# The same date/boundary must always receive the same decision, independent of
# instrument and treatment class.
decisions_per_timestamp = audit.groupby(["date", "boundary_ct"])["release_excluded"].nunique()
if not decisions_per_timestamp.eq(1).all():
    raise RuntimeError("Exclusion decision varies by instrument or boundary class")

group_columns = ["year", "instrument", "boundary_class"]
before = audit.groupby(group_columns).size().rename("before")
excluded = audit[audit["release_excluded"]].groupby(group_columns).size().rename("excluded")
retained = audit[~audit["release_excluded"]].groupby(group_columns).size().rename("retained")
exclusion_audit = pd.concat([before, excluded, retained], axis=1).fillna(0).astype(int)
reconciled = exclusion_audit["before"] == exclusion_audit["excluded"] + exclusion_audit["retained"]
if not reconciled.all():
    raise RuntimeError("Before != excluded + retained")

release_exclusion_mask = audit["release_excluded"].copy()
release_exclusion_mask.index = _source_events.index
locked_events_excluded = _source_events.loc[~release_exclusion_mask].copy()

print("--- MACRO CALENDAR V2 AUDIT ---")
print("source rows:", len(calendar))
print("unique release timestamps:", len(unique_releases))
print("locked input rows:", len(audit))
print("excluded rows:", int(audit["release_excluded"].sum()))
print("retained rows:", int((~audit["release_excluded"]).sum()))
print("\n--- BEFORE / EXCLUDED / RETAINED ---")
print(exclusion_audit.to_string())
print("\nPASS: date-specific +/-10-minute mask is symmetric and outcome-blind")
print("Filtered frame is available as `locked_events_excluded`; do not analyze it yet.")


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


def boot_ci(days: np.ndarray, rng: np.random.Generator) -> tuple[float, float, float]:
    """Mean and bootstrap 95% CI over per-day values."""
    days = days[np.isfinite(days)]
    if len(days) < 5:
        return float("nan"), float("nan"), float("nan")
    means = np.array([days[rng.integers(0, len(days), len(days))].mean() for _ in range(N_BOOT)])
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
            a[rng.integers(0, len(a), len(a))].mean() - b[rng.integers(0, len(b), len(b))].mean()
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
        out["volume_change"] = np.log(out["vol_fwd_60s"].where(out["vol_fwd_60s"] > 0)) - np.log(
            out["vol_pre_60s"].where(out["vol_pre_60s"] > 0)
        )
        out["vol_change"] = np.log(out["postvol_5m"].where(out["postvol_5m"] > 0)) - np.log(
            out["prevol_5m"].where(out["prevol_5m"] > 0)
        )
    return out


def class_table(frame: pd.DataFrame, label: str, rng: np.random.Generator) -> None:
    print(f"\n### {label} (events={len(frame)}, days={frame['date'].nunique()})")
    header = (
        f"{'class':<9} {'metric':<16} {'mean':>10} {'95% CI (day-clustered)':>24} {'events':>7}"
    )
    print(header)
    print("-" * len(header))
    for boundary_class in ("A_00_30", "B_15_45", "placebo"):
        sub = frame[frame["boundary_class"] == boundary_class]
        for seconds in HORIZONS:
            mean, low, high = boot_ci(daily_mean(sub, f"absr_{seconds}").to_numpy(), rng)
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
            print(f"{boundary_class:<9} {metric:<16} {fmt(mean, low, high):>36} {len(sub):>7}")


def paired_daily_contrast(
    frame: pd.DataFrame,
    column: str,
    split_column: str,
    positive: object,
    negative: object,
    rng: np.random.Generator,
) -> tuple[float, float, float, int]:
    per_day = frame.pivot_table(index="date", columns=split_column, values=column, aggfunc="mean")
    if positive not in per_day or negative not in per_day:
        return float("nan"), float("nan"), float("nan"), 0
    difference = (per_day[positive] - per_day[negative]).dropna().to_numpy()
    mean, low, high = boot_ci(difference, rng)
    return mean, low, high, len(difference)


def quarter_effect_by_day(frame: pd.DataFrame, column: str) -> pd.Series:
    per_day = frame.pivot_table(index="date", columns="is_quarter", values=column, aggfunc="mean")
    if True not in per_day or False not in per_day:
        return pd.Series(dtype=float)
    return (per_day[True] - per_day[False]).dropna()


def contrasts(frame: pd.DataFrame, label: str, rng: np.random.Generator) -> None:
    print(f"\n### Contrasts - {label} (all day-clustered)")
    for seconds in HORIZONS:
        mean, low, high, count = paired_daily_contrast(
            frame, f"absr_{seconds}", "is_quarter", True, False, rng
        )
        print(f"quarter - placebo |r| {seconds}s bp: {fmt(mean, low, high)} ({count} days)")
    for column, name in (
        ("volume_change", "volume chg"),
        ("vol_change", "vol chg"),
    ):
        mean, low, high, count = paired_daily_contrast(
            frame.dropna(subset=[column]), column, "is_quarter", True, False, rng
        )
        print(f"quarter - placebo {name:<10}: {fmt(mean, low, high)} ({count} days)")
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
        print(f"A(:00/:30) - B(:15/:45) |r| {seconds}s bp: {fmt(mean, low, high)} ({count} days)")


def cross_instrument_contrast(frame: pd.DataFrame, rng: np.random.Generator) -> None:
    print("\n### ES - NQ contrast of the quarter effect (paired by day)")
    for seconds in HORIZONS:
        es = quarter_effect_by_day(frame[frame["instrument"] == "ES"], f"absr_{seconds}")
        nq = quarter_effect_by_day(frame[frame["instrument"] == "NQ"], f"absr_{seconds}")
        joined = pd.concat([es, nq], axis=1, join="inner").dropna()
        difference = (joined.iloc[:, 0] - joined.iloc[:, 1]).to_numpy()
        mean, low, high = boot_ci(difference, rng)
        print(f"|r| {seconds}s bp: {fmt(mean, low, high)} ({len(difference)} common days)")


def development_validation_contrast(frame: pd.DataFrame, rng: np.random.Generator) -> None:
    print("\n### development (2021-2023) - validation (2024) quarter effect")
    for instrument in ("ES", "NQ"):
        sub = frame[frame["instrument"] == instrument]
        development = sub[sub["year"] <= 2023]
        validation = sub[sub["year"] == 2024]
        for seconds in HORIZONS:
            dev_effect = quarter_effect_by_day(development, f"absr_{seconds}").to_numpy()
            val_effect = quarter_effect_by_day(validation, f"absr_{seconds}").to_numpy()
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
    raise RuntimeError(f"Expected {EXPECTED_ROWS:,} retained rows, found {len(analysis_frame):,}")

analysis_frame["date"] = analysis_frame["date"].astype(str)
analysis_frame["year"] = pd.to_datetime(
    analysis_frame["date"], format="%Y-%m-%d", errors="raise"
).dt.year
fingerprint = analysis_frame.groupby(["year", "instrument", "boundary_class"]).size().to_dict()
if fingerprint != EXPECTED_RETAINED:
    raise RuntimeError("Retained-count fingerprint changed; analysis refused")
if set(analysis_frame["resolution_used"]) - {"minute", "second"}:
    raise RuntimeError("Unexpected resolution label")
if (
    not analysis_frame.loc[
        analysis_frame["boundary_class"].isin(["A_00_30", "B_15_45"]),
        "is_quarter",
    ]
    .eq(True)
    .all()
):
    raise RuntimeError("Quarter-class identity mismatch")
if (
    not analysis_frame.loc[analysis_frame["boundary_class"] == "placebo", "is_quarter"]
    .eq(False)
    .all()
):
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
        instrument_frame = analysis_frame[analysis_frame["instrument"] == instrument]
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
