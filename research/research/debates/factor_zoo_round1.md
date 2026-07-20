# Adversarial verification: factor_zoo.md — Round 1

Verifier: adversarial subagent, round 1. Date: 2026-07-19.
Target: /home/user/quant/research/prior_art/factor_zoo.md (status at audit time: "draft round 0")
Method: every claim C1-C28 independently re-verified. Primary PDFs were fetched and text-extracted locally (pypdf) rather than trusting the researcher's quotes; local CSV claims recomputed with pandas from the file on disk. SSRN pages are blocked (403), so SSRN-only abstracts were corroborated via at least two independent secondary sources.

Overall result: 25 of 28 claims CONFIRMED. 3 objections: C6 (OVERSTATED), C20 (WRONG, minor), C21 (WRONG, minor). Do not cite the specific mis-scoped numbers in REPORT.md until fixed.

---

## Claim-by-claim verdicts

### C1 — CONFIRMED
Checked: 316 factors, 313 articles, 250 published, (63 working papers).
Evidence (extracted from the published PDF myself): "We end with 63 working papers. In total, we focus on 313 articles, among which are 250 published articles. We catalogue 316 different factors." (250 + 63 = 313 checks.) Abstract opens "Hundreds of papers and factors attempt to explain the cross-section of expected returns."
Source: https://people.duke.edu/~charvey/Research/Published_Papers/P118_and_the_cross.PDF (fetched, text-extracted)

### C2 — CONFIRMED
Checked: t > 3.0 hurdle; "most claimed research findings ... likely false".
Evidence (abstract, extracted verbatim): "Given this extensive data mining, it does not make sense to use the usual criteria for establishing significance. ... A new factor needs to clear a much higher hurdle, with a t-statistic greater than 3.0. We argue that most claimed research findings in financial economics are likely false."
Source: same PDF as C1.

### C3 — CONFIRMED
Checked: 1967 start, 2032 projection, Bonferroni/Holm/BHY framework, "likely even higher".
Evidence (extracted): "We provide recommended test thresholds from the first empirical tests in 1967 to present day. We also project minimum t-statistics through 2032, assuming the rate of 'factor production' remains the same as the last ten years." Bonferroni benchmark "starts at 1.96 and increases to 3.78 by 2012. It reaches 4.00 in 2032"; BHY(5%) 2.78 (2012) -> 2.81 (2032). "Given that our count of 316 tested factors is surely too low, this means the t-statistic cutoff is likely even higher."
Source: same PDF as C1.

### C4 — CONFIRMED
Checked: 296 / 158 / 142 / 132 / 80.
Evidence (extracted verbatim): "of the 296 published significant factors, 158 would be considered false discoveries under Bonferonni, 142 under Holm, 132 under BHY (1%), and 80 under BHY (5%)." Arithmetic: 80/296 = 27.0%, 158/296 = 53.4% — the claim's "roughly 27% to 53%" is correct.
Source: same PDF as C1.

### C5 — CONFIRMED
Checked: 824 and >1,300 estimates; 238/316 with t > 2.57.
Evidence (extracted): "Given that 238 out of the original 316 factors have a t-statistic exceeding 2.57, the total number of factor tests is estimated to be 824 (= 238/(1-71.1%))" and "...relies on an estimate of more than 1,300 for the total number of factor tests."
Source: same PDF as C1.

### C6 — OVERSTATED (objection)
Checked: "382 factors published in top journals through 2018, with the total including working papers approaching/exceeding 400"; Google-sheet census; "out of control"; many false.
What verified: (a) SSRN abstract (corroborated via two independent web-search snippets): "The rate of factor production in the academic research is out of control. We document over 400 factors published in top journals." and "Surely, many of them are false." (b) CXO Advisory (fetched): "Through 2018, top academic journal articles identify 382 factors" and the 382 figure "does not include those factors appearing only in working papers or those discarded as uninteresting during the search process." (c) Google-sheet census with citation info and download links: confirmed by both secondary sources.
Problem: the file's reconciliation — 382 = top journals, 400+ = only after adding working papers — is the researcher's inference and is contradicted by the paper's own abstract, which attributes "over 400 factors" to "published in top journals" (not to working papers). CXO's "approaching 400" sentence is also about the through-2018 trajectory, not about working papers. Primary text unreachable (SSRN 403; Scribd and ResearchGate copies also blocked), so the decomposition cannot be verified. The individual numbers (382 per CXO chart; 400+ per abstract; the two quotes) are each real, but the claim's framing asserts an attribution the sources do not support.
Fix suggested: state "CXO's reading of the census chart shows 382 factors in top journals through 2018; the paper's abstract itself says 'over 400 factors published in top journals'; the exact reconciliation (dates vs working papers) could not be verified because SSRN is unreachable."
Sources: https://www.cxoadvisory.com/big-ideas/equity-factor-census/ (fetched); https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3341728 (blocked; abstract text corroborated via WebSearch snippets on two distinct queries)

