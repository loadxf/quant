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
  **2026-02-01 → 2026-07-17** (the last available date at generation, ~5.5 months). This is
  the immutable provenance window — the
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

## D2 addendum — loop-2 search made restart-resilient (infrastructure, pre-results)

The execution environment repeatedly restarted mid-search, killing loop-2 runs. Changes,
made before any loop-2 variant completed: (a) evolutionary search checkpoints per
generation and resumes deterministically (per-generation RNG streams; cached fitness
replays without new ledger rows); (b) loop-2 search-FITNESS economy: population 100 x 6
generations; equities5 fitness computed on the 2010-2018 train subwindow and a
deterministic stride-sampled 252-name subuniverse. Gate evaluations are unchanged (full
universe, full periods). Interrupted-run ledger rows are retained, overcounting N in the
DSR's disfavor.

## D3 — Loop 3 declared as DIAGNOSTIC loop; holdout stays sealed (pre-declared)

**Date:** 2026-07-20, after loop-2 gate results, before any loop-3 computation.

**Loop-2 evidence:** C013 val SR +0.10, C014 -0.27, C016 +0.22 (all Gate-1 fail); C015
(range-volatility family, convergently found by both independent searches) val SR +0.66,
t=1.63 — passes all Gate-2 robustness checks but fails Gate 1's |t|>2, repeating C010's
profile. 18 gated candidates over two loops: zero Gate-1 passes.

**Loop-3 plan:** generation is STOPPED (a third generation round would select for flukes —
pre-declared risk R8). Loop 3 is diagnostics for the report:
1. The pre-registered family-wide Reality Check (protocol §6) on all candidates'
   validation net returns.
2. Deflated Sharpe Ratio of the best candidate (C015) with the FULL ledger N — the
   multiple-testing arithmetic the report must show.
3. Survivorship autopsy of the range-volatility family: long-leg vs short-leg return
   decomposition, the same construct on the ETF universe (historically described as having
   no equity-style membership deletion; final review clarifies that a current surviving fund
   list can still have fund-closure bias), and sub-period stability. Purpose: test the
   declared suspicion in C015's spec.
