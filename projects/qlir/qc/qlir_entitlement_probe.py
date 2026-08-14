# Q-LIR QC ENTITLEMENT PROBE (round 12 — corrected) — one cell, paste
# into a QC Research notebook and run. Development-only, read-only, $0.
#
# Purpose: determine the ACCOUNT'S REAL entitlement, not the dataset's
# documented capability. Tests, for ONE 2021 ES session (2021-03-02):
#   - trade ticks and quote ticks, classified by POSITIVE fields (QC
#     represents unused sides as zero, not NaN) and by TickType when the
#     frame exposes it;
#   - second- and minute-resolution TradeBars and QuoteBars, with quote
#     bars checked for USABLE positive two-sided observations, not
#     merely column names;
#   - prevailing two-sided BBO at exactly boundary+5s with INDEPENDENT
#     per-side carry-forward state and per-side staleness;
#   - the verbatim error/empty shape for unavailable resolutions.
# Runtime behavior: qb.history reads only — zero filesystem, ObjectStore,
# or download calls at runtime; no 2024+ data is requested.
# Output: printed report only — copy the verdict block back verbatim.
#
# Windows are deliberately tiny to fit the free research node:
#   ticks   09:55-10:20 CT (25 min, around the 10:00 and 10:15 boundaries)
#   seconds 09:30-10:30 CT (1 h)
#   minute  full session
# The QuantBook clock is set to New York explicitly below so request
# windows and returned indices share ONE DECLARED time zone (CT + 1h).

import datetime as dt

import pandas as pd
from AlgorithmImports import *  # noqa: F403

qb = QuantBook()  # noqa: F405
qb.set_time_zone(TimeZones.NEW_YORK)  # noqa: F405
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
print("Q-LIR ENTITLEMENT PROBE r12 — ES", SESSION.isoformat(), "| $0 | dev-only")
print("=" * 72)
print(f"QuantBook time zone (declared): {qb.time_zone}")
exchange_tz = getattr(getattr(future, "exchange", None), "time_zone", "UNAVAILABLE")
print(f"Exchange time zone:             {exchange_tz}")

# NY-time windows (CT + 1h), interpreted on the declared QuantBook clock.
TICK_WIN = (dt.datetime(2021, 3, 2, 10, 55), dt.datetime(2021, 3, 2, 11, 20))
SEC_WIN = (dt.datetime(2021, 3, 2, 10, 30), dt.datetime(2021, 3, 2, 11, 30))
MIN_WIN = (dt.datetime(2021, 3, 2, 4, 0), dt.datetime(2021, 3, 2, 17, 0))
# Boundaries to reconstruct BBO at b+5s (NY time = CT+1): 10:00/10:15 CT
# — one A-class (:00) and one B-class (:15) boundary.
BOUNDARIES_NY = [dt.datetime(2021, 3, 2, 11, 0, 0), dt.datetime(2021, 3, 2, 11, 15, 0)]


def pos(series):
    """Positive-and-present: QC uses zero (not NaN) for unused fields."""
    return series.fillna(0).gt(0)


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


def usable_two_sided(frame):
    """Count quote bars with POSITIVE bid AND ask closes — usable
    observations, not merely existing columns."""
    if frame is None:
        return 0
    if "bidclose" not in frame.columns or "askclose" not in frame.columns:
        return 0
    return int((pos(frame["bidclose"]) & pos(frame["askclose"])).sum())


