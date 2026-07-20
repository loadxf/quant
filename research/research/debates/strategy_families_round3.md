# Final adversarial verification — strategy_families.md — ROUND 3

Date: 2026-07-20. Verifier: final adversarial judge (round 3). The previous round-3 pass
crashed before ruling; this pass re-ran the verification from scratch.
Target: research/prior_art/strategy_families.md (post-round-2 revision, status "draft round 2").
Method: no prior audit summary was trusted. Every claim below was re-verified against sources
fetched during THIS pass: primary PDFs downloaded and text-extracted locally (pdftotext/pypdf),
publisher/Emerald/NBER pages via WebFetch, and web search where publishers 403'd (Wiley, HBS,
SSRN). Verdict scale: CONFIRMED / OVERSTATED / WRONG / UNVERIFIABLE.

**Bottom line: the one outstanding round-2 objection (C12) was fixed correctly by the round-2
revision — verified from two independent primary sources. All four claims whose text changed
in the round-2 revision (C1, C2, C4, C16) re-verified verbatim against primary full texts.
Five additional load-bearing numeric spot-checks (C6, C7, C17, C28, C29) all CONFIRMED. Two
precision-level edits applied (C29 sign hedge; C4 source provenance). Nothing load-bearing
remains wrong. Status advanced to "agreed round 3".**

---

## 1. What remained disputed after round 2

Round 2 (research/debates/strategy_families_round2.md) returned 29 CONFIRMED and exactly one
objection:

- **C12 — WRONG (study year + missing co-author).** The out-of-sample pre-holiday study was
  cited as "a 2021 out-of-sample study" by "Ko"; the auditor found it was published by Ko AND
  Yang in Critical Finance Review 13(3-4), 531–538, in 2024, with "2021" only the vintage in
  the CFR hosting filename.

The round-2 revision changed the header to "a 2024 out-of-sample study (Ko–Yang; accepted
2021)" and expanded the evidence line (CFR 13(3-4), 531–538, published 2024; sample 1983–2019;
small-firm-only survival; Emerald URL added). The crashed round-3 pass never independently
verified this fix — that is the item resolved here. Round 2 also listed five nitpicks (C1
Panel A envelopes, C2 sample clause, C4 quote marks/ranges, C16 alpha label, plus the C12
co-author fold-in), all of which the revision applied; since those edits post-date any audit,
they were re-verified here too.

## 2. Claims checked, evidence, and verdicts

### A. The outstanding objection

**C12 (Ko–Yang publication year/authors; Ariel magnitudes) — CONFIRMED (fix verified).**
- Emerald CFR article page, fetched directly
  (https://www.emerald.com/cfr/article-abstract/13/3-4/531/1326451/): "The Pre-Holiday Premium
  of Ariel (1990) Has Largely Become a Small-Firm Effect Out of Sample", authors Kuan-Cheng Ko
  and Nien-Tzu Yang, Critical Finance Review Vol. 13, No. 3-4, pp. 531–538, publication date
  August 12, 2024, DOI 10.1561/104.00000111. Matches the file's "2024... CFR 13(3-4), 531–538".
- CFR-hosted PDF (https://cfr.ivo-welch.org/published/papers/ko2021pre.pdf, downloaded and
  text-extracted): title page lists both authors; abstract verbatim: "Extending the sample to
  1983-2019, we find that the pre-holiday effect now exists only among small firms. For large
  firms, the differences in returns between pre-holidays and non-pre-holidays have become
  insignificant, and especially after 1990." Also confirms Ariel's magnitude as quoted in the
  file: CRSP EW/VW index pre-holiday returns "9 to 14 times higher" over 1963–1982.
- The "(accepted 2021)" parenthetical: PDF metadata shows creation June 16, 2021, and the
  manuscript already thanks "Ivo Welch (the editor) and an anonymous referee" — consistent
  with the 2021 acceptance vintage the file describes. The file's framing (filename reflects
  acceptance vintage, not publication year) is accurate.
- Ruling: round-2 fix stands as written. No change.

### B. Round-2 revision wording re-verified (text changed after the last audit)

