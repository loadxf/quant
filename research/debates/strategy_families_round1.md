# Adversarial verification round 1 — research/prior_art/strategy_families.md

Verifier: independent adversarial pass (round 1), 2026-07-19.
Method: every load-bearing claim (all numbers, years, journal cites, and characterizations of
what papers found) was re-verified against sources fetched during this audit — primary PDFs
where obtainable (extracted locally), otherwise publisher/NBER/RePEc abstracts or multiple
concordant secondary sources. I did not rely on the researcher's quotes.

Overall verdict: 27 of 30 claims CONFIRMED. Three claims contain real errors (C1 range,
C16 strategy classification, C24 control list). Status header NOT advanced to "agreed".

---

## Claim-by-claim verdicts

### C1. Jegadeesh–Titman 1993 — OVERSTATED (one evidence number wrong; header fine)
- CONFIRMED: JF 48(1), 65–91, March 1993 (verified from JSTOR scan of the paper). Abstract:
  "strategies which buy stocks that have performed well in the past and sell stocks that have
  performed poorly in the past generate significant positive returns over 3- to 12-month
  holding periods" — verbatim match. "Roughly 1% per month" headline: paper says the 6-month
  formation period "produces returns of about 1% per month regardless of the holding period."
- ERROR: the Evidence line says "across the 16 formation/holding combinations average monthly
  returns ran about 0.9%–1.3%". The paper's Table I (no-skip panel) actually runs from 0.32%
  per month (3-month/3-month, the only strategy not statistically significant) up to 1.31%
  (12-month/3-month); the 1-week-skip panel runs up to 1.49%. The 0.9–1.3% band describes only
  the 6- and 12-month formation strategies, not all 16 combinations. Paper text verified
  directly: "This strategy yields 1.31% per month... and it yields 1.49% per month... The
  6-month formation period produces returns of about 1% per month"; "All these returns are
  statistically significant except for the 3-month/3-month strategy that does not skip a week."
- Source: https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf (full text extracted).

### C2. Time-series momentum (Moskowitz–Ooi–Pedersen 2012) — CONFIRMED
- AQR journal-article page: "58 diverse futures and forward contracts that include country
  equity indices, currencies, commodities and sovereign bonds"; "persists for about a year and
  then partially reverses over longer horizons"; profits "positive... for every asset contract."
  JFE 104, 228–250 correct. The TSMOM factor/portfolio results cover Jan 1985–Dec 2009
  (dataset back to 1965), consistent with "sample 1985–2009".
- Source: https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum

### C3. Quantpedia TSMOM backtest — CONFIRMED
- Direct fetch of the Quantpedia page: Sharpe Ratio 1.31; 20.7% p.a.; volatility 15.74%;
  max drawdown −33.87%; backtest period 1965–2009; 58 instruments (24 commodities, 12 FX
  pairs, 9 equity indices, 13 bond futures); figures sourced from MOP Table 3 Panel A.
- Nitpick (not an objection): Quantpedia's footnote describes the 20.7% as "estimated alpha
  (using Fama&French factors)", which the file rounds to "annual return". Internally consistent
  with Sharpe 1.31 x vol 15.74%, so immaterial, but worth tightening.
- Source: https://quantpedia.com/strategies/time-series-momentum-effect

### C4. Short-term reversal (Jegadeesh 1990; Lehmann 1990) — CONFIRMED
- Jegadeesh 1990 (JF 45, 881–898): RePEc/IDEAS abstract verbatim: "The difference between the
  abnormal returns on the extreme decile portfolios over the period 1934-87 is 2.49 percent
  per month." File's 2.49%/month, 1934–1987 exact.
  https://ideas.repec.org/a/bla/jfinan/v45y1990i3p881-98.html
