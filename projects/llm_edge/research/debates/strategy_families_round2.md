# Adversarial audit — strategy_families.md — ROUND 2

Date: 2026-07-19. Auditor: adversarial verifier (round 2), independent re-verification.
Target: research/prior_art/strategy_families.md (post-round-1 revision, status "draft round 1").
Method: every load-bearing claim re-verified against sources fetched by this auditor
(WebFetch/WebSearch, plus direct text extraction from the primary PDFs with pypdf —
several publisher pages 403/425/503'd, in which case the primary full-text PDF or the
publisher abstract via an independent mirror was used). No researcher quote was trusted
without re-fetching.

Verdict scale: CONFIRMED / OVERSTATED / WRONG / UNVERIFIABLE.

**Bottom line: 30 claims checked. 29 CONFIRMED. 1 error (C12: the Ko out-of-sample study
is published 2024, not 2021, and is by Ko AND Yang). Several nitpicks listed at the end.
Status NOT advanced to "agreed round 2" — one load-bearing year claim is wrong; the fix
is a one-line edit.**

---

## Claim-by-claim verdicts

**C1 (Jegadeesh–Titman 1993) — CONFIRMED.**
Verified directly from the JSTOR full-text PDF (fetched from
https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf, text extracted locally):
- Cover page: The Journal of Finance, Vol. 48, No. 1 (Mar. 1993), pp. 65–91. ✓
- Abstract verbatim: "strategies which buy stocks that have performed well in the past and
  sell stocks that have performed poorly in the past generate significant positive returns
  over 3- to 12-month holding periods" ✓; "part of the abnormal returns generated in the
  first year after portfolio formation dissipates in the following two years" ✓.
- Table I (p. 70): "The sample period is January 1965 to December 1989." ✓
- Panel A (no skip) buy-sell values: J=3: 0.32/0.58/0.61/0.69; J=6: 0.84/0.95/1.02/0.86;
  J=9: 1.09/1.21/1.05/0.82; J=12: 1.31/1.14/0.93/0.68. Min = 0.32% (3/3, t=1.10), max =
  1.31% (12/3). Panel B 12/3 = 1.49% (t=4.28). ✓ Exactly as the file states.
- Text p. 69: "All these returns are statistically significant except for the
  3-month/3-month strategy that does not skip a week" ✓ ("the only insignificant
  strategy"); "The 6-month formation period produces returns of about 1% per month
  regardless of the holding period" ✓ verbatim.
- Nitpick (not an objection): "the 6- and 12-month formation strategies cluster around
  0.9%–1.3%" is loose — Panel A J=6 runs 0.84–1.02 and J=12 runs 0.68–1.31, so the true
  envelope is 0.68–1.49 including Panel B; "cluster around" saves it, but 0.84–1.31 (Panel
  A) would be tighter.

**C2 (Moskowitz–Ooi–Pedersen 2012) — CONFIRMED.**
- AQR page (https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum):
  "58 diverse futures and forward contracts", asset classes = country equity indices,
  currencies, commodities, sovereign bonds; "past 12-month excess return of each
  instrument is a positive predictor of its future return"; effect "persists for about a
  year and then partially reverses over longer horizons". ✓