4. Phase D prior-art attack on the range-vol family (diagnostic, NOT promotion — the
   family failed Gate 1 and remains failed regardless of the attack's outcome).

**Holdout:** remains SEALED. No candidate met the pre-registered Gate-1+2 bar, so no
holdout shot is fired in this experiment. The one-shot design's integrity is preserved:
an unfired holdout is itself a reportable result.

## D4 — RETROSPECTIVE: universe broader than pre-registered (found by adversarial review)

**Date logged:** 2026-07-20, during the two-mandate report review (overclaim objection O5).

**Deviation:** protocol.md section 3 pre-registered "current S&P 500 constituents with >= 15
years of history (~400 names)"; the harness as built used ALL 503 current constituents with
no history filter (recent listings like ABNB/COIN included) plus 71 ETFs (vs "~60"). This
was an implementation oversight, never intentional, and was NOT logged when it happened —
it was caught by the project's own adversarial review of the final report.

**Effect on results:** worsens the survivorship/recent-listing exposure that the loop-3
autopsy identified — i.e., it biases TOWARD finding spurious positive candidates, and the
experiment still found none that passed the gates. The negative headline result is therefore
conservative with respect to this deviation; the C015 survivorship kill is strengthened.

## D5 — RETROSPECTIVE: final implementation-integrity audit invalidated old exact metrics

**Date logged:** 2026-08-10, after the original loop cap and validation results had been
observed, during a full-codebase adversarial audit.

The audit found implementation deviations that cannot be repaired retroactively by rerunning
the code after validation has been seen:

- Original G2 runs for the default equity and ETF variants loaded all available history
  through 2018 rather than enforcing the registered 2005 train start. The original ledger's
  roughly 12,328 observations for affected fitness calls is direct evidence; a 2005–2018
  daily window has only about 3,500 sessions. Selection provenance for the affected G2
  winners (including C010–C012 and the ETF search) is therefore not the pre-registered
  experiment. The driver now binds the train start, but no rerun is described as the
  original search.
- The backtester removed flat calendar days between sparse positions before annualizing
  Sharpe. That materially mis-scored timing strategies, especially C002. It now retains the
  continuous post-formation daily return path and charges terminal liquidation turnover.
- Gate-1 subperiod stability included data before 2005. It is now restricted to the fixed
  train-plus-validation window. Gate 3 likewise now excludes pre-2005 data from its pooled
  statistic.
- Candidate-specific registered Gate-2 comparisons and correlation classifications were not
  executed by the original generic harness. They are now explicit checks, but the old Gate-2
  labels were incomplete. The original four-point cost sweep was also incomplete and is now
  fully recorded at 0, 5, 10, and 25 bps.
- C003 used a median split rather than its stated decile/tercile breadth rule. Its historical
  episode loop also started at `k=2`, excluded a prior-day spike entirely, and omitted the
  spike-day return from every episode sum. The corrected handler implements the specified
  inclusive earliest-spike-through-t-1 return and breadth-dependent tails. C007's written
  3-day formula contradicted its expanded 2-period formula. The executable rules and
  specifications are now unambiguous; the old evaluations are not called exact-spec tests.
- C002's historical executable selected month edges with generic Monday-Friday business days,
  so NYSE holidays could displace the true first/last trading sessions. The corrected handler
  uses an explicit NYSE holiday/exception calendar, including the Saturday New-Year rule, and
  is regression-tested at holiday month ends. This is another forward exact-signal correction,
  not a retroactive repair of the original evaluation.
- The gate driver backtested the full pre-2005 history before slicing its reported statistics,
  so irrelevant early data defects could abort a registered-window replay and its ledger row
  did not describe the registered horizon. The hardened engine preserves pre-window signal
  warm-up and position state but evaluates, audits missing held returns, and ledgers only from
  the registered 2005 start.
- Sector/macro signals could rank current constituents before their listings because the
  external signal was finite while the stock price was absent (for example ABNB in C009's
  2005 cross-section). Quantile eligibility is now masked by same-date observed price. This
  uses no future availability; a missing later return on an actually held asset remains a
  fail-closed data error.
- The family Reality Check was described as maximum Sharpe but implemented as maximum mean
  performance. The implementation now matches the registered maximum-Sharpe statistic.
- The historical restart mechanism trusted cached checkpoint fitness without new ledger
  rows. Hardened recovery no longer trusts editable checkpoint expressions or scores; it
  validates the bound run identity, then deterministically replays and re-ledgers the search
  from generation zero. This is crash-safe but deliberately not a fast incremental resume.
- Validation cost, perturbation, comparison, and diagnostic attempts were labeled as
  validation trials in the ledger, but the stored Sharpe and observation count covered the
  combined 2005-2023 train-plus-validation output. A future holdout call would have had the
  same pooled-history labeling error. The inspected Gate statistics were sliced correctly,
  but the ledger dispersion was not a faithful distribution of those inspected statistics.
  The engine now binds a separate ledger scoring window into every parameter hash and records
  the exact inspected validation or holdout slice. Historical rows remain append-only and are
  not rewritten; the final report treats DSR based on the mixed historical ledger as
  unavailable rather than presenting it as a calibrated probability.

Consequently, the previously tracked validation JSON, family return parquet, diagnostics,
and exact numeric claims are superseded. A hardened full-family replay is an engineering
audit of the corrected system, not a retroactive restoration of pre-registration. The
holdout remained unopened, and this retrospective discovery does not authorize another
generation loop or a post-hoc holdout attempt.

## D6 — RETROSPECTIVE: G1 lag-response cells were labeled one session too recent

**Date logged:** 2026-08-10, during the same final implementation-integrity audit.

The original G1 panel paired `ret1.shift(k)` with the next-session response while calling it
lag `k`. At close t, the most recent completed return is `ret1[t]`, so lag 1 requires no
shift and lag k requires `shift(k-1)`. The day-of-week and dispersion lag-1 tables had the
same extra-session gap. Consequently C007's quoted `lag_7 = -0.056` generator statistic was
the now-corrected lag-8 condition, not the stated lag 7. During the audit, one intermediate
artifact was mistakenly recomputed through 2026-08-07; that access remains honestly logged,
but it is not generation provenance. The G1 capability and corrected artifact are now pinned
to the original 2026-07-17 end and bind the exact manifest/universe snapshots. On that fixed
window the corrected lag-7 cell is -0.00542 (t=-0.28), while the original -0.05594
(t=-2.96) cell is now correctly labeled lag 8. C007's historical formula is retained, but
its numerical provenance is not exact and cannot be repaired after validation was observed.

## D7 — RETROSPECTIVE: accepted Yahoo rewrite of EA's pre-2005 history

**Date logged:** 2026-08-11, before the hardened full-family engineering replay.

A force refresh exposed a stable upstream rewrite of EA's Yahoo history. The previously
verified cache had 9,273 rows from 1989-09-20 through 2026-07-17. The current provider
returned 9,274 rows from 1989-09-25 through 2026-08-07, removing some previously observed
early sessions while adding recent sessions. Two independent full-history retrievals returned
the same 9,274-row index and identical index hash. Because an earlier unguarded audit refresh
had already replaced the old parquet, the revised snapshot is accepted explicitly rather than
misrepresented as a monotone update. The exact accepted parquet and prior manifest identity are
recorded in `data/manifest.json`.

The removed coverage predates the registered 2005 evaluation start, and every hardened metric
is recomputed and bound to the accepted manifest. This does not retroactively repair or alter
the original experiment. Force refreshes now fail closed when a provider response omits any
session in the currently verified cache, preserving the prior bytes and manifest; accepting a
future legitimate history rewrite requires another explicit, audited action.
