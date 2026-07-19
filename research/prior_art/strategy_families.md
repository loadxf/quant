---
status: draft round 2
topic: strategy_families
---

# Strategy Families Beyond the Cross-Sectional Factor Zoo

Practitioner prior-art map for the machine-readable factor database. Covers documented
trading-strategy families that the Chen–Zimmermann open-source list (cross-sectional US
equity predictors only) does NOT cover, plus the canonical cross-sectional anchors needed
for T0 matching. Each claim gives family name, mechanism, asset class, key citation + year,
and documented magnitude where a source was verified online.

## Claims

**C1. Cross-sectional momentum (Jegadeesh–Titman 1993): buying 3–12-month winners and selling losers in US equities earned roughly 1% per month over 3–12-month holding periods.**
Evidence: "Strategies which buy stocks that have performed well in the past and sell stocks that have performed poorly in the past generate significant positive returns over 3- to 12-month holding periods". Table I (verified from full text, sample Jan 1965–Dec 1989): across the 16 formation/holding combinations, zero-cost buy-sell returns range from 0.32% per month (3-month/3-month no-skip, the only statistically insignificant strategy) to 1.31% (12-month/3-month no-skip; 1.49% with a 1-week skip); "The 6-month formation period produces returns of about 1% per month regardless of the holding period"; in Panel A the 6-month formation strategies run 0.84%–1.02% and the 12-month formation strategies 0.68%–1.31% across holding periods. Part of the first-year abnormal return dissipates in the following two years. Journal of Finance 48(1), 65–91.
Source: https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1993.tb04702.x and https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf (Table I numbers extracted directly from the full-text PDF)
Confidence: high

**C2. Time-series momentum (Moskowitz–Ooi–Pedersen 2012): an instrument's own past 12-month excess return predicts its future return across 58 futures/forward contracts spanning equity indices, currencies, commodities, and government bonds.**
Evidence: "Significant 'time series momentum' in equity index, currency, commodity, and bond futures for each of the 58 liquid instruments considered... persistence in returns for 1 to 12 months that partially reverses over longer horizons"; a diversified TSMOM portfolio "delivers substantial abnormal returns with little exposure to standard asset pricing factors and performs best during extreme markets." Journal of Financial Economics 104, 228–250; TSMOM strategy evaluation sample 1985–2009 (underlying futures data begin January 1965).
Source: https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum
Confidence: high

**C3. Quantpedia's independent backtest of time-series momentum (1965–2009 variant) reports a Sharpe ratio of 1.31 with a 20.7% per-annum performance figure (labeled by Quantpedia as estimated Fama–French alpha) and 15.74% volatility.**
Evidence: Quantpedia strategy page lists "Sharpe Ratio 1.31", "20.7%" per annum (Quantpedia's footnote describes this as estimated alpha using Fama–French factors, not raw annual return), "estimated volatility 15.74%", max drawdown −33.87% (third-party replication figures sourced from MOP Table 3 Panel A, not the original paper's text).
Source: https://quantpedia.com/strategies/time-series-momentum-effect
Confidence: medium (practitioner-database backtest, not peer-reviewed; verified by direct fetch of the page)

**C4. Short-term reversal (Jegadeesh 1990; Lehmann 1990): last month's (or week's) losers beat winners; the monthly extreme-decile spread was about 2.5% per month in 1934–1987, and weekly contrarian profits exceeded 2% per month.**
Evidence: Jegadeesh (JF 45, 881–898) found "negative first-order serial correlation in monthly stock returns"; "the difference between abnormal returns on the extreme decile portfolios over 1934–1987 was 2.49 percent per month." Lehmann (QJE 105, 1–28): winners/losers one week "experience sizeable return reversals the next week" with contrarian abnormal returns of over 2% per month (the standard literature characterization, not a verbatim abstract quote) surviving bid-ask and plausible cost corrections.
Source: https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1990.tb05110.x ; https://ideas.repec.org/a/bla/jfinan/v45y1990i3p881-98.html (Jegadeesh 2.49%/month verbatim) ; https://academic.oup.com/qje/article-abstract/105/1/1/1928416 ; https://finance.martinsewell.com/stylized-facts/dependence/Lehmann1990.pdf (NYSE/AMEX, July 1962–Dec 1986: winner portfolios averaged −0.35 to −0.55%/week the next week, loser portfolios +0.86 to +1.24%/week)
Confidence: high (both magnitudes verified against primary/abstract sources in adversarial round 1)

