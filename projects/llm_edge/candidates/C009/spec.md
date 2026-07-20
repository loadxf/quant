# C009 — Sector-ETF next-day member reversal (G1: data-first, post-cutoff provenance)

**Generation trace (provenance).** Prompted by the post-cutoff `sector_etf_lead_lag` panel
(`report/g1_panels.json`, 2026-02-02..2026-07-17): the correlation between a sector ETF's
daily return and its member stocks' NEXT-day mean return is negative for 8 of 11 sectors
(XLI -0.149, XLY -0.147, HYG-adjacent financials -0.089), opposite in sign to the classic
documented industry lead-lag (Moskowitz-Grinblatt; Hou 2007), which is positive continuation
at weekly/monthly horizons. P-derived claimed, subject to Phase D (prior-art risk: index-level
daily reversal is documented in older samples; the sector-relative daily granularity is the
claim).

**Hypothesis.** The common (sector) component of a stock's daily move reverts the next day:
stocks whose sector ETF rose today underperform tomorrow, cross-sectionally.

**Signal (exact formula).** For each stock, `signal(t) = -sector_etf_ret1(t)` where
`sector_etf_ret1` is the daily return of the stock's GICS sector ETF (XLB..XLY per
data/universe.json sector map). Cross-sectional decile long-short (ties within a sector share
the same signal; decile cut across the full panel), held 1 day, t+2 execution.

**Predicted sign:** positive. **Gate-2 comparison:** correlation with C004 reported (the
signal is the sector component of reversal; if |corr| > 0.6 it is a reversal variant, T1).

**Tier ceiling:** T2 at best (prior-art risk acknowledged in trace).