- IDEAS (https://ideas.repec.org/a/eee/jfinec/v104y2012i2p228-250.html): JFE 104(2),
  228–250, 2012 ✓; abstract: "significant 'time series momentum' in equity index,
  currency, commodity, and bond futures for each of the 58 liquid instruments we
  consider"; "persistence in returns for one to 12 months that partially reverses over
  longer horizons"; "A diversified portfolio of time series momentum strategies across all
  asset classes delivers substantial abnormal returns with little exposure to standard
  asset pricing factors and performs best during extreme markets." ✓ All quoted phrases
  match.
- Sample: published PDF (w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf,
  extracted locally): "We compute this return for each instrument and each available month
  from January 1985 to December 2009"; "For the evaluation of time series momentum
  strategies, we rely on the sample starting in 1985"; underlying futures data are Jan
  1965–Dec 2009 (24 commodities + 12 currency pairs + 9 equity indexes + 13 bond futures
  = 58). File's "sample 1985–2009" is the correct TSMOM-evaluation sample. ✓

**C3 (Quantpedia TSMOM backtest) — CONFIRMED.**
Direct fetch of https://quantpedia.com/strategies/time-series-momentum-effect:
Sharpe 1.31 ✓; 20.7% p.a. described as "estimated alpha (using Fama&French factors)" ✓
(the file's re-labeling from round 1 is exactly right); volatility 15.74% ✓; max drawdown
−33.87% ✓; backtest period shown as 1965–2009 ✓ (matches the file's "1965–2009 variant").
Confidence "medium, practitioner database" is appropriate.

**C4 (Jegadeesh 1990; Lehmann 1990) — CONFIRMED** (with two citation-style nitpicks).
- Jegadeesh: IDEAS page (https://ideas.repec.org/a/bla/jfinan/v45y1990i3p881-98.html)
  abstract verbatim: "The negative first-order serial correlation in monthly stock returns
  is highly significant... The difference between the abnormal returns on the extreme
  decile portfolios over the period 1934-87 is 2.49 percent per month." JF 45(3), 881–898.
  ✓ Exactly as the file states.
- Lehmann: QJE 105(1), 1–28 confirmed via IDEAS
  (https://ideas.repec.org/a/oup/qjecon/v105y1990i1p1-28..html); abstract verbatim: "the
  'winners' and 'losers' one week experience sizeable return reversals the next week in a
  way that reflects apparent arbitrage profits which persist after corrections for bid-ask
  spreads and plausible transactions costs." ✓
- Magnitudes cross-checked in the NBER WP 2533 full text (webfetch cache, extracted
  locally): "Portfolios of securities that had positive returns in one week typically had
  negative returns in the next week (on average, -0.35 to -0.55 per cent per week) while
  those with negative returns in one week typically had positive returns in the next week
  (on average, 0.86 to 1.24 per cent per week)"; sample "securities listed on the New York
  and American Stock Exchanges between July 1962 and December 1986". ✓ The file's
  −0.55/+1.24 are the extreme ends of these ranges (see nitpicks). The ">2% per month"
  contrarian-profit magnitude is the standard characterization in the follow-on literature
  (e.g., surveyed in the short-term-reversal literature retrieved via search) and is
  conservative relative to Lehmann's own Table 1 costless-portfolio profits (~1.79% per
  week per dollar long, t≈41), so the header is safe. ✓
- Nitpick 1: the phrase "of over 2% per month" is set in quotation marks in the file but
  does not appear in the QJE abstract or the WP text I could search (the published QJE
  body is a JSTOR image scan; no OCR available here). It reads as a literature paraphrase,
  not a verbatim quote — quotation marks should be dropped.
- Nitpick 2: "winner portfolios −0.55%/week vs loser portfolios +1.24%/week" cites the
  endpoints of the ranges (−0.35 to −0.55 and +0.86 to +1.24); if the file means specific
  Table II entries of the published version, that could not be re-verified here (image
  scan). Safer wording: the ranges.

**C5 (De Bondt–Thaler 1985) — CONFIRMED.**
Full-text mirrors located via search (studocu/academia full text of JF July 1985):
"loser portfolios of 35 stocks outperform the market by, on average, 19.6%, thirty-six
months after portfolio formation. Winner portfolios earn about 5.0% less than the
market" — cumulative difference 24.6% (t=2.20) ✓ (file: "~24.6%", "roughly 25%").
"The overreaction effect is asymmetric; it is much larger for losers than for winners" ✓;
"most of the excess returns are realized in January" ✓. Monthly CRSP NYSE data, formation
periods within Jan 1926–Dec 1982 ✓ (file: "NYSE, 1926–1982"). Journal of Finance, July
1985 ✓. Sources: https://www.studocu.vn/vn/document/dai-hoc-ton-duc-thang/quan-tri-su-thay-doi/the-journal-of-finance-july-1985-bondt-does-the-stock-market-overreact/25279015 ;
https://www.academia.edu/7502534/Does_the_Stock_Market_Overreact

**C6 (Frazzini–Pedersen 2014 BAB) — CONFIRMED.**
Full text (pages.stern.nyu.edu → w4.stern.nyu.edu BettingAgainstBeta.pdf, extracted
locally): "The U.S. BAB factor realizes a Sharpe ratio of 0.78 between 1926 and March
2012" ✓; "its Sharpe ratio is about twice that of the value effect and 40% higher than
that of momentum over the same time period" ✓; Treasury BAB: "This portfolio produces
highly significant risk-adjusted returns with a Sharpe ratio of 0.81" ✓ (also Table:
Sharpe 0.81); "within each of the 19 other developed MSCI stock markets" ✓ (file: "19
other MSCI markets"); credit/corporate-bond BAB and futures documented ✓. JFE 111(1),
1–25 confirmed via https://ideas.repec.org/a/eee/jfinec/v111y2014i1p1-25.html ✓.

**C7 (Koijen–Moskowitz–Pedersen–Vrugt, Carry) — CONFIRMED.**
Published JFE PDF (S3 mirror, extracted locally): masthead "Journal of Financial
Economics 127 (2018) 197–225" ✓; abstract: "Carry predicts returns cross-sectionally and
in time series for a host of different asset classes, including global equities, global
bonds, commodities, US Treasuries, credit, and options" ✓; text: "earns significant
returns in each asset class with an annualized Sharpe ratio of 0.8 on average. Further, a
diversified portfolio of carry strategies across all asset classes earns a Sharpe ratio
of 1.2" ✓ (Table 2: "Sharpe ratio of 1.20 per annum").
WP version note re-verified from NBER WP 19325 PDF (extracted locally): "an annualized
Sharpe ratio of 0.7 on average... Forming a portfolio of carry strategies diversified
across all asset classes earns a Sharpe ratio of 1.1"; Table II text: "the average being
0.74 across all asset classes." ✓ File's "(WP: 1.1 diversified, ~0.74 average)" is right.

**C8 (Turn-of-the-month, Xu–McConnell) — CONFIRMED.**
Abstract extracted directly from the chesler.us PDF (locally): "the turn-of-the-month
effect persists over the recent interval of 1987-2005: in essence, over this 19-year
period (and over the 109-year period of 1897-2005) all of the excess market return
occurred during the four-day turn-of-the-month interval. Thus, during the other 16
trading days of the month, on average, investors received no reward for bearing market
risk" ✓; interval defined as last trading day through the next three days ✓; "not
confined to small or low-priced stocks... not confined to calendar-quarter-ends; it is
not confined to the U.S." ✓; Lakonishok–Smidt DJIA 1897–1986 attribution ✓.

**C9 (January effect, Rozeff–Kinney / Keim) — CONFIRMED.**
The exact sentence "Rozeff and Kinney (1976) found that the average return on an
equal-weighted index of NYSE prices from 1904 through 1974 was 3.5 percent during
January and only about 0.5 percent during the other months" is verified (it is Keim's
summary of Rozeff–Kinney; surfaced verbatim via search of the Keim/January literature).
Keim abstract: "nearly fifty percent of the average magnitude of the 'size effect' over
the period 1963–1979 is due to January abnormal returns", JFE 12, 13–32, 1983 ✓.
Sources: https://www.sciencedirect.com/science/article/abs/pii/0304405X83900259 ;
https://www.semanticscholar.org/paper/744f28a1fb855c31931d629eff8c9c629cfd6826

**C10 (Halloween/sell-in-May, Bouman–Jacobsen) — CONFIRMED.**
AEA page confirms AER 92(5), Dec 2002, 1618–1635 ✓. "36 of the 37 developed and emerging
markets studied" confirmed via multiple independent summaries of the paper (SSRN listing,
follow-up literature "everywhere and all the time" whose out-of-sample period starts
September 1998, consistent with the original Jan 1970–Aug 1998 sample). ✓

**C11 (Weekend effect, French 1980) — CONFIRMED.**
Primary PDF (round-1 cache, first page): "Journal of Financial Economics 8 (1980) 55-69
... STOCK RETURNS AND THE WEEKEND EFFECT, Kenneth R. French" ✓. Abstract (via Rotman
mirror surfaced in search): daily returns to the S&P composite 1953–1977; average Monday
return significantly negative for the full period "and during each of five-year
subperiods", other four days positive ✓.
Source: https://www-2.rotman.utoronto.ca/~kan/3032/pdf/AssetPricingAnomalies/French_JFE_1980.pdf

**C12 (Pre-holiday effect, Ariel 1990 + Ko out-of-sample) — Ariel part CONFIRMED;
"2021" study-year WRONG.**
- Ariel: JF Vol. 45, No. 5 (Dec. 1990), 1611–1626 ✓; abstract: pre-holiday "high mean
  returns averaging nine to fourteen times the mean return for the remaining days of the
  year" ✓; sample 1963–1982 ✓ (over a third of total market-portfolio return earned on
  the eight pre-holiday days per year). Sources:
  https://econpapers.repec.org/RePEc:bla:jfinan:v:45:y:1990:i:5:p:1611-26 ;
  https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1990.tb03731.x
