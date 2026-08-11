# Phase D novelty verdict — Family C010 + C015 (range-volatility / vol-of-range)

**Scope of this verdict.** Covers the family `roll_std(rng, 63)` with `rng = (high-low)/close`
(C015, 5-day hold; C010, 1-day hold): cross-sectional decile long-short, LONG highest
range-volatility, S&P 500 equities, 1-5 day holds.
Adversarial prior-art attack performed 2026-07-20 per `research/methodology/novelty_scale.md`
(frozen). This verdict is diagnostic only: the family already failed the empirical gates
(val t < 2; DSR unavailable after the mixed-window ledger defect in retrospective D5;
survivorship-suspect per the specs' own declared suspicion), so no tier
here promotes it.

**Verdict: T1 — recombination / re-parameterization of documented ideas.** Provenance grade
per specs: P-derived at the selection level, but the resulting expression is P-known —
near-neighbors of every component exist in pre-2026 text.

## The five nearest documented neighbors

### 1. Baltussen, Van Bekkum & Van der Grient (2018), "Unknown Unknowns: Uncertainty About Risk and Stock Returns," *JFQA* 53(4)
- **Characteristic: same abstract quantity.** Their VOV is the 20-day standard deviation of a
  stock's daily volatility proxy (ATM option implied vol), scaled by its mean (verified in the
  paper PDF, eq. (4)); a **robustness variant drops the scaling** — the unscaled version is the
  candidate's exact construction with implied vol replaced by the daily range fraction as the
  vol proxy. C010/C015 is a realized-range implementation of the vol-of-vol characteristic.
- **Sign: OPPOSITE.** High-minus-low VOV quintile earns −0.85%/month (verified in the PDF;
  unscaled variant "even stronger"), US and European equities, robust to >20 controls.
- **Horizon: monthly** rebalance vs the candidate's 1-5 days. Same asset class, same sort
  methodology. This is the closest conceptual neighbor; the candidate is a sign-flipped,
  range-proxy re-parameterization of it.

### 2. Blau & Whitby (2017), "Range-based volatility, expected stock returns, and the low volatility anomaly," *PLoS ONE* 12(11)
- **Characteristic: same raw input.** Sorts the US cross-section on Parkinson-motivated
  high-low range volatility (log of the month's high-low range). The candidate sorts on the
  *std* of the daily range rather than its level, but unscaled std-of-range and level-of-range
  are strongly correlated (the specs do not scale by mean range), so the sorts overlap heavily.
- **Sign: OPPOSITE.** Next-month returns monotonically decreasing in range vol; extreme-quintile
  spread ~1.1%/month, driven by lottery-like/high-IVOL stocks. Confirms the low-vol anomaly in
  range-based measures specifically.
- **Horizon: monthly.** Same asset class, same portfolio-sort logic.

### 3. Kakushadze (2016), "101 Formulaic Alphas" (arXiv 1601.00991 / Wilmott) — **Alpha#40**; duplicated as **GTJA Alpha191 #42**
- **Expression: same grammar, near-identical term.**
  `Alpha#40 = ((-1 * rank(stddev(high, 10))) * correlation(high, volume, 10))` — a rolling
  standard deviation of a daily price-extreme, cross-sectionally ranked. Guotai Junan's 191
  formulaic alphas (2017) contain the identical expression as Alpha42 (verified in multiple
  public implementations). AlphaGen-style mined libraries likewise emit `Var(low, 50)`-type
  range/extreme-variance terms (see `research/prior_art/llm_in_trading.md` C10).
- **Sign: OPPOSITE on the std term** (the −1 shorts high std-of-high).
- **Horizon: SAME.** The 101 alphas' average holding periods are 0.6-6.4 days — exactly the
  candidate's 1-5 day regime. The *method* (evolutionary/formulaic search over an OHLCV
  operator grammar including rolling Std) is wholesale documented prior art
  (factor_db `x_method_101_alphas`; llm_in_trading.md C7-C24), which is why the specs
  themselves declared a T1 method ceiling.

### 4. Ang, Hodrick, Xing & Zhang (2006), "The Cross-Section of Volatility and Expected Returns," *JF* 61(1)
- **Characteristic: parent family.** Canonical cross-sectional volatility sorts (factor_db
  entries `cz_IdioVol3F`, `cz_RealizedVol`, `cz_IdioVolCAPM`, direction −1). Because the
  candidate's std-of-range is unscaled, it is highly correlated with the *level* of range
  volatility, making the candidate largely a repackaged volatility sort. Related same-family
  entries with the same negative sign: Bali-Cakici-Whitelaw MAX/lottery (`cz_MaxRet`, JFE 2011),
  and rolling-std-of-activity signals Chordia-Subrahmanyam-Anshuman volume/turnover variability
  (`cz_VolSD`, `cz_std_turn`, JFE 2001, both −1 — rolling std of a daily market-activity series
  as a characteristic, negative premium).
- **Sign: OPPOSITE. Horizon: monthly.**

### 5. Documented POSITIVE-sign high-vol premia (the candidate's sign is also not undocumented)
- **Fu (2009), *JFE* 91(1):** conditional (EGARCH-expected) idiosyncratic volatility is
  *positively* priced in the cross-section — the classic documented long-high-vol result
  (later attributed to look-ahead bias by Critical Finance Review replication, but documented).
