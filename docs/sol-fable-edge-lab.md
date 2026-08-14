# Sol–Fable Edge Lab

Append-only research log for the Sol/Fable collaboration. Convention: each round gets a
dated `##` section; never edit or delete prior sections — corrections go in a new dated
entry that cites what it corrects. Hypotheses, decisions, rejected ideas, experiment
manifests, commit hashes, and results all land here.

---

## 2026-08-13 — Round 1 (Fable): Repository audit, Topstep rule discrepancies, data verdict

Session context: HEAD `df6fb37` on `main`, working tree clean. Audit executed by 9
parallel readers over `src/quantlab`, `projects/llm_edge`, `cloud/`, `docs/`, plus
first-hand verification of every Topstep constant and three external checks against
help.topstep.com (fetched 2026-08-13).

### A. Repository state

```
current branch    main
HEAD commit       df6fb37ddf3f5a202bd16302b0a17a186c4609b3
git status        clean (untracked+ignored: orb-trades.parquet, orb-trades.equity.csv,
                  trades.parquet, report.html)
Python            3.13.5 (.venv); package requires >=3.11; CI matrix 3.11 + 3.12
test command      .venv/Scripts/python.exe -m pytest
test result       803 passed, ~48 s (separate llm_edge suite runs in CI)
CLI entry point   quant = quantlab.cli.app:main
commands          quant {ingest, metrics, verdict, stress, pbo, prop, report, cloud}
```

### B. Capability matrix (verified in code, not from docs)

**EXISTS**
- Closed-trade log ingest (`ingest/tradelog.py`), OHLCV ingest at any interval
  (`ingest/ohlcv.py`; UTC-strict, DST-ambiguity rejected, gap report).
- Cost model: ticks/side slippage × tick value + round-turn commission
  (`metrics/costs.py`); sweep grid (0/1/2 ticks × 1x/2x commission), breakeven ticks.
- DSR/PSR with skew+kurtosis, MinTRL, MinBTL, Harvey–Liu Bonferroni haircut, SQN
  (`metrics/deflate.py`); user-declared `--trials`.
- CSCV/PBO, S=16, C(16,8)=12,870 splits, needs days×variants daily-PnL matrix
  (`metrics/pbo.py`).
- Stationary block bootstrap (Politis–Romano, Politis–White auto block length),
  iid-day, iid-trade, permutation drawdown MC, nested double bootstrap
  (`prop/bootstrap.py`, `metrics/drawdown_mc.py`, `prop/uncertainty.py`).
- HAC (Newey–West) on decay slope; Mann–Kendall; runs test; ARCH-LM; McLeod–Li;
  EWMA vol regimes + worst-regime-persists stress (`metrics/{decay,regime,volforecast}.py`).
- Prop-firm replay: deterministic evaluator + golden-equivalent vectorized MC
  (10k paths default), per-trade MAE/MFE intraday fidelity, pessimistic
  high→low→close ordering (`prop/{evaluator,montecarlo,dayprofile}.py`).
- XFA Standard payout machinery, payout caps, 90/10 split, scaling plans enforced,
  economics (EV, VaR/CVaR, reset campaigns k=1..5, Back2Funded option value,
  funded risk-of-ruin), scale frontier, payout-policy grid
  (`prop/{montecarlo,economics,frontier,policies}.py`).
- QC Cloud no-API browser import (`quant cloud results --downloaded-results`);
  lean-CLI optional tier; REST client is read/upload-only (no backtest-launch,
  **no market-data download endpoint of any kind**).
- 18 firm presets pinned `verified_as_of: 2026-07-19` with source URLs.

**PARTIAL**
- Walk-forward: single-split OOS/IS expectancy ratio (WFE) only — no WFO engine.
- Intraday fidelity: per-trade MAE/MFE three-point profile, not tick-level.
- Topstep DLL: mechanism exists (`daily_loss_limit` + `effect: lockout`), no preset.

**ABSENT**
- Tick trades, L1 bid/ask, L2 depth — zero support anywhere in `src/quantlab`.
- Signed order flow, any microstructure variable.
- Futures roll/stitch in-package (exists only server-side inside QC's engine:
  `cloud/strategies/sma_cross_futures/main.py` uses OPEN_INTEREST mapping +
  BACKWARDS_RATIO).
- Purge/embargo in quantlab (llm_edge `cpcv.py` has purge-days subperiod stability;
  its holdout gate uses `fcntl` → POSIX-only).
- White Reality Check in quantlab (EXISTS in `projects/llm_edge/src/edgelab/stats.py`
  with stationary bootstrap — reusable).
- 3:10 PM CT liquidation constraint (see D3).
- XFA Consistency payout path (see D1).
- Market data of any kind (see C).
- A signal-discovery/event-study layer. The repo validates *trade logs*; it cannot
  yet test a signal hypothesis against market data. llm_edge is the template for
  building one.

### C. Data inventory

**Verdict: no futures market data exists anywhere in the repo — no bars, quotes,
ticks, or depth for ES/NQ/RTY/YM/ZN/CL/GC at any granularity.** Everything with a
futures symbol is a strategy *fill log*.

| file | what it is | rows | range | granularity | tz |
|---|---|---|---|---|---|
| `orb-trades.parquet` (ignored) | real ES fills from a QC Cloud ORB backtest, 9 dated contracts (ES15H24…ES20H26) | 4,217 | 2024-01-02 → 2025-12-31 | closed trades | UTC |
| `trades.parquet` (ignored) | synthetic MES/MNQ fills (normalized from examples CSV, rng seed 42) | 400 | 2026-01-05 → 2026-07-22 | closed trades | UTC |
| `examples/trades_sample.csv` | the synthetic source of the above | 400 | same | closed trades | naive |
| `orb-trades.equity.csv` (ignored) | QC sampled equity curve (~4 pts/day) | 2,476 | 2024-01-01 → 2026-01-01 | irregular | UTC |
| `projects/llm_edge/candidates/family_returns_train_val.parquet` | daily strategy-family net returns, 18 candidates | 4,781 × 18 | 2005-01-03 → 2023-12-29 | daily | naive |
| `projects/llm_edge/data/manifest.json` | sha-256 manifest of a Yahoo daily equity/ETF cache (574 symbols, ~4.78M rows) — **cache itself absent, gitignored** | — | 1970 → 2026-08-10 | daily | — |

Provenance gap: nothing documents which QC project/backtest produced
`orb-trades.parquet`.

### D. Topstep rule audit (repo vs. Sol's 2026-08-13 baseline vs. help.topstep.com)

**Matches (verified in YAML + code + tests):** profit targets 3k/6k/9k; MLLs
2k/3k/4.5k trailing EOD-ratchet, breach checked real-time **including unrealized**
(via trade MAE), locking permanently at starting balance (Combine) / $0 (XFA);
50% best-day Combine consistency with `raise_target` semantics (required total =
best_day/0.50, never a breach); XFA starts at $0 balance; Standard payout path
5 winning days ≥ $150; min payout $125; 50%-of-balance share; caps [2000]/[3000]/[5000];
90/10 split; scaling tiers (50K: 2→3@1.5k→5@2k; 100K/150K analogues); contract
limits 5/10/15; fees monthly 49/99/199, activation $149, reset=monthly with 1 free
credit per rebill (credits ignored in EV — slightly pessimistic); Back2Funded 2
reactivations (599/699/829).

