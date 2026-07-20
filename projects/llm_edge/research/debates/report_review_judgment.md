# Judge rulings on the two-mandate report review

Reviews: `report_review_overclaim.md` (1 BLOCKING, 8 MATERIAL, 9 MINOR),
`report_review_underclaim.md` (0 BLOCKING, 6 MATERIAL, 4 MINOR). Rulings below; all
accepted fixes are applied in the final REPORT.md commit. Rule: the conclusion must follow
the evidence table in both directions.

## Overclaim objections

- **O1 (BLOCKING, review-already-happened header) — UPHELD.** The draft header asserted a
  completed review that had not yet occurred at commit time. Fixed: the final header states
  the review sequence factually with record filenames; the reviewed version is this commit.
- **O2 (dangling pre-registration hash) — UPHELD.** All references now cite in-branch
  `1761f72` (tree-identical to the previously cited dangling `617c69d`); the report now
  discloses that the branch was rebased (timestamps rewritten) and that the audit rests on
  commit ORDER and content, not timestamps.
- **O3 (1,932 "distinct" expressions) — UPHELD.** Now: 1,932 ledgered search evaluations,
  856 distinct parameterizations (interrupted-run repeats retained, inflating DSR's N).
- **O4 (8/11 vs 7/11 sectors) — UPHELD.** Panel shows 7/11; the error originated in C009's
  frozen spec and is now disclosed in the report as a generation-trace defect (the spec file
  itself is left unmodified as historical record).
- **O5 (unlogged universe deviation) — UPHELD.** Logged retrospectively as D4; report §6/§8
  note it and its direction (conservative for the headline negative).
- **O6 (verification-bottleneck causal overreach) — UPHELD IN PART.** The design cannot
  separate "verification is the bottleneck" from "generation ceiling at recombination"; the
  conclusion now presents both as jointly compatible readings and drops the causal "the
  reason is" phrasing. (Merged with underclaim O2, which pushed the opposite direction on
  §9.1 — the combined wording grades weights-alone creativity at the structure level only
  and against a human-normal combinational baseline.)
- **O7 (unscoped absence claims) — UPHELD.** Scope qualifiers restored everywhere.
- **O8 (C010 vacuous perturbation check) — UPHELD.** Report now says C010's ±25% check was
  vacuous (hardcoded windows; gate passed on the remaining checks) and that only C015 ran a
  real perturbation; framed as a harness-design lesson.
- **O9 (AlphaDev is RL, not LLM) — UPHELD.** AlphaDev reclassified as a non-LLM RL
  precedent; the LLM-proposer pattern claim now rests on FunSearch/AlphaEvolve only.
- **9 minors — ALL UPHELD** (N=1,998 at DSR time vs 2,000 final; 18 candidates; claim refs
  C15–C16; 62 = 35+27 curated; "25/25 confirmed after two quote corrections"; "near-identical
  term"; g3-verdict commit timing disclosed here: the verdict file was committed together
  with the report sections rather than before them; imprecise "eight days" removed in favor
  of the rebase disclosure; G1 range −2.82…−4.10).

## Underclaim objections

- **O1 (C002 nearest approach to T2) — UPHELD.** §7 now names C002 as the closest approach:
  the killing prior art is aggregate-level (Graziani JMP; plus HKS 2010 finding *no* TOM
  dependence cross-sectionally); the exact cross-sectional formulation was not found; T1
  stands via the near-neighbor clause of the frozen scale.
- **O2 (double standard on combinational creativity) — UPHELD** (merged with overclaim O6).
- **O3 (G1 provenance mechanism underweighted) — UPHELD.** Now a standalone paragraph in
  §9, scoped ("absent from our surveyed LLM-trading literature").
- **O4 (C015 self-audit buried) — UPHELD.** Now an explicit finding in §9.5.
- **O5 (timescale) — UPHELD IN PART.** Precise hours are not cleanly auditable post-rebase;
  the report states the compression honestly without a fake-precise number.
- **O6 (integrity-channels-empty unstated) — UPHELD.** New §9.5 paragraph enumerates the
  empty p-hacking channels, including the one exception (D4) found by this review itself.
- **4 minors — UPHELD** where not already covered.

## Net effect on the verdict

No ruling changes any tier, any gate outcome, or the headline negative. The fixes make the
report more accurate in both directions: weaker where it borrowed unearned precision or
causal certainty, stronger where it buried genuine positive findings.
