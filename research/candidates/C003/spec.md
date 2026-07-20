# C003 — Marginal value theorem: patch-abandonment timing for attention episodes

**Mechanism (G3 cross-domain transfer).** Charnov's marginal value theorem (1976, foraging
ecology): a forager leaves a resource patch when the instantaneous intake rate falls below the
environment-wide average — not when the patch is exhausted. Map: active traders forage
attention-grabbing stocks; the "patch" is an attention episode (volume spike + price move).
**Hypothesis:** the informative moment is not the attention SPIKE (heavily documented) but the
ABANDONMENT — the day relative volume decays back below its pre-episode baseline. At that
crossing, the marginal trader has left, price support/pressure from the episode ends, and the
dislocation built during the episode partially reverts. Prior art nearby (must be beaten, and
distinguished in Phase D): high-volume return premium (Gervais-Kaniel-Mingelgrin — entry AT
the spike, opposite timing) and attention-reversal (Barber-Odean — no timing element).

**Generation trace (provenance).** Source analogy: marginal value theorem from behavioral
ecology. Chosen by the orchestrating LLM before viewing any market data from this project; no
fresh-data statistics consulted. Provenance at best P-ambiguous.

**Signal (exact formula).**
1. `volz` = z-score of log volume vs rolling 63-day stats.
2. Episode: any day with `volz > 2` within the past 10 trading days (days t-10..t-1).
3. Abandonment trigger at t: episode exists AND `volz(t) < 0` AND `volz(t-1) >= 0`
   (first crossing back below baseline).
4. Episode return: cumulative `ret` from the first `volz > 2` day of the episode through t-1.
5. **Candidate signal at trigger day t: `-(episode return)`; zero otherwise. Position held
   10 days** (rolling-mean overlap).
6. Gate-2 comparisons: must outperform (a) entry AT the spike day with the same -episode-return
   direction and holding, and (b) plain `-ret5` reversal — the timing is the novelty claim.

**Universe:** S&P 500 equities. **Portfolio:** decile long-short among nonzero-signal names
(tercile if breadth is thin), daily, t+2 execution. **Predicted sign:** positive.

**Tier ceiling:** T2/T3 (if no prior art found for baseline-recrossing timing of
attention-episode reversal).