**C5. Long-term reversal (De Bondt–Thaler 1985): 3–5-year loser portfolios beat winner portfolios by roughly 25% over the subsequent 36 months (NYSE, 1926–1982), with the effect concentrated in January.**
Evidence: Loser portfolios outperformed the market by 19.6% and winners underperformed by about 5%, a cumulative winner–loser spread of ~24.6% over 36 months; overreaction effect "asymmetric... much larger for losers"; January returns notably higher for losers. Journal of Finance, July 1985.
Source: https://onlinelibrary.wiley.com/doi/full/10.1111/j.1540-6261.1985.tb05004.x
Confidence: high

**C6. Betting-against-beta (Frazzini–Pedersen 2014): a self-financing factor long leveraged low-beta and short de-leveraged high-beta US stocks realized a Sharpe ratio of 0.78 over 1926–March 2012; the analogous US Treasury BAB factor realized a Sharpe of 0.81.**
Evidence: From the paper: "The U.S. BAB factor realizes a Sharpe ratio of 0.78 between 1926 and March 2012... about twice that of the value effect and 40% higher than that of momentum over the same time period"; the Treasury maturity-sorted BAB "produces highly significant risk-adjusted returns with a Sharpe ratio of 0.81." Also documented in 19 other MSCI markets, corporate bonds, and futures. JFE 111, 1–25.
Source: https://pages.stern.nyu.edu/~lpederse/papers/BettingAgainstBeta.pdf (numbers extracted directly from the PDF)
Confidence: high

**C7. Carry (Koijen–Moskowitz–Pedersen–Vrugt 2018): a security's model-free "carry" predicts returns cross-sectionally and in time series in global equities, global bonds, commodities, US Treasuries, credit, and options; a carry factor diversified across asset classes attains an annualized Sharpe ratio of about 1.2 in the published version.**
Evidence: JFE 127(2), 197–225 (published version, verified from the journal PDF): "Carry predicts returns cross-sectionally and in time series for a host of different asset classes... not explained by known predictors"; individual asset-class carry strategies achieve "an annualized Sharpe ratio of 0.8 on average. Further, a diversified portfolio of carry strategies across all asset classes earns a Sharpe ratio of 1.2." (The earlier NBER WP 19325 reported 1.1 diversified and ~0.74 average — version matters.)
Source: https://www.sciencedirect.com/science/article/abs/pii/S0304405X17302908 ; https://spinup-000d1a-wp-offload-media.s3.amazonaws.com/faculty/wp-content/uploads/sites/3/2019/04/Carry.pdf (published-version Sharpes) ; https://www.nber.org/system/files/working_papers/w19325/w19325.pdf (WP figures)
Confidence: high (published-version numbers verified in adversarial round 1)

**C8. Turn-of-the-month (Lakonishok–Smidt 1988; Xu–McConnell 2008): essentially all of the US equity excess return over 1897–2005 accrued in the four-day window from the last trading day of the month through the next three days.**
Evidence: Xu–McConnell abstract: turn-of-month identified by Lakonishok and Smidt (1988) in DJIA 1897–1986 "persists over the recent interval of 1987–2005: in essence, over this 19-year period (and over the 109-year period of 1897–2005) all of the excess market return occurred during the four-day turn-of-the-month interval... during the other 16 trading days of the month, on average, investors received no reward for bearing market risk"; not confined to small/low-priced stocks, quarter-ends, or the US.
Source: https://www.chesler.us/resources/academia/turn_of_the_month_stock_returns.pdf (abstract extracted directly from PDF); Lakonishok–Smidt: https://academic.oup.com/rfs/article-abstract/1/4/403/1566965
Confidence: high

