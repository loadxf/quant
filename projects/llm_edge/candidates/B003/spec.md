# B003 — BASELINE for C003: spike-entry attention-episode reversal held 10 days

Identical direction and holding to C003 but entered AT the volume spike (the documented
timing — Gervais-Kaniel-Mingelgrin measure attention at the spike) instead of C003's
patch-abandonment crossing. C003's novelty claim requires beating this baseline on validation
cost-adjusted Sharpe. Not a novelty candidate itself (P-known/T1).

**Signal:** on days with `volz > 2`: `-(trailing 5-day return)`; else nothing. Median-tail
long-short among at least four triggered names (`QUANTILE = 0.5`, with strict upper/lower
tails and median ties left flat), held 10 days, t+2 execution, S&P 500 equities. This matches
the historical executable used as C003's thin-breadth baseline.
