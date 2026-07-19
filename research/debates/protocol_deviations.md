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
