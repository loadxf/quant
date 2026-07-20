# Can an LLM Create a Genuinely Novel Trading Edge?

**Final report.** Methodology pre-registered 2026-07-19 (commit `617c69d`, before any data
analysis existed — auditable in this branch's git history). Sections 7 and 9 were written
last, after adversarial prior-art attacks completed, and the conclusion was reviewed by two
opposite-mandate reviewers. Everything cited here — code, data manifests, candidate specs,
debate transcripts, the trials ledger — is in this repository.

---

## 1. The question, and why it is not trivial

The claim under test: *"an LLM can only think about what it already knows, so it cannot
create something never-before-existed — for example, a new edge in stock trading."*

Both sides of this claim have serious support, and neither is obviously right.

**The case against LLM novelty.** A trained language model's sampling distribution is a
compression of its corpus; its outputs are interpolations within that distribution. The
skeptical literature is quantitative, not rhetorical: measured "Creativity Index" of human
authors is ~66% higher than LLMs', and RLHF post-training reduces the models' index by a
further ~30% (Lu et al.; verified in `research/prior_art/llm_creativity.md` C13–C14);
alignment tuning measurably reduces output diversity (Kirk et al.; Padmakumar & He); LLM
use homogenizes idea sets across users (Anderson et al.; Doshi & Hauser); and Kambhampati
argues LLMs perform approximate retrieval rather than principled reasoning. On this view,
every "new" strategy an LLM proposes is a recombination of the factor literature it ingested.

**The case for the possibility.** Human creativity is also largely recombination — Poincaré
called invention the making of "useful combinations"; Boden's taxonomy classifies most human
creativity as combinational or exploratory, with transformational creativity rare. The
operative question is therefore not "can fixed weights contain something new" (they cannot,
by construction) but "can the **system** — LLM + tools + an external evaluator — produce
artifacts outside the training distribution?" Here there are existence proofs in
mathematics: FunSearch (Nature 2024) found a cap set of size 512 for n=8 where the previous
best was 496, improving the cap-set capacity lower bound from 2.2180 to 2.2202 — the
largest improvement in ~20 years — with the LLM proposing programs and a *code evaluator*
verifying them. AlphaEvolve (2025) found a 48-multiplication algorithm for 4×4
complex-valued matrix multiplication, beating Strassen's 49 from 1969. AlphaDev's sorting
kernels shipped in LLVM libc++. These results were not in any training corpus, because they
did not exist. (All figures verified against primary sources: `llm_creativity.md`,
status: agreed, 25/25 claims confirmed by an independent adversarial pass.)

**Why markets are the hard case.** Every verified AI-discovery above shares one feature: a
cheap, exact, automatic evaluator (a program either produces a valid cap set or it does
not). Markets invert all three properties: the evaluator (out-of-sample return) is
expensive, noisy, and adversarial — thousands of professionals have strip-mined the same
daily data for decades, and any real edge decays once traded. Whether the
FunSearch mechanism survives contact with a noisy, mined, adaptive domain is exactly what
this experiment tests. A negative result here would not refute machine creativity in
general; a positive one would be remarkable.

## 2. Operational definitions

Novelty claims are unfalsifiable without an operational scale. Ours was frozen before any
strategy work (`research/methodology/novelty_scale.md`, commit `617c69d`):

| Tier | Meaning |
|---|---|
| **T0** | Replication of a documented anomaly |
| **T1** | Recombination/re-parameterization of documented ideas |
| **T2** | Testable hypothesis with **no prior art found** by independent adversarial searches (always "none found in documented scope", never "proven novel") |
| **T3** | T2 **and** survives the full pre-registered gauntlet including a locked one-shot holdout (DSR > 0.95, pooled Newey–West \|t\| > 3) |

Orthogonally, every candidate carries a **provenance grade**: **P-known** (idea plausibly in
training data), **P-derived** (generation trace provably driven by inputs external to the
weights: post-knowledge-cutoff data statistics, or selection by data fitness), or
**P-ambiguous**. The headline result of the project is the best (Tier, Provenance) pair
achieved. The experiment was pre-committed to publishing whichever answer the evidence
supported.

## 3. What the literature says about LLM novelty

Full file: `research/prior_art/llm_creativity.md` (25 claims, every one re-verified from
primary sources by an independent adversarial agent; final status "agreed"). The verdict, in
brief:

1. **Weights alone: the skeptics are right.** Measured novelty of raw LLM output is
   substantially below human levels and *decreases* with preference tuning. LLM "ideas"
   score well on rated novelty (Si, Yang & Hashimoto 2024: LLM research ideas rated more
   novel than 49 human experts', p < 0.05) but the 2025 follow-up execution study found the
   advantage evaporates when ideas are actually executed (~103 hours each): rankings often
   flip and humans score higher. Idea generation is cheap; validated novelty is the
   bottleneck.
2. **Systems with exact evaluators: the optimists are right.** FunSearch, AlphaEvolve, and
   AlphaDev produced verified, previously-nonexistent artifacts. The pattern is consistent:
   the LLM is a *proposer* over a well-shaped hypothesis space; an external evaluator does
   the epistemic work; the composite system is epistemically open even though the weights
   are fixed (Hughes et al., open-endedness framing).
3. **The unresolved middle — this project's territory.** Every verified success lives in a
   domain with a cheap exact oracle. No peer-verified case exists (as of our searches) of an
   LLM system producing a *validated* novel discovery in a noisy, adversarial, heavily-mined
   domain. In Boden's terms, evaluator-in-the-loop systems demonstrate powerful
   *exploratory* creativity; whether that suffices in markets is an empirical question — the
   one we ran.

## 4. The prior-art map (the novelty filter)

To make "novel" falsifiable we built a machine-readable prior-art database
(`research/prior_art/factor_db.json`): **393 records** — all 331 Chen–Zimmermann Open Source
Asset Pricing signals (212 replicating predictors, 114 placebos, 5 drops; placebos count as
prior art) plus 62 curated records covering strategy families the cross-sectional zoo omits
(time-series momentum, seven carry variants, seven seasonalities, overnight/intraday
decomposition, lead-lag variants, pairs, volume effects, ETF-structure effects) and 27
method-level records of automated alpha mining (genetic programming 1997→, "101 Formulaic
Alphas", AlphaGen, Alpha-GPT, QuantAgent, Chain-of-Alpha, QuantEvolve, FactorMiner,
AlphaPROBE — the LLM-alpha-factory literature is crowded and current through Feb 2026).

Two Phase A findings frame everything downstream (files: `factor_zoo.md`,
`strategy_families.md`, `llm_in_trading.md`, all adversarially verified):

- **Daily US equity data is the most-mined dataset in finance.** Harvey–Liu–Zhu catalogue
  316 published factors and recommend t > 3 for new claims; Hou–Xue–Zhang find 65% of 452
  anomalies fail replication under standard filters; McLean–Pontiff measure 26%
  out-of-sample and 58% post-publication return decay; Chen–Lopez-Lira–Zimmermann show that
  *naively mining 29,000 accounting ratios matches the peer-reviewed literature's
  performance* — publication is not even the bar; the data itself has been exhausted to
  roughly the mining frontier.
- **Our G2 mechanism is documented prior art at the method level.** Evolutionary/grammar
  search over signal expressions has a continuous literature from Allen–Karjalainen (1999)
  through gplearn-based alpha mining to 2024–2026 LLM alpha factories. The *method* is T1 by
  construction; only a specific surviving *signal* could be novel.

## 5. Generation mechanisms and their traces

Four mechanisms, chosen to span the provenance spectrum. Every candidate's spec logs its
generation trace (`candidates/C###/spec.md`).

- **G1 — data-first mining on provably post-cutoff data (strongest provenance).** The model
  computed descriptive-statistics panels (`report/g1_panels.json`) on the window
  **2026-02-02 → 2026-07-17** — after its training cutoff (Jan 2026), so the numbers cannot
  be memorized. Access was token-gated and logged; to prevent generation/evaluation
  contamination the G1 generation window was excluded from those candidates' holdout
  (deviation D1, committed before any post-2023 data was touched). The model then
  articulated hypotheses from anomalous cells: a lag-7 reversal spike (IC −0.056, t≈−3.0),
  a gap×intraday "coherence" U-shape (+40.5/+29.0 bps corners), a negative sector-ETF
  lead-lag (8/11 sectors). → C007, C008, C009, plus two slow variants in loop 2 (C013, C014).
- **G2 — FunSearch-style evolutionary search with data fitness.** A small signal grammar
  (8 OHLCV-derived terminals, 13 operators, depth ≤ 5) chosen once by the model; an
  evolutionary search (checkpointed, deterministic seeds) then explored it with fitness =
  net train-period Sharpe only. The data, not the model, selects survivors → P-derived at
  the selection level. Three searches (1-day hold; 5-day hold; ETF universe) evaluated
  **1,932 distinct ledgered expressions**. → C010–C012, C015, C016.
- **G3 — cross-domain structural transfer (the "thinking outside the box" test).** The
  model deliberately imported formalisms with no known finance footprint, before seeing any
  project data: streamflow-recession constants from hydrology → per-stock volume-decay
  speed conditioning reversal (C001, C013); circadian phase-response curves → turn-of-month
  phase × shock-reversal interaction (C002); Charnov's marginal value theorem from foraging
  ecology → volume-decay-crossing entry timing (C003).
- **G4 — anti-consensus inversion (control group).** Documented effects, deliberately
  perturbed (plain 5-day reversal C004; inverted volume conditioning C005; intraday-component
  reversal C006; two explicit baselines B002, B003). Expected T0/T1 by construction; their
  role is calibration — if "novel" mechanisms can't beat known recombinations, that is
  itself the finding.

## 6. Empirical results

**Harness.** Yahoo daily OHLCV for 503 current S&P constituents + 71 ETFs (survivorship
caveat R2 below); train 2005–2018, validation 2019–2023, holdout 2024+ **locked in code and
git history** (single-shot access requires a committed spec hash; `holdout_gate.py`);
cross-sectional decile long-short with t+2 execution lag and 10 bps/side costs (5 bps
ETFs); a no-lookahead test suite (a perfect-foresight signal cannot profit in this engine);
and an **append-only trials ledger written inside the backtest engine** so every evaluation
ever run — including all 1,932 search evaluations and every dead candidate — counts against
the Deflated Sharpe Ratio. Final ledger: **N = 2,000 trials**. PSR/DSR implementations are
unit-pinned to the worked examples in Bailey–López de Prado (verified symbol-by-symbol
against the papers in `multiple_testing.md`).

**Pre-registered gates.** Gate 1 (validation): cost-adjusted SR > 0.5, Newey–West \|t\| > 2,
predicted sign, CPCV median > 0. Gate 2 (robustness): positive in both validation halves,
both volatility regimes, ±25% parameter perturbations, and at 25 bps costs. Gate 3
(one-shot holdout): SR > 0, DSR > 0.95 at full-ledger N, pooled \|t\| > 3 (≈ the
Harvey–Liu–Zhu standard).

**Loop 1 (14 candidates).** Every candidate failed Gate 1. The decomposition is
informative:

| Group | Best net validation SR | Diagnosis |
|---|---|---|
| Reversal family (C004 control + all G3 conditionings) | −0.81 … −2.15 | gross-positive (+0.68 control) but ~1.6×/day turnover → costs kill; matches the documented post-publication death of short-term reversal in large caps |
| G1 post-cutoff hypotheses (C007–C009) | −2.93 … −4.10 | **gross-negative** — the 115-day panel patterns were noise, exactly the pre-declared small-sample risk; C009's sign even flipped |
| G2 search winners (C010–C012) | +0.57 (C010, t=1.41) | the only Gate-2 survivor; lowest turnover (0.18×/day); fails Gate 1 significance |
| Controls behaved as documented | C005 (deliberately inverted conditioning) near-worst | evidence the harness measures real structure |

**Loop 2 (pre-declared pivot to low-turnover space, deviation D2).** New searches at 5-day
holds (equities + ETFs) and two slow G3/G1 variants. Results: C013 +0.10, C014 −0.27,
C016 +0.22 (all fail); **C015** — the 63-day standard deviation of the daily high-low range,
*independently rediscovered by the second search* (different seed, window, universe sample;
same family as C010) — validation SR +0.66, passes all Gate-2 robustness checks, **fails
Gate 1 at t = 1.63**.

**Loop 3 (pre-declared as diagnostics-only, deviation D3; generation stopped to avoid
selecting for flukes, risk R8).**

- **Family-wide Reality Check** (pre-registered; White-style stationary bootstrap over all
  18 gated candidates' validation returns): **p = 0.171**. No family-level discovery.
- **Deflated Sharpe Ratio of the best candidate** against the full ledger (N = 2,000 trials,
  V[SR] as recorded): **DSR ≈ 0** (the expected-maximum benchmark after 2,000 trials of that
  dispersion is far above C015's 0.66). The arithmetic is in
  `report/loop3_diagnostics.json`. Caveat: ledger V includes deliberately bad search
  expressions, making this DSR conservative; the Reality Check above, computed only on the
  18 gated candidates' actual return paths, independently agrees.
- **Survivorship autopsy of the range-vol family** (its spec *pre-declared* this suspicion):
  the "premium" is long high-volatility names beating the current-constituent average
  (long leg vs EW market: +0.73 SR; short leg vs market: −0.61) — the classic survivorship
  signature, since today's constituent list contains only the volatile names that survived.
  The same construct on the ETF universe (no deletion bias): SR 0.47, t = 1.15 — weaker and
  insignificant. Its sign is also *opposite* the documented low-volatility anomaly, which is
  what survivorship inflation of a current-constituent panel would manufacture.
- **The holdout was never fired.** No candidate met the pre-registered Gate-1+2 bar, so the
  one-shot 2024–2026 holdout remains sealed. An unfired holdout is a result: the experiment
  ended with its strongest integrity device intact.

## 7. Novelty verdicts

Adversarial prior-art attacks (agents whose success criterion was *finding* prior art;
full records: `candidates/C015/novelty_verdict.md`, `research/debates/g3_novelty_verdicts.md`)
were run on every family that retained any interest after the gates. Verdict wording follows
the frozen scale: "prior art found" is a kill; absence claims are always scoped.

| Candidate(s) | Mechanism | Validation outcome | Novelty verdict | Provenance |
|---|---|---|---|---|
| C001/C013 — volume-recession conditioning | G3 | −1.20 / +0.10, fail | **T1** — Cooper (1999) trades the same volume-trend×reversal combination; Llorente et al. (2002) per-stock volume-return moderation; the hydrology framing itself has no finance footprint | P-ambiguous |
| C002 — TOM phase-response interaction | G3 | −1.10, fail | **T1** — Graziani (2024) documents exactly the end-of-month shock-reversal interaction (with a mid-month placebo test); Etula et al. (2020) the flow mechanism | P-ambiguous |
| C003 — MVT patch-abandonment timing | G3 | −1.17, fail | **T1** — the volume-dry-up entry is documented practitioner method (Wyckoff secondary test; VDU rules); academic anchors in Cooper (1999), Li-Yin-Zhao (2024) | P-ambiguous |
| C007–C009 — post-cutoff panel hypotheses | G1 | −2.9 … −4.1, gross-negative | not attacked: falsified before novelty was binding; diagnosed as 115-day panel noise (C014, the one panel cell matching *documented* prior art, also failed) | **P-derived** (trace verifiable) |
| C010/C015 — range-volatility family | G2 | +0.57/+0.66, Gate-2 pass, Gate-1 fail | **T1** — Baltussen et al. (2018) vol-of-vol (same construction, opposite sign); Blau-Whitby (2017) range sorts; WQ101 Alpha#40 contains the same `rank(stddev(high,·))` subexpression at the same horizon; the long-high sign is a survivorship artifact (§6) | **P-derived** (selection by data) |
| C011/C012/C016 — other G2 winners | G2 | ≤ +0.48, fail | C012 is a T0 rediscovery of monthly reversal (the search finding a documented anomaly is itself informative); others not attacked (dead) | P-derived |
| C004–C006, B002/B003 — controls/baselines | G4 | −0.6 … −2.2, fail | T0/T1 by construction | P-known |

**Headline evidence-table result: nothing above T1.** Zero candidates reached T2 (novel with
no prior art found); zero passed Gate 1; the holdout was never fired. The single most
instructive pattern: every "creative" hypothesis that had any structure landed within one
step of documented territory, and the one family with empirical life was a documented
characteristic wearing a survivorship-flipped sign.

## 8. Limitations — and what each does to the conclusion

- **R1 — One data source, daily bars, mined territory.** Yahoo daily OHLCV only. The most
  plausible unmined edges live in intraday, options, flow, and alternative data we could not
  access. *Effect: weakens the negative result as evidence about LLM creativity in general;
  it is strong evidence only about this arena.*
- **R2 — Survivorship bias.** Current-constituent universe; long-side/vol-side results are
  inflated, which the loop-3 autopsy confirmed in the one surviving family. *Effect:
  strengthens the kill of C015; means even our +0.66 SR near-miss was likely overstated.*
- **R3 — Short provably-clean window.** Only Feb–Jul 2026 (~115 trading days) is provably
  post-cutoff; it powered hypothesis *generation*, not validation. *Effect: the P-derived
  provenance mechanism was demonstrated, but its hypotheses were noise — 115 days cannot
  reliably seed daily-frequency cross-sectional hypotheses.*
- **R4 — Ledger completeness.** Enforced by writing inside the engine; interrupted runs'
  rows were retained (overcounting N, in the DSR's disfavor — the conservative direction).
- **R5 — Narrative-memory contamination.** The model has memorized 2024–2025 market
  narratives; only the 2026 window is provably clean, and G1 traces cite specific statistics
  rather than narratives. *Effect: provenance grades for non-G1 mechanisms cap at
  P-ambiguous.*
- **R6 — Literature-search recall.** SSRN direct was blocked; practitioner lore is not
  fully indexed. *Effect: every T2-style verdict is "no prior art found in documented
  scope", never proof of absence.*
- **R7 — "The system isn't the LLM alone."** Conceded by design. The experiment answers two
  questions separately (weights alone: no; system: see conclusion) — the distinction is a
  finding, not a dodge.
- **R8 — Verifier overfitting via iteration.** Guarded by the 3-loop cap, the
  diagnostics-only loop 3, the ever-growing ledger N, and the G4 control group.
- **R9 — Sycophancy in either direction.** The conclusion below was drafted only after the
  evidence table was complete and was attacked by two reviewers with opposite mandates
  ("prove it overclaims novelty" / "prove it underclaims out of performative humility");
  the debate record is in `research/debates/`.

## 9. Conclusion

**Direct answer to the question posed.** In this experiment, the LLM system did **not**
create a genuinely novel trading edge. The evidence table is one-sided: 19 candidates over
two generation loops, 2,000 ledgered trials, zero pre-registered gate passes; a family-wide
Reality Check p of 0.171; a best-candidate Deflated Sharpe Ratio of ≈ 0; the best family
revealed as a documented characteristic (T1) whose apparent premium matches the survivorship
signature of the data; and a holdout that was never earned. Best (Tier, Provenance) pair
achieved: **T1 / P-derived** — data-driven provenance was demonstrated, novelty was not.

**The refined answer to the underlying theory.** The user's theory — "an LLM can only think
about what it already knows, so it cannot create a never-before-seen edge" — is *supported
in its weights-alone form and too strong in its systems form*, and this experiment sharpens
where the boundary actually is:

1. **Weights alone: supported.** Every hypothesis the model generated from its own priors
   (G3's cross-domain transfers) turned out to be one step from documented territory: the
   *framings* (streamflow recession, phase-response curves, foraging theory) have no finance
   footprint, but the *signal structures* they mapped onto were already in the literature —
   found not by the model knowing them, but by adversarial search after the fact. This is
   combinational creativity with genuine surface novelty and no structural novelty, which is
   precisely what the creativity-measurement literature predicts of LLM output.
2. **The system is epistemically open — that part of the skeptic's argument fails.** The G1
   mechanism generated hypotheses from statistics of provably post-training-cutoff data
   (P-derived, trace-verified): the system demonstrably reasoned from inputs that were in no
   training corpus. The FunSearch-class existence proofs stand: LLM+evaluator systems have
   created verified new mathematics. "It can only know what it was trained on" is false of
   the system.
3. **But openness is not discovery: the binding constraint is the evaluator, not the
   imagination.** Everything the open channels produced here died on contact with the data —
   the post-cutoff panel patterns were noise (115 daily observations cannot seed
   daily-frequency cross-sectional hypotheses), and the search mechanism's best product was
   a rediscovery. Where FunSearch had a cheap, exact, instant oracle, markets offer a noisy,
   expensive, adversarial one, strip-mined by thousands of prior searchers whose own mining
   (Chen–Lopez-Lira–Zimmermann) already matches the published frontier. **The bottleneck of
   novelty is not generation; it is verification.** An LLM can propose endlessly — this
   project generated and tested more candidate signals than most published papers — but in a
   domain where verification is the scarce resource, generation fluency adds little.
4. **What this experiment cannot conclude.** It cannot rule out that the same system with
   richer raw material — intraday or options data, point-in-time constituents, longer
   provably-clean windows, live forward validation — would find something real (limitation
   R1); daily bars on current S&P constituents are close to the worst possible arena for new
   discovery. Nor is the negative specific to LLMs: a human quant restricted to this data,
   these tools, and eight days would quite plausibly have fared no better — the experiment
   lacks a human control arm, so "LLM vs human" is not what it measures. What it does
   establish, with pre-registered rigor, is the *shape* of the limitation: no failure of
   idea generation was ever the binding constraint; the pre-registered statistical bar was.
5. **The honest positive findings.** The protocol itself behaved as designed — the controls
   reproduced documented behavior, the deliberately-inverted control was near-worst, the
   engine's costs reproduced the documented death of short-term reversal, and the
   convergent rediscovery of a real documented characteristic (vol-of-range, C012's monthly
   reversal) shows the pipeline detects true structure when it exists. And the system
   audited itself: the survivorship suspicion on its own best candidate was declared in the
   spec *before* the gates and confirmed by its own autopsy. An honest negative under a
   pre-registered protocol is the anti-sycophantic answer the experiment was built to be
   able to give.

**One-sentence verdict:** *this experiment found that an LLM-with-tools system can generate
hypotheses that are provably not memorized and superficially new, but — in the most-mined
data arena in finance, under a pre-registered multiple-testing-corrected protocol — it
created no validated novel edge, and the reason is not that the model can only repeat its
training data, but that in markets the scarce resource is verification, which no amount of
fluent generation can substitute for.*