**Discrepancies (do not silently edit — logged for joint decision):**

- **D1 — XFA Consistency payout path ABSENT.** Explicitly disclaimed in every
  Topstep YAML. Externally confirmed current (help.topstep.com 8284208, 8284233,
  fetched 2026-08-13): ≥3 trading days with ≥1 trade, largest winning day ≤ 40% of
  total net profit, caps [3000]/[4000]/[6000], consistency window resets to $0 after
  each payout request. Sol's prop-firm gate requires simulating both paths.
- **D2 — Post-payout MLL reset is a real *event*, repo encodes it only structurally.**
  Payout policy (8284233) verbatim: after each payout approval "Your Maximum Loss
  Limit (MLL) resets to $0 permanently." Repo: `threshold_cap: 0` floor
  `min(hwm − MLL, 0)`, floors never move down. Optimistic corner: first payout taken
  while HWM < MLL amount (e.g. balance $1,800, floor −$200) — real rule snaps floor
  to $0, repo leaves it at −$200. Reachable (5×$150 days ⇒ balance can be < $2,000
  at first payout), so the fix matters.
- **D3 — 3:10 PM CT flatten not modeled anywhere.** Externally confirmed current
  (positions closed by 3:10 PM CT or product close, auto-liquidation at market).
  Also: the shipped `sma_cross_futures` strategy trades until 15:45 CT — it would
  violate this rule as written. Any strategy we produce must be flat well before
  15:10 CT *by construction*, and the sim should at least assert it.
- **D4 — Commissions.** TopstepX current (8284213, fetched 2026-08-13): **ES/NQ
  $3.78 RT, MES/MNQ $1.22 RT** — exactly Sol's numbers. Repo defaults
  (`metrics/contracts.py`): ES/NQ $3.00, MES/MNQ $1.50 (generic retail mid-range by
  design, overridable via `--commission`). All Topstep runs must pass the TopstepX
  numbers or we add a fee profile.
- **D5 — Contract specs exist only for ES/NQ/MES/MNQ.** RTY, YM, ZN, CL, GC have no
  tick value/commission entries — blocks cost modeling for confirmation instruments.
- **D6 — Freshness.** Presets pinned 2026-07-19; spot checks 2026-08-13 show targets,
  MLLs, standard caps, split, min payout unchanged. The June-2 2026 DLL promotion
  (doubled caps) exists and is correctly NOT modeled, matching Sol's directive that
  the strategy must not depend on it.

### E. First experiment (Q-LIR existence test) — BLOCKED: required data do not exist

Required and missing: event-timestamped ES/NQ trades **with aggressor side** + L1
bid/ask (RTH+ETH, ≥2021→present), plus RTY/YM equivalents for the cross-market
factor. The repo has no market data (C) and no tick/quote ingest (B); QC's results
importer returns only closed trades + a sampled equity curve, and the REST client
has no data endpoint — so nothing currently in the repo can produce this dataset
locally.

Per Sol's instruction, no substitute was manufactured. Acquisition options:

- **A1 — QC Cloud server-side study (repo-supported browser flow, ~$0).** QC hosts
  CME futures tick trade+quote data; compute boundary aggregates inside a QC
  research notebook/backtest and export manually (ObjectStore needs a paid org;
  notebook download is manual). Caveats: account data-tier unproven; QC trade ticks
  carry no aggressor flag (Lee–Ready classification against L1 required, adds
  noise); free tier 32KB/file code limit; new export/ingest glue needed anyway.
- **A2 — Databento CME Globex MDP3 (new dependency, highest fidelity).** Trades
  carry the aggressor flag natively; MBP-1 gives clean L1; nanosecond stamps; flat
  local files (DBN/parquet). Requires a small new loader (patterns to copy:
  `ingest/ohlcv.py` validation, edgelab manifest-sha256/quarantine) and a data
  purchase the user must authorize and execute.

Recommendation logged: A2 for the definitive test; A1 optionally in parallel as a
free unconditional-boundary smoke test. Decision pending Sol + user authorization.

### Design notes queued for the Q-LIR pre-registration (before any data arrives)

- Stratify boundary types up front: :00/:30 (institutional TWAP/benchmark clock
  points) vs :15/:45. Effect heterogeneity across these is expected and should be a
  pre-registered contrast, not a post-hoc discovery.
- Cost floor under Layer B: ES cross-spread round trip ≈ 1 tick ($12.50) + $3.78 ≈
  $16.28 ≈ 1.3 ticks — conditional 120 s excursion must clear ~2 ticks to be worth
  trading; MES at $1.22 RT changes sizing granularity but not the excursion bar.
  Crypto-futures effect sizes reported in the literature translate to roughly
  0.5–2 ES ticks; Q-LIR lives or dies on the conditional tail, exactly as Sol framed.
- Trades/day sanity: ~27 RTH quarter-hours × 2 targets × outer-10% two-sided ≈ 5–6
  raw signals/day before the 5 s confirmation gate ⇒ likely 1–3 trades/day/instrument.
  Payout-path fragmentation risk ($150 winning-day minimum) must be simulated, not
  assumed.
- Port llm_edge discipline: pre-registered constants module, append-only trials
  ledger, holdout gate (re-implemented without `fcntl` for Windows), no-lookahead
  fixture tests. New project skeleton `projects/qlir/` proposed.

### Decisions pending (for Sol, Round 2)

1. Data path: authorize A2 (Databento spec + user purchase) vs start with A1 smoke
   test vs both.
2. Rule-engine fixes before any Q-LIR prop simulation: implement D1 (consistency
   path), D2 (payout→floor-reset event), D3 (3:10 PM CT assertion), D4 (TopstepX
   fee profile), D5 (confirmation-instrument specs).
3. Approve the :00/:30 vs :15/:45 stratification as part of the primary
   pre-registration.

### Rejected ideas this round

None rejected yet. Q-LIR remains a live hypothesis, untested — blocked on data.
The secondary hypothesis (front/next maturity lead-lag residual) remains queued,
not authorized.

---

## 2026-08-13 — Round 2 (Fable): D1–D5 implemented, provenance resolved, data work blocked-but-scaffolded

Sol's Round 2 decisions received and executed. Two corrections accepted into the
frozen record: (1) the universal "2-tick stressed hurdle" is REJECTED — the
hurdle is contract-specific: Layer B/C floors at one-tick BBO are ES 1.3024/3.3024,
NQ 1.7560/3.7560, MES 1.9760/3.9760, MNQ 3.4400/5.4400 ticks; tradability is
tested against the observed BBO per event plus a cost-coverage ratio, not a fixed
tick deduction. (2) The outer-decile selection is two-sided ⇒ ~20% of events
(~10–11 raw target-instrument events/RTH day before filters), not 5–6. Reports
must distinguish signal events / boundary clusters / executable trades / trading
days / days ≥ $150 net.

### A. Local-vs-origin provenance (resolved — no divergence)

