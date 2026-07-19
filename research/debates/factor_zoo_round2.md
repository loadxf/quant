# Adversarial audit — factor_zoo.md — round 2

Auditor: adversarial verifier (round 2), 2026-07-19.
File audited: /home/user/quant/research/prior_art/factor_zoo.md (post-round-1 revision, "status: draft round 1").
Method: every load-bearing claim independently re-verified. Primary PDFs were fetched fresh and text-extracted locally (PyMuPDF); local CSV statistics were recomputed from scratch with pandas; abstracts unreachable as PDFs were corroborated via direct fetches of secondary full-text copies or publisher/repec listings, plus web-search snippets. I did not rely on the researcher's quoted evidence for any verdict.

Result: 28/28 checked claims CONFIRMED. No objections. Minor nitpicks listed at the end (none rise to OVERSTATED/WRONG/UNVERIFIABLE).

---

## C1 — HLZ 2016: 316 factors, 313 articles (250 published, 63 WP) — CONFIRMED

Fetched https://people.duke.edu/~charvey/Research/Published_Papers/P118_and_the_cross.PDF (946.9 KB, 64 pp) and extracted text. Verbatim from Section 2: "We choose a subset of papers that we suspect are in review at top journals, have been presented at top conferences, or are due to be presented at top conferences. We end with 63 working papers. In total, we focus on 313 articles, among which are 250 published articles. We catalogue 316 different factors." 250 + 63 = 313. Journal/volume verified from running head: "The Review of Financial Studies / v 29 n 1 2016". Abstract opens "Hundreds of papers and factors attempt to explain the cross-section of expected returns." All elements of C1 match exactly.

## C2 — HLZ: t > 3.0 hurdle; "most claimed research findings in financial economics are likely false" — CONFIRMED

Same PDF, abstract verbatim: "Given this extensive data mining, it does not make sense to use the usual criteria for establishing significance. Which hurdle should be used for current research? Our paper introduces a new multiple testing framework and provides historical cutoffs from the first empirical tests in 1967 to today. A new factor needs to clear a much higher hurdle, with a t-statistic greater than 3.0. We argue that most claimed research findings in financial economics are likely false." Matches the file's quote exactly.

## C3 — Multiple-testing framework, 1967 origins, 2032 projections, "likely even higher" — CONFIRMED

Same PDF. (a) Introduction verbatim: "We provide recommended test thresholds from the first empirical tests in 1967 to present day. We also project minimum t-statistics through 2032, assuming the rate of 'factor production' remains the same as the last ten years." (b) The three adjustments are exactly Bonferroni, Holm, and Benjamini-Hochberg-Yekutieli: "Bonferroni, Holm, and Benjamini, Hochberg, and Yekutieli (BHY). Both Bonferroni and Holm control FWER, and BHY controls FDR." (c) Conclusion verbatim: "Given that our count of 316 tested factors is surely too low, this means the t-statistic cutoff is likely even higher." The 1967 anchor is Douglas (1967), cited in the paper's factor chronology. Body also confirms projected threshold values (3.78 by 2012, 4.00 in 2032 for Holm). All elements verified.

## C4 — 296 published significant factors: 158/142/132/80 false discoveries — CONFIRMED