**C9. January effect (Rozeff–Kinney 1976; Keim 1983): equal-weighted NYSE returns averaged about 3.5% in January versus roughly 0.5% in other months (1904–1974), and nearly 50% of the small-firm size premium over 1963–1979 came from January.**
Evidence: "Rozeff and Kinney (1976) found that the average return on an equal-weighted index of NYSE prices from 1904 through 1974 was 3.5 percent during January and only about 0.5 percent during the other months." Keim (JFE 12, 13–32): "nearly fifty percent of the average magnitude of the 'size effect' over the period 1963–1979 is due to January abnormal returns."
Source: https://www.sciencedirect.com/science/article/abs/pii/0304405X76900283 and https://www.sciencedirect.com/science/article/abs/pii/0304405X83900259
Confidence: high

**C10. Halloween / sell-in-May (Bouman–Jacobsen 2002): November–April returns significantly exceed May–October returns in 36 of 37 country markets studied over 1970–1998.**
Evidence: American Economic Review 92(5), 1618–1635: returns during November–April "are significantly higher than during summer (May–October) in 36 out of the 37 countries," across Europe, North America, Asia, Africa, Australia.
Source: https://www.aeaweb.org/articles?id=10.1257%2F000282802762024683
Confidence: high

**C11. Day-of-week / weekend effect (French 1980): mean Monday returns on the S&P were negative over 1953–1977 and in every five-year subperiod, while the other four weekdays averaged positive returns.**
Evidence: JFE 8(1), 55–69: "mean Monday returns were negative for the full period and also for every 5 year sub-period," rejecting both calendar-time and trading-time null models.
Source: https://www.sciencedirect.com/science/article/abs/pii/0304405X80900215
Confidence: high

**C12. Pre-holiday effect (Ariel 1990): the trading day before holidays showed mean returns nine to fourteen times the average of remaining days (NYSE/AMEX, 1963–1982); a 2024 out-of-sample study (Ko–Yang; accepted 2021) finds the premium has largely become a small-firm effect.**
Evidence: JF 45(5), 1611–1626 abstract: "stocks advance with disproportionate frequency and show high mean returns averaging nine to fourteen times the mean return for the remaining days of the year." Ko and Yang, "The Pre-Holiday Premium of Ariel (1990) Has Largely Become A Small-Firm Effect Out of Sample," Critical Finance Review 13(3-4), 531–538, published 2024 (the CFR hosting filename ko2021pre.pdf reflects the acceptance vintage, not the publication year): extending the sample to 1983–2019, the pre-holiday effect now exists only among small firms, with large-firm pre-holiday returns statistically indistinguishable from regular days.
Source: https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1990.tb03731.x ; https://www.emerald.com/cfr/article-abstract/13/3-4/531/1326451/ (verified: authors Ko and Yang, CFR 13(3-4), 531–538, 2024) ; https://cfr.ivo-welch.info/published/papers/ko2021pre.pdf
Confidence: high

**C13. Same-calendar-month seasonal momentum (Heston–Sadka 2008): stocks that historically did well in a given calendar month keep doing well in that month, with the pattern persisting up to 20 annual lags and seasonal strategies averaging over 50 bp per month.**
Evidence: From the paper: "Stocks with relatively high (low) returns tend to have high (low) returns every year in the same calendar month... a general pattern that lasts up to 20 annual lags"; "these strategies produce significantly positive returns for up to 20 years, averaging over 50 basis points per month"; independent of size, industry, earnings announcements, dividends, fiscal year. JFE 87 (2008).
Source: https://w4.stern.nyu.edu/finance/docs/pdfs/Seminars/063f-sadka.pdf (numbers extracted directly from the PDF)
Confidence: high

