# C002 — Phase-response curve: calendar-phase-dependent shock recovery

**Mechanism (G3 cross-domain transfer).** In circadian biology, the phase-response curve
(PRC) says the SAME light pulse shifts an organism's clock differently depending on the phase
at which it arrives. Map to markets: the monthly contribution/payroll flow cycle (the
documented driver of turn-of-month effects) is the market's clock. **Hypothesis:** an
idiosyncratic negative price shock arriving during the high-flow phase (turn-of-month window)
meets mechanical buy pressure and over-reverts; the same shock mid-month reverts less. The
tradeable object is the INTERACTION shock-timing x calendar-phase — not the well-known
level effect of TOM days themselves.

**Generation trace (provenance).** Source analogy: phase-response curves from chronobiology
(Johnson 1999 PRC atlas tradition). Chosen by the orchestrating LLM before viewing any market
data from this project; no fresh-data statistics consulted. The TOM flow mechanism itself is
documented finance literature (Ogden 1990); the PRC interaction framing is the candidate
novelty. Provenance at best P-ambiguous.

**Signal (exact formula).**
1. Shock: `shock = ret1` on the day it occurs (day t).
2. Calendar phase: `tom = 1` if t is within the last 2 or first 3 trading days of a calendar
   month, else 0.
3. **Candidate signal at t: `-(shock) * tom` with the position held 5 days** (rolling-mean
   overlap), i.e. only shocks born in the TOM window are traded, in the reversal direction.
4. Gate-2 comparison: must outperform the same reversal WITHOUT the tom gate (i.e.,
   `-ret1` held 5 days) on validation cost-adjusted Sharpe.

**Universe:** S&P 500 equities. **Portfolio:** decile long-short among nonzero-signal names,
daily, t+2 execution. **Predicted sign:** positive, and interaction must beat the ungated base.

**Tier ceiling:** T2/T3 (if no prior art found for TOM-phase-conditioned reversal of
idiosyncratic shocks).
