---
status: phase D adversarial verdicts, round 1
topic: g3_novelty (C001, C002, C003)
role: prior-art attacker
date: 2026-07-20
scale: research/methodology/novelty_scale.md (frozen)
---

# Phase D Novelty Verdicts — G3 Cross-Domain-Transfer Candidates (C001–C003)

Adversarial mandate: prove each hypothesis is already documented in finance. Wording
follows the frozen tiered scale. Local databases checked before web attack:
`research/prior_art/factor_db.json` (393 records; 54 volume/reversal/calendar-adjacent
records reviewed, none matching any of the three combinations),
`research/prior_art/strategy_families.md` (C4, C8, C16, C23 relevant),
`research/prior_art/signaldoc_chen_zimmermann.csv` (331 signals; no post-spike-volume-decay,
TOM-conditioned-reversal, or decay-crossing-timing entry). Web attack: 17 search queries
(listed per section) via general web search plus full-text retrieval of the single closest
paper per candidate. SSRN full texts unreachable (abstracts recovered via search snippets);
this is a documented scope limitation.

---

## C001 — "Hydrological recession": per-stock volume-spike decay speed as moderator of short-term reversal

### Verdict: **T1** (recombination/re-parameterization; combination logic documented in obvious near-neighbors)

### Nearest documented neighbors

1. **Cooper (1999), "Filter Rules Based on Price and Volume in Individual Security
   Overreaction," Review of Financial Studies 12, 901–935.** The killing near-neighbor.
   Weekly reversal filter strategies on large-cap NYSE/AMEX stocks conditioned on lagged
   volume *change*: "decreasing-volume stocks experience greater reversals; increasing-volume
   stocks exhibit weaker reversals and positive autocorrelation." This is precisely C001's
   combination logic — the direction/speed of volume decline after elevated trading
   conditions the strength of the reversal trade — implemented with a contemporaneous
   volume-growth filter rather than a rolling per-stock half-life characteristic.
2. **Conrad, Hameed and Niden (1994), "Volume and Autocovariances in Short-Horizon
   Individual Security Returns," Journal of Finance 49, 1305–1329.** Weekly reversal
   profits in individual securities conditioned on transaction/volume shocks: reversals
   stronger for high-volume-increase stocks (liquidity-pressure channel). Establishes
   volume-conditioned reversal as a documented family.
3. **Llorente, Michaely, Saar and Wang (2002), "Dynamic Volume-Return Relation of
   Individual Stocks," Review of Financial Studies 15, 1005–1047.** Estimates a per-stock
   coefficient (return on lagged return × volume) and shows the cross-section of that
   stock-level dynamic parameter determines whether high-volume days are followed by
   reversal (hedging/risk-sharing trade) or continuation (speculative/informed trade). A
   per-stock estimated volume-return dynamic used as a cross-sectional moderator of
   reversal-vs-continuation — the same conditioning architecture as C001's `rec_speed`,
   with disagreement/information persistence as the stated mechanism.
4. **Li, Yin and Zhao (2024), "Persistence or Reversal? The Effects of Abnormal Trading
   Volume on Stock Returns," European Journal of Finance (SSRN 4346340).** Devises an
   explicit measure of *Persistence in Abnormal Trading Volume* (PATV): while abnormal
   volume persists, high-ATV portfolio returns drift; "trading volumes of individual stocks
   gradually revert to their long-run means, accompanied by portfolio returns falling and
   turning negative as mispricing is corrected." The persistence/decay of the volume shock
   itself, as a measured cross-sectional quantity governing continuation-then-reversal — the
   inverse parameterization of C001's recession speed.
5. **Avramov, Chordia and Goyal (2006), "Liquidity and Autocorrelations in Individual Stock
   Returns," Journal of Finance 61, 2365–2394.** Reversal strength concentrated in
   high-turnover, low-liquidity stocks — documented cross-sectional state-conditioning of
   short-term reversal on volume/liquidity characteristics.
   Supporting: Hou and Moskowitz (2005, RFS 18, 981–1020) price-delay — a per-stock
   *speed-of-adjustment* characteristic priced in the cross-section; Haugen and Baker (1996)
   VolumeTrend (`cz_VolumeTrend` in factor_db) — per-stock volume-slope characteristic;
   Lee and Swaminathan (2000, JF 55) momentum life cycle (`cz_MomVol`).

### Justification

