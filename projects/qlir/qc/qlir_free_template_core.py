# Q-LIR Gate II free-tier QuantConnect Research template core.
# Run cells top to bottom. Do not extend the sample beyond 2024.
# ruff: noqa: F403, F405 - QuantConnect exposes its research API via star import.

# %% CELL 1 - setup
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


# %% CELL 2 - history and half-open window helpers
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


# %% CELL 3 - mandatory timezone alignment probe
probe = request_month(continuous["ES"], dt.datetime(2024, 3, 5), dt.datetime(2024, 3, 6))
cash_open_window = probe.between_time("09:25", "09:35")
if cash_open_window.empty:
    raise RuntimeError("No ES bars around the expected 09:30 New York cash open")
spike = cash_open_window["volume"].idxmax()
if not (spike.hour == 9 and 25 <= spike.minute <= 35):
    raise RuntimeError(f"Unexpected timestamp alignment; volume spike was {spike}")
print("PASS: ES history index is New York exchange time; cash-open spike:", spike)


# %% CELL 4 - year extraction function
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


# %% CELL 5 - extract 2021 through 2024 (resumable within this kernel)
if "events_by_year" not in globals():
    events_by_year = {}

for extraction_year in range(START_YEAR, END_YEAR + 1):
    if extraction_year not in events_by_year:
        events_by_year[extraction_year] = extract_year(extraction_year)
    print(extraction_year, len(events_by_year[extraction_year]))


# %% CELL 6 - retain only complete SPY cash sessions
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


# %% CELL 7 - lock and audit the pre-analysis frame
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
