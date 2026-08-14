# Q-LIR QC ENTITLEMENT PROBE (round 11) — one cell, paste into a QC
# Research notebook and run. Development-only, read-only, $0.
#
# Purpose: determine the ACCOUNT'S REAL entitlement, not the dataset's
# documented capability. Tests, for ONE 2021 ES session (2021-03-02):
#   - trade ticks and quote ticks (nonempty? columns? precision?)
#   - second-resolution TradeBars and QuoteBars
#   - minute-resolution TradeBars and QuoteBars (expected baseline)
#   - bid/ask prices AND sizes presence
#   - prevailing-BBO reconstruction at exactly boundary+5s
#   - the verbatim error/empty shape for unavailable resolutions
# Touches: no 2024 data, no Object Store, no downloads, no __file__.
# Output: printed report only — copy it back verbatim.
#
# Windows are deliberately tiny to fit the free research node:
#   ticks   09:55-10:20 CT (25 min, around the 10:00 and 10:15 boundaries)
#   seconds 09:30-10:30 CT (1 h)
#   minute  full session
# QC research history is indexed in America/New_York (verified in the
# Gate II workflow): CT boundaries shift +1 hour to NY.

import datetime as dt

import pandas as pd
from AlgorithmImports import *  # noqa: F403

qb = QuantBook()  # noqa: F405
future = qb.add_future(
    Futures.Indices.SP_500_E_MINI,  # noqa: F405
    Resolution.MINUTE,  # noqa: F405
    data_normalization_mode=DataNormalizationMode.RAW,  # noqa: F405
    data_mapping_mode=DataMappingMode.OPEN_INTEREST,  # noqa: F405
    contract_depth_offset=0,
)
CONT = future.symbol
SESSION = dt.date(2021, 3, 2)  # Tuesday, development period, pre-roll
print("=" * 72)
print("Q-LIR ENTITLEMENT PROBE — ES", SESSION.isoformat(), "| $0 | dev-only")
print("=" * 72)

# NY-time windows (CT + 1h).
TICK_WIN = (dt.datetime(2021, 3, 2, 10, 55), dt.datetime(2021, 3, 2, 11, 20))
SEC_WIN = (dt.datetime(2021, 3, 2, 10, 30), dt.datetime(2021, 3, 2, 11, 30))
MIN_WIN = (dt.datetime(2021, 3, 2, 4, 0), dt.datetime(2021, 3, 2, 17, 0))
# Boundaries to reconstruct BBO at b+5s (NY time = CT+1): 10:00/10:15 CT.
BOUNDARIES_NY = [dt.datetime(2021, 3, 2, 11, 0, 0), dt.datetime(2021, 3, 2, 11, 15, 0)]


def probe(label, fn):
    """Run one entitlement request; report shape or the VERBATIM failure."""
    print("\n---", label, "---")
    try:
        df = fn()
    except Exception as exc:  # report the exact error shape
        print(f"ERROR  {type(exc).__name__}: {exc}")
        return None
    if df is None or (hasattr(df, "empty") and df.empty):
        print(f"EMPTY  type={type(df).__name__}  (empty-result shape)")
        return None
    flat = df.droplevel(list(range(df.index.nlevels - 1))) if df.index.nlevels > 1 else df
    print(f"OK  rows={len(flat)}  columns={list(flat.columns)}")
    idx = flat.index
    subsec = [ts for ts in idx[: min(len(idx), 5000)] if ts.microsecond or ts.nanosecond]
    print(
        f"timestamp precision: first={idx[0]!r} "
        f"sub-second stamps in first 5k: {len(subsec)}"
        + (f" (e.g. {subsec[0]!r})" if subsec else " (all whole-second/minute)")
    )
    print("head(3):")
    print(flat.head(3).to_string())
    return flat


