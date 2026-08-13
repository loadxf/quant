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
