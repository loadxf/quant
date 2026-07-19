# Research notes: edge decay, backtest overfitting, and cost realism

Sources behind the Reality Check module (`quant stress`, the report's
"Reality check" section, and the scorecard's PSR/DSR gates). Every number
and formula below was verified against the primary source (July 2026).

## Why this module exists

A widely-shared argument (correct in spirit): markets adapt — an edge that
is published, sold, or crowded decays; a backtest without costs shows
phantom edges; and a strategy picked from many tries is partly luck. The
theoretical frame is Lo's **Adaptive Markets Hypothesis** (Lo, *The
Adaptive Markets Hypothesis*, Journal of Portfolio Management 30(5),
2004): efficiency is time-varying — opportunities appear, get competed
away, and re-emerge. Trading a real edge pushes prices toward efficiency;
crowding is what kills it.

## Edge decay: the verified numbers

| Claim | Verified value | Source |
|---|---|---|
| Out-of-sample decline of published predictors (statistical-bias upper bound) | **26%** | McLean & Pontiff, *Does Academic Research Destroy Stock Return Predictability?*, Journal of Finance 71(1), 2016 |
| Total post-publication decline | **58%** (≈32% attributable to publication-informed trading) | same |
| Post-publication decay outside the US | **not reliably present** — US-specific phenomenon | Jacobs & Müller, *Anomalies across the globe: Once public, no longer existent?*, Journal of Financial Economics 135(1), 2020 |
| Live vs backtest Sharpe | ≈ **50%** of backtest; decay worsens ~5ppt per publication year and with signal complexity | Falck, Rej & Thesmar, *When do systematic strategies decay?*, Quantitative Finance, 2022 |
| Anomaly attenuation in the high-liquidity era | roughly **halved** post-decimalization | Chordia, Subrahmanyam & Tong, Journal of Accounting & Economics 58(1), 2014 |
| Canonical crowded-strategy decay | contrarian returns **1.38%/day (1995) → 0.13%/day (2007)**; Sharpe 53.9 → 4.5 | Khandani & Lo, *What Happened to the Quants in August 2007?*, Journal of Financial Markets 14(1), 2011 |
| Measured vs true alpha during repricing | early-life returns can be **inflated** ~1.4%/yr by repricing flows | Pénasse, *Understanding Alpha Decay*, Management Science 68(5), 2022 |

These anchor the tiered **haircut scenarios** (26% / 50% / 58% / 90%).
The 58% tier is flagged US-specific per Jacobs & Müller.

**Deliberately refused:** fitting an exponential decay / "half-life" to a
single trade log. Decay rates are only identified cross-sectionally
(across many predictors/vintages); from one realization a fitted
half-life is indistinguishable from an ordinary drawdown. The tool offers
scenario haircuts only.

## Multiple-testing corrections (implemented)

- **PSR** (Probabilistic Sharpe Ratio) and **MinTRL** — Bailey & López de
  Prado, *The Sharpe Ratio Efficient Frontier*, Journal of Risk 15(2),
  2012. PSR(SR*) = Φ((SR−SR*)·√(n−1)/√(1−γ₃SR+(γ₄−1)/4·SR²)), raw
  kurtosis, per-trade SR. MinTRL = 1 + [denominator²]·(z_α/(SR−SR*))².
- **DSR** (Deflated Sharpe Ratio) — Bailey & López de Prado, *The
  Deflated Sharpe Ratio*, Journal of Portfolio Management 40(5), 2014.
  DSR = PSR at SR₀ = √V[SR]·((1−γ)Z⁻¹(1−1/N)+γZ⁻¹(1−1/(Ne))),
  γ ≈ 0.5772 (Euler–Mascheroni). With a single log, V[SR] is proxied by
  the SR estimator's own variance — a documented understatement when the
  true trial spread was wider.
- **MinBTL** — Bailey, Borwein, López de Prado & Zhu, *Pseudo-Mathematics
  and Financial Charlatanism*, Notices of the AMS 61(5), 2014. Years of
  backtest needed before an annualized SR of 1.0 exceeds the expected max
  of N random tries (their worked example: N=45 → ≈5 years).
- **Harvey–Liu haircut Sharpe** (Bonferroni variant) — Harvey & Liu,
  *Backtesting*, Journal of Portfolio Management 42(1), 2015. The
  Holm/BHY variants need the full cross-section of tried strategies, so
  only the Bonferroni haircut is honest from one log + a declared trial
  count.
- **t > 3.0 for novel factors** — Harvey, Liu & Zhu, *…and the
  Cross-Section of Expected Returns*, Review of Financial Studies 29(1),
  2016. The scorecard's sample-pillar A-grade already requires t ≥ 3.0.
- **Politis–White automatic block length** (stationary bootstrap) —
  Politis & White, Econometric Reviews 23(1), 2004, with the Patton,
  Politis & White (2009) correction; cross-checked against the `arch`
  package implementation.
