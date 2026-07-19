# Protocol Deviations / Refinements Log

Per protocol.md: any deviation from the pre-registered protocol must be logged here with
justification. Entries are append-only.

## D1 — G1 generation window narrowed to prevent generation/evaluation contamination

**Date:** 2026-07-19 (before any post-2023 data was accessed by any analysis — git-verifiable:
this commit precedes every candidate registration and every holdout-gate invocation).

**Issue found:** protocol.md section 8 describes G1 as mining "2024–2026" data for hypothesis
generation, while section 4 locks 2024-01-01 onward as the Gate-3 holdout. As written, a G1
candidate would be holdout-evaluated on the same window that generated it — a
generation/evaluation contamination the rest of the protocol is designed to prevent.

**Refinement (strictly more conservative):**
- G1 hypothesis generation may access ONLY the post-knowledge-cutoff slice
  **2026-02-01 → last available date** (~5.5 months). This is also the provenance window — the
  slice provably absent from model training data — so the narrowing *strengthens* the
  provenance claim rather than weakening it.
- Gate-3 holdout for G1-originated candidates is **2024-01-01 → 2026-01-31** (disjoint from
  the generation window, ~2.1 years, and untouched by generation).
- For G2/G3/G4 candidates (whose generation never touches post-2023 data), the full holdout
  2024-01-01 → end applies as pre-registered.
- Access to the G1 generation slice goes through `holdout_gate.authorize_g1_generation()`,
  which logs every access to `candidates/g1_access_log.json`; the registry entry of every G1
  candidate records `holdout_end: 2026-01-31`.

**Why this is not results-driven:** decided and committed before any candidate existed and
before any post-2023 market data had been loaded by analysis code.

## D2 — Loop-2 design refinement: low-turnover search space (pre-declared)

**Date:** 2026-07-19, after loop-1 gate results, BEFORE any loop-2 evaluation.

**Loop-1 evidence:** all 14 candidates failed Gate 1. Decomposition: reversal-family
candidates are gross-positive but die of turnover costs (e.g. C004: +0.68 gross, -0.81 net,
1.6x daily turnover); G1 post-cutoff-panel candidates are gross-negative (signal noise);
the only Gate-2 survivor (C010, net +0.57, t=1.41) is the lowest-turnover candidate (0.18x).

**Loop-2 plan (protocol section 9: concentrate on the mechanism that produced the best
survivors, pivot the rest):**
1. G2 search re-run with cost-aware slow-trading fitness: 5-day holding overlap in the
   fitness backtest (net SR at 10 bps as before). Fresh seed. Equity universe.
2. G2 search on the ETF cross-section (5 bps costs, no survivorship bias in the current ETF
   list, different data-generating process). 5-day holding.
3. Slow-horizon G3/G1 variants of the only gross-positive novel conditioning from loop 1:
   C013 = C001's volume-recession conditioning applied to monthly reversal, 21-day hold;
   C014 = sustained-volume premium (G1 volz_quintiles q4/q5 spread), 21-day hold, with the
   Gervais-Kaniel-Mingelgrin high-volume-premium prior art declared upfront.

**Multiple-testing accounting:** unchanged — every loop-2 evaluation (search fitness calls
included) appends to the trials ledger and inflates the DSR's N. No loop-1 result is
re-interpreted; C010 remains failed at Gate 1.
