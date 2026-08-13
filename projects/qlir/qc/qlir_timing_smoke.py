# Q-LIR Gate II timing smoke test — QuantConnect RESEARCH notebook code.
#
# PASTE each CELL below into a QC Cloud Research notebook (research.ipynb)
# and run top to bottom. It extracts one row per five-minute boundary per
# instrument per day (2021-01-04 .. 2024-12-31) from QC's built-in
# continuous-futures data and writes per-year CSVs into the research
# filesystem. DOWNLOAD those CSVs (right-click in the file browser) and
# run projects/qlir/scripts/timing_smoke_stats.py locally on them.
#
# Authorized scope (Sol round 2, section 5.1): unconditional forward
# returns after quarter-hour vs placebo boundaries, the :00/:30 vs
# :15/:45 contrast, and volatility/volume changes. TRADE bars only, no
# aggressor side — a null here does NOT falsify flow-conditioned Q-LIR.
# 2025-2026 are locked: do not extend END_YEAR.
#
# Data notes: tries Resolution.SECOND first and falls back to MINUTE per
# month if the request fails on the account tier. Forward returns use
# the last trade price at-or-before each offset; with minute bars the
# 60s/120s/300s offsets are minute-aligned (coarse, disclosed in the
# output as resolution_used).

# %% CELL 1 — setup
import datetime as dt

import numpy as np
import pandas as pd
from AlgorithmImports import *  # noqa: F403 (QC research environment)

qb = QuantBook()  # noqa: F405
FUTS = {
    "ES": Futures.Indices.SP_500_E_MINI,  # noqa: F405
    "NQ": Futures.Indices.NASDAQ_100_E_MINI,  # noqa: F405
}
CONT = {}
for name, ticker in FUTS.items():
    f = qb.add_future(
        ticker,
        Resolution.MINUTE,  # noqa: F405 - subscription res; history res set per call
        data_normalization_mode=DataNormalizationMode.RAW,  # noqa: F405 - real prices, no back-adjust
        data_mapping_mode=DataMappingMode.OPEN_INTEREST,  # noqa: F405
        contract_depth_offset=0,
    )
    CONT[name] = f.symbol
print("continuous symbols:", CONT)

START_YEAR, END_YEAR = 2021, 2024  # 2025+ LOCKED — do not extend
# Boundaries 08:45..14:45 America/Chicago inclusive, every 5 minutes.
# Frozen exclusions built in: the ±10-minute cash-open window (08:30
# open -> first eligible boundary 08:45; 08:40 sits exactly at +10 min
# and is excluded) and the final 20+ minutes before the 15:10 hard
# close (last boundary 14:45). Scheduled-release windows are excluded
# SYMMETRICALLY (quarter and placebo alike) in the local stats script.
BOUNDARIES = [
    dt.time(h, m)
    for h in range(8, 15)
    for m in range(0, 60, 5)
    if (h, m) >= (8, 45) and (h, m) <= (14, 45)
]
FORWARD_S = [60, 120, 300]
PRE_S = 60

# %% CELL 2 — sanity check timestamp alignment BEFORE the full run.
# QC research history is indexed in the notebook default time zone
# (America/New_York). Verify: the 08:30 CT cash-open volume spike must
# appear at 09:30 in the raw index. If it does not, STOP and report.
probe = qb.history(CONT["ES"], dt.datetime(2024, 3, 5), dt.datetime(2024, 3, 6), Resolution.MINUTE)  # noqa: F405
if not probe.empty:
    v = probe.droplevel(list(range(probe.index.nlevels - 1)))["volume"]
    spike = v.between_time("09:25", "09:35").idxmax()
    print("volume spike near NY 09:30 (should be ~09:30-09:31):", spike)
NY_TO_CT = -1  # hours; NY 09:30 == CT 08:30 year-round (both shift DST together)