- Lehmann 1990 (QJE 105(1), 1–28, Feb 1990): primary scan read page-by-page. Abstract: winners
  and losers "one week experience sizeable return reversals the next week in a way that
  reflects apparent arbitrage profits which persist after corrections for bid-ask spreads and
  plausible transactions costs." Table II (1962–1986): winner portfolios averaged −0.55%/week,
  loser portfolios +1.24%/week (weights on previous week's return), i.e., contrarian spreads
  far in excess of 2% per month — the file's ">2% per month" is conservative and supported.
  https://finance.martinsewell.com/stylized-facts/dependence/Lehmann1990.pdf
- The file's own "Confidence: medium" honesty note can now be upgraded: both magnitudes are
  primary-verified.

### C5. Long-term reversal (De Bondt–Thaler 1985) — CONFIRMED
- Paper text (JF, July 1985): loser portfolios of 35 stocks outperform the market by 19.6% on
  average thirty-six months after formation; winners earn about 5.0% less than the market;
  cumulative difference 24.6% ("roughly 25%" in the header is fair). Overreaction asymmetric,
  larger for losers; most excess returns in January. NYSE monthly data 1926–1982.
- Sources: https://onlinelibrary.wiley.com/doi/full/10.1111/j.1540-6261.1985.tb05004.x
  (paywalled); figures verified via full-text mirrors surfaced in search, e.g.
  https://www.academia.edu/7502534/Does_the_Stock_Market_Overreact and the replication
  literature quoting the same sentences.

### C6. Betting-against-beta (Frazzini–Pedersen 2014) — CONFIRMED
- Verified directly from the authors' PDF (extracted text): "The U.S. BAB factor realizes a
  Sharpe ratio of 0.78 between 1926 and March 2012... about twice that of the value effect and
  40% higher than that of momentum over the same time period." Treasury BAB: "delivers abnormal
  returns of 0.17% per month (t-statistic = 6.26) with a large annual Sharpe ratio of 0.81."
  Also confirmed: BAB constructed "within each of the 19 other developed MSCI stock markets";
  credit BAB Sharpe 0.82. JFE 111, 1–25 correct.
- Source: https://pages.stern.nyu.edu/~lpederse/papers/BettingAgainstBeta.pdf
  (redirects to https://w4.stern.nyu.edu/facdir/lpederse/papers/BettingAgainstBeta.pdf)

### C7. Carry (Koijen–Moskowitz–Pedersen–Vrugt) — CONFIRMED (as stated), with an update note
- The claim attributes the Sharpe figures to "working-paper versions", which checks out
  verbatim in NBER WP 19325: "Forming a portfolio of carry strategies diversified across all
  asset classes earns a Sharpe ratio of 1.1"; "the diversified carry trade has a remarkable
  Sharpe ratio of 1.10 per annum"; individual asset-class carry Sharpes "range from 0.37 for
  call options to 1.80 for put options, with the average being 0.74" (≈0.7 as claimed).
  https://www.nber.org/system/files/working_papers/w19325/w19325.pdf
- Published JFE 127(2), 197–225 (2018) version verified from the journal PDF: "an annualized
  Sharpe ratio of 0.8 on average. Further, a diversified portfolio of carry strategies across
  all asset classes earns a Sharpe ratio of 1.2." Asset classes (global equities, global bonds,
  commodities, US Treasuries, credit, options) and the abstract quote match.
  https://spinup-000d1a-wp-offload-media.s3.amazonaws.com/faculty/wp-content/uploads/sites/3/2019/04/Carry.pdf
- Recommendation (nitpick, not objection): cite the published numbers (1.2 diversified, 0.78
  average) since the anchor citation is the JFE version. Note an early July 2012 WP said 1.5,
  so version matters.

### C8. Turn-of-the-month (Lakonishok–Smidt 1988; Xu–McConnell 2008) — CONFIRMED
- Verified directly from the Xu–McConnell PDF (extracted): abstract matches the file nearly
  verbatim, including "over this 19-year period (and over the 109-year period of 1897-2005)
  all of the excess market return occurred during the four-day turn-of-the-month interval",
  the no-reward-for-risk statement for the other 16 trading days, and the
  not-confined-to-small-stocks / quarter-ends / US robustness list. L&S 1988 DJIA 1897–1986
  attribution confirmed in the same text.
- Source: https://www.chesler.us/resources/academia/turn_of_the_month_stock_returns.pdf

### C9. January effect (Rozeff–Kinney 1976; Keim 1983) — CONFIRMED
- Rozeff–Kinney: multiple independent sources give exactly "average return on an equal-weighted
  index of NYSE prices from 1904 through 1974 was 3.5 percent during January and only about
  0.5 percent during the other months" (e.g., https://economics.wm.edu/wp/cwm_wp15.pdf).
  Original: JFE 3, 379–402.
- Keim 1983 (JFE 12, 13–32): "nearly fifty percent of the average magnitude of the 'size
  effect' over the period 1963–1979 is due to January abnormal returns" — confirmed via
  abstract (https://www.sciencedirect.com/science/article/abs/pii/0304405X83900259 and
  Semantic Scholar mirror).

### C10. Halloween / sell-in-May (Bouman–Jacobsen 2002) — CONFIRMED
- AER 92(5), 1618–1635. "The Sell in May effect is present in 36 of the 37 countries in our
  sample"; sample January 1970–August 1998; 37 countries across Europe, North America, Asia,
  Africa, Australia. (Minor: sample ends August 1998, so "1970–1998" is fine.)
- Sources: https://www.aeaweb.org/articles?id=10.1257%2F000282802762024683 (metadata);
  quotes verified via multiple mirrors of the paper surfaced in search.

### C11. Weekend effect (French 1980) — CONFIRMED
- Verified directly from the paper PDF (extracted): "During most of the period studied, from
  1953 through 1977, the daily returns to the Standard and Poor's composite portfolio are
  inconsistent with both models. Although the average return for the other four days of the
  week was positive, the average for Monday was significantly negative during each of five
  five-year subperiods." JFE 8(1), 55–69 correct.
- Source: https://www-2.rotman.utoronto.ca/~kan/3032/pdf/AssetPricingAnomalies/French_JFE_1980.pdf

### C12. Pre-holiday effect (Ariel 1990; Ko 2021) — CONFIRMED
- Ko & Yang (Critical Finance Review), title verified verbatim: "The Pre-Holiday Premium of
  Ariel (1990) Has Largely Become A Small-Firm Effect Out of Sample". Its abstract confirms
  Ariel's finding ("9 to 14 times higher") and the CRSP EW/VW indices over 1963–1982, plus the
  out-of-sample decay to a small-firm effect (extended sample 1983–2019; insignificant for
  large firms especially after 1990).
- Nitpick: Ariel's indices are CRSP EW/VW (which cover NYSE/AMEX in that era); the file's
  "NYSE/AMEX" gloss is acceptable.
- Source: https://cfr.ivo-welch.org/published/papers/ko2021pre.pdf (redirect of the cited URL)

### C13. Heston–Sadka 2008 — CONFIRMED
- Verified directly from the cited PDF (extracted): "a general pattern... that lasts up to
  [for] 20 annual lags"; "these strategies produce significantly positive returns for up to
  20 years, averaging over 50 basis points per month."
- Source: https://w4.stern.nyu.edu/finance/docs/pdfs/Seminars/063f-sadka.pdf

### C14. Keloharju–Linnainmaa–Nyberg 2016 — CONFIRMED
- NBER WP 20815 abstract: "A strategy that selects stocks based on their historical
  same-calendar-month returns earns an average return of 13% per year"; seasonalities in
  anomalies, commodities, international indices, daily frequency.
- Source: https://www.nber.org/papers/w20815

### C15. Overnight vs intraday (Cooper–Cliff–Gulen 2008) — CONFIRMED
- SSRN abstract (id 1004081) via search mirrors: "The US equity premium over the last decade is
  solely due to overnight returns"; S&P 500 stocks 1993–2006; holds for individual stocks,
  indexes, futures, NYSE and Nasdaq; partly driven by high opening prices declining in the
  first trading hour.
- Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1004081

### C16. Tug of war (Lou–Polk–Skouras 2019) — WRONG on strategy classification (header)
- Verified from the published JFE PDF (extracted). Abstract: "profits are either earned
  entirely overnight (for reversal and a variety of momentum strategies) or entirely intraday,
  typically with profits of opposite signs across these components." Conclusion: "essentially
  all of the abnormal returns on momentum and short-term reversal strategies occur overnight
  while the abnormal returns on other strategies occur intraday." The short-term reversal
  strategy's overnight alpha is +0.93% (t=4.28) vs intraday −1.05% (t=−3.25).
- ERROR: the file's header says profits accrue "either entirely overnight (momentum-type) or
  entirely intraday (reversal/value-type)". That mis-sorts reversal: reversal profits accrue
  OVERNIGHT (with momentum); the intraday group is the value/size/profitability/etc. group.
  The file's own Evidence quote (which is accurate) contradicts its header.
- CONFIRMED: JFE 134(1), 192–213; 14 strategies (size, value, price/earnings/industry/
  time-series momentum, profitability, investment, idiosyncratic volatility, beta, turnover,
  equity issuance, discretionary accruals, short-term reversals); overnight/intraday
  persistence "lasts for years"; smoothed overnight-minus-intraday spread forecasts
  close-to-close strategy performance.
- Source: https://personal.lse.ac.uk/polk/research/TugOfWar.pdf

### C17. Overnight drift (NY Fed SR 917) + 2026 follow-up — CONFIRMED
- Verified directly from the staff report PDF (extracted): "More than half of this return is
  generated during the ON session: from 16:15 to 9:30 equity returns averaged 3.6% p.a. More
  striking than this, the return earned during the 2:00 to 3:00 hour averaged 3.7% p.a."
  Authors Boyarchenko, Larsen, Whelan confirmed; European-open framing confirmed ("U.S. equity
  returns are large and positive during the opening hours of European markets").
  https://www.newyorkfed.org/research/staff_reports/sr917
- Liberty Street Economics (July 2026), "The Disappearing Overnight Drift": "the 2:00–3:00
  window that previously generated roughly 3.7 percent per annum... has averaged close to zero
  since 2021" — fetched directly; matches the file.
  https://libertystreeteconomics.newyorkfed.org/2026/07/the-disappearing-overnight-drift/

### C18. Customer momentum (Cohen–Frazzini 2008) — CONFIRMED
- JF 63(4), 1977–2011. Abstract (via SSRN/IDEAS mirrors surfaced in search): "a long/short
  equity strategy based on this effect yields monthly alphas of over 150 basis points";
  investor-inattention mechanism confirmed.
- Sources: https://ideas.repec.org/a/bla/jfinan/v63y2008i4p1977-2011.html ;
  https://www.hbs.edu/faculty/Pages/item.aspx?num=31700

### C19. Industry momentum (Moskowitz–Grinblatt 1999) — CONFIRMED
- JF 54(4), 1249–1290. Abstract verbatim match: "strong and prevalent momentum effect in
  industry components of stock returns which accounts for much of the individual stock
  momentum anomaly"; industry momentum "highly profitable, even after controlling for size,
  book-to-market equity, individual stock momentum, the cross-sectional dispersion in mean
  returns, and potential microstructure influences." Sample: industry portfolios formed every
  month "from July 1963 to July 1995" (verified via replications quoting the data section).
- Sources: https://ideas.repec.org/a/bla/jfinan/v54y1999i4p1249-1290.html ;
  http://www-stat.wharton.upenn.edu/~steele/Courses/956/Resource/Momentum/MoskowitzGrinblatt99.pdf

### C20. Intra-industry lead-lag (Hou 2007) — CONFIRMED
- RFS 20(4), 1113–1138. Abstract: lead-lag between big and small firms "is predominantly an
  intra-industry phenomenon", "driven by sluggish adjustment to negative information",
  stronger in small, less competitive, neglected industries; related to small firms' drift
  after big firms' earnings releases. All match.
- Source: https://ideas.repec.org/a/oup/rfinst/v20y2007i4p1113-1138.html

### C21. Size lead-lag / cross-autocorrelation (Lo–MacKinlay 1990) — CONFIRMED
- RFS 3(2), 175–205 (NBER WP 2977). Abstract: contrarian profits can arise from positive
  cross-autocovariances even with independent individual returns; "lead-lag relations across
  securities" with larger stocks leading; evidence against overreaction as the primary source;
  weak individual autocorrelations coexist with strong portfolio autocorrelations.
- Source: https://www.nber.org/papers/w2977

### C22. Pairs trading (Gatev–Goetzmann–Rouwenhorst 2006) — CONFIRMED
- RFS 19(3), 797–827, daily data 1962–2002: "a simple trading rule yields average annualized
  excess returns of up to 11% for self-financing portfolios of pairs." (The 1999 NBER WP
  w7032, 1962–1997 sample, said "up to 12 percent" — the file correctly uses the published
  11% figure.)
- Sources: https://ideas.repec.org/a/oup/rfinst/v19y2006i3p797-827.html ;
  https://www.nber.org/papers/w7032

### C23. High-volume return premium (Gervais–Kaniel–Mingelgrin 2001) — CONFIRMED
- JF 56, 877–919. Abstract: "stocks experiencing unusually high (low) trading volume over a
  day or a week tend to appreciate (depreciate) over the course of the following month";
  visibility/attention mechanism confirmed.
- Source: https://ideas.repec.org/a/bla/jfinan/v56y2001i3p877-919.html

### C24. Amihud illiquidity (2002) — OVERSTATED (control list inflated)
- CONFIRMED from the full paper PDF (extracted): JFM 5, 31–56; ILLIQ = "average across stocks
  of the daily ratio of absolute stock return to dollar volume"; "over time, expected market
  illiquidity positively affects ex ante stock excess return"; price-impact interpretation.
- ERROR: the Evidence line says the cross-sectional effect "survives size, book-to-market, and
  beta controls." The paper's cross-sectional model controls beta, SIZE, volatility (SDRET),
  dividend yield, and past returns (R100, R100YR) — and explicitly does NOT include
  book-to-market: "The model does not include the ratio of book-to-market equity, BE/ME...
  This study employs only NYSE stocks for which BE/ME was found to have no significant effect."
- Source: https://www.cis.upenn.edu/~mkearns/finread/amihud.pdf

### C25. 52-week-high momentum (George–Hwang 2004) — CONFIRMED
- Verified directly from the paper PDF (extracted). Abstract verbatim: "Nearness to the
  52-week high dominates and improves upon the forecasting power of past returns (both
  individual and industry returns) for future returns. Future returns forecast using the
  52-week high do not reverse in the long run." JF 59(5), Oct 2004 (pages 2145–2176 correct).
- Source: https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf

### C26. Variance risk premium (Carr–Wu 2009) — CONFIRMED
- Verified directly from the paper PDF (extracted): variance swap rate synthesized from an
  options portfolio; VRP quantified as difference between realized variance and the synthetic
  swap rate; "five stock indexes and 35 individual stocks"; "average risk premia on return
  variances are strongly negative for the S&P 500 and 100 indexes"; CAPM's negative beta "can
  only explain a small portion"; "The common risk factors identified by Fama and French (1993)
  cannot explain the strongly negative variance risk premia, either." RFS 22(3), 1311–1341.
- Source: https://engineering.nyu.edu/sites/default/files/2019-01/CarrReviewofFinStudiesMarch2009-a.pdf

### C27. VIX futures basis (Simon–Campasano 2014) — CONFIRMED
- Verified directly from the paper PDF (extracted). Abstract: "the VIX futures basis does not
  have significant forecast power for the change in the VIX spot index from 2006 through 2011
  but does have forecast power for subsequent VIX futures returns"; short-in-contango /
  long-in-backwardation "hedged with mini-S&P 500 futures positions"; "highly profitable and
  robust to transaction costs." Data section: "from January 2006 through the end of December
  2011." Journal of Derivatives 21(3), 54–69 confirmed.
- Source: https://jod.pm-research.com/content/21/3/54.abstract ; full text via
  https://github.com/emintham/Papers/blob/master/Simon,Campasano-%20The%20VIX%20Futures%20Basis:%20Evidence%20and%20Trading%20Strategies.pdf

### C28. Index reconstitution premium (Petajisto 2011) — CONFIRMED
- Verified directly from the cited PDF (extracted). Abstract: "+8.8% and +4.7%, respectively,
  and −15.1% and −4.6% for deletions... estimate its lower bound as 21–28 bp annually for the
  S&P 500 and 38–77 bp annually for the Russell 2000"; sample 1990–2005; "premia have been
  growing over time, peaking in 2000." JEF 18(2), 271–288 correct.
- Source: https://www.petajisto.net/papers/petajisto%202011%20jef%20-%20hidden%20cost%20for%20index%20funds.pdf

### C29. Disappearing index effect (Greenwood–Sammon 2025) — CONFIRMED
- Published JF 80(2), 657–698 (April 2025). Published abstract (via search of the Wiley/RePEc
  record): additions "fallen from an average of 7.4% in the 1990s to 0.3% over the past
  decade"; deletions "only 0.1% between 2010 and 2020". Matches the file. (Caution for future
  rounds: draft versions differ — the June 2023 HBS draft says 7.6%→0.8% and −0.6%; cite only
  the published JF numbers, as the file does.)
