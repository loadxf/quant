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