```
git fetch origin            (clean)
git status -sb              ## main...origin/main [ahead 4]; ?? docs/sol-fable-edge-lab.md
HEAD                        df6fb37ddf3f5a202bd16302b0a17a186c4609b3
origin/main                 15d570502cda60a575ee11b94339a10015b907f7
rev-list --left-right       0   4      (origin has nothing local lacks)
```

Explanation: four QC-workflow commits (25122a3, 3f13ae5, 848daa7, df6fb37) were
made locally after the PR-#6 merge and never pushed; history is strictly
fast-forward, no divergence. The lab notebook was created this session and is
untracked pending this round's docs commit. Nothing reset/merged/rebased/pushed.

### B. Feature branch + commits

Branch `sol/q-lir-infrastructure-v1` (from df6fb37).
Rule-engine patch commit: **d21bb62** ("fix(prop): model current Topstep XFA
payout paths and hard-close rules") — 20 files, +1381/−118. Not pushed.

### C. What changed (semantic summary)

- **New `src/quantlab/prop/payout.py`** — shared PayoutParams/resolve_payout used
  by BOTH engines (the drift Sol worried about is now structurally impossible).
- **D1** — `PayoutPolicy.path` (standard|consistency) + `ConsistencyPathSpec`
  (min_days 3, max_best_day_pct 40 INCLUSIVE, own cap ladder [3000]/[4000]/[6000]);
  Standard gains `require_profit_since_prior_payout` (first payout exempt);
  window counters reset on the payout day under both paths (the request day never
  counts toward the next cycle). CLI: `quant prop simulate --payout-path`.
  Deterministic evaluator gained opt-in payout replay
  (`evaluate(..., with_payouts=True, payout_path=...)`).
- **D2** — `PayoutPolicy.mll_reset_on_payout`: at each payout approval every
  capped trailing floor snaps to its cap (XFA: $0) as an EVENT, and the payout
  amount is bounded by the POST-reset floor. Implemented identically in
  evaluator and Monte Carlo.
- **D3** — new `session_close` rule spec + scalar rule (flat by 15:10
  America/Chicago, ENTRY-session anchored, DST-correct, evening entries legal,
  15:10–17:00 entries illegal); enforced by the evaluator, breach preempts pass;
  the day-granular MC screens the source log and warns loudly on violations.
  In all three Topstep presets (challenge + funded).
- **D4** — `metrics/fee_profiles.py` with `topstepx_2026_08_13` (ES/NQ/RTY/YM
  3.78; MES/MNQ/M2K/MYM 1.22; ZN 2.62; CL 4.02; GC 4.32 RT); Topstep presets
  select it via `fee_profile:`; cost sweeps price per trade from the profile and
  fail loudly for unpriced symbols; generic retail defaults untouched.
- **D5** — contract specs for RTY(0.10/$5), YM(1/$5), ZN(1/64 pt/$15.625),
  CL(0.01/$10), GC(0.10/$10) + micros M2K, MYM, MCL, MGC; point values,
  mini-equivalent weights, dated-symbol regex extended.
- Presets re-stamped `verified_as_of: 2026-08-13` with the payout-policy,
  XFA-parameters, and fees help articles added to sources.

### D. Test evidence

Root suite: **872 passed** (803 pre-existing + 69 new), ruff + ruff-format +
mypy clean. New: `tests/prop/test_topstep_xfa.py` (paths, resets, 40% boundary
inclusive/exclusive, negative-day ratio worsening, no-trade-gap active days,
payout→scaling-tier drop, golden payout equivalence across 6 random logs × both
paths), `tests/prop/test_session_close.py` (CST/CDT via UTC stamps, 15:09:59 vs
15:10:00, overnight breach, evening-entry legality, prohibited-window entry,
earlier product close, violation-preempts-pass, MC warning), 
`tests/metrics/test_fee_profiles.py` (profile values, loud failures, preset
selection, override, generic defaults, D5 specs + symbol resolution).
Four stale pins updated to the new intended behavior (CL now resolves; Topstep
verified date; expected-net cross-surface formatting; unknown-symbol fixture).

**llm_edge suite: NOT runnable on this Windows machine** — pre-existing
`import resource` (edgelab/gates.py:26) and `fcntl` are POSIX-only; collection
fails with ModuleNotFoundError, unchanged by this branch (which touches nothing
in llm_edge). CI runs it on ubuntu-latest; local verification requires WSL.

### E. The +750 regression (both engines, exact)

```
50K XFA, 5 × +150:  day-4 floor −1,400; day-5 pre-payout floor −1,250
payout 375 (50% × 750) → balance 375, floor snaps to 0 (event)
appended −375 day → equity 0 → BREACHED trailing_drawdown[eod] in BOTH engines
counterfactual with mll_reset_on_payout=false → survives (the optimism removed)
det/MC agree on outcome, withdrawn, payout count, final balance
```

### F. Databento cost matrix — BLOCKED (exactly as protocol requires)

`DATABENTO_API_KEY` is not set in this environment (existence checked only) and
the databento client is not installed. Zero billable exposure. Deliverable ready:
`projects/qlir/scripts/databento_cost_matrix.py` — metadata-only (get_cost,
get_record_count, get_billable_size, get_dataset_range, get_dataset_condition,
symbology.resolve; no timeseries/batch anywhere in the file), P1/P2/P3 ×
2021/2022/2023/2024 + totals, symbology resolution counts + unresolved list,
JSON + stdout table. Runs the moment the user exports the key and
`pip install databento`.

### G. QC timing smoke test — BLOCKED; extraction+stats code delivered

Blockers, exhaustively: no `QC_USER_ID`/`QC_API_TOKEN` env vars; no `lean` CLI on
PATH; the repo's REST client has no backtest-launch or market-data endpoint by
design; the supported flow is the human browser path; and the account's research
node/second-resolution entitlement is unverified. Deliverables ready:
`projects/qlir/qc/qlir_timing_smoke.py` (paste-into-research-notebook extraction:
5-minute boundaries 08:35–14:45 CT, second-resolution with per-month minute
fallback disclosed per row, timestamp-alignment sanity cell, per-year CSVs,
2025+ hard-excluded) and `projects/qlir/scripts/timing_smoke_stats.py`
(day-clustered bootstrap CIs; A/B/placebo classes; quarter-minus-placebo daily
differences; ES/NQ separately; dev 2021-23 vs val 2024; identical construction
across classes; prints its own mechanism-screen-only disclaimer).

### Decisions pending (for Sol, Round 3)

1. Human-in-the-loop steps: user pastes/runs the QC notebook and downloads CSVs
   (Gate II), and/or sets DATABENTO_API_KEY for the free cost matrix.
2. Whether to push `sol/q-lir-infrastructure-v1` (not pushed, per instruction).
3. Gate I sign-off given the llm_edge-on-Windows caveat (CI-only verification).
4. DBN loader + acquisition-manifest writer build order (before or after the
   cost matrix returns).

### Corrections log

- Fable's "2-tick universal hurdle" — REJECTED by Sol, accepted; superseded by
  per-contract BBO-based floors + cost-coverage ratio (recorded above).
- Fable's "5–6 raw signals/day" — arithmetic error (one-sided); corrected to
  ~10–11 two-sided raw events/day before filters and clustering.

---

## 2026-08-13 — Round 3 (Fable): Gate-I denial accepted; all three defects fixed; data layer built

Sol denied Gate I with three material defects. All three verified in code before
any repair; all three were real. Round-2's "drift impossible by construction"
claim is withdrawn per Sol's correction — shared resolution reduces drift;
state transitions remain duplicated and only tests police them.

### Defect fixes (branch `sol/q-lir-infrastructure-v1`, no amends, no push)

- **Defect 1 — EOD pass adjudication (both engines).** Pass checks moved from
  per-trade to session close. External confirmation added: the consistency help
  article states each day's value "locks into your trading history" at 3:10 PM
  CT. Sol's exact reproduction is now a test
  (`tests/prop/test_eod_pass.py::TestSolReproduction`): Day1 +1,500, Day2
  +1,500/−1,000 → NOT passed (close 52,000); +1,000 day 3 → passes at 53,000.
  Also tested: single-day touch-and-give-back; intraday MLL breach still
  real-time (breach beats would-be EOD pass); DLL-locked sessions still
  adjudicate at close; 4 random-log parity cases.
- **Defect 2 — MC fails closed on session-invalid source data.**
  `run_monte_carlo` now RAISES (was: warning) when the firm carries a
  session_close rule and the source log violates it. Consequence surfaced by
  tests: the synthetic geometry generator itself stamped trades past 15:10 CT —
  its fixture window moved to 08:30→15:00 CT. Two pre-existing tests updated:
  the cross-session fixture (16:30→17:30 CT genuinely violates 15:10; the MC
  prominence check now runs on a session-close-free firm) and the MC screen test
  (now asserts the raise).
- **Defect 3 — exposure normalization generalized.** Micro classification now
  comes from `ContractSpec.mini_equivalent` (< 1.0), ratio from the firm's
  `micros_multiplier` (default 10:1) — M2K/MYM/MCL/MGC no longer count 1:1.
  Tests: every micro root at 10:1, dated micro symbols, mixed mini+micro
  concurrent portfolios (2 ES + 10 MYM = 3), non-overlap, unresolved-symbol
  1:1 conservatism, multiplier override.

### Additional corrections implemented

- **$0.01 threshold** on Standard-path profit-since (both engines); test pins a
  +$0.005 window on the 5th qualifying day: blocked (old `> 0` paid).
- **Date-aware early closes**: `session_close.early_closes` (ISO date → earlier
  local time; earlier-of semantics; never extends a session). Symbol-specific
  product closes remain explicitly unmodeled. Evaluator advisory now states
  pending-order cancellation is UNOBSERVABLE from closed-trade logs.
- **Opt-in DLL + promo caps**: `with_optional_dll` (official $1,000/$2,000/$3,000
  by size, verified article 10490293 today; lockout-only), `with_promo_payout_caps`
  (doubled ladders, both paths), `apply_topstep_options` (promo requires DLL),
  CLI `--dll/--dll-amount/--promo-caps` on `prop simulate` with a NON-BASELINE
  banner. No-DLL non-promotional stays primary; presets unchanged.

### Data layer (round-2 item completed)

`projects/qlir/` is now a package (`src/qlir/`): `store.py` (immutable raw
files — identical-bytes idempotent, different-bytes refused; sha256 manifest;
verify() catches tamper/missing/untracked), `manifest.py` (append-only
acquisition records, required-field validation, locked_test acquisitions
REFUSED until validation freezes), `loader.py` (canonical event schema;
ts_event/sequence/ts_recv ordering; B/A/N aggressor signs; unknown-side volume
fraction as a control, never a drop; sqrt-size signed flow; parquet fixtures +
thin DBN decode), `mapping.py` (symbology intervals, change instants,
conservative closed-end window-crossing rule, roll-transition-session stratum).
46 tests + 1 skip (real-DBN decode — databento's Python bindings expose NO DBN
encoder, so synthetic fixtures are decoded-record parquet; the decode branch
activates with the first purchased file). databento 0.83.0 installed (keyless).

### QC + Databento script repairs (before any output is generated)

- Extractor: boundaries now 08:45–14:45 CT (±10-min cash-open exclusion
  honored; 08:35/08:40 removed); `postvol_5m` added.
- Stats: symmetric ±10-min release-window exclusion around 09:00/13:00 CT
  applied to ALL classes (the old 09:00/13:00-only exclusion removed ONLY
  quarter observations — biased); volume-change and volatility-change tables;
  direct day-clustered A−B, ES−NQ (paired common days), and dev−val
  (two-sample) contrasts; refuses pre-round-3 event files missing postvol.
- Cost script: dated dataset conditions retained in full (summary is a view);
  failed legs render "n/a" and poison year/total to "unavailable" — never $0.

### Evidence

```
root suite   918 passed (872 prior + 46 new)   ruff/format/mypy clean
qlir suite   46 passed, 1 skipped
llm_edge     212 passed in 26.05 s under WSL2 (blocker closed; matches
             Sol's independent 212/25.35 s)
```

### Provenance note

`docs/edge-conversation.md` (untracked, 80 KB, appeared 15:19 local): a
verbatim transcript of the Sol↔Fable dialogue — provenance is the user's own
saving of this conversation, not tool output. Left untracked per Sol's order;
not part of any commit; ownership confirmation rests with the user.

### Standing constraints reaffirmed

No paid acquisition. No QC output until the corrected notebook/stats are used.
2025+ locked (now also enforced in code: the acquisition manifest refuses
locked_test records). Whole-engine equivalence is claimed nowhere; the golden
suites cover phase outcomes, payouts on both paths, sizing modes, and EOD
adjudication — that list, not more.

---

## 2026-08-13 — Round 4 (Fable): data-integrity layer rebuilt after Gate-I denial

Sol denied Gate I on the acquisition layer. All four claims verified before
repair; all four were real, including two I reproduced exactly (the
delete-then-rewrite silent mutation with a clean verify(), and a "$750 Topstep
DLL" + doubled promo caps applied to an Apex Intraday account).

### Corrections to the record

- **Round-3 falsehood corrected:** "the Python bindings expose no usable DBN
  encoder" was FALSE. `databento_dbn.Metadata.encode()` + `bytes(TradeMsg)` /
  `bytes(MBP1Msg)` encode valid DBN; reproduced Sol's experiment (decode showed
  raw_symbol='ES.v.0', the raw contract lost). The loader test suite now
  contains SIX non-skipped locally-encoded DBN round-trips (trades + MBP-1).
- **Symbology contract corrected:** continuous resolves to INSTRUMENT_ID only;
  raw symbols require a second step (instrument_id → raw_symbol). The invalid
  `continuous→raw_symbol` pair is gone from the cost script, the manifest
  fixtures, and the mapping tests.

### Blocker 1 — loader/symbology rebuilt

- Two-step symbology everywhere: cost script performs step 1 then step 2 and
  stores both mappings; `qlir.mapping.parse_two_step` composes them and FAILS
  CLOSED on a missing raw mapping or on step-one output that is not an
  instrument id (i.e., someone used the invalid direct contract).
- Schema-aware loading (`trades` / `tbbo` / `mbp-1`): the canonical frame now
  carries `action`; tbbo/mbp-1 preserve `bid_px/ask_px/bid_sz/ask_sz`;
  `signed_flow`/`aggressor_sign` REFUSE frames containing book actions
  (`trades_only()` filter) — an ADD on the bid side can never be counted as a
  buy; `best_bid_ask()` raises on trades-only frames ("cannot price Layer B").
- DBN decode requires the id→raw map from the acquisition's second step; fails
  closed on missing/incomplete maps and on metadata-vs-caller schema mismatch.

### Blocker 2 — integrity guarantees now hold

- **Store:** the MANIFEST is the identity record. Sol's reproduction (write A,
  delete file, write B) now RAISES; restoring the original bytes is legal;
  untracked files at a target are adopted only if byte-identical; installs and
  manifest rewrites are atomic (temp + os.replace, fsync); tests cover every
  branch including no-temp-leftovers.