- Sources: https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13410 ;
  https://ideas.repec.org/a/bla/jfinan/v80y2025i2p657-698.html

### C30. ETF premium/discount reversion (Petajisto 2017) — CONFIRMED
- CFA Institute page for FAJ 73(1): deviations "within a band of about 200 bps"; after the
  similar-ETF stale-pricing control "the average pricing band remains economically significant
  at about 100 bps"; strategies "produce substantial abnormal returns before transaction
  costs"; short-term mean reversion confirmed.
- Source: https://rpc.cfainstitute.org/research/financial-analysts-journal/2017/inefficiencies-in-the-pricing-of-exchange-traded-funds

---

## Objections (non-CONFIRMED load-bearing claims)

1. **C1 — OVERSTATED.** "across the 16 formation/holding combinations average monthly returns
   ran about 0.9%–1.3%" — actual Table I range is 0.32% (3/3 no-skip, insignificant) to 1.31%
   (12/3 no-skip; 1.49% with skip). Fix: "about 1% per month on average, from 0.32% (3/3) to
   1.49% (12/3 with 1-week skip); 6- and 12-month formations cluster around 0.9%–1.3%."
2. **C16 — WRONG (classification).** Reversal-strategy profits accrue overnight together with
   momentum; the intraday group is value/size/profitability/etc. The header's parenthetical
   "(reversal/value-type)" for the intraday side contradicts the paper (and the file's own
   quote). Fix header to: "entirely overnight (momentum and short-term reversal) or entirely
   intraday (value-type and most other anomalies)."
