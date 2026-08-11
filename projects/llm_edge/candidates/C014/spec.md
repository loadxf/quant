# C014 — Loop 2: sustained-volume premium at monthly hold (G1-slow)

**Generation trace (provenance).** From the post-cutoff G1 panel (`report/g1_panels.json`):
`volz_quintiles` next-day returns rise monotonically-ish toward high volume (q4 +14.9, q5
+15.6 bps vs q1-q3 5-10 bps). Loop-1 taught that daily-horizon exploitation dies of costs
(D2); this candidate tests the pattern at a 21-day hold.

**Retrospective artifact note (2026-08-10).** Those are the historical values shown during
generation. The corrected, fixed-window artifact (same 115 sessions, current sealed cache)
reports q4 **+14.4** and q5 **+15.6** bps and binds its manifest/universe hashes. This small
input-cleaning change does not retroactively replace the historical generation trace.

**Declared prior art (upfront):** the high-volume return premium is DOCUMENTED
(Gervais-Kaniel-Mingelgrin 2001: event-style, 1-week to 20-day horizons, NYSE). This
candidate is therefore expected to grade T0/T1 — it is registered primarily as a G1
mechanism data point (does a post-cutoff panel cell that matches documented prior art
validate backward, where the loop-1 noise cells did not?). If it validates, that says the
G1 mechanism can recover REAL (but known) effects from 115 post-cutoff days, sharpening the
interpretation of the loop-1 G1 failures as noise-mining rather than mechanism failure.

**Signal (exact formula).** `signal = volz` (rolling 63-day log-volume z-score with the
standard 63-observation warm-up), smoothed with `rolling(5, min_periods=3).mean()`. Decile
long-short, held 21 days, t+2 execution, S&P 500 equities.

**Predicted sign:** positive. **Tier ceiling:** T0/T1 by declared prior art.