- **Wald–Wolfowitz runs test** on the win/loss sign sequence — flags
  streak dependence, under which iid-based analyses (trade-order
  permutation, iid bootstrap) understate risk.
- **SQN** (Van Tharp's System Quality Number) — the retail-standard label
  for the t-statistic of mean trade PnL; Van Tharp caps the √n factor at
  n=100. Thresholds: <1.6 poor, 2.0–2.5 average, 2.5–3 good, 3–5
  excellent, >5 superb. Reported for familiarity; it IS the t-stat.

## Documented but NOT implemented (needs data one log lacks)

- **PBO via CSCV** (Bailey, Borwein, López de Prado & Zhu, Journal of
  Computational Finance, 2017) — needs the T×N return matrix across all
  N tried configurations.
- **White's Reality Check / Hansen's SPA / Romano–Wolf** — need the full
  cross-section of tested strategies; the degenerate single-strategy case
  collapses to the bootstrap expectancy CI the tool already reports.
- **Aronson's Monte Carlo permutation test** (*Evidence-Based Technical
  Analysis*, Wiley 2007) — permutes detrended market returns against the
  rule's signals; needs bar data + signals, not just fills.
- **Capacity / market impact** — the square-root impact law (impact ∝
  σ√(Q/V)) and decreasing returns to scale (Pástor, Stambaugh & Taylor,
  *Scale and Skill*, JFE 2015) need volume/participation data. Reported
  edges are capacity-agnostic; nothing in a trade log bounds how much
  capital the edge supports.

## Cost realism (defaults shipped)

- Tick values (CME specs): ES $12.50, MES $1.25, NQ $5.00, MNQ $0.50
  (0.25-point ticks). All-in round-turn commissions, mid-range of 2025–26
  retail pricing: micros ≈ $1.50, minis ≈ $3.00 (broker + exchange +
  regulatory; verify quarterly).
- Slippage conventions (Davey, *Building Winning Algorithmic Trading
  Systems*; Pardo, *The Evaluation and Optimization of Trading
  Strategies*; corroborated by practitioner forums): ~1 tick/side on
  liquid RTH market orders, 2 ticks conservative; **stops fill worse**
  (2–4 ticks on gaps/news) — hence the separate stop-stress row; a real
  edge should survive **2× assumed costs** (the "Davey survival" anchor).
- Trade-order permutation drawdown (Davey's "trades in a hat"):
  median/p95 max-DD and P(ruin) with the explicit caveat that permutation
  assumes independence — the block-bootstrap numbers are the
  streak-honest counterpart.

## Prop-firm cost gotchas (community-sourced, worth modeling)

Eval fees recur monthly until you pass; market-data fees (~$39/mo, more
with depth) are separate; payouts carry processing fees (~$30) and
consistency-rule delays; activation fees and habitual resets push the
real cost of maintaining an eval funnel well above the sticker price.
The economics module models recurring fees, resets, activation, and
payout gating; data fees and processing fees are listed here as a manual
adjustment.

## Fact-check of the motivating video's anecdotes

- Gerry Bamberger (Columbia CS) did pioneer pairs trading at Morgan
  Stanley (~1982–83), but left in 1985 — two years before the ~$50M
  (1987) year of Nunzio Tartaglia's APT group. The video conflates the
  two.
- Lineage: Morgan Stanley APT → D.E. Shaw (1988, David Shaw) → Two Sigma
  (2001, Overdeck & Siegel, both ex-D.E. Shaw). Two Sigma is one
  generation removed from Morgan Stanley.
- The January-2025 unsealed case is real: Cheuk Fung "Richard" Ho,
  ex-Headlands Technologies quant, SDNY trade-secrets indictment over
  code valued at $1B+.
- The video's decay numbers ("~10% bias, ~25% post-publication") are
  roughly HALF the published McLean–Pontiff figures (26% / 58%).

## Volatility clustering and vol-targeted sizing (M9)

Motivated by a video on GARCH forecasting; the theory verified, the
numbers corrected:

- **History**: Engle (1982, Econometrica) introduced ARCH; the 2003
  Nobel was **shared with Clive Granger** (the video omits him).
  Bollerslev (1986, J. Econometrics) — Engle's PhD student — extended it
  to GARCH. Volatility clustering is a canonical stylized fact
  (Mandelbrot 1963; Cont 2001; Schwert 1989 back to the 1800s).
- **Estimator policy**: GARCH(1,1) MLE is negatively biased and unstable
  in small samples — **≥500 observations recommended** (Hwang & Valls
  Pereira, European J. of Finance, 2006). Trade logs are typically
  60–250 days, so the default forecast is **EWMA/RiskMetrics λ=0.94**
  (J.P. Morgan RiskMetrics Technical Document, 4th ed., 1996 — the
  restricted IGARCH case, half-life ≈11 days). GARCH is offered above a
  250-day hard floor (warning under 500) with variance targeting
  (Engle & Mezrich 1996) and automatic EWMA fallback.
- **Sizing rule**: weight = clip(target/σ_forecast, 0.5, 1.5) — the
  1.5× cap per Moreira & Muir (J. Finance 2017); target defaults to the
  trader's own median forecast σ so median weight is 1 (never injects
  leverage a prop firm bars). Strict t−1 information; burn-in seeded
  from the first 20 days only.
