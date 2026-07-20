# C010 — G2 search winner: range-variability (vol-of-range) long-short

**Generation trace (provenance).** Produced by the G2 evolutionary search
(`quantlab.search.evolve`, seed 20260719, 430 distinct expressions, all ledgered): the
fitness-selected family converged on `roll_std(rng, 63)` — the 63-day standard deviation of
the daily high-low range fraction — with train net SR 0.70. Selection was purely by TRAIN
(2005-2018) cost-adjusted fitness; the model chose only the grammar. Provenance: P-derived at
the selection level (the data picked this expression), with the caveat that the grammar's
terminals/operators are model-chosen priors.

**Hypothesis (post-hoc articulation, to be tested).** Stocks whose daily trading range is
UNSTABLE (high vol-of-range) earn higher subsequent returns than stable-range stocks.

**Known prior-art risk (declared upfront for Phase D):** the documented idiosyncratic-
volatility and vol-of-vol literatures (Ang-Hodrick-Xing-Zhang 2006; Baltussen et al.) find
the OPPOSITE sign (high vol → low return). A positive sign on today's-constituents data is a
textbook survivorship-bias signature (protocol R2); the statistical red team must weigh this.

**Signal (exact formula).** `signal = rolling_std_63(rng)` where `rng = (high - low)/close`
(63-day window, min 31 obs). Decile long-short, held 1 day, t+2 execution, S&P 500 equities.

**Predicted sign:** positive (as selected on train). **Tier ceiling:** T1-T2 (method is
documented GP-alpha-mining; the specific expression may or may not have prior art).