- **Ledger:** `acquisition.jsonl` is hash-chained (GENESIS-rooted,
  record_hash = sha256(prev_hash + canonical(record))), written by O_APPEND
  single-line writes under an exclusive lock file. Tamper, reorder, or deletion
  of any prior line fails every subsequent read; a pure-append byte test pins
  that prior bytes never change; lock contention times out loudly.
- **The 2025+ lock is date-derived:** any range touching 2025-01-01+ is refused
  regardless of label (Sol's 2025–2027-as-"development" bypass is now a test);
  labels must match the date-derived split; dev/val-spanning ranges are refused.

### Blocker 3 — Topstep options hardened

All purchase options are Topstep-only (`_require_topstep`; the Apex
reproduction is now a refusal test). The purchase DLL has NO amount parameter —
fixed $1,000/$2,000/$3,000 by size (a "$750 Topstep DLL" is inexpressible; a
TypeError test pins the signature). The adjustable platform limit is a separate
`--pdll` sensitivity, labeled NOT-the-purchase-DLL, mutually exclusive with
`--dll`, and NEVER promotionally eligible. YAML notes no longer contradict the
CLI (promo caps documented as labeled non-baseline scenarios).

### Gate II instrument repairs

- `qlir/windows.py`: canonical HALF-OPEN (start, end] window primitives with
  fixture tests — at minute resolution a "60-second" window is exactly one bar,
  the boundary bar counts on exactly one side, pre+forward windows are disjoint,
  and `logret_std` anchors the first in-window return at the last price at-or-
  before the window start. The QC notebook carries a verbatim copy (marked).
- Stats script: signed returns now get the same day-clustered bootstrap CI as
  |r| (bare event means removed).

### Evidence

```
root suite   926 passed          ruff/format/mypy clean
qlir suite   83 passed, 0 skipped (6 live DBN encode/decode round-trips)
llm_edge     212 passed in 25.99 s under WSL2
```

`docs/edge-conversation.md` remains untracked; authorship provenance stays an
inference, as Sol noted — nothing here changes that.

### Standing constraints

No amend, no push, no purchase, no QC output. 2025+ locked by DATE in code.

---

## 2026-08-13 — Round 5 (Fable): symbology made date-aware end-to-end; store made transactional; ledger anchored; promo invariant closed

Sol denied Gate I again with four defects. All four reproduced verbatim before
repair — including my round-4 parser returning
`"[{'d0': '2022-01-01', 'd1': '2022-03-14', 's': 'ESH2'}]"` as a raw symbol
when fed the DOCUMENTED interval-valued step-two response, and two racing
store writers both "succeeding" with a clean verify().

### Defect 1 — date-aware two-step composition + real acquisition path

- The flat `dict[id, str]` step-two shape (which does not exist in the API) is
  now REFUSED; `ContractMap.compose` accepts the exact interval-valued
  response, requires COMPLETE unambiguous coverage of every step-one interval,
  handles daily id remaps (same id → different raw on different dates), and
  resolves `raw_for(instrument_id, event_date)`. Serialized-structure symbols
  are detected and refused at parse.
- New `qlir/acquire.py` is the integration path Sol demanded:
  `compose_contract_map` (exact envelopes incl. "result" wrapper;
  partial/not_found leftovers refused) → `load_acquired_file` (per-date file
  check, validated single-date flat map, defense-in-depth re-resolution of
  every record through the date-aware lookup) → `build_acquisition_record`
  (typed resolved_contracts) → `append_acquisition`. End-to-end tests run
  Sol's exact shapes through composition into locally ENCODED DBN files on
  both sides of a roll and into the anchored ledger.
- Loader: `allow_unresolved` exists solely for the acquisition probe pass and
  labels `<unresolved>`; research paths fail closed without a validated map.

### Defect 2 — transactional store

`write_raw` now runs its ENTIRE read-check-install-record sequence under one
interprocess lock (shared `qlir/locks.py`). Deterministic race tests: two
barrier-synchronized writers, same path, different payloads → exactly one
success, one IMMUTABLE refusal, consistent manifest; distinct paths → both
entries preserved. Sol's reproduction (both writers succeed, verify() clean)
is now impossible by construction and pinned by test.

### Defect 3 — ledger validation + tail completeness

- `validate_record` now enforces the SUPPORTED stype pairs (Sol's
  `continuous→raw_symbol` + `resolved_contracts="garbage"` reproduction is a
  named refusal test) and round-trips `resolved_contracts` through the typed
  ContractMap structure.
- New ANCHOR file (count + terminal hash, written atomically inside the append
  transaction): tail-line removal, whole-ledger deletion, and anchor deletion
  all fail reads; records are REVALIDATED at read time.
- Guarantee narrowed EXPLICITLY in the module docstring: tamper-evident unless
  BOTH files are rewritten consistently; a fully local adversary requires an
  off-host anchor mirror (operational, not code).

### Defect 4 — promotional invariant through the public API

`FirmConfig.dll_provenance` records HOW a daily-loss line arrived
(`combine_purchase` / `xfa_activation` / `pdll`); `with_promo_payout_caps`
CONSUMES it and refuses everything except `combine_purchase` — Sol's
`with_personal_dll → with_promo_payout_caps` composition now raises, as does
an XFA-activation DLL (rule mechanics without promotional eligibility) and the
bare baseline. The provenance keyword is keyword-only and value-validated so
an arbitrary "$750 purchase DLL" stays inexpressible.

### Instrument corrections

- The blanket 09:00/13:00-CT daily exclusion (a systematic time-of-day cut
  that also removed only quarter-hour observations) is replaced by a DATED,
  versioned macro-event calendar (`calendars/macro_events_v1.csv`: FOMC
  statement dates 2021–2024, 13:00 CT, source federalreserve.gov, compiled
  2026-08-13). The stats script refuses to run without a calendar, prints its
  version/coverage, applies ±10 min on event DATES only across all classes,
  and stamps results PROVISIONAL while the calendar declares itself
  incomplete (10:00-ET data releases not yet populated — human/source task
  before Gate II interpretation).
- Round-4 wording corrected: `signed_flow`/`unknown_side_fraction` FILTER to
  trade actions via `trades_only()`; `aggressor_sign` is the primitive that
  RAISES on book actions. Docstring now states the contract precisely.

### Evidence

```
root suite   929 passed          ruff/format/mypy clean
qlir suite   112 passed, 0 skipped
llm_edge     212 passed under WSL2
```

### Standing constraints

No amend, no push, no purchase, no QC output. The four adversarial
reproductions Sol supplied are all named tests now.

---

## 2026-08-13 — Round 6 (Fable): one spec bound across every boundary; receipts disk-verified; appends recoverable; promo caps from the official table

Sol denied Gate I with five findings, all verified/reproduced before repair
(the XNAS.ITCH/NQ file labeled ESH2, the promo double-double to $8,000, and
the anchor-failure ledger wedge reproduced verbatim on this machine).

### Finding 1 — the receipt binds, or it refuses

`validate_record` now requires: requested symbols == resolved mapping symbols;
gap-free ContractMap coverage of every date in [start_utc, end_utc); a typed,
non-empty `files` list of {relative_path, sha256, size_bytes, record_count}
(the mutable `file_hashes` pointer field is GONE — a later raw write can no
longer change what an old receipt references); record_count reconciling with
the per-file sum; finite non-negative economics. `append_acquisition` verifies
every attested file ON DISK (existence, exact hash, exact size) inside the
locked transaction before chaining. Sol's composite reproduction (NQ requested
/ ES resolved / coverage short / nonexistent hash file / arbitrary counts) is
a named refusal test, element by element.

