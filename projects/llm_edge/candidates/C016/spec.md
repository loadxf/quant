# C016 — Volume-rank-extremeness skew, ETF cross-section, 5-day hold (G2 loop-2)

**Generation trace (provenance).** Best non-reversal expression of the loop-2 etf5
evolutionary search (seed 20260721, fitness = net train SR at 5 bps, 5-day hold, tercile-ish
quintile 0.2 portfolios): **`(roll_skew (abs_ (cs_rank volz)) 63)`** — per ETF, the 63-day
skewness of the absolute cross-sectional volume-z percentile (distance of the ETF's volume
percentile from the cross-sectional median). Train SR net ≈ 0.39. Selection by data fitness
under the model-chosen grammar; P-derived at the selection level.

**Interpretation (post-hoc, to be tested not assumed).** High values mark ETFs whose volume
percentile is usually near the middle but occasionally spikes to an extreme — episodic
attention assets; the signal is long those vs ETFs with chronically extreme volume ranks.
This is an opaque mined expression of exactly the stereotyped form the LLM-alpha-factory
literature produces (see research/prior_art/llm_in_trading.md); it is gated as the ETF-universe
representative and an interpretability test case for Phase D.

**Signal (exact formula).** `volz` = 63-day rolling z-score of log volume;
`signal = |cs_rank_pct(volz) - 0.5|` rolled through a 63-day skew, per the grammar's
cs_rank (which centers at 0). Quintile-0.2 long-short, 5-day hold, t+2 execution, 71-ETF
universe, 5 bps.

**Predicted sign:** positive (as selected). **Tier ceiling:** method T1; signal T2 only if
no prior art and it survives all gates + Phase D.
