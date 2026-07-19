# C006 — CONTROL (G4): intraday-component reversal (documented decomposition)

**Purpose.** G4 documented-recombination control: the overnight/intraday decomposition is
established literature (Lou-Polk-Skouras 2019: overnight returns persist, intraday returns
revert). Reversing only the intraday component of the past week's return is a direct
application of a documented effect.

**Generation trace.** G4 control group (P-known, T0/T1 by construction).

**Signal:** `-(sum over past 5 days of intraday return)` where intraday = close/open - 1.
Decile long-short, held 1 day, t+2 execution, S&P 500 equities.

**Predicted sign:** positive, plausibly stronger than C004 (consistent with the documented
decomposition).