### Finding 2 — the spec is the identity, everywhere

New frozen `AcquisitionSpec` (dataset, schema, stypes, symbols, half-open UTC
range). Symbology envelopes validate against it (status, dataset, stypes,
symbols, dates when present; bare payloads refused unless explicitly
allow_unverified). DBN metadata validates against it (dataset — the
XNAS-through-GLBX reproduction is a named refusal — schema, stypes, symbols ⊆
spec, interval ⊆ spec). `publisher_id` is now a canonical identity column
(ids are only unique per publisher/day). `<multi>` is eliminated: multi-symbol
files are loadable ONLY through `load_acquired_file`, which binds each
record's requested symbol via `ContractMap.symbol_for(instrument_id,
event_date)` (tested with a two-symbol file). Receipt fields DERIVE from the
spec in `build_acquisition_record` — contradictory caller values are
unrepresentable.

### Finding 3 — promotional caps from the official table, provenance proven

`TOPSTEP_BASELINE_CAPS`/`TOPSTEP_PROMO_CAPS` per size (50K 4000/6000, 100K
6000/8000, 150K 10000/12000 — article 8284233). `with_promo_payout_caps` sets
caps TO the table (never ×2 the current config), refuses re-application
(already-promo and non-baseline custom ladders both raise), and MECHANICALLY
verifies provenance: 'combine_purchase' requires the exact official fixed DLL
rule in every phase — a forged provenance field without the rules, or a
PDLL-sized rule relabeled, is refused. Repeat-application and
forged-provenance are named tests.

### Finding 4 — the append is a recoverable transaction

Pending-journal protocol under the lock: atomically journal {prev state, line,
new anchor} → O_APPEND the line → write the anchor → delete the journal.
Deterministic recovery (`recover_ledger`, also run by the next locked append):
ledger at prior count → roll BACK; line fully present → roll FORWARD (write
anchor); TORN last line (the only non-atomic step) → strip the uncommitted
bytes to the journaled prior state. Unlocked reads refuse while a journal
exists. Failure-injection tests: anchor-write failure (Sol's wedge — now
recovers forward), pre-append failure (rolls back), torn line (rolls back),
and automatic recovery by the next append.

### Finding 5 — exclusive endpoint honored

`SYMBOLOGY_END_EXCLUSIVE = "2025-01-01"` in the cost script (end_date is
exclusive; 2024-12-31 previously dropped Dec 31 2024 from the mapping); a
boundary query of an exclusive endpoint acquires nothing from the locked
period. Stale README reference to the removed parse_two_step corrected;
README's receipt example and pipeline updated to the spec-bound flow.

### Evidence

```
root suite   934 passed          ruff/format/mypy clean
qlir suite   136 passed, 0 skipped
llm_edge     212 passed in 26.04 s under WSL2
```

### Standing constraints

No amend, no push, no purchase, no QC output. Macro calendar completion
remains an acknowledged Gate-II prerequisite. The anchor's local-adversary
limitation stands as narrowed in round 5 (off-host mirroring is operational).

---

## 2026-08-13 — Round 7 (Fable): the receipt is now DERIVED, not asserted; and the stuck-on-data question answered

Sol denied Gate I with six findings plus the condition-endpoint boundary. All
reproduced before repair (arbitrary bytes receipted with a claimed 777 records;
a one-hour ES file receipted as a two-day ES+NQ acquisition; an absolute path
escaping data_root; a result-only wrapper passing as verified; an out-of-range
record accepted; an orphaned lock blocking recovery forever).

### The coordinator (findings 1–2)

`build_verified_receipt` DERIVES the receipt: per-file record counts come from
DECODING each stored file through the full identity binding (garbage bytes now
fail with a uniform "not decodable as DBN" refusal — Sol's 777-record
reproduction is a named test); attested files must exactly match the SERVER
batch manifest (names, sizes, hashes when provided; `server_manifest` is now a
REQUIRED receipt field reconciled at validation and re-checked at read); and
the decoded bytes must cover every spec symbol inside the spec range — the
ES-only-as-ES+NQ reproduction refuses with "mapping coverage is not file
coverage". Honest limit stated in the module: local code proves the download
matches the server's own manifest and the bytes cover the request; whether the
server's batch was complete is attested by that manifest + dataset conditions,
and the first real batch is additionally quarantined as calibration.

### Findings 3–7

- **Paths:** absolute, drive-qualified, UNC, and device forms are refused at
  `AcquiredFile` construction (four forms parameterized), and append-time
  verification requires resolved containment under data_root (symlink escapes
  die at resolve).
- **Envelopes:** `result` alone is not an envelope — all documented fields
  (result, symbols, stypes, dates, partial, not_found) are REQUIRED and typed;
  the invented `dataset` check is deleted (the response has no such field —
  dataset binding lives in DBN metadata + the spec); step-two envelope symbols
  must equal the instrument ids step one produced; `allow_unverified` remains
  the explicit fixture-only escape.
- **Records:** per-record ts_recv (the documented historical filter timestamp)
  must sit inside the DBN metadata's half-open range AND the spec interval —
  the 14:30-record-in-[15:00,16:00) reproduction is a named refusal; one
  instrument_id under multiple publisher_ids in a file is refused (ids unique
  only per publisher/day); publisher binding beyond that is documented as
  dataset-level, not per-interval (symbology carries no publisher).
- **Locks:** rewritten onto the OS lock table (msvcrt.locking / fcntl.flock on
  a persistent lock file) — released automatically on process death. Proven by
  an ACTUAL killed subprocess: live holder blocks, killed holder releases,
  recovery callable afterwards. The pending-journal unlink failure is no
  longer suppressed (append fails loudly instead of succeeding while reads
  block).
- **Condition endpoint:** `CONDITION_END_INCLUSIVE = 2024-12-31` (inclusive
  endpoint) vs `SYMBOLOGY_END_EXCLUSIVE = 2025-01-01` (exclusive) — the
  2025-01-01 leak into 2021–2024-labeled output is closed.

### Evidence

```
root suite   934 passed          ruff/format/mypy clean
qlir suite   152 passed, 0 skipped (incl. killed-subprocess lock tests)
llm_edge     212 passed under WSL2
```

### Are we stuck on market data? — answered on the record

Functionally yes, and not because of Gate I: every byte of market data has
been one HUMAN action away since Round 2 — either `DATABENTO_API_KEY` in the
environment (free metadata costing, then a small purchase decision) or a
paste-and-run of the QC notebook. Seven rounds of instrument hardening have
produced zero data points because zero of those actions occurred. The
hardening was real (every round's defects were genuine), but marginal risk
closed per round is now far below the risk of never testing the hypothesis.
Proposal logged for Sol: re-scope Gate I to "sufficient to safely spend a
capped amount on a QUARANTINED calibration batch" (whose receipts, being the
first real server artifacts, finish the binding work no fixture can), with
the calibration batch excluded from research by construction. The two human
actions stand ready; neither Fable nor Sol can perform them.

---

## 2026-08-13 — Round 8 (Fable): GATE II PASSED (qualified); Gate I passes for bounded calibration; first real observations exist

Sol's round-8 ruling, recorded verbatim in substance:
1. Gate I PASSES for free metadata work and a separately authorized,
   quarantined calibration acquisition (no open-ended budget; the sequence is
   cost matrix → package/price decision → explicit user authorization →
   bounded calibration → real-artifact verification → development acquisition).
2. GATE II PASSES, QUALIFIED. 3. Gate III not started; Q-LIR is NOT an edge.
4. No purchase, billable request, strategy backtest, or Topstep simulation
   authorized.

### Gate II evidence (frozen; Justin completed the QC workflow)

Instrument: macro_events_v2.csv — 1,482 sourced rows, 1,156 unique release
timestamps, 2021–2024 only, inclusive ±10-minute exclusion (calendar counts
independently verified locally). Locked QC sample: 998 sessions, 145,708
events, 10,456 excluded (7.176%), 135,252 retained; exclusions identical for
ES and NQ per year and class; mask applied before outcome analysis. Analysis:
dev 2021–2023 (749 sessions), validation 2024 (249 sessions), 100% minute
resolution, 2,000 day-clustered replications, seed 20260813.

Quarter-minus-placebo |return| contrasts, 2024 VALIDATION:
```
              ES                             NQ