# ---- 1. ticks (trades + quotes arrive together at Resolution.TICK) ----
ticks = probe(
    "TICK history 25min",
    lambda: qb.history(CONT, TICK_WIN[0], TICK_WIN[1], Resolution.TICK),  # noqa: F405
)
trade_ticks = quote_ticks = None
if ticks is not None:
    cols = set(ticks.columns)
    price_col = "lastprice" if "lastprice" in cols else ("price" if "price" in cols else None)
    trade_mask = quote_mask = None
    type_col = next((c for c in ("ticktype", "type") if c in cols), None)
    if type_col is not None:
        census = ticks[type_col].value_counts(dropna=False).to_dict()
        print(f"\nTickType column {type_col!r} exposed; census: {census}")
        as_text = ticks[type_col].astype(str).str.lower()
        if as_text.str.contains("trade").any() or as_text.str.contains("quote").any():
            trade_mask = as_text.str.contains("trade")
            quote_mask = as_text.str.contains("quote")
            print("classification: by TickType (authoritative)")
    if trade_mask is None:
        # Positive-field fallback: trade ticks have positive price AND
        # quantity; quote ticks have a positive bid OR ask. Zeros are
        # "unused", so .notna() alone would misclassify (round 12, #1).
        if price_col is not None and "quantity" in cols:
            trade_mask = pos(ticks[price_col]) & pos(ticks["quantity"])
        if {"bidprice", "askprice"} <= cols:
            quote_mask = pos(ticks["bidprice"]) | pos(ticks["askprice"])
        print("\nclassification: by positive fields (no TickType column)")
    if trade_mask is not None:
        trade_ticks = ticks[trade_mask]
        print(f"trade ticks (usable): {len(trade_ticks)} rows")
    else:
        print("trade ticks: price/quantity columns ABSENT from tick frame")
    if quote_mask is not None:
        quote_ticks = ticks[quote_mask]
        has_sizes = {"bidsize", "asksize"} <= cols
        print(f"quote ticks (usable): {len(quote_ticks)} rows; bid/ask SIZES present: {has_sizes}")
    else:
        print("quote ticks: bid/ask columns ABSENT from tick frame")
    if trade_mask is not None and quote_mask is not None:
        overlap = int((trade_mask & quote_mask).sum())
        print(f"rows matching BOTH masks (ambiguous): {overlap}")

# ---- 2. second resolution: trades and quotes -------------------------
sec_trades = probe(
    "SECOND TradeBars 1h",
    lambda: qb.history(TradeBar, CONT, SEC_WIN[0], SEC_WIN[1], Resolution.SECOND),  # noqa: F405
)
sec_quotes = probe(
    "SECOND QuoteBars 1h",
    lambda: qb.history(QuoteBar, CONT, SEC_WIN[0], SEC_WIN[1], Resolution.SECOND),  # noqa: F405
)
sec_quotes_usable = usable_two_sided(sec_quotes)
print(f"\nsecond QuoteBars usable two-sided closes: {sec_quotes_usable}")

# ---- 3. minute resolution baseline -----------------------------------
min_trades = probe(
    "MINUTE TradeBars session",
    lambda: qb.history(TradeBar, CONT, MIN_WIN[0], MIN_WIN[1], Resolution.MINUTE),  # noqa: F405
)
min_quotes = probe(
    "MINUTE QuoteBars session",
    lambda: qb.history(QuoteBar, CONT, MIN_WIN[0], MIN_WIN[1], Resolution.MINUTE),  # noqa: F405
)
min_quotes_usable = usable_two_sided(min_quotes)
print(f"\nminute QuoteBars usable two-sided closes: {min_quotes_usable}")

# ---- 4. prevailing two-sided BBO at exactly boundary+5s ---------------
print("\n--- BBO reconstruction at b+5s ---")
print("(quote-tick state seeded at window start 10:55 NY; a quote tick")
print(" may update ONE side only, so bid and ask carry forward and age")
print(" INDEPENDENTLY; valid = both sides positive and not crossed)")


def bbo_state_at(quotes, instant):
    """Independent per-side carry-forward BBO state at `instant`.
    Bid updates only on a positive bid; ask only on a positive ask.
    Each side keeps its own timestamp, so staleness is per-side."""
    when = pd.Timestamp(instant)
    upto = quotes[quotes.index <= when]
    if not len(upto):
        return None
    state = {}
    bids = upto[pos(upto["bidprice"])]
    if len(bids):
        row = bids.iloc[-1]
        state["bid"] = float(row["bidprice"])
        state["bidsize"] = row.get("bidsize")
        state["bid_age_s"] = (when - bids.index[-1]).total_seconds()
    asks = upto[pos(upto["askprice"])]
    if len(asks):
        row = asks.iloc[-1]
        state["ask"] = float(row["askprice"])
        state["asksize"] = row.get("asksize")
        state["ask_age_s"] = (when - asks.index[-1]).total_seconds()
    return state


