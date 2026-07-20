# C001 — Hydrological recession: volume-shock half-life conditions reversal speed

**Mechanism (G3 cross-domain transfer).** In hydrology, streamflow after a rainstorm decays
exponentially with a catchment-specific recession constant reflecting groundwater storage
(Boussinesq/Maillet recession analysis): large-aquifer catchments release water slowly. Map to
markets: a volume spike is the rainstorm; elevated volume on following days is discharge; each
stock has an "attention-storage capacity" — its recession constant — set by the persistence of
disagreement in its holder base. **Hypothesis:** price dislocations in FAST-recession stocks
(attention drains quickly) are corrected by the reversal mechanism promptly — short-term
reversal profits should concentrate there — while SLOW-recession stocks keep trading on the
event (persistent disagreement), weakening reversal.

**Generation trace (provenance).** Source analogy: streamflow recession curves from hydrology
(Maillet 1905 exponential recession; catchment storage-discharge relations). Chosen by the
orchestrating LLM as a formalism with no known finance application, BEFORE any market data
from this project was viewed. No fresh-data statistics consulted. Provenance grade therefore
depends on the Phase D literature attack: at best P-ambiguous (the analogy came from model
weights; the specific signal was not knowingly retrieved from finance literature).

**Signal (exact formula).**
1. `volz` = z-score of log volume vs its rolling 63-day mean/std.
2. Spike days: `volz > 1.5`.
3. For each stock, over a rolling 252-day window, take all spike days with at least 5
   subsequent days; compute the mean of `volz` over days +1..+5 after each spike; the
   recession speed is `rec_speed = spike_day_volz_mean - post_spike_volz_mean` averaged
   across the window's spikes (larger = faster attention drain). Require >= 3 spikes, else NaN.
4. Base reversal: `rev = -ret5` (negative past 5-day return).
5. **Candidate signal: `rev * cs_rank_pct(rec_speed)`** — reversal scaled by the stock's
   cross-sectional recession-speed percentile (0..1).

**Universe:** S&P 500 equities. **Portfolio:** decile long-short, daily, t+2 execution.
**Predicted sign:** positive, and Gate-2 comparison: must OUTPERFORM the unconditioned
`-ret5` reversal (C004 control) on validation cost-adjusted Sharpe — the conditioning is the
novelty claim, not reversal itself.

**Tier ceiling:** T2/T3 (if no prior art found for per-stock volume-decay-speed as a
cross-sectional moderator of short-term reversal).