### C7 — CONFIRMED
Checked: 452 anomalies; 65% fail |t|>=1.96 with NYSE breakpoints + value weights; RFS 2020.
Evidence (abstract, extracted verbatim from the published PDF): "With microcaps mitigated via NYSE breakpoints and value-weighted returns, 65% of the 452 anomalies in our extensive data library, including 96% of the trading frictions category, cannot clear the single test hurdle of the absolute t-value of 1.96." PDF header confirms RFS 2020, pp. 2019-2133.
Source: https://global-q.org/uploads/1/2/2/6/122679606/houxuezhang2020rfs.pdf (fetched, text-extracted)

### C8 — CONFIRMED
Checked: 2.78 hurdle -> 82% failure; economic magnitudes.
Evidence (extracted verbatim): "Imposing the higher multiple test hurdle of 2.78 at the 5% significance level raises the failure rate to 82%. Even for replicated anomalies, their economic magnitudes are much smaller than originally reported."
Source: same PDF as C7.

### C9 — CONFIRMED
Checked: 96% trading frictions (RFS); 95/102 liquidity variables = 93% (NBER version); 286 (64%).
Evidence: RFS abstract as in C7 ("including 96% of the trading frictions category"); NBER w23394 page (fetched) quotes: "286 anomalies (64%) including 95 out of 102 liquidity variables (93%) are insignificant at the conventional 5% level."
Sources: same PDF as C7; https://www.nber.org/papers/w23394 (fetched)

### C10 — CONFIRMED
Checked: 97 predictors; 26% lower out-of-sample; 58% lower post-publication; JF 2016.
Evidence: CoLab page for doi 10.1111/jofi.12365 (fetched) quotes the published abstract: "97 variables shown to predict cross-sectional stock returns. Portfolio returns are 26% lower out-of-sample and 58% lower post-publication." Journal cite JF 71, 5-32 corroborated by scirp.org reference pages in search results.
Sources: https://colab.ws/articles/10.1111/jofi.12365 (fetched); https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12365

### C11 — CONFIRMED
Checked: 32% = 58% - 26% attributed to publication-informed trading.
Evidence: CoLab (fetched): "We estimate a 32% (58%-26%) lower return from publication-informed trading" and "investors learn about mispricing from academic publications."
Source: https://colab.ws/articles/10.1111/jofi.12365

### C12 — CONFIRMED
Checked: May 2013 WP; 82 characteristics; ~10% out-of-sample; ~35% post-publication.
Evidence (extracted from the fmg.ac.uk PDF myself): title page dated "May 16, 2013"; abstract: "We study the out-of-sample and post-publication return-predictability of 82 characteristics... The average out-of-sample decay due to statistical bias is about 10%... The average post-publication decay... is about 35%, and statistically different from both 0% and 100%."
Source: https://www.fmg.ac.uk/sites/default/files/2020-08/Jeffrey-Pontiff.pdf (fetched, text-extracted)

### C13 — CONFIRMED
Checked: declines greater for higher in-sample returns; returns higher in high-idiosyncratic-risk / low-liquidity stocks; 2013 WP wording on low idiosyncratic risk.
Evidence: CoLab (published abstract): "Post-publication declines are greater for predictors with higher in-sample returns, and returns are higher for portfolios concentrated in stocks with high idiosyncratic risk and low liquidity." 2013 WP (extracted): "post-publication return declines are greater for characteristic portfolios that consist of stocks with low idiosyncratic risk."
Sources: https://colab.ws/articles/10.1111/jofi.12365 ; fmg.ac.uk PDF as in C12.