3. **C24 — OVERSTATED.** Amihud 2002 does not control for book-to-market; the paper explicitly
   excludes BE/ME. Fix: "survives beta, size, volatility, dividend-yield, and past-return
   controls."

## Minor nitpicks (not objections)

- C3: Quantpedia's 20.7% figure is labeled by Quantpedia as estimated FF alpha p.a., not raw
  annual return.
- C7: anchor citation is JFE 2018, but the Sharpes quoted are from NBER WP 19325 (1.1 / 0.74);
  published version says 1.2 / 0.78 ("0.8 on average"). Update to published numbers.
- C10: Bouman–Jacobsen sample is Jan 1970–Aug 1998 (file says 1970–1998 — acceptable).
- C12: Ariel used CRSP EW/VW indices (NYSE/AMEX universe) — file's "NYSE/AMEX" gloss is fine.
- C4: confidence can be upgraded from "medium" — both magnitudes now primary-verified
  (Jegadeesh 2.49%/month via IDEAS abstract; Lehmann Table II winners −0.55%/week vs losers
  +1.24%/week, 1962–1986).

## Disposition

Three objections above must be fixed before the file can be marked agreed. Everything else,
including all Sharpe ratios, basis-point magnitudes, sample years, journal volumes, and decay
claims (C17 overnight-drift death post-2021; C29 index-effect decay), verified against
independently fetched sources.
