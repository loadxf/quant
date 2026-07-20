# C008 — Gap-intraday coherence premium (G1: data-first, post-cutoff provenance)

**Generation trace (provenance).** Prompted by the corner structure of the post-cutoff
`gap_x_intraday` double-sort (`report/g1_panels.json`, 2026-02-02..2026-07-17): next-day
returns are strongly positive in BOTH sign-agreement corners — stocks that gapped down AND
fell intraday: **+40.5 bps**; stocks that gapped up AND rose intraday: **+29.0 bps** — while
the sign-disagreement corners are near zero (-1.8, +2.7). This is not simple reversal (which
would make the up-up corner negative): it is a U-shape in the agreement between the overnight
and intraday components of the same day's move. Model never saw this window (post-cutoff);
P-derived claimed, subject to Phase D.

**Hypothesis.** When a stock's overnight gap and its intraday move agree in sign (a
"coherent" day — the overnight crowd and the intraday crowd traded the same direction), the
next day carries a positive premium; incoherent days carry none. Interpretation to test, not
assume: coherent days are liquidity-demand days (one-sided pressure) compensated next day
regardless of direction.

**Signal (exact formula).** `coherence = gap * intraday` (product of the day's overnight and
intraday simple returns; positive iff same sign, magnitude scales with both). Signal =
cross-sectional value of `coherence`, smoothed `roll_mean(3)` to reduce single-day noise.
Decile long-short, held 1 day, t+2 execution, S&P 500 equities.

**Predicted sign:** positive. **Gate-2 comparisons:** daily-return correlation with C004
(-ret5) and C006 (-intraday5) reported; |corr| > 0.6 with either declares it a reversal
variant (T1 ceiling).

**Tier ceiling:** T2/T3 if no prior art for a sign-agreement (coherence) premium between
overnight and intraday same-day components.