- **What to expect**: vol targeting is **insurance, not return
  enhancement** — Harvey et al. (JPM 2018) find tail/drawdown reduction
  for risk assets with roughly Sharpe-neutral returns, and Cederburg,
  O'Doherty, Wang & Yan (JFE 2020) show Moreira–Muir's Sharpe gains
  largely vanish out-of-sample. Under static dollar prop limits the
  survival benefit is **conditional** (Grossman & Zhou 1993 for the
  drawdown-constraint theory): it helps when losses cluster in
  high-forecast-vol periods and can hurt otherwise — which is why the
  simulator MEASURES it per log (fixed vs vol-targeted comparison and
  the `--sizing vol_target` MC mode) instead of promising it.
- **Clustering diagnostics**: Engle's ARCH-LM (T·R² ~ χ²(q)) and
  McLeod-Li (1983) on squared daily PnL; χ² tail probabilities via the
  regularized upper incomplete gamma (Numerical Recipes 6.2, ~1e-10).
  Clustering present ⇒ the block bootstrap is essential and vol
  targeting likely matters; absent ⇒ it likely will not help.
- **Counterfactual caveat** (printed on output): same-fill
  linear-scaling assumption — identical entries/exits at scaled size;
  ignores sub-contract granularity, margin, and larger-size psychology.
- NOT adopted from the video: its downloadable Claude skill / Pine
  indicator (unvetted third-party code), GARCH-first estimation at
  trade-log sample sizes, and any "extra return" framing.

## M10 — everything-review verifications and economics ledger

Findings from the full completeness/correctness review (three parallel
audits + direct re-verification of every flagged defect).

- **Apex 50K "preset drift" — REFUTED.** A gap-analysis pass flagged our
  $2,000 trailing drawdown against 2026 secondaries quoting $2,500. Direct
  re-verification: $2,500 belongs to the **legacy (pre-2026-03) product**;
  the Apex 4.0 line these presets model is $3,000 target / $2,000 trailing
  / $1,000 DLL (Apex "Legacy Evaluation Rules" help-center article vs the
  4.0 rules articles cited in the YAMLs). Presets unchanged.
- **Back2Funded reactivations (Topstep)**: now valued as an *analytic
  option* in `economics.summarize` — eligibility mirrors the firm rule
  (account lost before any payout, max 2, $599 each; only sold before the
  first payout), each paid reactivation is approximated as a fresh funded
  phase worth E[received], the k-th opportunity arises with probability
  ruin^k, and every term is floored at zero because exercise is optional.
  Reported SEPARATELY from headline EV ("what the option is worth if you'd
  exercise it"), never silently added. Generic point (verified): for a
  marginal trader a fresh funded account is often worth *less* than $599 —
  the report now computes this per log instead of assuming either way.
- **Data/platform fees**: the deferred ledger assumed ~$39/mo mandatory
  data fees. Verified wrong for the modeled funnel: Topstep Level-1 data
  is **free during the Combine** (the ~$38/mo item is the optional L2
  add-on) and CME professional data fees (~$133/mo/exchange) apply to
  **Live Funded accounts only** — beyond the simulated eval→XFA/PA phases.
  Hence no firm-specific data-fee model; instead the generic
  `--extra-monthly` / `--per-payout-fee` knobs (FeeSchedule.extra_monthly /
  per_payout) let a trader bill their own overheads into every EV figure
  (density-aware months, same convention as subscription fees).
- **Equity-curve trading** (pausing/sizing by your own equity curve —
  a recurring guru claim): only helps when PnL is serially dependent;
  the runs test in the decay panel is exactly the test for that. If runs
  z ≥ 0 (no loss clustering), equity-curve filters just delete random
  trades. No feature needed — the decay panel already answers it.
- **Log-selection / survivorship caveat**: every number the tool emits is
  conditional on the ONE log you fed it. If that log was picked from
  several attempts/accounts because it looked best, all statistics inherit
  that selection bias — the honest fix is `--trials N` (deflation) and
  feeding the *complete* trading history, not the good months.
- **Calendar seasonality**: day-of-week/month effects in trade logs are
  almost always noise at these sample sizes; the block bootstrap already
  preserves short-range dependence. Not modeled deliberately.
- **Per-symbol cost sweeps**: mixed-symbol logs get the dominant symbol's
  tick economics plus an explicit warning; a minority symbol with very
  different tick values is the residual risk (accepted, documented).
- **Stop-slippage stress**: a log does not record order types, so the
  all-exits-as-stops row is the correct worst-case bound (inherent input
  limitation, not a modeling gap).