**C14. Return seasonalities generalize beyond US single stocks (Keloharju–Linnainmaa–Nyberg 2016): a same-calendar-month selection strategy earns about 13% per year, and seasonalities also appear in anomaly portfolios, commodities, international stock indices, and at daily frequency.**
Evidence: NBER WP 20815 abstract: "A strategy that selects stocks based on their historical same-calendar-month returns earns an average return of 13% per year"; seasonalities documented in individual stocks, anomalies, commodities, international indices, and daily returns, and "overwhelm unconditional differences in expected returns."
Source: https://www.nber.org/papers/w20815
Confidence: high

**C15. Overnight vs intraday decomposition (Cooper–Cliff–Gulen 2008): over 1993–2006 the entire US equity premium was earned close-to-open (overnight); open-to-close (intraday) returns were near zero or negative.**
Evidence: "The US equity premium over the last decade is solely due to overnight returns; the returns during the night are strongly positive, and returns during the day are close to zero and sometimes negative"; holds for individual stocks, indexes, and index futures on NYSE and Nasdaq; partly driven by high opening prices declining in the first trading hour.
Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1004081
Confidence: high

**C16. "Tug of war" (Lou–Polk–Skouras 2019): overnight and intraday return components each persist for years but offset each other, and across 14 strategies profits accrue either entirely overnight (momentum and short-term reversal) or entirely intraday (value-type and most other anomalies), typically with opposite signs in the other session.**
Evidence: JFE 134(1), 192–213 (verified from the published PDF): "strong overnight and intraday firm-level return continuation along with an offsetting cross-period reversal effect... profits are either earned entirely overnight (for reversal and a variety of momentum strategies) or entirely intraday, typically with profits of opposite signs across these components"; conclusion: "essentially all of the abnormal returns on momentum and short-term reversal strategies occur overnight while the abnormal returns on other strategies occur intraday." E.g., the short-term reversal strategy's overnight alpha is +0.93% per month (t=4.28) versus a −1.05% intraday CAPM alpha (t=−3.25); the smoothed overnight-minus-intraday spread forecasts a strategy's close-to-close performance.
Source: https://ideas.repec.org/a/eee/jfinec/v134y2019i1p192-213.html and https://personal.lse.ac.uk/polk/research/TugOfWar.pdf
Confidence: high

**C17. Overnight drift in equity index futures (Boyarchenko–Larsen–Whelan, NY Fed SR 917): more than half of S&P 500 futures returns accrue in the 16:15–9:30 overnight session, with ~3.7% p.a. earned in the 2:00–3:00 a.m. hour alone around European open — a pattern the authors report has averaged close to zero since 2021.**
Evidence: "More than half of S&P 500 futures returns is generated during the overnight session: from 16:15 to 9:30, equity returns averaged 3.6% p.a... the return earned during the 2:00 to 3:00 hour averaged 3.7% p.a."; linked to inventory risk and close-of-day order imbalances, with strong positive overnight reversals after selloffs. NY Fed Liberty Street (July 2026) follow-up: "the 2:00–3:00 window that previously generated roughly 3.7 percent per annum has averaged close to zero since 2021."
Source: https://www.newyorkfed.org/research/staff_reports/sr917 and https://libertystreeteconomics.newyorkfed.org/2026/07/the-disappearing-overnight-drift/
Confidence: high

**C18. Customer–supplier lead-lag / customer momentum (Cohen–Frazzini 2008): buying suppliers after positive news to their principal customers yields monthly long-short alphas of over 150 basis points.**
Evidence: JF 63(4), 1977–2011: "a long–short equity strategy based on the customer momentum effect yields monthly alphas of over 150 basis points," robust to the three-factor model, liquidity, own-firm momentum, industry momentum, and within-industry lead-lag controls; mechanism is investor inattention to firm-level economic links.
Source: https://www.aqr.com/Insights/Research/Journal-Article/Economic-Links-and-Predictable-Returns and https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2008.01379.x
Confidence: high

