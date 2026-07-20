---
role: reviewer 1 of 2 (mandate: prove REPORT.md overclaims — novelty, rigor, provenance, significance)
protocol: risk R9, pre-registered two-mandate adversarial review
date: 2026-07-20
verified against: git history of branch claude/llm-novelty-trading-research-afrv74 (HEAD dcf0d8f),
  candidates/*/results_validation.json, candidates/trials_ledger.csv, report/loop3_diagnostics.json,
  report/g1_panels.json, candidates/g1_access_log.json, research/prior_art/*.md, factor_db.json,
  research/debates/*, research/methodology/protocol.md, src/quantlab/{gates,grammar}.py, data/universe.json
---

# Overclaim review of REPORT.md

Method note: every objection below cites the exact sentence and the repository artifact that
contradicts or fails to support it. Claims I attacked and could NOT break are listed at the end;
a motivated reviewer's failures are part of the record.

---

## BLOCKING

### O1. The report claims, in the past tense, an adversarial review of the conclusion that had not happened when the claim was committed

- **Quoted (header):** "the conclusion was reviewed by two opposite-mandate reviewers."
- **Quoted (S8, R9):** "The conclusion below was drafted only after the evidence table was
  complete and was attacked by two reviewers with opposite mandates ('prove it overclaims
  novelty' / 'prove it underclaims out of performative humility'); the debate record is in
  `research/debates/`."
- **Evidence:** At the commit that introduced these sentences (`dcf0d8f`, 2026-07-20 01:35:19,
  the branch HEAD), `research/debates/` contains no report-review record of any kind
  (contents: factor_zoo_round1/2, g3_novelty_verdicts, llm_creativity_round1,
  llm_in_trading_round1/2, multiple_testing_round1, protocol_deviations,
  strategy_families_round1/2/3). The R9 review is happening *now* — this document is the first
  half of it. The report asserts a completed integrity process and points to a record that did
  not exist.
- **Severity:** BLOCKING. The report's anti-sycophancy story leans on this exact device; stating
  it as completed before it occurred is the same class of error the report was designed to avoid.
- **Fix:** Rewrite in the future/present tense ("is being reviewed; records will be committed to
  `research/debates/report_review_*.md`"), or finalize the report only after both reviews and a
  judge resolution are committed, then cite the actual files.

---

## MATERIAL

### O2. The pre-registration commit hash cited twice in the report is unreachable from any branch; the early history was rewritten

- **Quoted (header):** "Methodology pre-registered 2026-07-19 (commit `617c69d`, before any data
  analysis existed — auditable in this branch's git history)." Also S2: "frozen before any
  strategy work (`research/methodology/novelty_scale.md`, commit `617c69d`)."
- **Evidence:** `git branch -a --contains 617c69d` returns nothing — `617c69d` exists only as a
  dangling local object; it is in NO branch's history and will not survive a clone or gc. The
  reachable pre-registration commit is `1761f72` (2026-07-19 22:53:32). The tree diff
  `617c69d..1761f72` is empty (content identical), so the substance survives — but the hash the
  report tells auditors to check fails the exact audit it invites. Additionally, the first six
  branch commits (`1761f72`..`01e4276`) carry committer timestamps within a 2-second span
  (22:53:32-22:53:34), the signature of a history rewrite: commit ORDER is intact, but the
  original timestamps that the pre-registration commit message calls "the audit anchor" were
  rewritten.
- **Severity:** MATERIAL. Provenance/auditability overclaim at the exact point where the report
  stakes its credibility. (Order-based pre-registration does still hold — see "attacks that
  failed" below.)
- **Fix:** Cite `1761f72` (the reachable commit), note the rebase explicitly, and rest the
  pre-registration claim on commit order rather than timestamps.

### O3. "1,932 distinct ledgered expressions" — the ledger shows 1,932 evaluations of at most 856 distinct expressions

- **Quoted (S5):** "Three searches (1-day hold; 5-day hold; ETF universe) evaluated **1,932
  distinct ledgered expressions**."
- **Evidence:** `candidates/trials_ledger.csv`: 1,932 rows with `g2_*` candidate ids, but only
  **856 distinct `params_hash` values** among them. The word "distinct" inflates the search's
  hypothesis coverage by ~2.3x. (S6's phrasing "all 1,932 search evaluations" is the correct
  one; the DSR uses row count, which is fine and conservative.)
- **Severity:** MATERIAL — overstates the breadth of the G2 exploration, one of the two
  headline generation mechanisms.
- **Fix:** "evaluated 1,932 ledgered expression evaluations (856 distinct expressions)."

### O4. The G1 sector lead-lag statistic is misreported: 7/11 sectors, not 8/11 — and the error originates in the very "generation trace" offered as provenance proof

- **Quoted (S5):** "a negative sector-ETF lead-lag (8/11 sectors)."
- **Evidence:** `report/g1_panels.json` `sector_etf_lead_lag`: negative next-day correlations in
  exactly **7** of 11 sectors (XLF -0.089, XLI -0.149, XLP -0.059, XLRE -0.076, XLU -0.053,
  XLV -0.072, XLY -0.147); positive: XLB +0.018, XLC +0.020, XLE +0.078, XLK +0.001. The same
  "8 of 11" error appears in `candidates/C009/spec.md` — the generation trace that S7 grades
  "P-derived (trace verifiable)". A trace that misreads the committed artifact it cites is
  weaker evidence of "the system demonstrably reasoned from inputs" (S9.2) than the report
  implies: the verifiable part is data access, not faithful reading.
- **Severity:** MATERIAL — a wrong number in the report AND a demonstrated gap between "trace
  logged" and "trace correct" in the provenance mechanism the report showcases.
- **Fix:** Correct to 7/11 in S5; add a sentence in S7 or R-limitations noting the trace itself
  contained a misreading of the panel (which strengthens, not weakens, the honesty of the report).

### O5. The harness deviates from the pre-registered universe, and the deviation is not logged

- **Quoted (S6):** "Yahoo daily OHLCV for 503 current S&P constituents + 71 ETFs"; and (S9.4)
  "What it does establish, with pre-registered rigor..."
- **Evidence:** `research/methodology/protocol.md` S3 (frozen at pre-registration) specifies
  "current S&P 500 constituents **with >= 15 years of history (~400 names)** plus **~60** liquid
  ETFs." `data/universe.json` contains **503** equities with no minimum-history filter (includes
  ABNB 2020-, COIN 2021-, KVUE 2023-) and **71** ETFs; no history filter exists in
  `src/quantlab/universe.py`/`data.py`; `research/debates/protocol_deviations.md` logs only
  D1-D3 — nothing about the universe. Protocol: "Any deviation must be logged." Dropping the
  >=15-year filter materially worsens the R2 survivorship exposure the report then diagnoses in
  its own best candidate (recent high-fliers with short histories are precisely the
  survivorship-inflated names).
- **Severity:** MATERIAL — an unlogged protocol deviation directly contradicts the "every
  deviation logged" rigor claim, in a dimension (survivorship) central to the loop-3 verdict.
- **Fix:** Log it as D0/D4 with justification, and note in S6 and R2 that the universe was
  broader (and more survivorship-exposed) than pre-registered.

### O6. The bolded causal conclusion — "the bottleneck... is verification" — is not supported over the report's own alternative: generation never produced structural novelty

- **Quoted (S9.3):** "**The bottleneck of novelty is not generation; it is verification.**"
  Echoed in the one-sentence verdict: "...the reason is not that the model can only repeat its
  training data, but that in markets the scarce resource is verification..." and S9.4: "no failure
  of idea generation was ever the binding constraint."
- **Evidence:** The report's own S7 headline ("nothing above T1. Zero candidates reached T2")
  and S9.1 ("the *signal structures* they mapped onto were already in the literature...
  combinational creativity with genuine surface novelty and **no structural novelty**") are
  direct evidence that generation DID fail — every hypothesis with structure was a documented
  near-neighbor. On this record, "generation only reaches recombinations of documented
  structure" explains the outcome at least as well as "verification is the scarce resource";
  the experiment has no design that separates the two (no arm supplying externally-verified
  novel hypotheses to the same evaluator, no human control — conceded in S9.4). A single-arena,
  single-data-source negative with 18 gated candidates cannot identify *which* constraint binds,
  yet the verdict sentence asserts the mechanism ("the reason is...") as a finding.
- **Severity:** MATERIAL — the report's most-quoted line claims causal identification the
  evidence table does not license, and it contradicts S9.1 three paragraphs earlier.
- **Fix:** Downgrade to stated-as-interpretation: "consistent with the verification-bottleneck
  reading suggested by the FunSearch contrast; the design cannot distinguish it from a
  generation ceiling at recombination, and S9.1's structural-novelty result supports the
  latter." Strike "the reason is" from the one-sentence verdict.

### O7. G3 absence claims are stated unscoped, violating the report's own frozen wording discipline

- **Quoted (S7, C001/C013 row):** "the hydrology framing itself has no finance footprint."
  (S9.1): "the *framings* (streamflow recession, phase-response curves, foraging theory) have
  no finance footprint."
- **Evidence:** The frozen scale (S2 of the report itself) requires absence claims to be
  "always 'none found in documented scope', never 'proven novel'", and R6 repeats it. The
  underlying verdict file (`research/debates/g3_novelty_verdicts.md`) is disciplined: "the
  source-domain formalism... has **no finance application findable in this scope**," with an
  explicit scope caveat that SSRN full texts were unreachable. The report drops the scoping in
  both S7 and S9.1, converting a scoped search result into an unscoped fact. (S5's "no known
  finance footprint" is acceptable; S7/S9.1 are not.)
- **Severity:** MATERIAL — this is the precise wording failure the protocol pre-registered
  against, applied to the report's "surface novelty" narrative, which is the strongest
  pro-novelty residue the report keeps.
- **Fix:** "...has no finance footprint *found in our documented search scope*" in both places.

### O8. C010's Gate-2 pass silently skipped the pre-registered perturbation test

- **Quoted (S6):** "Gate 2 (robustness): positive in both validation halves, both volatility
  regimes, **+/-25% parameter perturbations**, and at 25 bps costs" ... "G2 search winners
  (C010-C012) | +0.57 (C010, t=1.41) | the only Gate-2 survivor."
- **Evidence:** Protocol Gate 2 requires surviving "+/-25% perturbation of **every window
  parameter**." C010's windows (10 and 63) are hardcoded inside its expression
  (`candidates/C010/signal.py`; spec formula `roll_mean(roll_std(rng,10),63)`), so `gates.py`
  found no perturbable module attribute and passed the gate vacuously —
  `candidates/C010/results_validation.json`: `"perturbations": {}` with `"pass": true` via the
  `else True` branch (gates.py line 181). A pre-registered robustness check was never applied
  to the loop-1 survivor the report headlines. (C015's WINDOW was perturbed — 0.54/0.61 — so
  the loop-2 near-miss is unaffected; hence MATERIAL, not BLOCKING.)
- **Severity:** MATERIAL — rigor overclaim: the stated gate and the executed gate differ for
  exactly the candidate class (G2 expressions) most prone to window overfitting.
- **Fix:** Disclose in S6 that expression-embedded windows were not perturbed for loop-1 G2
  winners; ideally run the +/-25% window variants for C010 and report them.

### O9. AlphaDev is swept into the "LLM proposer + evaluator" pattern; the project's own prior-art file says it is not an LLM system

- **Quoted (S3.2):** "FunSearch, AlphaEvolve, and AlphaDev produced verified,
  previously-nonexistent artifacts. The pattern is consistent: the **LLM is a proposer** over a
  well-shaped hypothesis space..." (also S1 lists AlphaDev among the existence proofs).
- **Evidence:** `research/prior_art/llm_creativity.md` C8: AlphaDev "used **deep RL (an
  AlphaZero-style single-player 'assembly game')**" — no LLM proposer. The report's verified
  source file establishes two LLM existence proofs (FunSearch, AlphaEvolve), not three; folding
  AlphaDev into "the pattern is consistent: the LLM is a proposer" overstates the evidence base
  for the report's central "existence proofs stand" move (S9.2), which borrows the trio's
  credibility for the LLM-specific claim.
- **Severity:** MATERIAL — misattribution inside the argument that carries S9.2's "that part of
  the skeptic's argument fails."
- **Fix:** Present AlphaDev as an evaluator-in-the-loop RL result supporting the
  *external-evaluator* pattern, not the LLM-proposer pattern; keep the LLM claim on
  FunSearch/AlphaEvolve alone.

---

## MINOR

### O10. DSR reported "against the full ledger (N = 2,000 trials)" — the artifact says N = 1,998
`report/loop3_diagnostics.json`: `"n_trials": 1998` (the two `diag_rangevol_*` rows written
during loop 3 are not in the computation). No effect on the conclusion (DSR ~ 2.3e-46), but
the stated N does not match the recorded arithmetic the report itself points to ("the
arithmetic is in report/loop3_diagnostics.json"). Fix: "N = 1,998 of the final 2,000-row
ledger."

### O11. "19 candidates over two generation loops" (S9) — there are 18
C001-C016 + B002 + B003 = 18 directories; the Reality Check used `n_candidates: 18`; D3 says
"18 gated candidates over two loops"; S6 says loop 1 had 14 and loop 2 added 4. Fix: 18.

### O12. Wrong claim IDs for the Creativity Index (S1)
"verified in `research/prior_art/llm_creativity.md` C13-C14" — the ~66%/~30% numbers are
**C15-C16**; C13-C14 are Kambhampati. Fix citation.

### O13. factor_db arithmetic reads as 331 + 62 + 27 = 420; the DB is 393
S4: "393 records — all 331 Chen-Zimmermann... plus 62 curated records covering strategy
families... and 27 method-level records." `factor_db.json` meta: n_cz 331 + n_curated 62 =
393; the 27 `x_method_*` records are a **subset** of the 62 (35 family + 27 method). Fix:
"62 curated records (35 strategy-family + 27 method-level)."

### O14. "25/25 claims confirmed by an independent adversarial pass" glosses the record
The pass's own revision log (llm_creativity.md) reports two evidence quotes corrected: C3's
supporting quote had been taken from the blog and attached to a different claim (the capacity
bound), and C24's "quoted" definition was a re-ordered paraphrase inside quotation marks.
"25/25 confirmed; 0 wrong, 0 overstated" is the file's own summary of the *claims*, but the
report's phrasing implies a cleaner pass than occurred. Auditability context: the file was
created 01:16:31 and reached "agreed" 01:25:46 — the entire 25-source verification window in
git is ~9 minutes, after all empirical work. Fix: "confirmed after two quote-fidelity
corrections (see revision log)."

### O15. S7 hardens the WQ101 match beyond the verdict file's wording
S7: Alpha#40 "contains the **same** `rank(stddev(high,.))` subexpression at the same horizon."
`candidates/C015/novelty_verdict.md` says "near-identical term": Alpha#40 is
`rank(stddev(high, 10))`; the candidate is `rank(stddev((high-low)/close, 63))` — different
input series, different window; "same horizon" refers to holding period. Overstates in the
kill direction (does not rescue novelty — items 1-2 of the verdict carry the kill), but is
inaccurate. Fix: "a near-identical rolling-std-of-price-extreme term."

### O16. The G3 attack record is not auditable as preceding the report
Header: "Sections 7 and 9 were written last, after adversarial prior-art attacks completed."
`research/debates/g3_novelty_verdicts.md` was added **in the same commit** as the completed
report (`dcf0d8f`), so for the G3 families the attack record and the report are simultaneous
in history (C015's verdict, `4c758d3` 01:30:27, does precede by 5 minutes). Not evidence of
fabrication; it is an auditability gap in a report that leans on commit ordering. Fix: commit
verdict records before the report sections that cite them (as was done for C015).

### O17. "eight days" (S9.4) is unsupported by the repository's own audit trail
"a human quant restricted to this data, these tools, and eight days..." Repo evidence: initial
commit 2026-07-18 21:06 -0600; all experimental commits from pre-registration to finished
report span 2026-07-19 22:53 -> 2026-07-20 01:35 UTC (~2.7 hours; ~28.5 hours end to end).
Work may have occurred outside git, but the report elsewhere offers git history as the audit
anchor; an unauditable 8-day figure inflates the effort baseline of the human-comparison
counterfactual. Fix: state the auditable duration or the basis for the figure.

### O18. G1 outcome range slightly misstated (S6 table)
"G1 post-cutoff hypotheses (C007-C009): -2.93 ... -4.10" — actual net validation SRs: C007
-2.93, **C008 -2.82**, C009 -4.10 (results_validation.json). Correct range -2.82 ... -4.10.
Trivially overstates the failure. Fix the bound.

---

## Attacks attempted that did NOT land (for the record)

- **Commit order of pre-registration:** despite the rewrite (O2), `1761f72` (methodology,
  content-identical to 617c69d) precedes the harness, all specs, all results in branch order;
  D1 precedes the first G1 access (22:53:33 < 22:54:39); D2 precedes loop-2 evaluations; D3
  (01:22:43) precedes the loop-3 diagnostic ledger rows (01:23:41) and diagnostics commit
  (01:24:19). The pre-registration story survives on ordering.
- **C015's "spec pre-declared the survivorship suspicion before the gates":** verified —
  spec.md committed in `91baeb6` (01:20:25) with the DECLARED SUSPICION paragraph;
  results_validation.json arrived in `603d9e2` (01:22:43). The S9.5 claim is genuine.
- **Loop-3 numbers:** RC p = 0.171 (n=18), DSR ~ 2.3e-46, long-leg +0.73 / short-leg -0.61,
  ETF construct 0.47 (t 1.15), C015 0.66/1.63, C010 0.57/1.41/0.18x turnover, C004 gross
  +0.68 / net -0.81 / 1.6x turnover — all match the JSON artifacts.
- **Prior-art numbers:** HLZ 316 and t>3; HXZ 65% of 452; McLean-Pontiff 26%/58%; CLZ 29,000
  ratios; FunSearch 512 vs 496 and 2.2180->2.2202 ("largest improvement in ~20 years" is the
  paper's own claim); AlphaEvolve 48 vs Strassen 49 (complex-valued caveat present in both
  file and report S1); Creativity Index 66.2%/30.1%; Si-Yang-Hashimoto 49 experts, p<0.05;
  execution study ~103 h — all consistent with research/prior_art/*.md, which are themselves
  quote-anchored.
- **Grammar spec:** 8 terminals, 13 operators (4 unary + 6 rolling + 3 binary), depth <= 5 —
  matches `src/quantlab/grammar.py` exactly.
- **Ledger discipline:** 2,000 rows, append-only timestamps monotone, interrupted-run rows
  retained (matches R4/D2-addendum), all 18 gated candidates present.
- **"The holdout was never fired":** no `holdout_results.json` exists anywhere under
  `candidates/`; holdout-gate tests present. Confirmed.

## Summary count

- BLOCKING: 1 (O1)
- MATERIAL: 8 (O2-O9)
- MINOR: 9 (O10-O18)

The report's empirical core (gates, ledger, loop-3 diagnostics, unfired holdout, T1 verdicts)
survives adversarial audit. The overclaims concentrate in (a) process claims stated as
completed or auditable when they are not (O1, O2, O16), (b) inflation at the margins of the
generation/provenance story (O3, O4, O5, O8), and (c) a conclusion sentence that asserts
causal identification the design cannot deliver and its own S9.1 contradicts (O6), plus
wording-discipline slips the protocol explicitly banned (O7).
