# C015 — Range-volatility premium, 5-day hold (G2 loop-2, equities)

**Generation trace (provenance).** Top expression of the loop-2 equities5 evolutionary
search (seed 20260720, fitness = net train SR at 5-day hold on the 2010-2018 subwindow,
252-name stride subuniverse; checkpointed run, every evaluation ledgered):
**`(roll_std rng 63)`** — the 63-day standard deviation of the daily high-low range
fraction ((high-low)/close). Train SR net ≈ 0.82. Selection was by data fitness; the model's
priors chose only the grammar. Provenance: P-derived at the selection level.

**Convergence evidence:** the historical loop-1 search (different seed, 1-day hold, full
universe, unintentionally including pre-2005 data through 2018 per retrospective audit D5)
independently landed its only Gate-2 survivor in the SAME family (C010 =
`roll_std(rng,63)`, historical val SR +0.57). The two searches converged on range-volatility,
but the loop-1 selection was not an exact registered-window run; C015's own declared
2010-2018 selection is unaffected.

**DECLARED SUSPICION (pre-registered honesty).** The direction is LONG high-range-volatility
names — the OPPOSITE sign of the documented low-volatility/IVOL anomaly (Ang et al. 2006:
high IVOL underperforms; Bali et al. MAX: lottery stocks underperform). A long-high-vol
premium on a CURRENT-constituent universe is exactly what survivorship bias manufactures
(volatile names that survived into today's index outperformed; volatile names that died are
absent). Phase D's statistical red team must specifically test this (e.g., sign of the
long leg vs short leg contribution, behavior in the ETF universe where survivorship is
absent). If the effect is survivorship artifact, the candidate dies regardless of gates.

**Signal (exact formula).** `signal = rng.rolling(63, min_periods=31).std()` where
`rng = (high-low)/close`; for window perturbations the minimum is always
`floor(window / 2)`. Decile long-short (long high), 5-day hold, t+2 execution,
S&P 500 equities, 10 bps.

**Predicted sign:** positive (as selected by the search). **Tier ceiling:** the method is T1
(documented GP/LLM alpha mining); the specific signal could reach T2 only if Phase D finds
no prior art for cross-sectional range-vol sorted with THIS sign — see declared suspicion.
