# Pre-Registered Experimental Protocol

**Status: FROZEN at pre-registration. Committed before any data analysis, candidate
generation, or backtesting. Later phases cite this document by commit hash. Any deviation
must be logged in `research/debates/protocol_deviations.md` with justification.**

Pre-registration date: 2026-07-19.

## 1. The question

Can an LLM (Claude, with tools: web research, code execution, market-data access) produce a
trading signal that is (a) novel per the tiered scale in `novelty_scale.md` and (b) supported
by out-of-sample evidence that survives multiple-testing correction? A negative or nuanced
answer is a valid outcome and will be published with the same rigor as a positive one.

## 2. Epistemic loop (applies to every phase)

Every substantive artifact passes: **initial pass → adversarial pass → revision**, looping
until the adversary registers zero standing objections or a judge rules on each remaining
objection. Round caps: literature topics ≤ 3 rounds; novelty verdicts ≤ 2 rounds; final report
≤ 3 rounds. All debates are preserved in `research/debates/`.

## 3. Data

- Source: Yahoo Finance chart API (daily OHLCV + adjusted close, dividends). Sole available
  source in this environment; this is limitation R1.
- Universe: current S&P 500 constituents with ≥ 15 years of history (~400 names) plus ~60
  liquid ETFs (US sectors, country funds, bonds, gold, oil, dollar). Recorded in
  `data/universe.json`; every download hashed in `data/manifest.json`.
- Survivorship bias: the universe is today's constituents (limitation R2). Mitigation:
  candidate signals should be cross-sectional long-short (bias partially nets out); any
  long-only result is flagged as suspect in the report.

## 4. Splits — fixed now, before any analysis

| Split | Period | Use |
|-------|--------|-----|
| Train | 2005-01-01 → 2018-12-31 | signal development, G2 search training fitness |
| Validation | 2019-01-01 → 2023-12-31 | One fixed Gate 1/2 evaluation per candidate |
| **Holdout (LOCKED)** | 2024-01-01 → last available (~2026-07-17) | Gate 3, one shot per candidate |
| Post-cutoff sub-window | 2026-02-01 → end | provably outside model training data (cutoff Jan 2026); ~5.5 months — directional consistency check only, never primary evidence |

Holdout lock mechanism: analysis code loads data through `load_panel(end="2023-12-31")` by
default. Holdout evaluation is possible only through `src/edgelab/holdout_gate.py`, which
(a) requires the candidate's spec SHA256 to exist in `candidates/registry.json`,
(b) verifies via `git log` that the registry entry was committed before invocation,
(c) writes `candidates/C###/holdout_results.json` exactly once and refuses re-runs.
The git history in the final PR is the public audit trail.

## 5. Backtest engine rules

- Daily cross-sectional long-short: signal computed from data ≤ t, positions formed at close
  t+1 (one-day implementation lag), P&L accrued t+1 → t+2. Decile long-short for the equity
  universe, quintile or tercile for ETF-only universes; equal weight.
- Transaction costs: 10 bps per side single-name equities, 5 bps per side ETFs, charged on
  turnover. Sensitivity sweep at {0, 5, 10, 25} bps.
- A timing unit test must pass before any results are produced: a synthetic signal equal
  to the next-day return must earn only its correctly lagged, stale alignment. Promotable
  candidates are literal declarations dispatched through a trusted causal
  registry. Every registry handler is exhaustively checked at every prefix on independent
  panels; arbitrary Python is confined to non-promotable adversarial development tests.

## 6. Statistics (implemented in `src/edgelab/stats.py`, pinned by unit tests)

- Annualized Sharpe: SR = mean(r)/std(r) · √252 (daily returns, ddof=1).
- Newey–West t-statistic of the mean daily return, lag 10.
- Probabilistic Sharpe Ratio (Bailey & López de Prado), non-annualized SR inputs:
  PSR(SR*) = Φ( (SR̂ − SR*)·√(n−1) / √(1 − γ₃·SR̂ + ((γ₄−1)/4)·SR̂²) ),
  n = number of returns, γ₃ = skewness, γ₄ = kurtosis (normal = 3).
