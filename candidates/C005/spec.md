# C005 — CONTROL (G4): low-volume-conditioned reversal (inverted conditioning)

**Purpose.** G4 anti-consensus control: the literature mostly conditions reversal on HIGH
volume (Campbell-Grossman-Wang 1993: returns accompanied by high volume revert more;
Cooper 1999). This control deliberately INVERTS the documented conditioning: trade `-ret5`
reversal only in the LOWEST-volume-shock names. If inversion of a documented effect performs
comparably to the G3 "novel" mechanisms, recombination/perturbation explains their
performance and their novelty claim is weakened.

**Generation trace.** G4 control group — mechanical perturbation of documented prior art
(P-known, T1 ceiling by construction).

**Signal:** `-ret5 * (1 - cs_rank_pct(volz))` — reversal scaled toward low-volume names.
Decile long-short, held 1 day, t+2 execution, S&P 500 equities.

**Predicted sign:** positive (weaker than C004 if the documented high-volume conditioning is
right; comparable if conditioning direction is unstable).