Same PDF, conclusion verbatim (including the paper's own misspelling "Bonferonni"): "many of the factors discovered in the field of finance are likely false discoveries: of the 296 published significant factors, 158 would be considered false discoveries under Bonferonni, 142 under Holm, 132 under BHY (1%), and 80 under BHY (5%)." Arithmetic check of the file's gloss: 80/296 = 27.0%, 158/296 = 53.4% — "roughly 27% to 53%" is correct.

## C5 — Total factor tests estimated at 824 to >1,300 — CONFIRMED

Same PDF. Appendix A.1 verbatim: "Given that 238 out of the original 316 factors have a t-statistic exceeding 2.57, the total number of factor tests is estimated to be 824 (=238/(1−71.1%))". Section 4 verbatim: "Our current estimate assumes a certain level of correlation among returns and relies on an estimate of more than 1,300 for the total number of factor tests." Both endpoints verified with their mechanisms.

## C6 — Harvey-Liu census: "over 400 factors" in top journals (abstract), 382 through 2018 (CXO chart reading), Google-sheet citizen-science census — CONFIRMED

(a) SSRN page itself still blocked (403), consistent with the file's caveat. Abstract wording re-corroborated via fresh web search (SSRN listing snippet, Semantic Scholar): "The rate of factor production in the academic research is out of control. We document over 400 factors published in top journals. Surely, many of them are false." — matches the file's quote, and the abstract attributes the 400+ to top journals, exactly as the file (post-round-1) states.
(b) Direct fetch of https://www.cxoadvisory.com/big-ideas/equity-factor-census/ returned verbatim: "Through 2018, top academic journal articles identify 382 factors (see the chart below), materially reusing the same source data." and "This count does not include those factors appearing only in working papers or those discarded as uninteresting during the search process." — matches the file's quotes exactly, and CXO names its source as Harvey and Liu's February 2019 "A Census of the Factor Zoo".
(c) Google-sheet / citizen-science element: corroborated independently — Semantic Scholar's summary of the paper: "a comprehensive census of factors published in top academic journals through January 2019 and a citizen science project that allows researchers to add to the database both published papers as well as working papers"; Harvey's own research page (people.duke.edu/~charvey/research.htm, via search snippet) describes the paper as providing "a link to a Google sheet that lists each of the factors as well as links and citation information" and "proposes a citizen science project in which researchers can offer additional factors (from both published papers and working papers)"; the live "Factor Census" Google sheet surfaced directly in search (docs.google.com/spreadsheets/d/1mws1bU56ZAc8aK7Dvz696LknM0Vp4Rojc3n61q2-keY).
(d) Bonus corroboration the file does not claim but which supports its 382 figure: Harvey's own page describes the paper as detailing "382 factors published in top academic journals" — i.e., the CXO chart reading agrees with the author's own description. The file's refusal to reconcile 382 vs 400+ remains appropriately cautious. Verdict: CONFIRMED as written (medium confidence remains reasonable).

## C7 — HXZ 2020: 452 anomalies, 65% fail |t|>=1.96 — CONFIRMED

Fetched https://global-q.org/uploads/1/2/2/6/122679606/houxuezhang2020rfs.pdf (839.8 KB, 115 pp), extracted text. Abstract verbatim: "With microcaps mitigated via NYSE breakpoints and value-weighted returns, 65% of the 452 anomalies in our extensive data library, including 96% of the trading frictions category, cannot clear the single test hurdle of the absolute t-value of 1.96." Running head confirms "The Review of Financial Studies / v 33 n 5 2020". Exact match.

## C8 — HXZ: |t|>=2.78 raises failure rate to 82%; magnitudes smaller — CONFIRMED

Same PDF, abstract verbatim: "Imposing the higher multiple test hurdle of 2.78 at the 5% significance level raises the failure rate to 82%. Even for replicated anomalies, their economic magnitudes are much smaller than originally reported." Exact match.

## C9 — Trading frictions hardest hit: 96% (RFS); NBER 2017 version: 95/102 liquidity (93%) — CONFIRMED

RFS 96% verified under C7. NBER w23394 fetched directly (https://www.nber.org/papers/w23394); abstract verbatim: "With microcaps alleviated via New York Stock Exchange breakpoints and value-weighted returns, 286 anomalies (64%) including 95 out of 102 liquidity variables (93%) are insignificant at the conventional 5% level." Matches the file's quote. (Note for completeness: the NBER version's library is 447 variables, vs 452 in the RFS version; the file makes no claim about the NBER count, so no issue.)

## C10 — McLean-Pontiff JF 2016: 97 predictors, 26% / 58% — CONFIRMED

Fetched a full-text copy of the published version (https://tevgeniou.github.io/EquityRiskFactors/bibliography/AcademicReviewFactor.pdf, header "Journal of Finance, Forthcoming"), extracted text. Abstract verbatim: "We study the out-of-sample and post-publication return-predictability of 97 variables that academic studies show to predict cross-sectional stock returns. Portfolio returns are 26% lower out-of-sample and 58% lower post-publication." Also corroborated by search snippets of the SSRN/Wiley listings (Wiley page itself returns 402). JF 2016 publication confirmed via Wiley listing (doi 10.1111/jofi.12365). Exact match.

## C11 — Decomposition: 26% upper bound on data mining; 32% publication-informed trading — CONFIRMED

Same abstract, verbatim: "The out-of-sample decline is an upper bound estimate of data mining effects. We estimate a 32% (58% - 26%) lower return from publication-informed trading." Exact match.

## C12 — 2013 WP version: 82 characteristics, ~10% / ~35% — CONFIRMED

Fetched https://www.fmg.ac.uk/sites/default/files/2020-08/Jeffrey-Pontiff.pdf (dated May 16, 2013), extracted text. Abstract verbatim: "We study the out-of-sample and post-publication return-predictability of 82 characteristics that are identified in published academic studies. The average out-of-sample decay due to statistical bias is about 10%, but not statistically different from zero. The average post-publication decay, which we attribute to both statistical bias and price pressure from aware investors, is about 35%..." The published version's 97/26%/58% verified under C10. The version-sensitivity point is exactly right.

## C13 — Decay interacts with limits to arbitrage — CONFIRMED

Published abstract verbatim (same copy as C10): "Post-publication declines are greater for predictors with higher in-sample returns, and returns are higher for portfolios concentrated in stocks with high idiosyncratic risk and low liquidity." 2013 WP abstract verbatim: "Consistent with costly (limited) arbitrage, post-publication return declines are greater for characteristic portfolios that consist of stocks with low idiosyncratic risk." Both quotes match the file.

## C14 — JKP: Bayesian model, 153 factors, 93 countries, 13 themes, strengthened not weakened — CONFIRMED

Fetched https://www.nber.org/system/files/working_papers/w28432/w28432.pdf (Feb 2021), extracted text. Abstract verbatim: "The majority of asset pricing factors: (1) can be replicated, (2) can be clustered into 13 themes, the majority of which are significant parts of the tangency portfolio, (3) work out-of-sample in a new large data set covering 93 countries, and (4) have evidence that is strengthened (not weakened) by the large number of observed factors." Body: "We study a global dataset with 153 factors in 93 countries." Publication verified via search: Journal of Finance 2023, 78(5): 2465-2518, doi 10.1111/jofi.13249. All elements match.

## C15 — JKP reconciliation with HXZ: 35.0% -> 56.9% (+4.3/+4.0/+8.5) -> 84.9% CAPM alpha; Bayesian 84.0% US / 84.9% global — CONFIRMED

Same PDF. Figure 1 bar labels extracted in sequence: "35.0% 56.9% 64.7% 84.9% 77.3% 84.0% 84.9%". Body verbatim: "in direct comparability to the 35% calculation from Hou et al. (2020)... we find a baseline replication rate of 56.9%, a difference of 21.9 percentage points... we use a longer sample, which contributes +4.3%... Our focus on only the 1-month holding period factor for each characteristic contributes +4.0%... capped value weights contribute +8.5% to our higher replication rate." "the replication rate rises to 84.9% based on tests of factors' CAPM alpha" (fourth bar); "From our Bayesian approach to the MT problem, our estimated replication rate rises to 84.0% (the sixth bar of Figure 1)" (US); "the global sample, the final replication rate rises slightly to 84.9%." Every number and attribution in C15 matches.

## C16 — Chen-Zimmermann: 161 clearly significant, 98% reproduce; slope 0.90/R2 83% (FEDS), 0.88/82% (CFR) — CONFIRMED

Fetched https://www.federalreserve.gov/econres/feds/files/2021-037pap.pdf (FEDS 2021-037, March 2021), extracted text. Abstract verbatim: "Our 319 characteristics draw from previous meta-studies... For the 161 characteristics that were clearly significant in the original papers, 98% of our long-short portfolios find t-stats above 1.96... A regression of reproduced t-stats on original long-short t-stats finds a slope of 0.90 and an R2 of 83%." CFR published version: nowpublishers.com returns 403, but the repec listing of the CFR article (https://ideas.repec.org/a/now/jnlcfr/104.00000112.html, via search) gives: Critical Finance Review vol 11(2), pages 207-264, May 2022, with abstract "...finds a slope of 0.88 and an R^2 of 82%." Both the FEDS and CFR numbers in the file are correct and correctly attributed to their versions.

## C17 — CZ vs HXZ: 114 Placebo characteristics; originals reproduce as originally constructed — CONFIRMED

Same FEDS PDF, abstract verbatim: "The remaining 114 characteristics were insignificant in the original papers or are modifications of the originals created by Hou, Xue, and Zhang (2020). These remaining characteristics are almost always significant if the original characteristic was also significant." 161 + 44 (mixed) + 114 = 319 consistent within the abstract. The gloss that CZ reproduce originals as originally constructed is the paper's stated method ("we differ by comparing our t-stats to the original papers' results"). Matches.

## C18 — Local CSV: 331 signals = 212 Predictor / 114 Placebo / 5 Drop — CONFIRMED

Recomputed independently with pandas on /home/user/quant/research/prior_art/signaldoc_chen_zimmermann.csv: rows = 331; Cat.Signal value counts = Predictor 212, Placebo 114, Drop 5; column GScholarCites202509 present. Provenance re-verified by fetching https://www.openassetpricing.com/: site self-describes as providing "test asset returns and signals replicated from the academic asset pricing literature"; release history shows August 2024 release "updated through 2023" returns (latest code release Oct 2025, no further return extension stated) — consistent with the file's "releases extended through 2023 returns."

## C19 — Family composition of 212 predictors — CONFIRMED

Recomputed: Cat.Data among Predictors = Accounting 99, Price 45, Analyst 18, Trading 13, Other 12, Options 9, 13F 8, Event 8. Price+Trading+Options = 67. Sum = 212. Economic categories among predictors: other 27, valuation 17, external financing 12, momentum 11, investment alt 10, liquidity 9, lead lag 9. Every number in C19 (including the round-1-corrected ordering with "other" largest) reproduces exactly.

## C20 — CZ predictor vintages — CONFIRMED

Recomputed: Year min/max = 1973/2016; median Year among 212 predictors = 2006.0 (median over all 331 rows = 2005.0, exactly as the file's parenthetical states); 77.4% published >= 2000 (file: 77%); 2000-2009 decade count = 117; SampleStartYear median = 1971; SampleEndYear median = 2001; median sample length = 27 years; 81.1% of predictor samples end <= 2005; 19 of 212 end >= 2010. Every number reproduces exactly, including the round-1 correction.

## C21 — Original-paper evidence strength — CONFIRMED

Recomputed: T-Stat non-missing count 188, mean 4.61, median 3.995, max 16.19; among the 188 recorded: t>3 = 132/188 = 70.2%, t>2 = 180/188 = 95.7% (file: 70% and 96%); as fractions of all 212 (missing counted as failures): 62.3% and 84.9% (file: 62% and 85%); Stock Weight EW = 184, VW = 28 (184+28 = 212); mean original long-short Return = 0.793%/month, median 0.69% (file: 0.79%/0.69%). Every number reproduces exactly, including the round-1 rescoping.

## C22 — Chen, Lopez-Lira & Zimmermann: 29,000 mined ratios ~ peer review; ~50% decay for both — CONFIRMED

Fetched https://arxiv.org/abs/2212.10317 directly. Abstract contains verbatim: "Mining 29,000 accounting ratios for t-statistics >2.0 leads to cross-sectional return predictability similar to the peer review process." and "For both, ≈50% of predictability remains after the original sample periods." Also: "inferences about post-sample performance depend little on whether the predictor is peer-reviewed or data mined" — supporting the file's gloss. Authors confirmed (Chen, Lopez-Lira, Zimmermann); versions v1 Dec 20, 2022 through v7 Dec 29, 2025 — key sentences present in the current abstract.

## C23 — Jacobs-Müller JFE 2020: 241 anomalies, 39 markets, US-only post-publication decline — CONFIRMED

sciencedirect page paywalled, but fetched the repec journal listing directly (https://ideas.repec.org/a/eee/jfinec/v135y2020i1p213-230.html — JFE vol 135(1), 2020, pp 213-230). Abstract verbatim: "we study the pre- and post-publication return predictability of 241 cross-sectional anomalies in 39 stock markets", "based on more than two million anomaly country-months", "the United States is the only country with a reliable post-publication decline in long-short returns." All elements of C23 match. (The file's confidence "medium" is now conservative; the abstract is verified from a full journal listing.)

## C24 — Sullivan-Timmermann-White JF 1999: 7,846 rules, 100 years DJIA, OOS 1987-1996 failure — CONFIRMED

Fetched https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Sullivan_Timmermann_White.pdf, extracted text (The Journal of Finance, Vol. LIV, No. 5, October 1999). Abstract verbatim: "In this paper we utilize White's Reality Check bootstrap methodology... We consider the study of Brock, Lakonishok, and LeBaron (1992), expand their universe of 26 trading rules, apply the rules to 100 years of daily data on the Dow Jones Industrial Average, and determine the effects of data-snooping." Body: "We consider a very large number (7,846) of trading rules"; conclusion: "we also find that the superior performance of the best technical trading rule is not repeated in the out-of-sample experiment covering the 10-year period 1987–1996. In this sample the results are completely reversed and the best-performing trading rule is not even statistically significant at standard critical levels." All elements match. (Nitpick: the file's evidence line quotes the conclusion as "the best technical trading rule is not repeated...", eliding the leading words "the superior performance of" — meaning unchanged; the claim text itself paraphrases correctly.)

## C25 — STW 2001 calendar effects: 9,452 rules, effects dissolve under full-universe evaluation — CONFIRMED (verified against primary text this round)

Fetched the UCSD working-paper version of the paper itself (https://escholarship.org/content/qt2z02z6d9/qt2z02z6d9.pdf, UCSD Discussion Paper 98-16, June 1998), extracted text. Body verbatim: "The full set of calendar effects comprises 9,452 different rules." (with the composition summing "...+ 1,024 = 9,452"). Abstract verbatim: "We find that although nominal P-values of individual calendar rules are extremely significant, once evaluated in the context of the full universe from which such rules were drawn, calendar effects no longer remain significant." Journal publication corroborated: Journal of Econometrics, 2001, vol 105(1), pp 249-286 (ideas.repec listing + search). This round verifies the 9,452 count from the authors' own text, not merely a citing paper — the file's stated reason for "medium" confidence is now resolved; confidence could be upgraded to high (no text change required, claim as written is fully accurate).

## C26 — Lo-MacKinlay RFS 1990 data-snooping — CONFIRMED

Fetched https://www.nber.org/papers/w3001 directly. Abstract confirms: misleading inferences when "properties of the data [are used] to construct the test statistics"; focus on portfolios "sorted on some empirically motivated characteristic"; "Monte Carlo simulations... show the effects of this type of data-snooping to be substantial." Publication info confirmed: Review of Financial Studies, Vol. 3, No. 3, pp. 431-467 (1990). Matches the file (which correctly labels the quote "per NBER w3001 page").

## C27 — Harvey 2017 Presidential Address — CONFIRMED

Fetched https://people.duke.edu/~charvey/Research/Published_Papers/P131_The_scientific_outlook.pdf (The Journal of Finance, Vol. LXXII, No. 4, August 2017), extracted text. Abstract verbatim: "Given the competition for top journal space, there is an incentive to produce 'significant' results. With the combination of unreported tests, lack of adjustment for multiple tests, and direct and indirect p-hacking, many of the results being published will fail to hold up in the future." Minimum-Bayes-factor proposal verbatim: "I offer a simple alternative (the minimum Bayes factor)." Publication (JF 72:1399-1440, 2017) corroborated via search listings. All elements match.

## C28 — Synthesis / base-rate claim — CONFIRMED (as synthesis)

All quantitative anchors cited (HLZ t>3.0; 316/400+ counts; 27-53% false-discovery range; MP 26%/58%; CLZ ~50%) are individually verified above, and the qualitative inference drawn ("minority probability of being both real and genuinely new" for an in-sample t~2 candidate) follows from those inputs. No overstatement detected: the claim is framed as a base-rate argument, not a theorem.

---

## Minor nitpicks (not objections; no text changes required)

1. C24 evidence line: the quotation "the best technical trading rule is not repeated in the out-of-sample experiment..." silently drops the leading words "the superior performance of" from the source sentence. The claim text itself ("the best in-sample rule's performance 'is not repeated...'") is accurate. Suggest restoring the full clause if the quote is reused in REPORT.md.
2. C25 confidence: marked "medium" because the 9,452 count had only been verified via a citing paper. This round verified it from STW's own working-paper text (eScholarship UCSD 98-16). Confidence can be upgraded to high; wording of the claim needs no change.
3. C23 confidence: "medium (abstract corroborated via search snippets)" — the abstract is now verified from the repec full journal listing; could be upgraded.
4. C9 completeness: the NBER w23394 version compiles 447 anomaly variables (vs 452 in the RFS version). The file never claims a count for the NBER version, so this is informational only.
5. C6 bonus corroboration: Harvey's own research-page description of the census paper says it "details 382 factors published in top academic journals," independently agreeing with CXO's chart reading; the live Factor Census Google sheet exists (docs.google.com/spreadsheets/d/1mws1bU56ZAc8aK7Dvz696LknM0Vp4Rojc3n61q2-keY). This strengthens, and does not alter, the claim as written.
6. C22: the arXiv paper is now at v7 (Dec 29, 2025); the quoted sentences are present in the current abstract, so version drift is not an issue today, but pinning a version (e.g., v7) in the citation would be more robust.

## Source URLs used this round

- https://people.duke.edu/~charvey/Research/Published_Papers/P118_and_the_cross.PDF (fetched, text-extracted; C1-C5)
- https://global-q.org/uploads/1/2/2/6/122679606/houxuezhang2020rfs.pdf (fetched, text-extracted; C7-C9)
- https://www.nber.org/papers/w23394 (fetched; C9)
- https://www.cxoadvisory.com/big-ideas/equity-factor-census/ (fetched; C6)
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3341728 (blocked 403; abstract via search snippets; C6)
- https://www.semanticscholar.org/paper/A-Census-of-the-Factor-Zoo-Harvey-Liu/02e03489135809355e85d2b049859b695e5256e2 (search snippet; C6)
- https://docs.google.com/spreadsheets/d/1mws1bU56ZAc8aK7Dvz696LknM0Vp4Rojc3n61q2-keY/edit (existence; C6)
- https://tevgeniou.github.io/EquityRiskFactors/bibliography/AcademicReviewFactor.pdf (fetched, text-extracted; C10, C11, C13)
- https://www.fmg.ac.uk/sites/default/files/2020-08/Jeffrey-Pontiff.pdf (fetched, text-extracted; C12, C13)
- https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12365 (402 paywall; listing via search; C10)
- https://www.nber.org/system/files/working_papers/w28432/w28432.pdf (fetched, text-extracted; C14, C15)
- https://onlinelibrary.wiley.com/doi/full/10.1111/jofi.13249 (publication metadata via search; C14)
- https://www.federalreserve.gov/econres/feds/files/2021-037pap.pdf (fetched, text-extracted; C16, C17)
- https://ideas.repec.org/a/now/jnlcfr/104.00000112.html (via search; C16 CFR version)
- /home/user/quant/research/prior_art/signaldoc_chen_zimmermann.csv (recomputed with pandas; C18-C21)
- https://www.openassetpricing.com/ (fetched; C18)
- https://arxiv.org/abs/2212.10317 (fetched; C22)
- https://ideas.repec.org/a/eee/jfinec/v135y2020i1p213-230.html (fetched; C23)
- https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Sullivan_Timmermann_White.pdf (fetched, text-extracted; C24)
- https://escholarship.org/content/qt2z02z6d9/qt2z02z6d9.pdf (fetched, text-extracted; C25)
- https://ideas.repec.org/a/eee/econom/v105y2001i1p249-286.html (publication metadata; C25)
- https://www.nber.org/papers/w3001 (fetched; C26)
- https://people.duke.edu/~charvey/Research/Published_Papers/P131_The_scientific_outlook.pdf (fetched, text-extracted; C27)

## Verdict summary

28 claims checked (C1-C28): 28 CONFIRMED, 0 OVERSTATED, 0 WRONG, 0 UNVERIFIABLE. Per protocol, the prior_art file's status header is advanced to "status: agreed round 2".
