# C011 — G2 search winner: gap-volatility minus monthly return

**Generation trace (provenance).** Second structurally distinct expression among the G2
search survivors (seed 20260719, ledgered): `roll_std(gap, 63) - ret21`, train net SR 0.63.
Selection purely by train fitness. P-derived at the selection level.

**Hypothesis (post-hoc articulation, to be tested).** A combination of overnight-gap
instability (long stocks with volatile overnight gaps) and one-month reversal (short recent
winners). The gap-vol component is the non-obvious part; ret21 reversal is documented.

**Known prior-art risk:** monthly reversal is T0 (Jegadeesh 1990); overnight-return
volatility appears in the overnight/intraday literature (Lou-Polk-Skouras). The specific
combination and the gap-vol-specific channel are the only possible novelty.

**Signal (exact formula).** `signal = rolling_std_63(gap) - ret21` with
`gap = open/prev_close - 1`, `ret21 = 21-day return`. Decile long-short, held 1 day, t+2
execution, S&P 500 equities.

**Predicted sign:** positive (as selected on train). **Tier ceiling:** T1-T2.