Every component is documented: volume spikes (Gervais–Kaniel–Mingelgrin 2001,
`x_high_volume_premium`), 5-day reversal (Lehmann 1990, `x_weekly_reversal`;
Jegadeesh 1990, `cz_STreversal`), and — decisively — the combination logic itself:
"declining post-event volume ⇒ stronger reversal; persistent volume ⇒ weaker
reversal/continuation" is documented at least four independent times (Cooper 1999
directly as a trading rule; CHN 1994; Llorente et al. 2002 with a per-stock estimated
parameter and a persistent-disagreement mechanism; Li–Yin–Zhao 2024 with an explicit
volume-persistence measure). C001's specific parameterization (rolling 252-day average
post-spike volz drop as a stock characteristic, multiplied into `-ret5`) was **not** found
verbatim anywhere; the hydrological framing (Maillet recession constants) was likewise not
found in finance. Per the frozen scale, a re-parameterization whose components and
combination logic are documented is T1 regardless of novel packaging. The analogy is new
label, not new signal.

### Searches performed (C001)

1. "volume shock decay rate stock returns short-term reversal cross-sectional conditioning"
2. "'attention decay' investor attention speed stock return reversal cross-section"
3. "'abnormal trading volume' persistence duration after volume spike return predictability"
4. "Llorente Michaely Saar Wang dynamic volume-return relation individual stocks reversal continuation"
5. "streamflow recession hydrology analogy stock market volume decay half-life" (no finance application of hydrological recession found)
6. "Conrad Hameed Niden 1994 volume weekly return reversal autocovariance high-transaction stocks"
7. "Hou Moskowitz price delay measure speed of information incorporation cross-section expected returns"
8. "'high volume return premium' Gervais Kaniel duration how long volume stays elevated subsequent return conditioning"
9. "Avramov Chordia Goyal 2006 liquidity autocorrelation individual stock returns turnover reversal conditional"
10. "Cooper 1999 filter rules 'volume growth' weekly reversal overreaction individual stocks"
11. "'volume decay' OR 'volume half-life' per stock estimate cross-section returns paper" (no exact match found)

---

## C002 — "Phase-response curve": TOM flow-phase × idiosyncratic-shock reversal interaction

### Verdict: **T1** (the interaction itself is documented at the aggregate level; cross-sectional variant is a re-parameterization)

### Nearest documented neighbors

1. **Graziani (2024), "Time Series Reversal: An End-of-the-Month Perspective" (earlier
   title: "Time Series Reversal: A Payment Cycle Friction"), Bocconi JMP; AFA/EFMA 2024.**
   The killing near-neighbor, full text verified. Abstract: "the end-of-the-month return of
   the S&P500 negatively correlates with one-month ahead returns... consistent with pension
   funds' liquidity trading to meet pension payment obligations." Critically, its Appendix
   A.2.4 runs exactly C002's interaction contrast as a placebo: "the reversal pattern is
   lost by considering a placebo test around the second week of the month." I.e., *the same
   return shock reverts if it arrives in the month-end payment window and does not if it
   arrives mid-month* — C002's phase-response claim, with the same flow-clock mechanism,
   documented at the aggregate/index level (sample 1975–2020).
2. **Etula, Rinne, Suominen and Vaittinen (2020), "Dash for Cash: Monthly Market Impact of
   Institutional Liquidity Needs," Review of Financial Studies 33, 75–111.** Documents the
   within-month flow cycle as predictable price pressure and reversal: selling pressure
   days T-8..T-4, "strong market level return reversal four days before month end," rebound
   into the turn; stock-level cross-sectional corroboration (stocks with higher mutual-fund
   ownership show more pronounced TOM pressure/reversal patterns). Establishes that
   month-phase-timed shocks and their reversal are jointly documented, including a
   cross-sectional conditioning variable.
3. **Heston, Korajczyk and Sadka (2010), "Intraday Patterns in the Cross-Section of Stock
   Returns," Journal of Finance 65 (arXiv 1005.3535).** Explicitly tested whether
   cross-sectional reversal/continuation strategy returns differ at the turn of the month
   versus mid-month (reporting results separately for TOM days as a control). The
   question "does calendar-month phase interact with cross-sectional reversal" is therefore
   already *asked and answered* (there: no TOM dependence at their frequency) in the
   literature — the interaction is not an undocumented dimension.
4. **Ogden (1990), JF 45, 1259–1272; Xu and McConnell (2008); Lakonishok and Smidt (1988)**
   (`x_turn_of_month` in factor_db) — the TOM level effect and its
   payroll/contribution-flow mechanism: the documented components C002 recombines.
5. **"The turn-of-the-month effect and trading of types of investors" (Pacific-Basin
   Finance Journal, 2022)** and **"Price Pressure and the Turn-of-the-Month Effect" (AEA
   2022 conference paper)** — TOM effect explicitly attributed to measurable investor-type
   price pressure, including reversal accentuated when late-month volatility/retail
   activity is high.