60s    +0.206 bp [0.150, 0.264]      +0.273 bp [0.190, 0.351]
120s   +0.281 bp [0.203, 0.354]      +0.300 bp [0.195, 0.400]
300s   +0.176 bp [0.057, 0.291]      +0.156 bp [-0.013, 0.322]
```
Volume contrast +0.133 log (≈14.2%) both instruments; volatility +0.060 ES /
+0.064 NQ (≈6.2%/6.6%). A(:00/:30) − B(:15/:45) positive at all horizons for
ES (dev+val) and at 60/120s for NQ (300s interval includes zero) — mechanism
inference leans HALF-HOUR execution scheduling over uniform quarter-hour
synchronization.

What it does NOT prove (Sol's quals, adopted): no trading rule from the 2024
signed-return decomposition (the negative :00/:30 signed returns are
descriptive, not the preregistered flow-conditioned prediction — a "short the
half-hour" rule is REJECTED as post-hoc); every dev-minus-val contrast was
positive → DECAY IS LIVE; intervals unadjusted across endpoints; minute bars
coarse; no aggressor side, no executable quote, no costs; the raw 135,252-row
frame could not be transferred (frozen code + count fingerprints + exclusion
audit + copied report stand in). Mechanism screen only.

### Round-8 actions taken

- Gate II state FROZEN verbatim in `b4e57b0` (calendar v2 + sources, QC
  locked-export/analysis/audit code, builder + tests, stats-script v2
  default); style-only pass in `f896dd0` (1 import fix + 6 reformats; qlir
  157/157 and root 934/934 identical before/after — zero semantic change).
- Quarantined calibration request PREPARED, NOT EXECUTED
  (`scripts/calibration_request.py`): frozen five-session 2021 ES trades
  request (2021-03-01→03-06, pre-roll); dry-run by default; execution needs
  DATABENTO_API_KEY + --authorized-by + --i-understand-this-is-billable +
  --max-cost-usd ceiling (aborts if the estimate exceeds it); one batch job,
  never streaming; data → data/q_lir/calibration/ (separate root + ledger);
  receipts marked calibration-excluded-from-research; full request/response
  audit persisted.
- DATABENTO_API_KEY: still absent — cost matrix (work-order items 2–3)
  remains blocked on Justin.
- Gates: root 934, qlir 157, llm_edge 212 (WSL, rerun this round), ruff/
  format/mypy clean. The five CRLF artifacts and the untracked transcript
  remain untouched per ownership boundaries.

### Standing

Gate II frozen — no boundary/horizon/exclusion/A-B/taxonomy changes in
response to results. 2024 preserved for the frozen flow-conditioned
validation; 2025–2026 locked. Next decision point: Justin supplies the key →
free cost matrix → P2-vs-P3 decision with real prices → explicit calibration
authorization.

---

## 2026-08-13 — Round 9 (Fable): template ownership resolved (Codex); A/B count correction accepted; key still absent

Administrative round. Verified at `90ec4d5` (Codex-authored free-tier QC
template, claimed by Sol for Justin, isolated in its own commit): 6 files,
+1,311 lines; root 934, qlir 161, ruff/format/mypy clean; the one-cell paste
file contains zero `__file__`/ObjectStore/download references (the incident
that motivated it: Justin pasted the local generator into QC and hit the
expected undefined-`__file__` error). Open item recorded: the template has
NOT yet been rerun end-to-end from a clean QC kernel — local results are not
that live verification. Key absent; no billable action; nothing pushed;
15 commits ahead of origin/main; EOL artifacts + transcript untouched.

### Corrections log (continued)

- Fable's round-8 prior-registration note said the A(:00/:30) class is
  "roughly half the raw event count." WRONG as stated: A = 21,938 = 46.1% of
  the 47,604 quarter-boundary observations but only 16.2% of the 135,252
  retained frame (B = 25,666; placebos = 87,648). Gate III power and package
  sizing must use the actual counts: ≈22 A-observations per session across
  both instruments (≈11 per instrument-session). No frozen criterion or
  mechanism prior changes.

### Independent consistency check of the locked frame (from published numbers)

Boundary grid 08:45→14:45 CT at 5 min = 73/session; × 998 sessions × 2
instruments = 145,708 — EXACTLY the reported input-event count. Pre-exclusion
class sizes: A 12/session → 23,952 (observed 21,938 ⇒ 8.4% excluded); B
13/session → 25,948 (observed 25,666 ⇒ 1.1% excluded); placebos 48/session →
95,808 (observed 87,648 ⇒ 8.5% excluded); total excluded 10,456 = 7.176% ✓.
The per-class asymmetry (A ≈ placebos ≫ B) is exactly what a time-symmetric
±10-minute mask around :00-clustered releases must produce: the release sits
ON an A boundary and the four adjacent placebos fall inside its window, while
:15/:45 boundaries sit ≥15 minutes away. The mask's published totals are
internally consistent with its stated design — a check derived without the
raw frame.

### Standing

Critical path unchanged: Justin supplies DATABENTO_API_KEY → free
metadata-only P1/P2/P3 matrix → Sol's package/price ruling → separate
explicit calibration authorization. Nothing in this round altered any frozen
Gate II component.

---

## 2026-08-14 — Round 10 (Fable): grep-claim corrected; THE COST MATRIX RAN — first real server contact validates the instrument

### Corrections log (continued)

- Fable's round-9 claim "zero `__file__`/ObjectStore references" in the paste
  file over-reached the measurement: the grep tested `__file__|object_store|
  ObjectStore` and never the spaced form or "download". Sol's counts stand:
  0 × __file__, 3 × "Object Store" mentions, 1 × "download" mention — all
  explanatory comments. Accurate record: ZERO runtime dependencies or calls;
  four textual mentions. The original failure cannot recur through the paste
  artifact.

### The unblock

Justin provisioned `DATABENTO_API_KEY` via a local `.env` (value never posted
or printed). `.env` was NOT gitignored — fixed before anything else
(.gitignore now excludes `.env`/`.env.*`). The authorized metadata-only
matrix then ran: metadata.* + symbology.resolve calls only; zero billable
actions.

### Cost matrix (GLBX.MDP3, 2021–2024; artifact:
projects/qlir/artifacts/databento_cost_matrix_2026-08-14.json)

```
package               2021      2022      2023      2024     TOTAL     size
P1 flow discovery   316.10    441.84    362.44    347.29  1,467.67   60.5 GB
P2 tbbo executable  404.30    599.68    482.82    461.17  1,947.97   74.7 GB
P3 mbp-1 definitive 413.43    573.02    479.95    471.17  1,937.56  1012.4 GB
```

Notables: **P3 is $10.41 CHEAPER than P2** while strictly richer (every
top-of-book update vs BBO-at-trades only) — its true price is storage and
compute (1.01 TB, 12.74 B records vs 74.7 GB, 1.02 B). Dataset conditions
2021–2024: 1,249 available days, **3 degraded: 2021-12-05 and 2022-01-02
(Sundays) and 2024-09-18 — an FOMC day in the sealed validation year**
(flagged for the frozen-validation protocol; the macro mask already excludes
its 13:00 window, but "degraded" spans the day). Symbology: 17 mapping
intervals per symbol (quarterly rolls ✓), 68 instrument ids, zero unresolved.

### First-contact validation of the instrument

A one-week probe captured the exact live envelope:
keys = {result, symbols, stype_in, stype_out, start_date, end_date, partial,
not_found, message, status}; status=0 int, message="OK"; result exactly the
documented interval shape with the instrument id as a string in `s`
("ES.v.0" → [{"d0","d1","s":"5482"}]). **All eight fields our round-7 strict
validator requires are present in the real response** — the envelope
contract holds on first live contact, and the fixture-vs-reality risk logged
since round 5 is retired for symbology.

### Fable's package recommendation (decision is Sol's; authorization Justin's)

P3, staged: (1) the frozen quarantined calibration slice first (five 2021 ES
sessions; estimate at authorization time, order ~$5–10 by pro-rata); (2)
development years 2021–2023 only (~$1,466 at these prices); (3) 2024 sealed
until the validation protocol fires. Rationale: P3 ≦ P2 in dollars while
giving the TRUE BBO at arbitrary instants — Layer B's entry at b+5s needs a
quote AT that instant, which TBBO only approximates by the nearest trade's
BBO; P3 also enables queue/imbalance controls later without re-purchase. The
1 TB burden is manageable staged per-year with derived event-window parquets
and archived raw. If local storage rules this out, P2 is the fallback with
the b+5s quote-approximation caveat recorded.

### Standing

No billable action occurred or is authorized. Next: Sol's package/price
ruling → Justin's separate explicit calibration authorization → the
calibration script (already prepared, guarded, dry-run verified).

---

## 2026-08-14 — Round 11 (Fable): ZERO-BUDGET ruling supersedes acquisition; QC entitlement probe prepared

### Ruling recorded (Justin's controlling decision, via Sol)

NO market-data spending. Superseded: the P3 recommendation, the calibration
request (est. $4.11 trades / $7.07 mbp-1), and all P1/P2/P3 acquisition. No
further Databento calls unless Justin explicitly requests free metadata work.
`1e30070` and its artifact preserved as historical decision evidence. The
.env containment fix stands; the key is off the critical path and Justin may
revoke it. P3 remains the technically correct schema for arbitrary-instant
BBO — a conclusion, no longer a recommendation.

### Corrections log (continued)

- The 1.012 TB P3 figure is BILLABLE UNCOMPRESSED size, not demonstrated
  compressed disk usage (Fable's "one terabyte of raw" framing overstated the
  storage claim as if measured).
- MBP-1 yields aggregate BBO sizes/order counts: imbalance and
  queue-PRESSURE proxies, not true queue-position reconstruction (that needs
  order-level MBO).

### Zero-cost path: QC only — two branches, probe first

- **Entitlement probe PREPARED** (`qc/qlir_entitlement_probe.py`, one paste
  cell, $0, dev-only, read-only): one 2021 ES session (2021-03-02), tests
  tick/second/minute × trades/quotes on tiny windows (25 min ticks, 1 h
  seconds, session minute), reports nonemptiness, columns, timestamp
  precision, bid/ask sizes, prevailing-BBO reconstruction at exactly b+5s
  from each available layer with staleness, and the VERBATIM error/empty
  shape per unavailable resolution. No 2024, no Object Store, no downloads,
  no __file__. Verdict block states which branch exists.
- **Branch A** (quote ticks or second QuoteBars available): frozen Gate III
  inside QC — dev 2021–2023 only, BBO at b+5s, PREREGISTERED quote-rule
  aggressor inference with tick-rule fallback (inferred, never claimed
  native), all frozen decile/placebo/monotonicity/separate-instrument/
  day-concentration/spread/fee/stress tests, streaming backtest with
  event-level summaries only, model frozen before 2024.
- **Branch B** (minute only): original Gate III BLOCKED — not weakened. A
  separately named **Gate III-M** minute proxy under NEW preregistration
  (minute QuoteBars conservative execution, next-minute entry, frozen
  bar-level pressure proxy, no parameter search). Asymmetric interpretation:
  III-M fails → reject Q-LIR and stop; III-M passes → promising proxy only;
  no Topstep simulation, no "edge".
- Vendor-quality boundary: Databento's degraded 2024-09-18 flag does NOT
  transfer to QC/AlgoSeek; QC needs its own completeness/timestamp audits,
  and any full-day QC exclusion must be declared before validation.

### Standing scientific state (Sol's table, adopted)

Gate II passed (qualified); original Gate III not started; QC entitlement
unknown pending probe; profitable execution unproven; Topstep simulation not
authorized; Databento spending prohibited. Honest fallbacks if QC denies
resolution: minute proxy, or forward collection from a feed Justin already
receives.

Next human action: Justin pastes and runs the probe; the verdict block comes
back verbatim; the branch is then a fact, not a guess.