- Out-of-sample study: title and finding confirmed from the CFR PDF itself (extracted
  locally): "The Pre-Holiday Premium of Ariel (1990) Has Largely Become A Small-Firm
  Effect Out of Sample", authors Kuan-Cheng Ko AND Nien-Tzu Yang; "Extending the sample
  to 1983-2019, we find that the pre-holiday effect now exists only among small firms."
  ✓ substance. **BUT the file's header calls it "a 2021 out-of-sample study": the paper
  was published in Critical Finance Review Vol. 13, Issue 3-4, pp. 531–538, in 2024**
  (per the CFR/Emerald article page:
  https://www.emerald.com/cfr/article-abstract/13/3-4/531/1326451/). The "2021" comes
  only from the hosting filename ko2021pre.pdf (acceptance vintage). Also single-author
  "Ko" omits co-author Yang. → **WRONG on the year (fix: "2024", or "accepted 2021,
  published 2024"); add Yang.**

**C13 (Heston–Sadka 2008) — CONFIRMED.**
WP full text (w4.stern.nyu.edu PDF, extracted locally): "Stocks with relatively high
(low) returns tend to have high (low) returns every year in the same calendar month" ✓;
"a general pattern that lasts up to 20 annual lags" ✓ (abstract and body); "these
strategies produce significantly positive returns for up to 20 years, averaging over 50
basis points per month" ✓; "The pattern is independent of size, industry, earnings
announcements, dividends, and fiscal year" ✓. Published version JFE 87(2), 418–445, 2008
confirmed via https://ideas.repec.org/a/eee/jfinec/v87y2008i2p418-445.html ✓.

**C14 (Keloharju–Linnainmaa–Nyberg 2016) — CONFIRMED.**
NBER WP 20815 abstract (https://www.nber.org/papers/w20815): "A strategy that selects
stocks based on their historical same-calendar-month returns earns an average return of
13% per year" ✓; "similar return seasonalities in anomalies, commodities, international
stock market indices, and at the daily frequency" ✓; "The seasonalities overwhelm
unconditional differences in expected returns" ✓.

**C15 (Cooper–Cliff–Gulen 2008) — CONFIRMED.**
SSRN abstract (via search; SSRN page itself 403s): "The US equity premium over the last
decade is solely due to overnight returns" with daytime (open-to-close) premium "zero or
even negative" ✓; individual S&P 500 stocks 1993–2006 ✓; holds for individual stocks,
equity indexes, and index futures, robust across NYSE and Nasdaq ✓; partly attributable
to high opening prices declining in the first trading hour ✓.
Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1004081 (abstract mirrored in
search results and secondary summaries).

**C16 (Lou–Polk–Skouras 2019) — CONFIRMED.**
Published JFE PDF (personal.lse.ac.uk/polk/research/TugOfWar.pdf, extracted locally):
masthead "Journal of Financial Economics 134 (2019) 192–213" ✓; abstract verbatim: "We
look for a similar tug of war in the returns of 14 trading strategies, finding in all
cases that profits are either earned entirely overnight (for reversal and a variety of
momentum strategies) or entirely intraday, typically with profits of opposite signs
across these components" ✓; conclusion verbatim: "essentially all of the abnormal
returns on momentum and short-term reversal strategies occur overnight while the
abnormal returns on other strategies occur intraday" ✓; Table 2 STR row: 0.93% (t=4.28)
overnight vs −1.05% (t=−3.25) intraday ✓; smoothed overnight-minus-intraday spread
"generally forecasts time variation in that strategy's close-to-close performance" ✓.
Nitpick: the paper's prose for STR calls the 0.93% the "overnight three-factor alpha"
while the intraday −1.05% is called a CAPM alpha (Table 2 reports the pair the file
quotes); the file labels both as CAPM alphas. Values and t-stats are exactly right;
consider "overnight alpha" to dodge the model-label wrinkle.

**C17 (Overnight drift, NY Fed SR 917 + Liberty Street 2026) — CONFIRMED.**
SR 917 full text (newyorkfed.org PDF, extracted locally): "More than half of this return
is generated during the ON session: from 16:15 to 9:30 equity returns averaged 3.6% p.a.
More striking than this, the return earned during the 2:00 to 3:00 hour averaged 3.7%
p.a. We dub this return sequence the 'overnight drift'" ✓; 2:00–3:00 is European open in
ET ✓; inventory-risk/order-imbalance mechanism with stronger reversals after sell-offs ✓
(also in the SR 917 landing-page abstract). Liberty Street Economics post "The
Disappearing Overnight Drift" (July 1, 2026, Boyarchenko/Larsen/Whelan) verbatim: "the
2:00–3:00 window that previously generated roughly 3.7 percent per annum has averaged
close to zero since 2021." ✓
Sources: https://www.newyorkfed.org/research/staff_reports/sr917 ;
https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr917.pdf ;
https://libertystreeteconomics.newyorkfed.org/2026/07/the-disappearing-overnight-drift/

**C18 (Cohen–Frazzini 2008) — CONFIRMED.**
JF 63(4), 1977–2011, Aug 2008 ✓; abstract: "A long–short equity strategy based on this
effect yields monthly alphas of over 150 basis points" ✓; mechanism = investor
inattention to customer–supplier links ✓ (AQR page + abstract mirrors).
Sources: https://ideas.repec.org/a/bla/jfinan/v63y2008i4p1977-2011.html ;
https://www.aqr.com/Insights/Research/Journal-Article/Economic-Links-and-Predictable-Returns

**C19 (Moskowitz–Grinblatt 1999) — CONFIRMED.**
JF 54(4), 1249–1290, Aug 1999 ✓; abstract: "a strong and prevalent momentum effect in
industry components of stock returns which accounts for much of the individual stock
momentum anomaly"; industry momentum "highly profitable, even after controlling for
size, book-to-market equity, individual stock momentum, the cross-sectional dispersion
in mean returns, and potential microstructure influences" ✓; portfolios formed every
month July 1963–July 1995 ✓ (via search of the full text mirrors).
Sources: https://ideas.repec.org/a/bla/jfinan/v54y1999i4p1249-1290.html ;
http://www-stat.wharton.upenn.edu/~steele/Courses/956/Resource/Momentum/MoskowitzGrinblatt99.pdf

**C20 (Hou 2007) — CONFIRMED.**
RFS 20(4), 1113–1138, July 2007 ✓; abstract: lead-lag between big and small firms is
"predominantly an intra-industry phenomenon", driven by slow diffusion of industry
information and "sluggish adjustment to negative information"; more pronounced in small,
less competitive, neglected industries; related to small firms' drift after big firms'
earnings releases ✓.
Sources: https://ideas.repec.org/a/oup/rfinst/v20y2007i4p1113-1138.html ;
https://www.ssrn.com/abstract=1151155

**C21 (Lo–MacKinlay 1990) — CONFIRMED.**
RFS 3(2), 175–205 ✓; abstract: even with temporally independent individual returns,
contrarian strategies can profit from cross-autocovariances; "returns of large stocks
lead those of smaller stocks"; weak negative individual autocorrelations vs strong
positive portfolio autocorrelation reconciled ✓.
Sources: https://ideas.repec.org/a/oup/rfinst/v3y1990i2p175-205.html ;
https://web.mit.edu/Alo/www/Papers/lo-mackinlay-90b.html

**C22 (Gatev–Goetzmann–Rouwenhorst 2006) — CONFIRMED.**
RFS 19(3), 797–827 ✓; daily data 1962–2002; pairs matched on minimum distance between
normalized historical prices; "A simple trading rule yields average annualized excess
returns of up to 11 percent for self-financing portfolios of pairs"; profits typically
exceed conservative transaction-cost estimates; bootstrap distinguishes from reversal
profits ✓.
Source: https://academic.oup.com/rfs/article-abstract/19/3/797/1646694 (details via
search mirrors incl. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=141615)

**C23 (Gervais–Kaniel–Mingelgrin 2001) — CONFIRMED.**
IDEAS page quotes the abstract in full: "stocks experiencing unusually high (low)
trading volume over a day or a week tend to appreciate (depreciate) over the course of
the following month"; visibility/attention mechanism; "Return autocorrelations, firm
announcements, market risk, and liquidity do not seem to explain our results." JF 56(3),
877–919 ✓. Source: https://ideas.repec.org/a/bla/jfinan/v56y2001i3p877-919.html

**C24 (Amihud 2002) — CONFIRMED.**
Full text (cis.upenn.edu PDF, extracted locally): JFM 5 (2002) 31–56 ✓; ILLIQ = "the
average across stocks of the daily ratio of absolute stock return to dollar volume" ✓;
abstract: "over time, expected market illiquidity positively affects ex ante stock
excess return" ✓; cross-sectional controls include beta, size, volatility (SDRET),
dividend yield, and past returns R100/R100YR ✓; verbatim: "The model does not include
the ratio of book-to-market equity, BE/ME... This study employs only NYSE stocks for
which BE/ME was found to have no significant effect (Easley et al., 1999; Loughran,
1997)." ✓ The round-1 fix is exactly right.

**C25 (George–Hwang 2004) — CONFIRMED.**
JF 59(5), 2145–2176, Oct 2004 ✓ (primary PDF first page in cache: "THE JOURNAL OF
FINANCE • VOL. LIX, NO. 5 • OCTOBER 2004, The 52-Week High and Momentum Investing");
abstract: "Nearness to the 52-week high dominates and improves upon the forecasting
power of past returns (both individual and industry returns) for future returns";
"Future returns forecast using the 52-week high do not reverse in the long run" ✓.
Source: https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2004.00695.x

**C26 (Carr–Wu 2009) — CONFIRMED.**
RFS 22(3), 1311–1341 ✓; primary full text (Baruch WP version, extracted locally):
variance swap rate "well approximated by the value of a particular portfolio of
options"; "the difference between the realized variance and this synthetic variance swap
rate quantifies the variance risk premium"; "five stock indexes and 35 individual
stocks" ✓; "the average risk premia on return variances are strongly negative for the
S&P 500 and 100 indexes and for the Dow Jones Industrial Average" ✓; "The common risk
factors identified by Fama and French (1993) cannot explain the strongly negative
variance risk premia... the Fama-French risk factors can only explain a small portion of
the variance risk premia" (intercepts remain strongly negative) ✓.
Source: https://ideas.repec.org/a/oup/rfinst/v22y2009i3p1311-1341.html

**C27 (Simon–Campasano 2014) — CONFIRMED.**
Primary abstract (SSRN full-text PDF via GitHub mirror, extracted locally): "the VIX
futures basis does not have significant forecast power for the change in the VIX spot
index from 2006 through 2011 but does have forecast power for subsequent VIX futures
returns... shorting VIX futures contracts when the basis is in contango and buying VIX
futures contracts when the basis is in backwardation with the market exposure of these
positions hedged with mini-S&P 500 futures positions... highly profitable and robust to
transaction costs" ✓. Journal of Derivatives 21(3), 54–69, Spring 2014 ✓.
Sources: https://jod.pm-research.com/content/21/3/54.abstract ;
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2094510

**C28 (Petajisto 2011) — CONFIRMED.**
Full text (petajisto.net PDF, extracted locally): "This paper empirically investigates
the index premium and its implications from 1990 to 2005. For additions to the S&P 500
and Russell 2000, we find that the price impact from announcement to effective day has
averaged +8.8% and +4.7%, respectively, and −15.1% and −4.6% for deletions. The premia
have been growing over time, peaking in 2000... lower bound as 21–28 bp annually for the
S&P 500 and 38–77 bp annually for the Russell 2000." ✓ All six numbers and the peak
timing verbatim. Journal of Empirical Finance 18(2), 271–288 (standard citation). ✓

**C29 (Greenwood–Sammon 2025) — CONFIRMED.**
JF 80(2), 657–698, April 2025 ✓ (IDEAS + HBS listings); abstract: "The abnormal return
associated with a stock being added to the S&P 500 has fallen from an average of 7.4% in
the 1990s to 0.3% over the past decade. A similar pattern has occurred for index
deletions... only 0.1% between 2010 and 2020", despite growth in index-linked assets ✓.
Sources: https://ideas.repec.org/a/bla/jfinan/v80y2025i2p657-698.html ;
https://www.hbs.edu/faculty/Pages/item.aspx?num=65745

**C30 (Petajisto 2017 ETF mispricing) — CONFIRMED.**
CFA Institute page: deviations "typically within a band of about 200 bps, are larger in
funds holding international or illiquid securities" ✓; after the stale-pricing control
"the average pricing band remains economically significant at about 100 bps" ✓; "Active
trading strategies exploiting such inefficiencies produce substantial abnormal returns
before transaction costs" ✓; FAJ 73(1), 24–54, 2017 ✓ (IDEAS:
https://ideas.repec.org/a/taf/ufajxx/v73y2017i1p24-54.html); Graham & Dodd award
confirmed via CFA Institute 2017 awards announcement
(https://www.cfainstitute.org/about/press-room/2018/cfa-institute-financial-analysts-journal-announces-2017-winners). ✓

---

## Objections (non-CONFIRMED, load-bearing)

1. **C12 — WRONG (publication year of the out-of-sample study).** The file says "a 2021
   out-of-sample study finds the premium has largely become a small-firm effect." The
   study (Ko & Yang, "The Pre-Holiday Premium of Ariel (1990) Has Largely Become A
   Small-Firm Effect Out of Sample") was published in **Critical Finance Review Vol. 13,
   Issue 3-4, pp. 531–538, in 2024**; "2021" is only the vintage in the CFR hosting
   filename (ko2021pre.pdf). The substance of the finding and the Ariel numbers are
   confirmed. Fix: change "2021" to "2024" (or "accepted 2021, published CFR 2024") and
   credit "Ko–Yang". Evidence:
   https://www.emerald.com/cfr/article-abstract/13/3-4/531/1326451/ (year 2024, vol 13,
   issue 3-4, pp. 531–538, authors Ko and Yang); PDF title page lists both authors.

## Nitpicks (NOT objections — style/precision only)

- C1: "6- and 12-month formation strategies cluster around 0.9%–1.3%" — Panel A values
  actually span 0.68–1.31 for these formations (0.84, 0.86 for J=6; 0.68 for J=12/12);
  "cluster around" is defensible but could be tightened.
- C4: (a) "of over 2% per month" should not be in quotation marks — it is the standard
  literature characterization, not verbatim from the QJE abstract (which contains no
  magnitude); (b) the −0.55%/+1.24% weekly figures are the endpoints of the ranges −0.35
  to −0.55 and +0.86 to +1.24 reported in Lehmann's text; the published QJE Table II scan
  could not be re-OCR'd here to confirm the file's "Table II" attribution of the exact
  endpoints.
- C16: the paper's prose labels the STR overnight 0.93% (t=4.28) a "three-factor alpha"
  (the intraday −1.05% a CAPM alpha); the file calls both CAPM alphas. Numbers exact;
  label could be softened to "overnight alpha."
- C12: evidence line cites "Ko" alone; the paper is by Ko and Yang (fold into objection
  fix).
- C2: the file's "sample 1985–2009" is correct for the TSMOM strategy evaluation; the
  underlying futures data begin Jan 1965 — worth one clause if precision matters later.

## Status decision

One load-bearing claim (C12 study year) is WRONG → status header NOT advanced to
"agreed round 2". Everything else re-verified clean, including all round-1 fixes (C1,
C16, C24 exactly match the primary sources). After the one-line C12 fix (+ Yang credit),
this file is ready to be agreed in the next pass.