### C14 — CONFIRMED
Checked: 153 factors, 93 countries, 13 themes, "strengthened (not weakened)"; JF 2023 + NBER w28432 2021.
Evidence (extracted from NBER PDF myself): "The majority of asset pricing factors: (1) can be replicated, (2) can be clustered into 13 themes, the majority of which are significant parts of the tangency portfolio, (3) work out-of-sample in a new large data set covering 93 countries, and (4) have evidence that is strengthened (not weakened) by the large number of observed factors." Body: "a new global data set of 153 factors across 93 countries." Publication: Journal of Finance 78(5), Oct 2023, 2465-2518, doi 10.1111/jofi.13249 (Wiley/CBS search results).
Sources: https://www.nber.org/system/files/working_papers/w28432/w28432.pdf (fetched, text-extracted); https://onlinelibrary.wiley.com/doi/full/10.1111/jofi.13249

### C15 — CONFIRMED
Checked: 35.0% -> 56.9% (+4.3 longer sample, +4.0 1-month holding, +8.5 capped VW) -> 84.9% CAPM alphas -> Bayesian 84.0% US / 84.9% global; Figure 1 sequence.
Evidence (extracted): Figure 1 labels "35.0% 56.9% 64.7% 84.9% 77.3% 84.0% 84.9%"; text: "we find a baseline replication rate of 56.9%, a difference of 21.9 percentage points... we use a longer sample, which contributes +4.3%... Our focus on only the 1-month holding period factor for each characteristic contributes +4.0%... Capped value weights contribute +8.5%..."; "The fourth bar in Figure 1 shows that the replication rate rises to 84.9% based on tests of factors' CAPM alpha"; "From our Bayesian approach to the MT problem, our estimated replication rate rises to 84.0% (the sixth bar)"; "based on the global sample, the final replication rate rises slightly to 84.9%."
(Note for completeness: the three listed increments sum to 16.8pp of the 21.9pp gap; the claim presents them as components, not an exhaustive decomposition — acceptable.)
Source: NBER w28432 PDF as in C14.

### C16 — CONFIRMED
Checked: 319 characteristics; 161 clearly significant; 98% t>1.96; slope 0.90 / R2 83% (FEDS) and 0.88 / 82% (CFR); CFR 2022.
Evidence (extracted from FEDS PDF myself): "Our 319 characteristics draw from previous meta-studies... For the 161 characteristics that were clearly significant in the original papers, 98% of our long-short portfolios find t-stats above 1.96... A regression of reproduced t-stats on original long-short t-stats finds a slope of 0.90 and an R2 of 83%." IDEAS listing of the CFR version (fetched): "A regression of reproduced t-stats on original long-short t-stats finds a slope of 0.88 and an R2 of 82%", Critical Finance Review 11(2), 2022, 207-264.
Sources: https://www.federalreserve.gov/econres/feds/files/2021-037pap.pdf (fetched, text-extracted); https://ideas.repec.org/a/now/jnlcfr/104.00000112.html (fetched) [nowpublishers.com itself returns 403]

### C17 — CONFIRMED
Checked: 114 remaining characteristics insignificant in originals or HXZ modifications; originals reproduce as constructed.
Evidence (extracted verbatim from FEDS abstract): "The remaining 114 characteristics were insignificant in the original papers or are modifications of the originals created by Hou, Xue, and Zhang (2020). These remaining characteristics are almost always significant if the original characteristic was also significant."
Source: FEDS PDF as in C16.

### C18 — CONFIRMED
Checked: local CSV counts and provenance.
Evidence (recomputed with pandas on /home/user/quant/research/prior_art/signaldoc_chen_zimmermann.csv): 331 rows; Cat.Signal = Predictor 212, Placebo 114, Drop 5; column GScholarCites202509 present. openassetpricing.com (fetched) describes "test asset returns and signals replicated from the academic asset pricing literature" (verbatim) and its Aug 2024 release updated portfolios through end of 2023 (the Oct 2025 update is a code update, no stated extension) — "releases extended through 2023 returns" is supported.
Sources: local file; https://www.openassetpricing.com/ (fetched); https://github.com/OpenSourceAP/CrossSection

### C19 — CONFIRMED
Checked: family counts.
Evidence (recomputed): Cat.Data among 212 predictors = Accounting 99, Price 45, Analyst 18, Trading 13, Other 12, Options 9, 13F 8, Event 8; Price+Trading+Options = 67. Economic categories: valuation 17, external financing 12, momentum 11, investment alt 10, liquidity 9, lead lag 9 — all match.
Nitpick (not an objection): the evidence line "Economic categories among predictors are led by valuation (17)" ignores the catch-all "other" bucket, which is actually the largest at 27.
Source: local CSV, recomputed.