**C19. Industry momentum (Moskowitz–Grinblatt 1999): buying stocks in past winning industries and selling past losing industries is highly profitable (US, July 1963–July 1995) and accounts for much of individual-stock momentum.**
Evidence: JF 54(4), 1249–1290: "a strong and prevalent momentum effect in industry components of stock returns which accounts for much of the individual stock momentum anomaly"; industry momentum profitable "even after controlling for size, book-to-market equity, individual stock momentum, the cross-sectional dispersion in mean returns, and potential microstructure influences."
Source: https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00146
Confidence: high

**C20. Intra-industry size lead-lag (Hou 2007): the big-firms-lead-small-firms effect is predominantly an intra-industry phenomenon driven by slow diffusion of (especially negative) industry information.**
Evidence: RFS 20(4), 1113–1138: "The lead-lag effect between big firms and small firms is predominantly an intra-industry phenomenon... driven by sluggish adjustment to negative information"; strongest in small, less competitive, neglected industries and related to small firms' drift after big firms' earnings releases.
Source: https://academic.oup.com/rfs/article-abstract/20/4/1113/1615954
Confidence: high

**C21. Size-based lead-lag and cross-autocorrelation (Lo–MacKinlay 1990): returns of large stocks lead those of small stocks, so weekly contrarian profits can arise from cross-autocovariances even without individual-stock overreaction.**
Evidence: RFS 3(2), 175–205: "even if individual security returns are temporally independent, portfolio strategies exploiting return reversals may earn positive expected profits due to cross-autocovariances"; empirically "returns of large stocks lead those of smaller stocks," and weekly portfolio returns are strongly positively autocorrelated despite negative individual autocorrelations.
Source: https://academic.oup.com/rfs/article-abstract/3/2/175/1595488
Confidence: high

**C22. Pairs trading (Gatev–Goetzmann–Rouwenhorst 2006): a distance-based rule matching stocks into pairs by normalized historical prices and trading divergences yields average annualized excess returns up to 11% on self-financing portfolios.**
Evidence: RFS 19(3), 797–827: "A simple trading rule yields average annualized excess returns of up to 11% for self-financing portfolios of pairs"; profits "typically exceed conservative transaction cost estimates" and bootstrap results distinguish the effect from previously documented reversal profits.
Source: https://academic.oup.com/rfs/article-abstract/19/3/797/1646694
Confidence: high

**C23. High-volume return premium (Gervais–Kaniel–Mingelgrin 2001): stocks with unusually high (low) trading volume over a day or week tend to appreciate (depreciate) over the following month, consistent with a visibility/attention mechanism.**
Evidence: JF 56, 877–919: "stocks experiencing unusually high (low) trading volume over a day or a week tend to appreciate (depreciate) over the course of the following month"; return autocorrelations, announcements, market risk, and liquidity do not explain it.
Source: https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00349
Confidence: high

**C24. Amihud illiquidity (2002): the ILLIQ measure — average daily |return| / dollar volume — prices stocks both cross-sectionally and in time series, with expected market illiquidity raising ex-ante excess returns.**
Evidence: Journal of Financial Markets 5, 31–56 (verified from full text): ILLIQ is "the daily ratio of absolute stock return to its dollar volume, averaged over some period," a rough price-impact proxy; "over time, the ex ante stock excess return is increasing in the expected illiquidity of the stock market," and the cross-sectional effect survives beta, size, volatility (SDRET), dividend-yield, and past-return (R100, R100YR) controls. Note: the model does NOT control for book-to-market — "The model does not include the ratio of book-to-market equity, BE/ME," on the grounds that BE/ME has no significant effect in the NYSE-only sample used.
Source: https://ideas.repec.org/a/eee/finmar/v5y2002i1p31-56.html and https://www.cis.upenn.edu/~mkearns/finread/amihud.pdf (control list extracted directly from the full-text PDF)
Confidence: high

