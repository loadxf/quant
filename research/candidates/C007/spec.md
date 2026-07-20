# C007 — Lag-7 band reversal (G1: data-first, post-cutoff provenance)

**Generation trace (provenance).** Prompted by a specific statistic in the post-cutoff panel
(`report/g1_panels.json`, window 2026-02-02..2026-07-17, computed via the gated
`load_g1_window` path): the cross-sectional lag-response profile shows its strongest cell at
**lag 7: mean Spearman IC = -0.056, t = -2.96** — stronger than the lag-1 reversal cell
(-0.029, t = -1.49) in the same window, and NOT at lag 5 where a weekly-seasonality story
would put it. The generating model never saw this window in training (cutoff Jan 2026);
provenance grade P-derived claimed, subject to Phase D attack (multiple-testing caveat: the
profile has 10 cells; this is why the hypothesis is validated on 19 years of disjoint history
rather than trusted from the panel).

**Hypothesis.** The single-day return realized ~7 trading days ago carries a cross-sectional
reversal signal for tomorrow that is distinct from (a) the documented lag-1 short-term
reversal and (b) weekly (lag-5) seasonality. Economic story to be tested, not assumed:
delayed correction after multi-day event drift completes.

**Signal (exact formula).** `-ret_band(6..8)` where `ret_band = adjclose.pct_change(3)
shifted by 6` — i.e. minus the cumulative return over days t-8..t-6:
`signal(t) = -(adjclose(t-6)/adjclose(t-8) - 1)`.
Decile long-short, held 1 day, t+2 execution, S&P 500 equities.

**Predicted sign:** positive. **Gate-2 comparison:** must remain positive after
orthogonalization sanity check vs C004 (-ret5): correlation of daily returns with C004
reported; if |corr| > 0.6 the candidate is declared a reversal variant (T1), not novel.

**Tier ceiling:** T2/T3 if no prior art for an isolated medium-lag (6-8 day) single-band
cross-sectional reversal distinct from lag-1 and weekly effects.