### C20 — WRONG on one number, rest confirmed (objection, minor)
Checked: Year min/max/median; 77% >= 2000; 117 in 2000s; sample start/end medians; 81% <= 2005; 19 ending 2010+.
Recomputed on the 212 predictors: Year min 1973, max 2016 (ok); fraction >= 2000 = 77.4% (ok); 2000-2009 count = 117 (ok); SampleStartYear median 1971 (ok); SampleEndYear median 2001 (ok); median sample length 27 years (ok); 81.1% of samples end <= 2005 (ok); 19 of 212 end >= 2010 (ok).
ERROR: median publication year among the 212 predictors is 2006, not 2005. The 2005 figure is the median over all 331 rows (Predictor+Placebo+Drop; Predictor+Placebo alone gives 2005.5). As the claim scopes itself to "the CZ predictor corpus," the stated median is off by one year. Immaterial to the conclusion but should read 2006 (or re-scope).
Source: local CSV, recomputed.

### C21 — WRONG on two numbers, rest confirmed (objection, minor)
Checked: t-stat distribution and weighting scheme.
Recomputed: among the 188 predictors with recorded original t-stat — count 188 (ok), mean 4.61 (ok), median 3.995 ~ 3.99 (ok), max 16.19 (ok). Stock Weight: EW 184, VW 28 (ok). Mean original long-short return 0.79%/month, median 0.69% (ok).
ERROR: "62% exceed t=3 and 85% exceed t=2" is stated as a property of the 188 with recorded t-stats, but those fractions use denominator 212 (132/212 = 62.3%; 180/212 = 84.9%). Among the 188 actually referenced, 70.2% exceed 3 and 95.7% exceed 2. Either re-scope the sentence to "of all 212 predictors (counting missing t-stats as failures)" or update the percentages to 70%/96%. Note the corrected numbers make the original-evidence-strength point STRONGER, not weaker.
Source: local CSV, recomputed.

### C22 — CONFIRMED
Checked: 29,000 accounting ratios; t > 2.0; ~50% remaining for both.
Evidence (arXiv abstract, fetched): "Mining 29,000 accounting ratios for t-statistics > 2.0 leads to cross-sectional return predictability similar to the peer review process. For both, ~50% of predictability remains after the original sample periods." Also: "inferences about post-sample performance depend little on whether the predictor is peer-reviewed or data mined" — supports the claim's gloss. (The abstract's nuance that theory-agnostic research "shows signs of outperformance" slightly softens "peer review adds little," but the claim's summary is fair.)
Source: https://arxiv.org/abs/2212.10317 (fetched)

### C23 — CONFIRMED
Checked: 241 anomalies, 39 markets, 2M+ anomaly-country-months, US-only reliable post-publication decline; JFE 2020.
Evidence: TUM research portal page (fetched) quotes the abstract: "We study the pre- and post-publication return predictability of 241 cross-sectional anomalies in 39 stock markets"; "the United States is the only country with a reliable post-publication decline in long-short returns"; over 2 million anomaly country-months. Journal cite JFE 135(1), 2020, 213-230 (IDEAS in search results).
Sources: https://portal.fis.tum.de/en/publications/anomalies-across-the-globe-once-public-no-longer-existent/ (fetched); https://www.sciencedirect.com/science/article/abs/pii/S0304405X19301618 (paywalled)

### C24 — CONFIRMED
Checked: 7,846 rules; 100 years DJIA; White's Reality Check; expansion of BLL's 26 rules; out-of-sample 1987-1996 quote.
Evidence (extracted from PDF myself): abstract: "we utilize White's Reality Check bootstrap methodology... expand their universe of 26 trading rules, apply the rules to 100 years of daily data on the Dow Jones Industrial Average"; body: "We consider a very large number (7,846) of trading rules"; and verbatim: "the superior performance of the best technical trading rule is not repeated in the out-of-sample experiment covering the 10-year period 1987-1996. In this sample the results are completely reversed and the best-performing trading rule is not even statistically significant at standard critical levels."
Source: https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Sullivan_Timmermann_White.pdf (fetched, text-extracted)