**C25. 52-week-high momentum (George–Hwang 2004): nearness of the current price to the 52-week high explains a large share of momentum profits, dominates past-return measures, and — unlike conventional momentum — does not reverse long-run.**
Evidence: JF 59, 2145–2176: "Nearness to the 52-week high dominates and improves upon the forecasting power of past returns (both individual and industry returns) for future returns"; "future returns forecast using the 52-week high do not reverse in the long run."
Source: https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2004.00695.x
Confidence: high

**C26. Variance risk premium (Carr–Wu 2009): synthetic variance swap rates on stock indexes systematically exceed subsequently realized variance, so selling index variance earns a premium that standard risk factors (CAPM, Fama–French) cannot explain.**
Evidence: RFS 22, 1311–1341: the variance swap rate is replicated from an options portfolio and "the difference between the realized variance and this synthetic variance swap rate" quantifies the variance risk premium, studied on five stock indexes and 35 individual stocks; index variance risk premia are negative and their excess returns are unexplained by market or Fama–French factors (significant negative alphas).
Source: https://academic.oup.com/rfs/article/22/3/1311/1581057
Confidence: high

**C27. VIX futures basis harvesting (Simon–Campasano 2014): the VIX futures basis does not forecast spot VIX changes but does forecast futures price changes; shorting VIX futures in contango (and buying in backwardation), hedged with mini-S&P futures, was highly profitable over Jan 2006–Dec 2011.**
Evidence: Journal of Derivatives 21(3), 54–69: "the VIX futures basis does not have significant forecast power for the change in the spot VIX... but does have forecast power for VIX futures price changes"; the contango-short strategy is "highly profitable and robust to transaction costs."
Source: https://jod.pm-research.com/content/21/3/54.abstract
Confidence: high

**C28. Index reconstitution premium (Petajisto 2011): over 1990–2005, additions to the S&P 500 and Russell 2000 rose on average +8.8% and +4.7% from announcement to effective day (deletions −15.1% and −4.6%), imposing an index-turnover cost on index funds of 21–28 bp/yr (S&P 500) and 38–77 bp/yr (Russell 2000).**
Evidence: Journal of Empirical Finance 18(2), 271–288: "the price impact from announcement to effective day has averaged +8.8% and +4.7%... and −15.1% and −4.6% for deletions," with a lower-bound index turnover cost of "21–28 basis points annually for the S&P 500 and 38–77 basis points annually for the Russell 2000"; premia peaked around 2000.
Source: https://www.petajisto.net/papers/petajisto%202011%20jef%20-%20hidden%20cost%20for%20index%20funds.pdf
Confidence: high

**C29. The index effect has decayed (Greenwood–Sammon 2025): the abnormal return on S&P 500 additions fell from an average of 7.4% in the 1990s to 0.3% in the most recent decade, and deletion effects shrank to −0.1%-scale, despite growth in indexed assets.**
Evidence: Journal of Finance 80(2), 657–698: "The abnormal return associated with a stock being added to the S&P 500 has fallen from an average of 7.4% in the 1990s to 0.3% over the past decade. A similar pattern has occurred for index deletions... only 0.1% between 2010 and 2020."
Source: https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13410
Confidence: high

**C30. ETF premium/discount mean reversion (Petajisto 2017): ETF prices deviate from NAV within a band of roughly 200 bp (about 100 bp after controlling for stale underlying prices via a cross-section of similar ETFs), and trading these deviations produced substantial pre-cost abnormal returns.**
Evidence: Financial Analysts Journal 73(1), 24–54 (Graham & Dodd Award): "deviations are typically within a band of about 200 basis points and are larger in funds holding international or illiquid securities"; after the novel stale-pricing control "the average pricing band remains economically significant at about 100 basis points"; "active trading strategies exploiting such inefficiencies produce substantial abnormal returns before transaction costs," evidencing short-term mean reversion in ETF prices.
Source: https://rpc.cfainstitute.org/research/financial-analysts-journal/2017/inefficiencies-in-the-pricing-of-exchange-traded-funds
Confidence: high