- Deflated Sharpe Ratio: DSR = PSR(SR*₀) with
  SR*₀ = √V[{SRₖ}] · ( (1−γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e)) ),
  γ = Euler–Mascheroni ≈ 0.5772. **N and V[{SRₖ}] come from `candidates/trials_ledger.csv`**
  — a concurrency-safe CSV ledger written *inside the backtest engine itself*. Failed search
  and gate evaluations are recorded explicitly. Before holdout access the ledger must be
  committed and byte-identical to git HEAD. This makes changes auditable, not physically
  immutable to a repository owner. The final report states the total N.
- Family-wide test: stationary-bootstrap (Politis–Romano, mean block 20 days, 1000 resamples)
  Reality-Check-style p-value for the maximum validation SR across the candidate family.
- Combinatorial subperiod-stability analysis on train+validation: 8 blocks choose 2 selected
  blocks (28 selections), with five observations removed on both sides of each boundary.
  This is a descriptive stability check, not independent OOS evidence, because the strategy
  is not independently re-fit within each selection.

## 7. Promotion gates — fixed now

- **Gate 1 (validation):** cost-adjusted (10 bps) validation SR > 0.5; Newey–West |t| > 2;
  sign of returns matches the spec's predicted sign; median subperiod-stability SR > 0.
- **Gate 2 (robustness):** positive cost-adjusted SR in both validation subhalves; positive in
  both high- and low-volatility regime halves (split by median 63-day realized vol of the
  equal-weight universe); survives ±25% perturbation of every window parameter; SR > 0 at
  25 bps costs.
- **Gate 3 (holdout, one shot):** holdout cost-adjusted SR > 0; DSR > 0.95 with full-ledger N;
  pooled (train+validation+holdout) Newey–West |t| > 3 (Harvey–Liu–Zhu standard).
  Only Gate-3 survivors are eligible for tier T3.

## 8. Generation mechanisms (Phase B)

- **G1 — data-first mining on fresh data:** descriptive-statistics panels computed on
  2024–2026 data; hypotheses articulated from anomalous cells; trace must cite the specific
  statistic that prompted each hypothesis. Strongest provenance path.
- **G2 — grammar search with train-only fitness:** a small signal DSL and evolutionary search
  use only the 2005–2018 training window. The top distinct expressions are then evaluated
  once against the fixed 2019–2023 validation gates. All attempts hit the trials ledger.
- **G3 — cross-domain structural transfer:** formalisms imported from fields with no
  documented finance footprint (checked against factor_db); tests recombination reach.
- **G4 — anti-consensus inversion (control group):** perturbations/inversions of documented
  effects. T1 by construction. If G4 performs as well as G1–G3, that is evidence that "novel"
  generation adds nothing over recombination — and will be reported as such.

Candidates are specified in `candidates/C###/spec.md` (hypothesis, economic rationale, exact
formula, universe, predicted sign, generation trace) and registered by SHA256 in
`candidates/registry.json` **before any holdout access**.

## 9. Loop and stopping rules

Maximum **3 full generate→validate→verify loops**. Stop early if any candidate reaches T3.
Stop at 3 loops regardless of outcome and write up whatever the evidence shows. Iterating
because candidates failed novelty checks selects for obscurity, not truth (risk R8) — the loop
cap and the ever-growing ledger N are the guards.

## 10. Pre-declared risks and their handling in the report

- **R1** Yahoo daily-only data = heavily mined territory; a negative result is weaker evidence
  against LLM creativity than it appears.
- **R2** Survivorship bias in the universe; prefer long-short; flag long-only.
- **R3** Holdout brevity (~2.5 y; ~5.5 months provably post-cutoff); PSR quantifies the width.
- **R4** Ledger discipline; mitigated by engine-level ledger writes.
- **R5** The model has memorized 2024–2025 market narratives; G1 traces must cite the
  prompting statistic; Phase D attacks exactly this; only 2026 data is provably clean.
- **R6** Literature-search recall limits; T2 = "none found in documented scope."
- **R7** "Tool-augmented novelty isn't the LLM alone" — conceded; report answers weights-alone
  and system questions separately.
- **R8** Verifier-overfitting via iteration; loop cap + full-ledger DSR + G4 control.
- **R9** Sycophancy in either direction; final report reviewed by two opposite-mandate
  reviewers (one hunting overclaims of novelty, one hunting performative humility), judge-resolved.

## 11. Deliverable

`REPORT.md` at repo root, structured per the pre-committed skeleton, conclusion written last
and tied strictly to the evidence table. Everything committed and pushed to
`claude/llm-novelty-trading-research-afrv74`; PR opened on `loadxf/quant`.
