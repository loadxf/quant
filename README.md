# loadx-quant

QuantPad-style **backtesting + prop-firm challenge simulation**, built on
QuantConnect Cloud, that runs on data **you** provide.

Two independent halves:

- **Pure-Python core** — prop-firm Monte Carlo simulator, strategy metrics,
  A–F "Verdict" scorecard, overfit checks, self-contained HTML reports.
  Works anywhere from a trade-log CSV. No QuantConnect account, no Docker.
- **QuantConnect Cloud strategies** — the standalone `main.py` files under
  `cloud/strategies/` run on QuantConnect's online platform. Create a Cloud
  Python project, paste one file, Build, and Backtest. Download the finished
  result from the web UI and import it locally; no QuantConnect API, lean CLI,
  Docker, or Object Store is required for the built-in-data strategies.

The boundary is intentional: strategy execution happens in QuantConnect
Cloud; the pandas/pyarrow CLI, prop-firm simulation, and HTML reporting run
locally against the downloaded result. The full local package is not a
deployable `QCAlgorithm` and should not be copied into the Cloud project.

**Contents**

1. [Setup from scratch](#1-setup-from-scratch)
2. [Five-minute quickstart](#2-five-minute-quickstart)
3. [Command reference](#3-command-reference)
   - [`quant ingest trades`](#quant-ingest-trades--csv--canonical-parquet) ·
     [`quant ingest ohlcv`](#quant-ingest-ohlcv--normalize-market-bars) ·
     [`quant metrics`](#quant-metrics--strategy-statistics) ·
     [`quant verdict`](#quant-verdict--af-scorecard) ·
     [`quant prop firms`](#quant-prop-firms--list-and-inspect-presets) ·
     [`quant prop evaluate`](#quant-prop-evaluate--deterministic-replay) ·
     [`quant prop simulate`](#quant-prop-simulate--the-monte-carlo) ·
     [`quant prop frontier`](#quant-prop-frontier--position-size-sweep) ·
     [`quant prop policies`](#quant-prop-policies--funded-phase-payout-policies) ·
     [`quant prop geometry`](#quant-prop-geometry--no-trade-log-exploration) ·
     [`quant stress`](#quant-stress--the-reality-check) ·
     [`quant pbo`](#quant-pbo--probability-of-backtest-overfitting) ·
     [`quant report`](#quant-report--everything-in-one-html) ·
     [`quant cloud`](#quant-cloud--quantconnect-cloud-backtests)
4. [Firm presets and custom firm YAMLs](#4-firm-presets-and-custom-firm-yamls)
5. [How the simulation works](#5-how-the-simulation-works)
6. [Reading the numbers honestly](#6-reading-the-numbers-honestly)
7. [Related projects](#7-related-projects)
8. [Development](#8-development)

---

## 1. Setup from scratch

Requirements: **Python ≥ 3.11** and git. No Docker anywhere, for anything.

```bash
git clone https://github.com/loadxf/quant.git
cd quant
python -m venv .venv && source .venv/bin/activate

pip install -e .          # core + browser-downloaded QC result import
pip install -e ".[dev]"   # + pytest/ruff/mypy, for contributors

quant --version           # sanity check
quant --help              # top-level command tree
```

On **Windows** the only line that differs is the venv activation —
`.venv\Scripts\Activate.ps1` (PowerShell) or `.venv\Scripts\activate.bat`
(cmd); in Git Bash use `source .venv/Scripts/activate`. Everything else,
including every `quant` command in this README, is identical on all
platforms — pure Python, no Docker.

**No data yet?** The repo ships a deterministic ~6-month synthetic futures
log with deliberately messy formatting (to exercise the parser), so every
command below can be tried immediately:

```bash
quant ingest trades examples/trades_sample.csv -o trades.parquet
```

(`python examples/generate_sample.py` regenerates it byte-identically.)

**Cloud backtests need no API credentials.** The primary workflow in the
[`quant cloud` section](#quant-cloud--quantconnect-cloud-backtests) runs the
strategy in the web IDE, then uses **Overview → Download Results** on the
backtest page. The downloaded JSON contains the closed trades and charts the
local importer needs. Do not configure `QC_USER_ID` or `QC_API_TOKEN` for this
workflow.

Everything under [§3](#3-command-reference) except the Cloud execution step
works with no QC account. The complete online deployment and result-download
checklist is in [docs/quantconnect-cloud.md](docs/quantconnect-cloud.md).

## 2. Five-minute quickstart

The core loop, from a broker CSV export to a full report:

```bash
# 1. Convert your export to the canonical parquet (columns auto-detected)
quant ingest trades my_trades.csv -o trades.parquet

# 2. What does the strategy look like on its own?
quant metrics trades.parquet --equity 50000
quant verdict trades.parquet          # A-F scorecard + overfit flags

# 3. Pick a firm (18 verified presets)
quant prop firms list
quant prop firms show topstep_50k

# 4. Would THIS log have passed? (deterministic replay, day by day)
quant prop evaluate trades.parquet --firm topstep_50k

# 5. Would strategies LIKE this pass? (Monte Carlo over resampled days)
quant prop simulate trades.parquet --firm topstep_50k

# 6. Does the edge survive costs, decay, and multiple-testing deflation?
quant stress trades.parquet --firm topstep_50k --trials 5

# 7. Everything in one self-contained HTML file
quant report trades.parquet --firm topstep_50k -o report.html
```

`quant prop simulate` answers the questions that matter before buying a
challenge: pass probability (with CI), expected fees, expected payout value,
**net EV per attempt and per retry campaign**, VaR/CVaR, risk of ruin,
days-to-pass and days-to-first-payout distributions.

## 3. Command reference

Every command supports `--help`; the sections below explain what each one
is for, the knobs that change its answer, and how to read the output.

### `quant ingest trades` — CSV → canonical parquet

```bash
quant ingest trades my_trades.csv -o trades.parquet
```

Converts any broker/platform trade-log CSV into the canonical
`trades.parquet` every other command consumes. Columns are auto-detected
across common export formats, including messy values like `($151.57)`,
`$1,234.00`, and mixed date formats.

The canonical fields are: `entry_time`, `exit_time`, `symbol`, `side`,
`quantity`, `pnl` (net, in account currency), and optionally `fees`,
`mae`, `mfe`. Timestamps are stored tz-aware UTC; naive timestamps are
localized via the mapping's `tz`.

| Option | Meaning |
| --- | --- |
| `--mapping map.yaml` | Explicit column mapping when auto-detection guesses wrong — copy [`examples/trades_mapping.yaml`](examples/trades_mapping.yaml) and edit. |
| `--map pnl=NetPL` | Inline single-column overrides (repeatable), e.g. `--map tz=America/New_York`. |
| `-o / --output` | Output path (default `trades.parquet`). |
| `--currency` | Account currency label (default USD). |

**Include MAE/MFE columns if your platform exports them.** Without
per-trade excursions, intraday-sensitive rules (Apex-style real-time
trailing, daily loss limits) are checked at trade-close fidelity and
results are **optimistic** — every downstream report states which fidelity
was used.

### `quant ingest ohlcv` — normalize market bars

```bash
quant ingest ohlcv my_bars.csv --symbol demo --tz America/Chicago
```

Normalizes a user OHLCV bar CSV (any broker export). The output also feeds
`quant stress --ohlcv`. QuantConnect's Object Store requires a paid
organization: paid users can upload the file manually under Organization →
Object Store without API access, or use `--upload` only when CLI/API access is
available. `--symbol` names the default key `quantlab/<symbol>.csv`; `--key`
overrides it, `--tz` localizes naive timestamps, and `-o` sets the local file.

### `quant metrics` — strategy statistics

```bash
quant metrics trades.parquet --equity 50000     # --json for machine output
```

Standard statistics from the log alone, no firm involved: profit factor,
expectancy with bootstrap CI and t-stat, max drawdown, daily-annualized
Sharpe/Sortino, MAR, win/loss streaks, and profit concentration. `--equity`
sets the starting equity used for drawdown/Sharpe context. The JSON carries
the same fidelity/gross-PnL caveats as the table (the `warnings` array).

### `quant verdict` — A–F scorecard

```bash
quant verdict trades.parquet          # --json / --html verdict.html
```

Grades the strategy on four pillars — edge, robustness, risk, sample size —
each capped by what the sample can actually support, plus overfit flags
(e.g. profit concentrated in a handful of days, regime-dependent edge).
A small log cannot earn an A no matter how pretty its equity curve; that is
deliberate.

### `quant prop firms` — list and inspect presets

```bash
quant prop firms list                 # 18 presets: account size, eval phases, verified date
quant prop firms show apex40_50k_eod  # full resolved rules, payout policy, fees, citations
```

`show` prints the complete resolved configuration — every rule with its
parameters, the payout policy, the fee schedule, `verified_as_of`, and the
source URLs. Works on preset names and custom YAML paths alike.

### `quant prop evaluate` — deterministic replay

```bash
quant prop evaluate trades.parquet --firm topstep_50k
```

Replays **your actual log**, in order, against the firm's rules: a
day-by-day timeline of balance, the trailing floor, rule hits, phase
transitions, and the final outcome. This answers "would this exact history
have passed?" — the Monte Carlo answers the more useful "how often would
strategies like this pass?".

| Option | Meaning |
| --- | --- |
| `--phase challenge` | Evaluate one phase in isolation instead of chaining all phases through the log. |
| `--equity-csv eq.csv` | Cross-check intraday-sensitive rules against a TRUE mark-to-market equity curve (`datetime,equity`, e.g. from `quant cloud results --chart`) instead of fill-level reconstruction — catches open-equity breaches fills can't see. |

### `quant prop simulate` — the Monte Carlo

```bash
quant prop simulate trades.parquet --firm topstep_50k
```

The core of the system. Trading **days** are resampled from your log
(stationary block bootstrap by default), each simulated day replays its
trades against the full rule set, vectorized across paths, through the
challenge phase(s) and the funded phase — payouts, fees, resets and all.
Output: pass probability with Wilson CI, days-to-pass quantiles, funded
risk of ruin, payout probability and days-to-first-payout, expected fees,
expected payouts, **net EV per attempt and per retry campaign**, VaR/CVaR,
and an EV decomposition whose bars sum to the headline EV exactly.

Engine knobs:

| Option | Meaning |
| --- | --- |
| `--paths` | Monte Carlo paths (default 10 000; 10k × 250 days ≈ 1 s). |
| `--seed` | Reproducibility; identical seed ⇒ identical numbers. |
| `--bootstrap` | `stationary` (default; preserves streaks/vol clustering, block length auto-tuned via Politis–White) \| `iid_day` \| `iid_trade`. |
| `--block-len` | Override the automatic block length. |
| `--challenge-horizon` / `--funded-horizon` | Trading-day caps per phase (defaults 120 / 252). |

Position-sizing what-ifs:

| Option | Meaning |
| --- | --- |
| `--scale 0.5` | Rerun everything at a fraction/multiple of your size (`--challenge-scale`/`--funded-scale` to split by phase). |
| `--sizing vol_target` | Dynamic per-path EWMA vol-targeted sizing with strict day-start information; tune with `--vol-lambda` (default 0.94), `--vol-target` (default: median EWMA sigma of the log), `--vol-clip-lo/hi` (0.5/1.5). |
| `--sizing cushion` | The prop-native heuristic: size by the live buffer above your drawdown floor — weight = cushion today / initial allowance, clipped to `--cushion-clip-lo/hi` (0.25/1.5). Auto de-risks toward the floor. |
| `--base-contracts` | Your real allowance in mini-equivalents (1 mini = 10 micros by default), used to bind **contract scaling plans** (Topstep XFA balance tiers, Apex 4.0 half-size-until-safety-net). Defaults to the log's peak concurrent gross exposure — a warning states the assumption whenever the default is used. |

Funded-phase payout policy:

| Option | Meaning |
| --- | --- |
| `--payout-policy keep_buffer --keep-buffer 2000` | Withdraw only what's above the payout floor **plus** $2 000 — leave a cushion working instead of the default withdraw-max-ASAP. |
| `--extract-weight 0.5` | Once the cycle's qualifying days are banked, cut size to this weight until the payout lands (protect the banked cycle). |

Real-world overheads (also on `quant stress` and `quant report`):

| Option | Meaning |
| --- | --- |
| `--extra-monthly 39` | Recurring $/mo overhead (data feed, platform) folded into every EV figure. |
| `--per-payout-fee 30` | Processing cost deducted from each payout. |
| `--payout-haircut 0.1` | **Your own** counterparty assumption (0–1): fraction of payout value lost to denials/delays/firm failure. Presets ship 0; every output labels this a user-supplied assumption. |

Extras: `--accounts 2,3,5` appends the multi-account table (copy-trading k
accounts is k× leverage, not diversification — real correlated numbers next
to the independence illusion); `--json out.json` writes the machine-readable
summary (`prop_simulation` schema v4, including the `sizing` and `policy`
blocks).

### `quant prop frontier` — position-size sweep

```bash
quant prop frontier trades.parquet --firm topstep_50k --scales 0.5,1.0,1.5,2.0
```

Sweeps position-size multiples with common random numbers (same seed and
day draws per grid point, so differences are the treatment effect, not MC
jitter) and reports EV, pass probability, funded ruin, and CVaR vs scale —
plus the **EV-maximizing scale** and the **risk-constrained pick** (largest
scale keeping funded ruin under `--ruin-cap`, default 50%), which is
usually smaller. Contract scaling plans stay enforced at every multiple, so
the frontier is honest at >1×. `--chart frontier.html` writes a
self-contained chart; `--accounts 2,5` adds the multi-account table;
`--json` for machine output.

### `quant prop policies` — funded-phase payout policies

```bash
quant prop policies trades.parquet --firm apex40_50k_eod --buffers 0,1000,2000,4000
```

Withdraw-ASAP is a **policy, not a law**: withdrawing shrinks the cushion
above the trailing floor, so "take money off the table now" trades directly
against "survive longer, extract more later". This command reruns the full
Monte Carlo per policy cell — `--buffers` levels (0 = asap) × with/without
`--extract` (extraction weight, default 0.5; pass 0 to disable the column)
— with common random numbers, and reports pass prob, EV, funded ruin,
P(≥1 payout), median days to first payout, and expected withdrawals per
cell, flagging the best-EV and lowest-ruin policies. `--sizing` composes
with any sizing mode. Empirically the buffer often **compounds** (higher
long-run EV) but delays the first payout, so payout-conditioned ruin can
rise — neither direction is universal, which is exactly why the grid runs
on your own distribution. Inert axes are labeled (e.g. Topstep XFA pays
the same day qualifying completes, so extraction never activates there).

### `quant prop geometry` — no-trade-log exploration

```bash
quant prop geometry --firm topstep_50k --win-rate 0.5 --rr 1.0 --trades-per-day 3
```

No trade log at all? Generates a synthetic strategy from a risk geometry —
`--win-rate`, `--rr` (reward:risk), `--trades-per-day`, `--risk` ($ per
trade), `--ev` ($ per trade, default 0), `--days` — and runs the full
Monte Carlo on it. Useful for exploring how firm rules interact with
geometry before any strategy exists. (For pure barrier rules at zero EV,
pass probability is geometry-independent in the diffusion limit; geometry
effects come from day-scale rules — daily loss limits, consistency, time
limits — and finite trade sizes.)

### `quant stress` — the reality check

```bash
quant stress trades.parquet --firm topstep_50k --trials 5
```

The honesty layer. Sections, in order:

- **Cost sweep** — expectancy and MC pass probability across a slippage ×
  commission grid, a stop-stress row (`--stop-slip` extra ticks on stops),
  and a breakeven-ticks headline: how much friction the edge can absorb.
  `--tick-value` and `--commission` override the auto-resolution
  (ES/MES/NQ/MNQ are built in). Includes the Davey 2×-costs survival test.
- **Edge decay** — is the edge deteriorating *inside* the log: split-half
  comparison, HAC-robust trend, Mann–Kendall, runs test, rolling
  expectancy (`--window`), plus literature-anchored decay scenarios
  (26% / 50% / 58% / 90%) — never a half-life fitted to one log, which is
  statistically unidentifiable. `--oos-start 2026-03-01` declares where
  out-of-sample begins (e.g. the strategy went live) and adds the
  walk-forward-efficiency row.
- **Deflated statistics** — PSR and MinTRL always; with `--trials N` (how
  many strategy variants you tried before this one) also the Deflated
  Sharpe Ratio, MinBTL, and the Harvey–Liu haircut Sharpe.
- **Permutation drawdowns** — trade-order-shuffled max-drawdown
  distribution; `--ruin-capital` adds P(ruin) at your capital.
- **Volatility clustering** — ARCH-LM and McLeod–Li tests (honest
  "insufficient data" verdicts on short logs) plus a fixed-vs-vol-targeted
  sizing counterfactual.
- **Regime analysis** — per-day EWMA-sigma tercile regimes, per-regime
  PnL/persistence, a worst-regime-persists stress (labeled stress, never
  forecast); `--ohlcv bars.csv` adds a descriptive trend × vol market join.
- **Sampling-uncertainty band** — a nested bootstrap (`--outer` resamples
  of the source days × `--inner-paths` MC paths each) showing what the log
  itself can pin down: the p5–p95 pass-prob/EV band next to the Wilson CI,
  which only measures simulation noise. `--outer 0` skips it.

The overhead knobs (`--extra-monthly`, `--per-payout-fee`,
`--payout-haircut`) apply here too, but — like the MC pass-prob columns
they feed — only when `--firm` is given; without a firm there is no EV to
fold them into and they are ignored. `--json` for machine output. Methods
and thresholds are literature-anchored — citations in
[docs/research-notes.md](docs/research-notes.md).

### `quant pbo` — probability of backtest overfitting

```bash
quant pbo variants.csv --partitions 16
```

Feed the per-variant **daily PnL** of every strategy version you tried
(one column per variant — e.g. a QC parameter sweep — one row per day,
optional date column). Runs CSCV (Bailey–Borwein–López de Prado–Zhu):
PBO ≈ 0.5 means your in-sample winner is a coin flip out-of-sample; near 0
means it genuinely dominates. This is the *measured* complement to the
*declared* `--trials N` on `quant stress`.

### `quant report` — everything in one HTML

```bash
quant report trades.parquet --firm topstep_50k -o report.html
```

Metrics + verdict + prop Monte Carlo + reality check in a single
**self-contained** HTML file (plotly inlined; open it anywhere): fan
charts, day-resolution histograms, payout distribution, the EV waterfall
(path-exact — bars sum to the headline EV to the cent), the policy/sizing
configuration, every warning and assumption, and a firm-rules appendix
with citations. Key knobs: `--paths`, `--seed`, `--scale`, `--trials`,
`--equity` (defaults to the firm's account size), `--no-reality` to skip
the reality-check section, `--outer/--inner-paths` for the sampling band,
`--ohlcv` for the market join, the three overhead knobs, and
`--json out.json` for the combined machine-readable bundle
(`schema_version` 4).

### `quant cloud` — QuantConnect Cloud web workflow

The supported workflow does not use the QuantConnect REST API or lean CLI.
Only a standalone strategy `main.py` executes in QuantConnect Cloud. The
local package imports the completed backtest and performs the prop-firm
analysis and reporting.

#### Deploy and backtest online

1. Sign in to [QuantConnect Algorithm Lab](https://www.quantconnect.com/terminal)
   and create a new **Python** project.
2. Replace the Cloud project's `main.py` with one of the files below.
3. Do **not** copy `config.json`. It is local LEAN CLI metadata, not a Cloud
   IDE source file. Set the project description or parameters in the Project
   panel if needed.
4. Click **Build**, resolve every compiler error, then click **Backtest**.
5. On the completed backtest page, inspect Overview, Orders, Trades, and Logs.
6. In **Overview**, click **Download Results**. Do not use Download Trades for
   this importer because the full result JSON also carries charts and metadata.
7. Import the downloaded file locally:

```bash
quant cloud results --downloaded-results ~/Downloads/backtest.json \
  --output trades.parquet --chart
quant report trades.parquet --firm apex40_50k_eod -o report.html
```

`--from-json` remains an alias for `--downloaded-results`. Add
`--firm <preset>` to the results command to run the open-equity cross-check;
it implies `--chart`. QuantConnect applies chart-point quotas, so a downloaded
equity series can miss an intrabar breach between retained points. The report
labels this limitation.

No `QC_USER_ID`, `QC_API_TOKEN`, Object Store write, Docker installation, or
local LEAN process is used by this path.

#### Cloud-ready strategy files

| Cloud project source | Data | Organization requirement |
| --- | --- | --- |
| [`sma_cross_futures/main.py`](cloud/strategies/sma_cross_futures/main.py) | QuantConnect built-in continuous ES minute data | Free Cloud backtesting is supported |
| [`orb_equity/main.py`](cloud/strategies/orb_equity/main.py) | QuantConnect built-in SPY minute data | Free Cloud backtesting is supported |
| [`custom_data_demo/main.py`](cloud/strategies/custom_data_demo/main.py) | User CSV through QuantConnect Object Store | **Paid organization** with storage permission |

Each file is self-contained, imports only Python's standard library plus
`AlgorithmImports`, contains one `QCAlgorithm`, and is below the current
32 KB Free-tier per-file limit. The custom-data project is not a Free-tier
path because QuantConnect currently limits Object Store access to paid
organizations. Manual Object Store upload avoids the REST API but not the paid
storage requirement.

#### Use your own strategy

A normal Cloud `QCAlgorithm` needs no quantlab-specific export block.
QuantConnect's **Download Results** artifact supplies the closed-trade records
and Strategy Equity chart.

1. Keep one `QCAlgorithm` subclass in `main.py`.
2. Use QuantConnect Dataset Market subscriptions or Cloud-compatible custom
   data. Never reference a Windows path, this repository, a local service, or a
   local virtual environment from the algorithm.
3. Add helper `.py` files through the Cloud Explorer if needed. Keep every
   file within the organization tier's size quota.
4. Build and backtest in Cloud, then import the Overview download as above.

The examples intentionally keep their backtest dates and sizing in source so a
fresh paste runs without configuring project parameters. If you parameterize a
strategy, add values in the Cloud Project panel and read them with
`self.get_parameter`.

#### Verification boundary

Local CI checks Python syntax, project structure, result parsing, file-size
limits, and the no-credentials import path. It cannot compile against the
current hosted LEAN build, prove QuantConnect data availability, or replace a
real browser-download smoke test. Before
relying on a strategy, perform the manual Cloud gate: **Build succeeds,
Backtest completes, no runtime error appears, trades are present, Download
Results imports successfully, and the generated report opens**.

See [docs/quantconnect-cloud.md](docs/quantconnect-cloud.md) for the complete
runbook, current platform constraints, troubleshooting, and official source
links.

## 4. Firm presets and custom firm YAMLs

18 presets with rule parameters **verified against official firm sources on
2026-07-19** (citations inside each YAML):

| Presets | Firm / product |
| --- | --- |
| `topstep_{50k,100k,150k}` | Topstep Trading Combine + Express Funded Account |
| `apex40_{25k,50k,100k,150k}_{intraday,eod}` | Apex 4.0 evaluation + PA (the product line sold since 2026-03-01; both trailing conventions) |
| `tpt_{25k,50k,75k,100k,150k}` | Take Profit Trader |
| `ftmo_{2step,1step}_100k` | FTMO 2-Step / 1-Step |

Encoded mechanics include: EOD vs intraday high-water ratchets with
always-real-time breach tests and threshold locks; pause-not-fail daily
loss lockouts; FTMO's midnight-re-anchoring daily loss and refundable fee;
consistency rules that raise targets or gate payouts; Apex 4.0's 30-day
expiry, payout cap ladders, and 6-payout lifetime account closure;
**contract scaling plans enforced in-engine** (Topstep XFA balance tiers;
Apex half-of-firm-max until the safety-net unlock, sticky once earned).

**Custom firms**: copy any preset from
[`src/quantlab/prop/firms/`](src/quantlab/prop/firms) and pass the path to
`--firm`. The shape:

```yaml
name: my_firm_50k
display_name: "My Firm 50K"
account_size: 50000
day_boundary: {tz: America/Chicago, cutoff_hour: 17}   # session roll
phases:                          # evaluation phases, in order; each needs profit_target
  - name: challenge
    profit_target: 3000
    rules:
      - {type: trailing_drawdown, amount: 2000, ratchet: eod}   # or ratchet: intraday
      - {type: min_trading_days, days: 2}
funded:                          # no profit target
  name: funded
  rules:
    - {type: trailing_drawdown, amount: 2000, ratchet: eod, threshold_cap: 50100}
    - {type: daily_loss_limit, amount: 1000, effect: lockout}   # pause-not-fail
    - {type: consistency, max_best_day_pct: 50, basis: total_profit, effect: gate_payout}
    - {type: scaling_plan, half_until_safety_net: true}         # or tiers: [{min_balance, max_contracts}, ...]
    - {type: contract_limit, max_contracts: 10}                 # the firm's full allowance
payout:
  profit_split: 0.9
  min_payout: 500
  period_days: 14
  qualifying_days: {count: 5, min_daily_profit: 50}
  safety_net_floor: 52100        # balance must stay >= after payout
  # also available: payout_cap_ladder, max_lifetime_payouts,
  # payout_share_of_balance, buffer_above_initial, reactivations
fees:
  one_time: 149                  # or monthly: (exclusive); plus reset, activation,
  activation: 85                 # refundable_on_first_payout, extra_monthly,
                                 # per_payout, payout_haircut
verified_as_of: "2026-07-19"
sources: ["https://..."]
```

Rule types: `trailing_drawdown`, `static_max_loss`, `daily_loss_limit`,
`consistency`, `min_trading_days`, `time_limit`, `contract_limit`,
`scaling_plan`. Amounts accept `pct` instead of `amount` where a firm
defines rules as percentages (FTMO). `quant prop firms show my_firm.yaml`
validates and prints the resolved config.

**Prop firms change rules constantly** (Apex replaced its entire product
line in March 2026; Topstep, TPT, and FTMO all changed 2024–2026). Check
`verified_as_of` and re-verify before relying on EV numbers.

## 5. How the simulation works

Trading **days** are resampled with a stationary block bootstrap
(preserving streaks/volatility clustering; IID modes available), then each
day replays its trades step-by-step against the rule set, vectorized
across paths. A scalar evaluator implements identical semantics and a
golden-equivalence test suite forces exact agreement — including dynamic
vol-targeted sizing, cushion sizing, and scaling-plan caps. 10k paths ×
250 days runs in ~1 s.

Per-path day weights compose in a fixed order: sizing weight
(fixed / vol_target / cushion) × extraction multiplier, then capped by the
scaling plan — no sizing mode may exceed the firm's allowed size, and a
cap never scales a weight *up*.

Validation anchors (zero-EV synthetic strategies):

- static floor/target hit gambler's-ruin `D/(T+D)` exactly;
- an uncapped trailing drawdown hits `exp(-target/drawdown)` — and is
  **geometry-independent** (Brownian scale invariance). Sensitivity to
  win-rate/RR geometry appears only through rules with absolute day-scale
  parameters (daily loss limits, consistency, time limits) — a refinement
  of the popular claim that low-RR/high-win-rate always passes trailing
  challenges more often.

## 6. Reading the numbers honestly

The tool is deliberately noisy about its own limits. Things it will tell
you, and that you should not ignore:

- **Fidelity**: without MAE/MFE columns, intraday-sensitive rules are
  checked at trade-close fidelity and results are optimistic. The
  `--equity-csv` / `--chart --firm` cross-check exists because even
  fill-level replay can miss open-equity breaches.
- **Assumptions are labeled**: the same-fill linear-scaling assumption on
  every sizing what-if; the scaling-plan base-contracts assumption when
  derived from the log; the payout haircut as a user-supplied counterparty
  assumption. These warnings propagate into stress, report, frontier, and
  policy-grid output — they are part of the answer, not decoration.
- **Small logs**: the scorecard caps grades by sample size; the
  sampling-uncertainty band shows what the log can and cannot pin down;
  short logs downgrade the bootstrap and say so.
- **Multiple testing**: `--trials` and `quant pbo` exist because your best
  backtest is biased by however many you threw away.
- **Schema versions**: machine-readable outputs carry `schema_version`
  (currently 4) so downstream consumers can detect format changes.

Methods and thresholds are cited in
[docs/research-notes.md](docs/research-notes.md), including what is
**documented but deliberately not modeled** (conduct/news rules,
attempt-to-attempt psychology, payout-denial rates).

## 7. Related projects

[`projects/llm_edge`](projects/llm_edge) — a self-contained research
project (own package, tests, and report) testing whether an LLM can create
a genuinely novel, empirically validated trading edge under a
pre-registered protocol with a locked holdout. See its
[README](projects/llm_edge/README.md) and final
[REPORT.md](projects/llm_edge/REPORT.md); it does not affect the `quant`
CLI.

[`docs/rohonchain-review.md`](docs/rohonchain-review.md) — a claim-by-claim
review of a widely-shared social-media quant corpus (Polymarket arbitrage,
Kelly sizing, Markov regime models), tracing each claim to its academic
source and separating the real math from the profit marketing. A worked
example of the skepticism [§6](#6-reading-the-numbers-honestly) asks for.

## 8. Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest
```

- ~790 tests, including golden scalar↔vector equivalence, analytic
  anchors, formula pins against published worked examples, and a
  performance budget. CI runs the same gates on Python 3.11 and 3.12 —
  no Docker, no network.
- Layout: `src/quantlab/` (schema, ingest, metrics, prop engine + firm
  YAMLs, report, cloud, CLI), `tests/`, `cloud/strategies/` (LEAN
  examples), `examples/` (sample data + mapping), `docs/research-notes.md`
  (citations and modeling decisions).