## Synthesis

The practitioner prior-art map is far wider than the Chen–Zimmermann cross-sectional-equity
list, and this file is the project's defense against false novelty claims in exactly the
directions an LLM is most likely to wander: asset classes other than single US stocks,
calendar time rather than cross-section, and intraday/overnight structure visible in daily
OHLC data. Five broad meta-families organize nearly everything above. (1) Trend and
reversal at three horizons — weekly/monthly reversal (C4), 3–12-month momentum in
cross-sectional, time-series, industry, 52-week-high, and lead-lag flavors (C1–C3, C18–C21,
C25), and 3–5-year reversal (C5). Any candidate signal built on lagged returns must be
checked against this grid of horizon × aggregation-level combinations, including the
subtle economically-linked and big-leads-small variants. (2) Risk-premium harvesting —
low-beta (C6), carry generalized across every major asset class (C7), and the variance risk
premium in both option-implied (C26) and VIX-futures-basis (C27) form. These set a high
bar: "sell insurance in market X" is documented essentially everywhere. (3) Calendar
seasonality — turn-of-month (C8), January (C9), Halloween (C10), day-of-week (C11),
pre-holiday (C12), and crucially Heston–Sadka/Keloharju et al. same-calendar-month
seasonality that generalizes to commodities, indices, anomalies, and daily frequency
(C13–C14). The last is the biggest trap for "novel" seasonality candidates: almost any
periodic conditioning of returns has a documented near-neighbor here. (4) Session
decomposition — the equity premium accrues overnight (C15), strategy PnL splits
systematically into persistent overnight vs intraday components (C16), and index futures
exhibit hour-resolved overnight drift (C17). A candidate using close-to-open vs
open-to-close returns is presumptively T0/T1. (5) Structural/flow effects — pairs (C22),
volume-attention (C23), illiquidity pricing (C24), index reconstitution (C28–C29), and ETF
premium/discount reversion (C30).

Two cross-cutting lessons matter for scoring. First, magnitudes documented in-sample are
large (1%/month momentum, Sharpe ~0.8–1.3 for BAB/TSMOM/carry, 11%/yr pairs), so a
candidate matching a family but showing smaller live-sample numbers is still T0 — decay is
expected, not novelty. Second, several families carry documented post-publication decay or
regime death: the index effect fell from 7.4% to 0.3% (C29), the pre-holiday premium
became a small-firm effect (C12), and the 2–3 a.m. overnight drift went to zero after 2021
(C17). "Known effect, now weaker/gone" and "known effect, revived by a filter" are both T1
recombinations, not T2. For the factor database, each claim above should become an entry
keyed on (mechanism, asset class, conditioning variable, horizon), so the Phase D
adversarial search can match candidates on structure rather than on name.

## Revision log round 1

Response to adversarial audit (research/debates/strategy_families_round1.md, 2026-07-19).
All three objections fixed; corrected facts re-verified directly from primary full-text PDFs
during this revision (Jegadeesh–Titman 1993 Table I, Lou–Polk–Skouras 2019 published JFE PDF,
Amihud 2002 full text), not merely copied from the audit.

- **C1 (OVERSTATED — fixed).** Replaced the wrong "across the 16 formation/holding
  combinations average monthly returns ran about 0.9%–1.3%" with the actual Table I range:
  0.32%/month (3/3 no-skip, the only insignificant strategy) to 1.31% (12/3 no-skip; 1.49%
  with 1-week skip); 0.9%–1.3% now correctly attributed to the 6- and 12-month formation
  strategies only. Header ("roughly 1% per month") unchanged, per audit. Added full-text PDF
  source (bauer.uh.edu).
