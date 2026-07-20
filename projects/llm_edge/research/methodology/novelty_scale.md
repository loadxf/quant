# Operational Definition of Novelty

**Status: FROZEN at pre-registration. This file must not be edited after the pre-registration
commit. All later phases cite this document by its commit hash.**

## Why this document exists

The question under test — *"can an LLM create a genuinely novel trading edge, or can it only
recombine what is already in its training data?"* — is unanswerable without an operational
definition of "novel." Vague novelty claims are unfalsifiable in both directions: an enthusiast
can call any recombination "new," and a skeptic can call any idea "implicit in the corpus."
This scale makes the question decidable *within a documented scope*, and its verdict wording is
constrained so the final report cannot overclaim.

## The tiered novelty scale

| Tier | Definition | Verification requirement |
|------|-----------|--------------------------|
| **T0** | Replication of a documented anomaly (momentum, short-term reversal, low-volatility, turn-of-month, ...) | Matches an entry in the prior-art database (`research/prior_art/factor_db.json`) |
| **T1** | Recombination or re-parameterization of documented ideas, where every component **and** the combination logic are documented somewhere findable | Adversarial search finds prior art for the combination or an obvious near-neighbor |
| **T2** | A concrete, testable hypothesis for which independent adversarial literature searches find **no documented prior art** — no academic paper, no practitioner write-up, no factor-database entry describing the same signal on the same asset class | Survives the Phase D literature attack (≥3 independent search angles). Verdict is always worded *"no prior art found within the documented search scope"* — never "proven novel" |
| **T3** | A T2 hypothesis that is **also empirically validated**: passes the full pre-registered statistical harness including the locked holdout, with Deflated Sharpe Ratio > 0.95 and pooled Newey–West \|t\| > 3 | Survives the Phase C gates *and* the Phase D statistical red team (independent re-implementation from the spec alone) |

## The orthogonal provenance grade

Tier answers "is it new to the literature?" Provenance answers "could it be regurgitation of
training data?" Every candidate receives both.

- **P-known** — the idea (or a near-neighbor) plausibly appears in pre-2026 text anywhere
  findable; the model could have memorized it.
- **P-derived** — the generation trace shows the hypothesis was driven by inputs provably
  external to the model weights: statistics computed from post-knowledge-cutoff market data
  (Feb 2026 onward), or selection by out-of-sample fitness rather than model priors. The trace
  (which mechanism, which specific input) is logged at generation time in the candidate's spec.
- **P-ambiguous** — provenance cannot be determined either way.

**The headline result of this project is the best (Tier, Provenance) pair achieved.**
"T3 / P-derived" is the strongest possible positive result. "Nothing above T1 / P-known
survived" is the strongest negative result. Both are publishable findings; the report is
pre-committed to stating whichever the evidence supports.

## The philosophical dispute, steelmanned in advance

**The case against LLM novelty.** An LLM's sampling distribution is a lossy compression of its
corpus; outputs are interpolations in that distribution. RLHF sharpens modes and reduces tail
diversity ("mode collapse"), and measured "creativity" of LLM text shows heavy n-gram overlap
with training corpora. On this view every candidate this project generates should die at T0/T1,
and any apparent T2 merely reflects gaps in our literature-search recall. This position must be
researched honestly in Phase A (topic A3) and, if the evidence supports it, stated as the
conclusion.

**The case for the possibility.** Human creativity is also largely recombination (Poincaré's
"useful combinations," Koestler's bisociation); the demand that novelty arise *ex nihilo* is a
standard no human inventor meets. The operative question is therefore not "can the weights
contain something new" (they cannot, by construction) but "can the **system** — LLM + tools +
external data — produce artifacts outside the training distribution?" FunSearch
(Romera-Paredes et al., *Nature* 2024: new lower bounds for the cap-set problem) and
AlphaEvolve (2025: improved 4×4 matrix-multiplication algorithms) are existence proofs in
mathematics that an LLM-proposer + ground-truth-evaluator loop can exceed the training corpus.
Whether *markets* — noisy, adversarial, and strip-mined by decades of factor research — permit
the same is an open empirical question, and this project's evaluator is out-of-sample market
data.

**The honest middle.** Any novelty achieved here may be attributable to the system rather than
"the LLM alone." That objection is conceded up front, not dodged: the final report answers the
two questions separately — (a) can the weights alone emit novelty, (b) can the LLM-as-scientist
system produce it — and treats the distinction itself as a finding. See risk R7 in
`protocol.md`.

## Wording discipline (binding on the final report)

1. T2+ verdicts must enumerate the searches performed and say "no prior art found in this
   scope." Nonexistence of prior art is never claimed as proven.
2. A candidate killed by prior art is reported with the specific prior art that killed it.
3. The conclusion of REPORT.md must be a function of the (Tier, Provenance) evidence table and
   nothing else — not of narrative appeal in either direction.