def last_at_or_before(frame, when):
    idx = frame.index.searchsorted(pd.Timestamp(when), side="right") - 1
    return frame.iloc[idx] if idx >= 0 else None


bbo_valid_any = False
for b in BOUNDARIES_NY:
    instant = b + dt.timedelta(seconds=5)
    print(f"\nboundary {b.time()} NY (+5s = {instant.time()}):")
    if quote_ticks is not None and len(quote_ticks):
        state = bbo_state_at(quote_ticks, instant)
        if state and "bid" in state and "ask" in state:
            crossed = state["bid"] > state["ask"]
            valid = not crossed
            bbo_valid_any = bbo_valid_any or valid
            print(
                f"  from QUOTE TICKS: bid={state['bid']} ask={state['ask']} "
                f"bidsz={state['bidsize']} asksz={state['asksize']} "
                f"bid_age={state['bid_age_s']:.3f}s ask_age={state['ask_age_s']:.3f}s "
                f"crossed={crossed} VALID_TWO_SIDED={valid}"
            )
        else:
            sides = sorted(k for k in (state or {}) if k in ("bid", "ask"))
            print(f"  from QUOTE TICKS: two-sided state UNAVAILABLE (sides seen: {sides})")
    else:
        print("  quote ticks unavailable for tick-level BBO")
    if sec_quotes is not None and len(sec_quotes):
        row = last_at_or_before(sec_quotes, instant)
        if row is not None:
            print(
                f"  from SECOND QuoteBars: bar_end={row.name} "
                f"bidclose={row.get('bidclose')} askclose={row.get('askclose')} "
                f"bidsz={row.get('bidsize')} asksz={row.get('asksize')} "
                f"bar_age={(pd.Timestamp(instant) - row.name).total_seconds():.3f}s "
                f"(interval-close approximation — NOT exact b+5s BBO)"
            )
    else:
        print("  second QuoteBars unavailable")
    if min_quotes is not None and len(min_quotes):
        row = last_at_or_before(min_quotes, instant)
        if row is not None:
            print(
                f"  from MINUTE QuoteBars: bar_end={row.name} "
                f"bidclose={row.get('bidclose')} askclose={row.get('askclose')} "
                f"bar_age={(pd.Timestamp(instant) - row.name).total_seconds():.3f}s "
                f"(interval-close approximation, up to 60s stale — NOT exact b+5s BBO)"
            )
    else:
        print("  minute QuoteBars unavailable")

# ---- 5. verdict -------------------------------------------------------
tick_trades_ok = trade_ticks is not None and len(trade_ticks) > 0
tick_quotes_ok = quote_ticks is not None and len(quote_ticks) > 0
sec_trades_ok = sec_trades is not None and len(sec_trades) > 0
sec_quotes_ok = sec_quotes_usable > 0
min_trades_ok = min_trades is not None and len(min_trades) > 0
min_quotes_ok = min_quotes_usable > 0

if tick_trades_ok and tick_quotes_ok and bbo_valid_any:
    branch = "A"
elif sec_trades_ok and sec_quotes_ok:
    branch = "S"
elif min_trades_ok and min_quotes_ok:
    branch = "M"
else:
    branch = "NONE"

print("\n" + "=" * 72)
print("ENTITLEMENT VERDICT (copy this block back verbatim):")
print(f"  trade ticks usable:           {tick_trades_ok}")
print(f"  quote ticks usable:           {tick_quotes_ok}")
print(f"  valid two-sided BBO at b+5s:  {bbo_valid_any}")
print(f"  second TradeBars:             {sec_trades_ok}")
print(f"  second QuoteBars usable:      {sec_quotes_ok} ({sec_quotes_usable} two-sided closes)")
print(f"  minute TradeBars:             {min_trades_ok}")
print(f"  minute QuoteBars usable:      {min_quotes_ok} ({min_quotes_usable} two-sided closes)")
print("  BRANCH REQUIREMENTS:")
print("    A    trade ticks + quote ticks + valid two-sided BBO (frozen Gate III)")
print("    S    second TradeBars + second QuoteBars (one-second proxy only)")
print("    M    minute TradeBars + minute QuoteBars (minute proxy only)")
print("    NONE insufficient quote data")
print(f"  VERDICT: BRANCH {branch}")
print("=" * 72)
