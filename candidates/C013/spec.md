# C013 — Loop 2: volume-recession conditioning of MONTHLY reversal (slow C001)

**Generation trace (provenance).** Loop-2 refinement declared in deviation D2: C001's
hydrological recession-speed conditioning was the only novel conditioning that was
gross-positive in loop 1 (+0.76 gross vs control's +0.68) but died of 1.5x daily turnover.
This candidate applies the same cross-domain mechanism (catchment recession constants from
hydrology; see C001 spec for the full analogy and trace) to the monthly-reversal horizon with
a 21-day hold — a turnover regime where loop-1 evidence says costs are survivable. Mechanism
unchanged; horizon moved. Provenance: same as C001 (P-ambiguous pending Phase D attack), with
the loop-2 horizon choice being data-informed (documented here and in D2, and paid for in the
ledger).

**Hypothesis.** Mispricings in fast-attention-drain (fast volume-recession) stocks correct
within the month; monthly reversal should concentrate there.

**Signal (exact formula).** `rev21 = -ret21`; `rec_speed` exactly as C001 (spike volz > 1.5,
mean 5-day post-spike decay, 252-day rolling mean, >= 3 spikes).
**Candidate signal: `rev21 * cs_rank_pct(rec_speed)`.** Decile long-short, held 21 days,
t+2 execution, S&P 500 equities.

**Predicted sign:** positive, and must OUTPERFORM plain `-ret21` (C012 results, same hold)
on validation cost-adjusted Sharpe — the conditioning is the claim.

**Tier ceiling:** T2/T3 (same novelty claim as C001, slow horizon).