- **Khovansky & Zhylyevskyy (2013), *JBF* 37(8):** the idiosyncratic-volatility premium is
  *positive at daily frequency* while negative at monthly+ — documenting a horizon-dependent
  sign flip precisely at the candidate's 1-5 day horizon.
- **Nagel (2012), *RFS* 25(7) "Evaporating Liquidity":** short-horizon returns to liquidity
  provision concentrate in high-volatility stocks — the standard documented mechanism by which
  holding high-vol names over days earns a premium.
- **Closeness:** same sign, same short horizon, volatility-family characteristic (not
  range-std specifically).

## Verdict justification (one paragraph)

Every component of the family is documented, and so is the combination logic. The raw input
((high-low)/close as a daily volatility proxy) is Parkinson (1980) and is sorted on directly
by Blau-Whitby (2017); the transformation (rolling std of a daily vol proxy = vol-of-vol as a
stock characteristic, including the unscaled variant) is Baltussen et al. (2018); the exact
expression shape (cross-sectional rank of rolling stddev of a price extreme, held days) exists
verbatim in the two most-circulated mined-alpha libraries (WQ101 Alpha#40 = GTJA191 Alpha42);
and the generating method (fitness-selected search over an OHLCV expression grammar) is
documented prior art at the method level (Kakushadze 2016; AutoAlpha; AlphaGen; Alpha-GPT
lineage). The only aspect for which no exact match was found is the specific package
"LONG-high std-of-range, decile, 1-5d" — but that is a sign flip of documented sorts rather
than a new hypothesis class, the positive sign itself has documented near-neighbors at exactly
this horizon (Fu 2009; Khovansky-Zhylyevskyy 2013's daily-frequency positive premium; Nagel
2012's liquidity-provision mechanism), and the family's own empirical record (val t < 2,
DSR unavailable under retrospective D5, survivorship-suspect on a current-constituent
universe) indicates the flipped sign is
an artifact, not an undocumented premium. This is T1: recombination/re-parameterization with
obvious near-neighbors, not T2. No claim about nonexistence of further prior art is made;
findings are limited to the documented search scope below.

## Searches performed (actual queries)

Web searches (≥5 restatements of the hypothesis, 3+ independent angles):
1. `cross-section stock returns sorted "range-based volatility" high-low range Parkinson`
2. `"volatility of volatility" cross-section stock returns sorted portfolios Baltussen "Unknown Unknowns"`
3. `Blau Whitby range-based volatility expected stock returns low volatility anomaly`
4. `Fu 2009 idiosyncratic volatility positively related expected returns EGARCH cross-section`
5. `realized "vol-of-vol" OR "volatility of volatility" daily returns stock characteristic predicts returns not options-based`
6. `"alpha#40" "stddev(high" 101 formulaic alphas rank stddev`
7. `"daily price range" OR "high-low range" cross-section expected stock returns anomaly predictability`
8. `"volatility of volatility" stock returns China realized measure cross-sectional evidence`
9. `Nagel liquidity provision returns high volatility stocks short-term reversal premium daily horizon`
10. `alpha191 Guotai Junan formulaic alphas STD "HIGH-LOW" range expressions`
11. `"change in idiosyncratic volatility" OR "volatility innovations" predicts cross-section stock returns sign`

Primary-source verifications:
- Baltussen et al. full PDF fetched (Quantpedia mirror): VOV construction (eq. 4: 20-day std of
  daily ATM IV / mean IV), −0.85%/month High−Low spread, unscaled-VOV robustness confirmed.
- GitHub code search `"STD(HIGH" alpha191` and `"(high - low) / close" rolling std alpha`:
  confirmed GTJA Alpha42 / WQ101 Alpha#40 expression text in multiple independent
  implementations; (high-low)/close rolling constructions ubiquitous in public alpha code.
- arXiv 1601.00991 (101 Formulaic Alphas) abstract page fetched; Alpha#40 text confirmed via
  public implementations.

Local prior-art DB checks:
- `factor_db.json` (393 records) regex sweep for volatility/range/vol-of-vol/lottery/beta:
  nearest entries cz_IdioVol3F, cz_RealizedVol, cz_IdioVolCAPM, cz_MaxRet, cz_VolSD,
  cz_std_turn (all dir −1), x_method_101_alphas. No range-based or vol-of-vol characteristic
  present in the CZ set itself (search-scope gap noted).
- `signaldoc_chen_zimmermann.csv` swept for range/high-low/Parkinson/Garman/vol-of-vol/
  intraday: no matching predictor.
- `strategy_families.md`, `llm_in_trading.md` (C7-C24 alpha-mining lineage, C10 AlphaGen
  operator grammar including Std/Var over high/low) reviewed.

**Wording discipline:** within this documented search scope, prior art WAS found for the
characteristic, the input, the expression grammar, the method, and (partially) the sign; the
family is therefore T1, and the specific 1-5-day long-high-range-vol package is at most an
undocumented sign/parameter variant of documented sorts. No part of this verdict claims the
family is "proven novel," and per rule 2 the killing prior art is items 1-3 above.