- **C16 (WRONG — fixed).** Header re-sorted the strategy groups to match the paper: profits
  accrue entirely overnight for momentum AND short-term reversal; the intraday group is
  value-type and most other anomalies (size, profitability, investment, etc.). Evidence quote
  corrected to the verbatim abstract ("for reversal and a variety of momentum strategies"),
  added the conclusion sentence and the STR overnight alpha +0.93% (t=4.28) vs intraday
  −1.05% (t=−3.25).
- **C24 (OVERSTATED — fixed).** Removed the nonexistent book-to-market control; control list
  corrected to beta, size, volatility (SDRET), dividend yield, and past returns (R100,
  R100YR), with an explicit note quoting the paper that BE/ME is NOT included. Added
  full-text PDF source (cis.upenn.edu).

Audit nitpicks (not objections) also applied:
- **C3.** 20.7% p.a. now labeled as Quantpedia's estimated Fama–French alpha, not raw annual
  return; noted figures trace to MOP Table 3 Panel A.
- **C4.** Confidence upgraded medium → high: Jegadeesh's 2.49%/month verified verbatim via
  the IDEAS abstract and Lehmann's magnitudes via the primary scan (Table II, 1962–1986:
  winners −0.55%/week vs losers +1.24%/week); sources added.
- **C7.** Sharpe figures updated to the published JFE 2018 version (diversified 1.2, average
  0.8) with the NBER WP 19325 figures (1.1, ~0.74) retained as a version note; confidence
  upgraded medium → high with the journal-PDF source added.

No claims were renumbered or removed. Status advanced to "draft round 1"; not marked agreed
(adversary/judge decision).

## Revision log round 2

Response to adversarial audit round 2 (research/debates/strategy_families_round2.md,
2026-07-19). One objection (C12 WRONG on the study year); fix re-verified during this
revision by direct fetch of the Emerald/CFR article page, not merely copied from the audit.

- **C12 (WRONG — fixed).** "a 2021 out-of-sample study" corrected to "a 2024 out-of-sample
  study (Ko–Yang; accepted 2021)". Verified by direct fetch of
  https://www.emerald.com/cfr/article-abstract/13/3-4/531/1326451/ : Kuan-Cheng Ko and
  Nien-Tzu Yang, "The Pre-Holiday Premium of Ariel (1990) Has Largely Become A Small-Firm
  Effect Out of Sample," Critical Finance Review 13(3-4), 531–538, published 2024. The
  prior "2021" came only from the CFR hosting filename ko2021pre.pdf (acceptance vintage),
  and the evidence line had credited "Ko" alone, omitting co-author Nien-Tzu Yang — both
  fixed. Evidence line now also states the paper's finding precisely (sample extended to
  1983–2019; effect survives only among small firms) and the Emerald source URL was added.
  The Ariel 9–14x figure and the substance of the decay finding were confirmed by the
  audit and are unchanged.

Audit nitpicks (not objections) also applied:
- **C1.** "6- and 12-month formation strategies cluster around 0.9%–1.3%" tightened to the
  actual Panel A envelopes: 0.84%–1.02% (6-month formation) and 0.68%–1.31% (12-month
  formation).
- **C2.** Clarified that 1985–2009 is the TSMOM strategy-evaluation sample; underlying
  futures data begin January 1965.
- **C4.** Dropped quotation marks around "of over 2% per month" (a standard literature
  characterization, not a verbatim QJE-abstract quote, now flagged as such inline); the
  Lehmann weekly figures restated as the ranges reported in the text (winners −0.35 to
  −0.55%/week, losers +0.86 to +1.24%/week, July 1962–Dec 1986) instead of the bare
  endpoints attributed to Table II.
- **C16.** STR overnight +0.93% (t=4.28) relabeled "overnight alpha" (the paper's prose
  calls it a three-factor alpha) while the intraday −1.05% (t=−3.25) keeps the CAPM-alpha
  label; numbers unchanged.

No claims were renumbered or removed. Status advanced to "draft round 2"; not marked agreed
(adversary/judge decision).