### C25 — CONFIRMED (with the file's own disclosed caveat intact)
Checked: 9,452 calendar rules; conclusion about full-universe evaluation; Journal of Econometrics 105(1), 249-286.
Evidence: Hansen-Lunde-Nason Brown WP 2003-3 (fetched, text-extracted myself): "STW evaluated 9,452 trading rules that were based on a set of calendar effects that essentially is identical to ours" and "Our universe of calendar-rules is almost identical to that STW used to construct 9,452 trading rules from." Journal citation confirmed via EconPapers/IDEAS (fetched; no abstract available there). The qualitative conclusion ("nominal p-values ... become insignificant in the context of the full universe from which such rules were drawn") corroborated via multiple citing sources in search; STW's own abstract remained unreachable (ScienceDirect paywalled, LSE eprints has no full text). The claim's confidence note already discloses exactly this, so the claim as written is accurate.
Sources: https://economics.brown.edu/sites/default/files/papers/2003-3_paper.pdf (fetched, text-extracted); https://econpapers.repec.org/article/eeeeconom/v_3a105_3ay_3a2001_3ai_3a1_3ap_3a249-286.htm (fetched); https://ideas.repec.org/a/eee/econom/v105y2001i1p249-286.html (fetched)

### C26 — CONFIRMED (substance); quotation-wording nitpick
Checked: sorting on empirically motivated characteristics; data-snooping effects substantial; RFS 1990.
Evidence: NBER w3001 page (fetched): abstract includes "we focus on tests using returns to portfolios of common stock where portfolios are constructed by sorting on some empirically motivated characteristic" and "We present both analytical calculations and Monte Carlo simulations that show the effects of this type of data-snooping to be substantial." RFS 3(3), 431-467 (1990) confirmed via search.
Nitpick (not an objection): the file renders the quote as "the effects of this type of data snooping can be substantial" and labels it verbatim; the actual abstract wording is "...show the effects of this type of data-snooping to be substantial." Substance identical; quotation marks should be adjusted or the "verbatim" label dropped. Also "35 years ago" is 36 as of 2026 — immaterial.
Sources: https://www.nber.org/papers/w3001 (fetched); https://academic.oup.com/rfs/article-abstract/3/3/431/1592120 (abstract not rendered on fetch)

### C27 — CONFIRMED
Checked: JF 2017 Presidential Address; unreported tests / multiple tests / p-hacking quote; minimum Bayes factor.
Evidence (extracted from Harvey's own published PDF myself): abstract verbatim: "Given the competition for top journal space, there is an incentive to produce 'significant' results. With the combination of unreported tests, lack of adjustment for multiple tests, and direct and indirect p-hacking, many of the results being published will fail to hold up in the future. ... I offer a simple alternative (the minimum Bayes factor)." JF Vol. LXXII No. 4, August 2017 confirmed from the PDF header.
Source: https://people.duke.edu/~charvey/Research/Published_Papers/P131_The_scientific_outlook.pdf (fetched, text-extracted)

### C28 — CONFIRMED (as a synthesis)
All quantitative anchors it cites (t>3.0; 26%/58%; ~50% generic decay; 300-400+ published factors) verified above. The probabilistic conclusion ("minority probability of being both real and genuinely new" at in-sample t~2) is presented as inference, not as a literature result, and follows from the verified inputs. Note it inherits the C6 caveat on the exact census count, which does not affect the "300-400+" range used here.

---

## Summary of objections (load-bearing, non-CONFIRMED)

1. C6 — OVERSTATED. The 382-vs-400+ decomposition ("382 in top journals; 400+ only including working papers") is unsupported: the census paper's own abstract says "over 400 factors published in top journals." Constituent numbers are individually corroborated; the attribution is not.
2. C20 — WRONG (minor). Median publication year of the 212 CZ predictors is 2006, not 2005 (2005 is the all-331-row median). Every other number in C20 reproduces exactly.
3. C21 — WRONG (minor). "62% exceed t=3 / 85% exceed t=2" uses denominator 212, but the sentence scopes to the 188 with recorded t-stats, where the true fractions are 70.2% / 95.7%. Every other number in C21 reproduces exactly.

## Minor nitpicks (not objections)

- C26: quote labeled verbatim differs from actual abstract wording ("can be" vs "to be"); "35 years ago" is 36 as of 2026.
- C19 evidence line: "led by valuation (17)" ignores the largest (catch-all) economic category "other" (27).
- C15: the three listed decomposition components (+4.3, +4.0, +8.5) sum to 16.8pp of the 21.9pp HXZ-JKP gap; fine as written ("stepwise ... components") but not exhaustive.
- C22: the arXiv abstract's caveat that theory-agnostic research "shows signs of outperformance" slightly softens the "peer review adds little" gloss.

Status header left unchanged ("draft round 0") because not all load-bearing claims were CONFIRMED.