**C1 (Jegadeesh–Titman 1993 Table I envelopes) — CONFIRMED.**
- Primary full text (https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf, extracted
  locally). Table I buy-sell rows read directly from the extraction: J=3 Panel A
  0.32/0.58/0.61/0.69; J=6 Panel A 0.84/0.95/1.02/0.86; J=9 Panel A 1.09/1.21/1.05/0.82;
  J=12 Panel A 1.31/1.14/0.93/0.68; Panel B 12/3 = 1.49 (t=4.28 per the text). So: minimum
  0.32% (3/3 no-skip), maximum 1.31% Panel A / 1.49% Panel B; 6-month formation Panel A
  envelope 0.84–1.02; 12-month formation envelope 0.68–1.31 — the revision's numbers exactly.
- Text verbatim: "All these returns are statistically significant except for the
  3-month/3-month strategy that does not skip a week"; "This strategy yields 1.31% per month
  (shown in Panel A)... 1.49% per month (shown in Panel B)"; abstract's dissipation sentence
  present. Sample "January 1965 to December 1989" on the table note.

**C2 (MOP 2012 sample clause) — CONFIRMED.**
- Published PDF (https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf,
  extracted locally): "equity index, currency, commodity, and bond futures for each of the 58
  liquid instruments we consider"; futures data "from January 1965 through December [2009]";
  TSMOM returns computed for each "available month from January 1985 to December 2009". The
  revision's clause (evaluation sample 1985–2009; underlying data begin Jan 1965) is exact.

**C4 (Lehmann weekly ranges; quote-mark removal) — CONFIRMED, with a provenance fix.**
- NBER WP 2533 full text (https://www.nber.org/system/files/working_papers/w2533/w2533.pdf,
  downloaded and extracted): verbatim: "positive returns in one week typically had negative
  returns in the next week (on average, -0.35 to -0.55 per cent per week) while those with
  negative returns in one week typically had positive returns in the next week (on average,
  0.86 to 1.24 per cent per week)"; sample "securities listed on the New York and American
  Stock Exchanges between July 1962 and December 1986". The revision's restatement as ranges
  is exactly right, and the un-quoted ">2% per month" characterization remains conservative
  (the costless weekly portfolio profits are far larger).
- NBER abstract page (https://www.nber.org/papers/w2533) contains no magnitudes — the ranges
  come from the WP body text.
- Provenance issue found: the cited martinsewell Lehmann1990.pdf is an image-only scan (zero
  extractable text — pdftotext yields 28 bytes), so it cannot be the verbatim source of the
  ranges. RULING APPLIED: source line annotated (scan flagged image-only) and the NBER WP 2533
  PDF added as the verbatim source of the ranges.

**C16 (Lou–Polk–Skouras alpha labels) — CONFIRMED.**
- Published JFE PDF (https://personal.lse.ac.uk/polk/research/TugOfWar.pdf, extracted
  locally). Masthead "Journal of Financial Economics 134 (2019) 192–213". Abstract verbatim:
  "profits are either earned entirely overnight (for reversal and a variety of momentum
  strategies) or entirely intraday, typically with profits of opposite signs across these
  components". Conclusion verbatim: "essentially all of the abnormal returns on momentum and
  short-term reversal strategies occur overnight while the abnormal returns on other
  strategies occur intraday". STR paragraph verbatim: "the intraday CAPM alpha is −1.05%
  (t-statistic of −3.25) while the overnight three-factor alpha is 0.93% (t-statistic of
  4.28)" — the revision's relabeling (generic "overnight alpha", CAPM label kept only on the
  intraday side) is exactly faithful. Table 2 STR row 0.93/−1.05 with (4.28)/(−3.25)
  confirmed. Smoothed overnight-minus-intraday spread "forecasts time variation in that
  strategy's close-to-close performance" confirmed.

### C. Spot-checks (5 additional load-bearing numeric claims)

**C6 (Frazzini–Pedersen BAB Sharpes) — CONFIRMED.**
- Authors' PDF (https://pages.stern.nyu.edu/~lpederse/papers/BettingAgainstBeta.pdf,
  extracted locally): "The U.S. BAB factor realizes a Sharpe ratio of 0.78 between 1926 and
  March 2012... its Sharpe ratio is about twice that of the value effect and 40% higher than
  that of momentum over the same time period"; Treasury section: "BAB portfolio delivers
  abnormal returns of 0.17% per month (t-statistic = 6.26) with a large annual Sharpe ratio
  of 0.81"; "within each of the 19 other developed MSCI stock markets". All match the file.