# ---- 1. ticks (trades + quotes arrive together at Resolution.TICK) ----
ticks = probe(
    "TICK history 25min",
    lambda: qb.history(CONT, TICK_WIN[0], TICK_WIN[1], Resolution.TICK),  # noqa: F405
)
trade_ticks = quote_ticks = None
if ticks is not None:
    cols = set(ticks.columns)
    if "lastprice" in cols or "price" in cols:
        price_col = "lastprice" if "lastprice" in cols else "price"
        trade_ticks = ticks[ticks[price_col].notna() & (ticks.get("quantity", 0) > 0)]
        print(f"\ntrade ticks: {len(trade_ticks)} rows (price+quantity present)")
    if {"bidprice", "askprice"} <= cols:
        quote_ticks = ticks[ticks["bidprice"].notna() | ticks["askprice"].notna()]
        has_sizes = {"bidsize", "asksize"} <= cols
        print(f"quote ticks: {len(quote_ticks)} rows; bid/ask SIZES present: {has_sizes}")
    else:
        print("quote ticks: bid/ask columns ABSENT from tick frame")

# ---- 2. second resolution: trades and quotes -------------------------
sec_trades = probe(
    "SECOND TradeBars 1h",
    lambda: qb.history(TradeBar, CONT, SEC_WIN[0], SEC_WIN[1], Resolution.SECOND),  # noqa: F405
)
sec_quotes = probe(
    "SECOND QuoteBars 1h",
    lambda: qb.history(QuoteBar, CONT, SEC_WIN[0], SEC_WIN[1], Resolution.SECOND),  # noqa: F405
)

# ---- 3. minute resolution baseline -----------------------------------
min_trades = probe(
    "MINUTE TradeBars session",
    lambda: qb.history(TradeBar, CONT, MIN_WIN[0], MIN_WIN[1], Resolution.MINUTE),  # noqa: F405
)
min_quotes = probe(
    "MINUTE QuoteBars session",
    lambda: qb.history(QuoteBar, CONT, MIN_WIN[0], MIN_WIN[1], Resolution.MINUTE),  # noqa: F405
)

# ---- 4. prevailing BBO at exactly boundary+5s ------------------------
print("\n--- BBO reconstruction at b+5s ---")


def last_at_or_before(frame, when):
    pos = frame.index.searchsorted(pd.Timestamp(when), side="right") - 1
    return frame.iloc[pos] if pos >= 0 else None


for b in BOUNDARIES_NY:
    instant = b + dt.timedelta(seconds=5)
    print(f"\nboundary {b.time()} NY (+5s = {instant.time()}):")
    if quote_ticks is not None and len(quote_ticks):
        row = last_at_or_before(quote_ticks, instant)
        if row is not None:
            age = (pd.Timestamp(instant) - row.name).total_seconds()
            print(
                f"  from QUOTE TICKS: bid={row.get('bidprice')} "
                f"ask={row.get('askprice')} bidsz={row.get('bidsize')} "
                f"asksz={row.get('asksize')} quote_age={age:.3f}s"
            )
    else:
        print("  quote ticks unavailable for tick-level BBO")
    if sec_quotes is not None and len(sec_quotes):
        row = last_at_or_before(sec_quotes, instant)
        if row is not None:
            close_bid = row.get("bidclose", row.get("close"))
            close_ask = row.get("askclose")
            print(
                f"  from SECOND QuoteBars: bar_end={row.name} "
                f"bidclose={close_bid} askclose={close_ask} "
                f"(bar-close proxy, <=1s stale)"
            )
    else:
        print("  second QuoteBars unavailable")
    if min_quotes is not None and len(min_quotes):
        row = last_at_or_before(min_quotes, instant)
        if row is not None:
            print(
                f"  from MINUTE QuoteBars: bar_end={row.name} "
                f"(coarsest fallback; up to 60s stale at b+5s)"
            )

# ---- 5. verdict -------------------------------------------------------
print("\n" + "=" * 72)
print("ENTITLEMENT VERDICT (copy this block back verbatim):")
print(f"  trade ticks nonempty:   {trade_ticks is not None and len(trade_ticks) > 0}")
print(f"  quote ticks nonempty:   {quote_ticks is not None and len(quote_ticks) > 0}")
print(f"  second TradeBars:       {sec_trades is not None and len(sec_trades) > 0}")
print(f"  second QuoteBars:       {sec_quotes is not None and len(sec_quotes) > 0}")
print(f"  minute TradeBars:       {min_trades is not None and len(min_trades) > 0}")
print(f"  minute QuoteBars:       {min_quotes is not None and len(min_quotes) > 0}")
print("  BRANCH A (frozen Gate III in QC) needs quote ticks or second QuoteBars.")
print("  BRANCH B (Gate III-M minute proxy) needs minute QuoteBars only.")
print("=" * 72)