# %% CELL 3 — window primitives.
# VERBATIM COPY of projects/qlir/src/qlir/windows.py (unit-tested there);
# any change must be mirrored. All windows are HALF-OPEN (start, end]:
# the boundary bar counts on exactly one side, and at minute resolution
# a "60-second" window is exactly one bar, never two.
def half_open_slice(series: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    index = series.index
    lo = index.searchsorted(start, side="right")
    hi = index.searchsorted(end, side="right")
    return series.iloc[lo:hi]


def window_sum(series: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float:
    return float(half_open_slice(series, start, end).sum())


def last_at_or_before(series: pd.Series, when: pd.Timestamp):
    position = series.index.searchsorted(when, side="right") - 1
    return float(series.iloc[position]) if position >= 0 else None


def logret_std(closes: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float:
    window = half_open_slice(closes, start, end)
    base = last_at_or_before(closes, start)
    if base is None or len(window) < 1:
        return float("nan")
    prices = np.concatenate([[base], window.to_numpy(dtype="float64")])
    if len(prices) < 3:
        return float("nan")
    return float(np.std(np.diff(np.log(prices)), ddof=1))


# %% CELL 4 — extraction


def extract_year(year: int) -> pd.DataFrame:
    rows = []
    for month in range(1, 13):
        m_start = dt.datetime(year, month, 1)
        m_end = dt.datetime(year + (month == 12), month % 12 + 1, 1)
        for name, symbol in CONT.items():
            res_used = "second"
            try:
                hist = qb.history(symbol, m_start, m_end, Resolution.SECOND)  # noqa: F405
                if hist.empty:
                    raise ValueError("empty second history")
            except Exception as exc:  # tier/limit fallback, disclosed per row
                print(f"{year}-{month:02d} {name}: second failed ({exc}); minute fallback")
                res_used = "minute"
                hist = qb.history(symbol, m_start, m_end, Resolution.MINUTE)  # noqa: F405
                if hist.empty:
                    continue
            bars = hist.droplevel(list(range(hist.index.nlevels - 1)))
            closes, volumes = bars["close"], bars["volume"]
            # Index is New York time; convert boundary wall times CT->NY.
            for session in sorted({ts.date() for ts in closes.index}):
                for b_ct in BOUNDARIES:
                    b_ny = dt.datetime.combine(session, b_ct) - dt.timedelta(hours=NY_TO_CT)
                    b = pd.Timestamp(b_ny)
                    p0 = last_at_or_before(closes, b)
                    p_pre = last_at_or_before(closes, b - pd.Timedelta(seconds=PRE_S))
                    if p0 is None or p_pre is None or p0 <= 0 or p_pre <= 0:
                        continue
                    prevol = logret_std(closes, b - pd.Timedelta(minutes=5), b)
                    postvol = logret_std(closes, b, b + pd.Timedelta(minutes=5))
                    if not (np.isfinite(prevol) and np.isfinite(postvol)):
                        continue
                    row = {
                        "date": session.isoformat(),
                        "instrument": name,
                        "boundary_ct": b_ct.strftime("%H:%M"),
                        "minute": b_ct.minute,
                        "is_quarter": b_ct.minute % 15 == 0,
                        "boundary_class": (
                            "A_00_30"
                            if b_ct.minute % 30 == 0
                            else ("B_15_45" if b_ct.minute % 15 == 0 else "placebo")
                        ),
                        "resolution_used": res_used,
                        "price_b": p0,
                        "ret_pre_60s": np.log(p0 / p_pre),
                        "prevol_5m": prevol,
                        "postvol_5m": postvol,
                        # Half-open (b-60s, b]: the boundary bar counts here
                        # and NEVER in the forward windows below.
                        "vol_pre_60s": window_sum(volumes, b - pd.Timedelta(seconds=PRE_S), b),
                    }
                    ok = True
                    for s in FORWARD_S:
                        pf = last_at_or_before(closes, b + pd.Timedelta(seconds=s))
                        if pf is None or pf <= 0:
                            ok = False
                            break
                        row[f"ret_fwd_{s}s"] = np.log(pf / p0)
                        # Half-open (b, b+s]: excludes the boundary bar.
                        row[f"vol_fwd_{s}s"] = window_sum(volumes, b, b + pd.Timedelta(seconds=s))
                    if ok:
                        rows.append(row)
        print(f"{year}-{month:02d}: cumulative rows {len(rows)}")
    return pd.DataFrame(rows)


for year in range(START_YEAR, END_YEAR + 1):
    df = extract_year(year)
    out = f"qlir_events_{year}.csv"
    df.to_csv(out, index=False)
    print(f"wrote {out}: {len(df)} rows — download this file")