**C7 (Koijen–Moskowitz–Pedersen–Vrugt Carry, published Sharpes) — CONFIRMED.**
- Published JFE PDF (S3 mirror,
  https://spinup-000d1a-wp-offload-media.s3.amazonaws.com/faculty/wp-content/uploads/sites/3/2019/04/Carry.pdf,
  extracted locally): masthead "Journal of Financial Economics 127 (2018) 197–225"; abstract
  asset-class list verbatim ("global equities, global bonds, commodities, US Treasuries,
  credit, and options"); text: "...alized Sharpe ratio of 0.8 on average. Further, a
  diversified [portfolio of carry strategies across all asset classes earns a] Sharpe ratio
  of 1.2." Matches the file's published-version figures (1.2 diversified, 0.8 average).

**C17 (NY Fed overnight drift + 2026 decay) — CONFIRMED.**
- SR 917 PDF (https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr917.pdf,
  extracted locally): verbatim "More than half of this return is generated during the ON
  session: from 16:15 to 9:30 equity returns averaged 3.6% p.a. More striking than this, the
  return earned during the 2:00 to 3:00 hour averaged 3.7% p.a. We dub this return sequence
  the 'overnight drift'"; authors Nina Boyarchenko, Lars C. Larsen, Paul Whelan.
- Liberty Street Economics post fetched directly
  (https://libertystreeteconomics.newyorkfed.org/2026/07/the-disappearing-overnight-drift/):
  July 1, 2026, same three authors; the 2:00–3:00 window "previously generated roughly 3.7
  percent per annum" but has "averaged close to zero since 2021", attributed mainly to
  reduced end-of-day order imbalances. Matches the file, including the Synthesis's
  "went to zero after 2021" decay lesson.

**C28 (Petajisto 2011 index premium) — CONFIRMED.**
- Author-hosted PDF
  (https://www.petajisto.net/papers/petajisto%202011%20jef%20-%20hidden%20cost%20for%20index%20funds.pdf,
  extracted locally): abstract verbatim: sample "from 1990 to 2005"; additions "+8.8% and
  +4.7%, respectively, and −15.1% and −4.6% for deletions"; "premia have been growing over
  time, peaking in 2000"; cost lower bound "21–28 bp for the S&P 500 and 38–77 bp for the
  Russell 2000" (body, Section conclusions). All six numbers verbatim.

**C29 (Greenwood–Sammon disappearing index effect) — CONFIRMED, with one precision edit.**
- Wiley and HBS pages 403'd this pass; the published JF 80(2), 657–698 (April 2025) abstract
  was confirmed via web search surfacing the HBS/Harvard DASH records
  (https://www.hbs.edu/faculty/Pages/item.aspx?num=65745 ;
  https://dash.harvard.edu/entities/publication/2cc676bd-c8da-40e7-b112-3ecc8644e687 ;
  https://ideas.repec.org/a/bla/jfinan/v80y2025i2p657-698.html): "The abnormal return
  associated with a stock being added to the S&P 500 has fallen from an average of 7.4% in
  the 1990s to 0.3% over the past decade... A similar pattern has occurred for index
  deletions, with large negative abnormal returns during the 1990s, but only 0.1% between
  2010 and 2020." The 7.4% → 0.3% addition decay and the 0.1% deletion figure match the file.
- Precision issue: the abstract states the recent-decade deletion figure as "only 0.1%"
  WITHOUT a sign; the file's header asserted "−0.1%-scale". RULING APPLIED: header softened
  to "a 0.1% magnitude (abstract states the figure without sign)". Evidence line already
  quoted the abstract correctly and is unchanged.

## 3. Rulings applied to the file

1. **C12 — CONFIRMED, no change.** The round-2 fix (2024, Ko–Yang, accepted-2021 vintage) is
   verified from the Emerald record and the paper itself.
2. **C1, C2, C16 — CONFIRMED, no change.** Round-2 revision wording matches primary full
   texts word-for-word and number-for-number.
3. **C4 — CONFIRMED; provenance annotation applied.** Weekly-reversal ranges verified
   verbatim in NBER WP 2533; the image-only martinsewell scan flagged as such and the WP PDF
   added to the source line.
4. **C6, C7, C17, C28 — CONFIRMED, no change.**
5. **C29 — CONFIRMED; one-word-scale softening applied** (deletion figure stated as a 0.1%
   magnitude, sign not given in the abstract).

## 4. Status decision

The single outstanding objection is resolved (fix verified correct), every revision-touched
claim re-verifies against primary sources, and all five spot-checks are CONFIRMED. The two
edits applied are precision/provenance improvements, not corrections of load-bearing errors.
No residual disputes remain. Status header advanced to **"agreed round 3"**.
