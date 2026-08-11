# C011 — G2 search winner: gap-volatility minus monthly return

**Generation trace (provenance).** Second structurally distinct expression among the G2
search survivors (seed 20260719, ledgered): `roll_std(gap, 63) - ret21`, train net SR 0.63.
Selection was purely by historical fitness, but retrospective audit D5 established that the
original run included available pre-2005 observations through 2018 instead of the registered
2005-2018 train window. It remains P-derived at the selection level, but is not presented as
an exact pre-registered selection; the corrected forward driver binds the 2005 start.

**Hypothesis (post-hoc articulation, to be tested).** A combination of overnight-gap
instability (long stocks with volatile overnight gaps) and one-month reversal (short recent
winners). The gap-vol component is the non-obvious part; ret21 reversal is documented.

**Known prior-art risk:** monthly reversal is T0 (Jegadeesh 1990); overnight-return
volatility appears in the overnight/intraday literature (Lou-Polk-Skouras). The specific
combination and the gap-vol-specific channel are the only possible novelty.

**Signal (exact formula).** `signal = rolling_std_63(gap, min_periods=31) - ret21` with
`gap = open/prev_close - 1`, `ret21 = 21-day return`; 31 observations are the grammar's
half-window warm-up for the rolling standard deviation. Decile long-short, held 1 day,
t+2 execution, S&P 500 equities.

**Predicted sign:** positive (as selected in the historical fitness sample). **Tier ceiling:**
T1-T2.