### Justification

C002's tradeable object is the interaction "shock born in the TOM window reverts more."
Graziani 2024 documents precisely this interaction — end-of-month return shocks revert,
identical mid-month shocks do not (his placebo) — driven by the same payment-cycle clock,
differing only in aggregation level (index time-series, one-month horizon) versus C002's
cross-sectional idiosyncratic daily shocks held 5 days. Etula et al. add the stock-level
conditioning (mutual-fund ownership) and the within-month reversal path. Under the frozen
scale this is an obvious near-neighbor of the combination, so the T2 wording ("no prior art
found") is not available. The chronobiology PRC framing itself was searched and no finance
application of phase-response curves was found — again novel label, documented signal
logic. Note the empirical failure of C002 is also consistent with documented decay of TOM
effects in recent US data (practitioner replications report the classical TOM window
largely gone in the last decade).

### Searches performed (C002)

1. "turn of the month effect interaction stock-level reversal price shock month-end buying pressure"
2. "Etula Rinne Suominen Vaittinen 'Dash for Cash' month-end reversal liquidity"
3. "short-term reversal strength calendar timing 'turn of the month' conditional overreaction correction"
4. "phase response curve circadian finance markets 'phase-response' trading shock timing" (no finance application found)
5. "cross-sectional stock reversal conditional on month-end flows mutual fund rebalancing individual stocks window"
6. "Graziani 'Time Series Reversal' 'payment cycle' abstract equity index returns month reversal" + full-text PDF retrieval (csef.it, Nov 2024 version)
7. "strategy short-term reversal turn of month stronger 'first three days' OR 'last trading day' cross-section stocks"
8. "reversal of daily winners losers conditional on 'turn of the month' OR 'month end' window paper cross-section"

---

## C003 — "Marginal value theorem": entry at the post-episode volume-decay crossing

### Verdict: **T1** (entry-on-volume-dry-up-after-spike is documented practitioner prior art; volume-decline-conditioned reversal is documented academic prior art)

### Nearest documented neighbors

1. **Wyckoff method (practitioner, 1930s tradition; extensively documented in current
   write-ups, e.g. trendspider.com, tradingwyckoff.com, luxalgo.com guides).** The killing
   practitioner near-neighbor. After a Selling Climax (high-volume spike + price
   dislocation = C003's "episode"), the documented entry is NOT at the climax but at the
   *Secondary Test / Spring*: a retest "with lower volume and narrower price movements,
   confirming that selling activity has decreased," with springs on "significantly
   below-average volume — typically 30–50% of the 20-day average." Entry against the
   episode's move, timed to the moment volume has decayed back to/below baseline ("supply
   has dried up"). This is the same timing logic as C003's abandonment crossing — wait for
   the marginal participant to leave, then trade the reversion of the episode's move.
2. **Kacher and Morales "Volume Dry-Up" (VDU) + pocket-pivot entries (O'Neil tradition;
   documented in *Trading Cockpit with the O'Neil Disciples*, 2012, and multiple web
   guides).** A named, rule-based entry trigger defined by daily volume declining to an
   extreme low relative to its average after a high-volume move — explicit practitioner
   codification of "the informative day is the volume-decay day, not the spike day."
3. **Cooper (1999), RFS 12, 901–935.** Academic version of the combination logic:
   weekly reversal profits concentrated in *decreasing-volume* stocks — trading the
   reversal conditional on volume having declined, rather than on the spike.
4. **Li, Yin and Zhao (2024), European Journal of Finance.** Documents C003's mechanism
   claim end-to-end: high abnormal-volume portfolios drift while volume persists, and
   returns "fall and turn negative" *as trading volume reverts to its long-run mean* — the
   reversal of the episode's return is empirically located at the volume-normalization
   phase.
5. **Lee and Swaminathan (2000), "Price Momentum and Trading Volume," Journal of Finance
   55, 2017–2069 (momentum life cycle; `cz_MomVol`).** High-volume winners are "late-stage"
   stocks near reversal; volume migration from high to low marks the end of the favoritism
   episode — a documented volume-decay-marks-episode-end structure at monthly horizon.
6. **Entry-at-spike contrast (documented, must-beat set):** Gervais, Kaniel and Mingelgrin
   (2001, JF 56) high-volume premium (entry at the spike, `x_high_volume_premium`);
   Kudryavtsev (2019), "Abnormal Trading Volumes around Large Stock Price Moves and
   Subsequent Price Dynamics," Review of Behavioral Economics 6(3), 283–311 (large moves
   with high abnormal volume are followed by reversals — event time = the move itself);
   Barber and Odean (2008, RFS 21) attention-grabbing buying pressure; Da, Engelberg and
   Gao (2011, JF 66) SVI attention spikes → ~2-week outperformance then reversal (horizon-,
   not crossing-, timed).

### Justification

The frozen scale's T2 bar requires *no practitioner write-up* describing the same signal.
That bar is failed: the Wyckoff Secondary Test/Spring and the VDU literature are exactly
"attention/supply episode ends when volume decays back below baseline; enter there against
(or with the resolution of) the episode's move," in widely available rule-level detail.
Academically, the two halves are also documented separately: reversal conditioned on
*declining* volume (Cooper 1999) and episode-return reversal coinciding with volume
mean-reversion (Li–Yin–Zhao 2024). C003's precise event-study formulation — first day
`volz` crosses below 0 after a `volz > 2` episode, shorting the episode's cumulative
return, 10-day hold — was not found verbatim in any academic paper within the search
scope, and the Charnov/MVT framing has no finance application we could find; but per the
scale, documented practitioner rules plus documented academic combination logic make this
a T1 recombination, not T2. The foraging-theory label is novel; the entry-timing signal is
not.

### Searches performed (C003)

1. "enter reversal trade when abnormal volume returns to normal baseline 'volume dries up' after spike stock"
2. "attention episode end fading attention stock price reversal timing 'when attention fades'"
3. "marginal value theorem foraging Charnov applied to financial markets traders attention" (no finance application found)
4. "Wyckoff 'volume dries up' test entry signal after climax reversal technical analysis"
5. "'Abnormal Trading Volumes around Large Stock Price Moves' subsequent price dynamics authors"
6. "Google search volume attention spike decline reversal timing trade entry after attention subsides SVI"
7. "'life cycle' OR 'lifecycle' of investor attention stock rise and fall pattern return reversal end of episode"
8. "'volume dry-up' OR 'VDU' O'Neil Morales pocket pivot buy point low volume pullback entry after spike"

---

## Summary table

| Candidate | Verdict | Killing prior art (most specific first) | What was NOT found (scope note) |
|---|---|---|---|
| C001 hydrological recession | **T1** | Cooper 1999 RFS (volume-decline-conditioned reversal rule); Llorente et al. 2002 RFS (per-stock volume-return parameter moderating reversal); Li–Yin–Zhao 2024 EJF (abnormal-volume persistence measure); CHN 1994 JF; ACG 2006 JF | The exact rolling post-spike half-life characteristic × `-ret5` interaction; any finance use of hydrological recession formalism |
| C002 phase-response curve | **T1** | Graziani 2024 JMP (EOM-shock reversal with mid-month placebo = the interaction, aggregate level); Etula et al. 2020 RFS (flow-cycle pressure/reversal, stock-level MF-ownership conditioning); Heston–Korajczyk–Sadka 2010 JF (reversal × TOM window tested) | The exact cross-sectional idiosyncratic-shock × TOM-window gated 5-day reversal; any finance use of PRC formalism |
| C003 marginal value theorem | **T1** | Wyckoff Secondary Test/Spring (practitioner entry at post-climax volume dry-up); Kacher–Morales VDU; Cooper 1999 RFS; Li–Yin–Zhao 2024 EJF (reversal located at volume mean-reversion); Lee–Swaminathan 2000 JF | The exact volz baseline-recrossing event-time formulation in academic literature; any finance use of Charnov's MVT |

**Aggregate conclusion for the report.** All three G3 cross-domain transfers are T1: in
each case the *source-domain formalism* (hydrology recession constants, chronobiology
PRCs, foraging MVT) has no finance application findable in this scope — the analogies are
genuinely unusual packaging — but the *resulting trading signal* has documented
near-neighbors covering both components and combination logic. Combined with the negative
validation results (all three failed empirically), the G3 family evidence is: novel
framing, non-novel signal structure, no edge. Provenance remains P-ambiguous as graded at
generation; nothing found here upgrades or downgrades it, though the density of
near-neighbors is consistent with the signals being reachable by recombination of
training-corpus finance knowledge (P-known cannot be ruled out for the signal layer).

**Scope caveats (binding wording).** These are "prior art found" verdicts, so no T2
wording applies. Limitations of the attack: SSRN full texts unreachable (abstract-level
verification only for Li–Yin–Zhao and Kudryavtsev); Graziani 2024 is an unpublished job
market paper (verified from full text; earliest circulated version 2024, i.e., plausibly
within LLM training data); practitioner Wyckoff/VDU sources are secondary write-ups of the
original books, not the primary texts.
