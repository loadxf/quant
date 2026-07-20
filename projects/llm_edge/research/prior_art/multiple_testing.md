---
status: agreed round 1
topic: multiple_testing
---

# Prior art: statistical safeguards against backtest overfitting

Scope: exact formulas (with variable definitions) for PSR, DSR, expected-max-SR benchmark,
MinTRL/MinBTL, PBO/CSCV, Harvey-Liu-Zhu t-hurdles, haircut Sharpe ratios, White's Reality
Check, Hansen's SPA, the Politis-Romano stationary bootstrap, and purged/combinatorial
cross-validation. These feed `src/quantlab/stats.py` and its unit tests. All primary-source
PDFs were fetched and text-extracted during this session; every worked example below was
additionally re-computed numerically (scipy) and reproduced the papers' printed values.

## Claims

**C1.** The Probabilistic Sharpe Ratio of Bailey & López de Prado is
PSR(SR\*) = Z[ (SR̂ − SR\*)·√(n−1) / √(1 − γ̂₃·SR̂ + ((γ̂₄−1)/4)·SR̂²) ],
where Z is the standard-normal CDF, SR̂ the estimated Sharpe ratio, SR\* the benchmark
threshold, n the number of return observations, γ̂₃ the skewness and γ̂₄ the kurtosis of the
returns.
Evidence: Eq. (11) of "The Sharpe Ratio Efficient Frontier" (working paper of the Journal of
Risk 15(2) article); the paper derives it from the SR-estimator standard deviation in Eq. (8)–(9).
Source: https://www.davidhbailey.com/dhbpapers/sharpe-frontier.pdf
Confidence: high

**C2.** The estimated standard deviation of the Sharpe-ratio estimator underlying PSR is
σ̂(SR̂) = √[ (1 − γ̂₃·SR̂ + ((γ̂₄−1)/4)·SR̂²) / (n−1) ], and the paper states the n−1 "is due
to Bessel's correction."
Evidence: "Eq.(8) gives the estimated standard deviation of SR̂ as ... where n−1 is due to
Bessel's correction" (Section 2.5, Confidence Band).
Source: https://www.davidhbailey.com/dhbpapers/sharpe-frontier.pdf
Confidence: high

**C3.** PSR inputs are expressly NON-annualized: SR̂ and SR\* must be in the original sampling
frequency of the returns.
Evidence: "PSR increases with greater SR̂ (in the original sampling frequency, i.e.
non-annualized), or longer track records (n)"; "All calculations are done in the original
frequency of the data, and there is no annualization."
Source: https://www.davidhbailey.com/dhbpapers/sharpe-frontier.pdf
Confidence: high

**C4.** The kurtosis γ₄ in the PSR/DSR formulas is RAW kurtosis (Normal = 3), not excess
kurtosis: the papers set γ̂₃=0, γ̂₄=3 for the Normal case, under which the variance term
reduces to Lo's IID-normal value 1 + SR²/2.
Evidence: "assuming Normality (γ̂₃ = 0, γ̂₄ = 3)" in the Sharpe-frontier worked example, and
the DSR paper's example "If the strategy had exhibited Normal returns (γ̂₃ = 0, γ̂₄ = 3)".
Source: https://www.davidhbailey.com/dhbpapers/sharpe-frontier.pdf and
https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
Confidence: high

**C5.** The Minimum Track Record Length is
MinTRL = n\* = 1 + [1 − γ̂₃·SR̂ + ((γ̂₄−1)/4)·SR̂²]·(Z_α / (SR̂ − SR\*))²,
in number of observations (not years); e.g. the paper's Figure 8 example: an annualized SR of
2 needs a 2.73-year daily track record to be deemed > 1 at 95% confidence (reproduced
numerically: 2.731 years).
Evidence: Eq. (13) and "a 2.73 years track record is required for an annualized Sharpe of 2
to be considered greater than 1 at a 95% confidence level"; "MinTRL is expressed in terms of
number of observations, not annual or calendar terms."
Source: https://www.davidhbailey.com/dhbpapers/sharpe-frontier.pdf
Confidence: high

**C6.** PSR worked example (Sharpe-frontier paper, Section 3): a 2-year monthly track record
with annualized SR 1.59 (monthly SR̂ ≈ 0.458) gives PSR(0) ≈ 0.98 under assumed normality but
falls below the 0.95 acceptance level once the track record's negative skewness and fat tails
are used, recovering to ≈0.95 only with 3 years of data.
Evidence: "This yields a reassuring PSR(0)=0.98.. However, when we incorporate the skewness
and kurtosis information, then PSR(0)=0.9..! ... should we have 3 years instead of 2,
PSR(0)=0.95.., enough to reject the hypothesis of skill-less performance." My scipy
reproduction with γ₃=−2.448, γ₄=10.164 (the HFR-style moments referenced in the paper) gives
0.982 / 0.914 / 0.954, matching the visible digits.
Source: https://www.davidhbailey.com/dhbpapers/sharpe-frontier.pdf
Confidence: medium (formula and 1.59/2-year/0.98/3-year facts are verbatim; the exact
skew/kurt digits were partially lost in PDF text extraction and are pinned by reproduction,
not by a clean quote)

**C7.** Bailey & López de Prado (2014, "The Deflated Sharpe Ratio", Journal of Portfolio
Management) approximate the expected maximum of N independent trial Sharpe ratios drawn from
a Normal with mean E[{SR̂ₙ}] and variance V[{SR̂ₙ}] as
E[max{SR̂ₙ}] ≈ E[{SR̂ₙ}] + √V[{SR̂ₙ}] · ( (1−γ)·Z⁻¹[1 − 1/N] + γ·Z⁻¹[1 − 1/(N·e)] ),
where γ ≈ 0.5772 is the Euler–Mascheroni constant, Z⁻¹ the standard-normal quantile function,
e Euler's number, and N ≫ 1 the number of independent trials.
Evidence: Eq. (1); confirmed verbatim by the paper's own Python Snippet 1:
"maxZ=(1-emc)*ss.norm.ppf(1-1./numTrials)+emc*ss.norm.ppf(1-1./(numTrials*np.e))" with
"emc=0.5772156649 # Euler-Mascheroni constant".
Source: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
Confidence: high

**C8.** The Deflated Sharpe Ratio is DSR = PSR evaluated at the multiple-testing benchmark:
DSR̂ = PSR̂(SR̂₀) = Z[ (SR̂ − SR̂₀)·√(T−1) / √(1 − γ̂₃·SR̂ + ((γ̂₄−1)/4)·SR̂²) ] with
SR̂₀ = √V[{SR̂ₙ}] · ( (1−γ)·Z⁻¹[1 − 1/N] + γ·Z⁻¹[1 − 1/(N·e)] ),
where V[{SR̂ₙ}] is the variance across the N independent trials' estimated (per-period) SRs
and T is the selected strategy's sample length; SR̂₀ is the expected maximum SR under the null
that the true SR is zero.
Evidence: Eq. (2): "DSR deflates SR by taking into consideration five additional variables:
the non-Normality of the returns (γ̂₃, γ̂₄), the length of the returns series (T), the
variance of the SRs tested (V[{SR̂ₙ}]), as well as the number of independent trials (N)."
Source: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
Confidence: high

**C9.** DSR worked example (usable to pin unit tests): N=100 trials, trial-SR variance
V[{SR̂ₙ}] such that √V = √(1/500) in per-period (daily) units, T=1250 daily observations
(250/year, 5 years), γ̂₃=−3, γ̂₄=10, selected annualized SR̂=2.5 (per-period SR̂=2.5/√250):
the paper computes SR̂₀ ≈ 0.1132 (non-annualized) and DSR̂ ≈ 0.9004 < 0.95, so the strategy
is rejected at 95% confidence.
Evidence: "the investor has determined that this is not a legitimate empirical discovery at a
95% confidence level ... SR̂₀ = √(1/500)((1−γ)Z⁻¹[1−1/100]+γZ⁻¹[1−1/(100e)]) ≈ 0.1132,
non-annualized (with 250 observations per year)". Reproduced numerically:
SR₀=0.113176, DSR=0.90035.
Source: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
Confidence: high

**C10.** In the same example the paper reports two sensitivity results: had only N=46
independent trials been run, DSR̂ would have been 0.9505 (acceptable at 95%); and with Normal
returns (γ̂₃=0, γ̂₄=3) DSR̂ ≈ 0.95 is retained up to N=88 trials.
Evidence: "Should the strategist have made his discovery after running only N=46 independent
trials ... DSR̂ would have been 0.9505"; "If the strategy had exhibited Normal returns
(γ̂₃=0, γ̂₄=3), DSR̂ ≈ 0.95 after N=88 independent trials." Both reproduced numerically
(0.9505 and 0.9505).
Source: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
Confidence: high

**C11.** For M correlated trials, the DSR paper (Appendix 3) proposes an effective number of
independent trials by interpolating between the limits N̂→M as average correlation ρ̂→0 and
N̂→1 as ρ̂→1, i.e. N̂ = ρ̂ + (1−ρ̂)·M, with the equal-weighted average correlation bounded by
ρ̄ ∈ (−1/(M−1), 1]; it also notes information-theoretic (entropy) alternatives.
Evidence: "as ρ→0, then N→M. Similarly, as ρ→1, then N→1. Given an estimated average
correlation ρ̂, we could therefore interpolate between these two extreme outcomes"; "the
average correlation is bounded by ρ̄ ∈ (−1/(M−1), 1]".
Source: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
Confidence: medium (the interpolation limits are quoted verbatim; the compact form of Eq. (9)
was partially garbled in PDF extraction)

**C12.** Bailey, Borwein, López de Prado & Zhu, "Pseudo-Mathematics and Financial
Charlatanism" (Notices of the AMS 61(5), May 2014, pp. 458–471) state (Proposition 2.1) that
for N ≫ 1 IID standard-normal trials the expected maximum is
E[max_N] ≈ (1−γ)·Z⁻¹[1 − 1/N] + γ·Z⁻¹[1 − (1/N)e⁻¹], with upper bound √(2·ln N); e.g. N=10
alternative configurations already yield an expected in-sample SR of 1.57 when the true OOS SR
of every strategy is zero (reproduced: 1.575).
Evidence: "if the researcher tries only N = 10 alternative configurations of an investment
strategy, he or she is expected to find a strategy with a Sharpe ratio IS of 1.57, despite the
fact that all strategies are expected to deliver a Sharpe ratio of zero OOS."
Source: https://www.davidhbailey.com/dhbpapers/backtest-pseudo.pdf (published version:
https://www.ams.org/notices/201405/rnoti-p458.pdf)
Confidence: high

**C13.** The Minimum Backtest Length (Theorem 3.1) is
MinBTL ≈ [ ((1−γ)·Z⁻¹[1−1/N] + γ·Z⁻¹[1−(1/N)e⁻¹]) / E[max_N] ]² < 2·ln N / (E[max_N])²,
in YEARS, where E[max_N] is the in-sample annualized SR the researcher is willing to tolerate
arising by pure chance; MinBTL is explicitly "a necessary, non-sufficient condition to avoid
overfitting."
Evidence: Theorem 3.1 and "the reader may find helpful to remember the upper bound to the
minimum backtest length (in years), MinBTL < 2 ln[N]/(E[max_N])²."
Source: https://www.davidhbailey.com/dhbpapers/backtest-pseudo.pdf
Confidence: high

**C14.** Concrete MinBTL calibrations: with only 5 years of data no more than 45 independent
model configurations should be tried, and after only 7 independent configurations a 2-year
backtest is expected to yield a spurious in-sample annualized SR of 1 with expected OOS SR of
zero (reproduced: MinBTL(45)=4.998y, MinBTL(7)=1.923y at E[max]=1).
Evidence: "if only 5 years of data are available, no more than 45 independent model
configurations should be tried, or we are almost guaranteed to produce strategies with an
annualized Sharpe ratio IS of 1, but an expected Sharpe ratio OOS of zero. ... After trying
only 7 independent strategy configurations, the expected maximum SR IS is 1 for a 2-year long
backtest."
Source: https://www.davidhbailey.com/dhbpapers/backtest-pseudo.pdf
Confidence: high

**C15.** Bailey, Borwein, López de Prado & Zhu define backtest overfitting via OOS ranks: the
strategy-selection process overfits if the IS-optimal strategy has expected OOS rank below the
median of all N trials, and PBO = Σₙ Prob[ r̄ₙ < N/2 | strategy n optimal IS ]·Prob[n optimal
IS] — a model-free, non-parametric definition about the SELECTION process, not any single
model's calibration. Published as Journal of Computational Finance (2017), DOI
10.21314/JCF.2016.322.
Evidence: Definitions 2.1–2.2 of "The Probability of Backtest Overfitting"; DOI and April 2017
date from the Western Michigan University repository page.
Source: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf and
https://scholarworks.wmich.edu/math_pubs/42/
Confidence: high

**C16.** The CSCV (combinatorially symmetric cross-validation) estimator of PBO: form the
T×N matrix M of synchronous P&L series for all N trials; partition rows into an EVEN number S
of disjoint equal submatrices; for each of the C(S, S/2) combinations use the joined S/2
submatrices as train set J (order preserved) and the complement as test set J̄ (each of size
T/2×N); find the IS winner n\*; compute its OOS relative rank ω̄_c = r̄ᶜ_{n\*}/(N+1) ∈ (0,1)
and logit λ_c = ln(ω̄_c/(1−ω̄_c)); then PBO φ = ∫₋∞⁰ f(λ)dλ, the fraction of combinations in
which the IS-optimal strategy underperforms the OOS median (λ_c ≤ 0).
Evidence: Algorithm 2.3 steps and "The PBO ... may now be estimated using the CSCV method with
φ = ∫₋∞⁰ f(λ)dλ. This represents the rate at which optimal IS strategies underperform the
median of the OOS trials."
Source: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf
Confidence: high

**C17.** The PBO paper's own S=16 illustration prints "12,780 combinations", but the binomial
coefficient C(16,8) is 12,870 — the printed figure is a typo; any implementation should use
C(S, S/2) exactly.
Evidence: "For instance, if S = 16, we will form 12,780 combinations" (appears twice in the
paper) versus direct computation C(16,8) = 12,870.
Source: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf
Confidence: high (arithmetic; the discrepancy itself is verified against the fetched PDF)

**C18.** CSCV is deterministic and symmetric: train/test sets are equal-sized, every training
combination is reused as a testing combination and vice versa, running CSCV twice on the same
inputs gives identical results, and the paper suggests rejecting models whose estimated PBO
exceeds 0.05 under a Neyman-Pearson-style convention.
Evidence: "running CSCV twice on the same inputs generates identical results"; "a customary
approach would be to reject models for which PBO is estimated to be greater than 0.05."
Source: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf
Confidence: high

**C19.** Harvey, Liu & Zhu ("...and the Cross-Section of Expected Returns", Review of
Financial Studies 29(1), 2016; NBER WP 20592, Oct 2014) catalogue 313 papers and 316 factors
proposed to explain the cross-section of returns and conclude that "a newly discovered factor
needs to clear a much higher hurdle, with a t-ratio greater than 3.0", echoing that "most
claimed research findings in financial economics are likely false."
Evidence: abstract of NBER WP 20592: "We catalogue 316 different factors ... The estimation of
our model suggests that a newly discovered factor needs to clear a much higher hurdle, with a
t-ratio greater than 3.0."
Source: https://www.nber.org/system/files/working_papers/w20592/w20592.pdf
Confidence: high

**C20.** HLZ's specific multiple-testing benchmarks: Bonferroni-implied t-cutoff rises from
1.96 (1965-era single test) to 3.78 by 2012 (projected 4.00 by 2032); Holm tracks slightly
below (3.64 at 316 factors, 3.29 at 113 factors); BHY (false-discovery-rate control)
stabilizes at 3.39 for FDR=1% and 2.78 at 5%; accounting for an estimated 71% of unpublished
trials (M > R) raises these to Bonferroni 4.01, Holm 3.96, BHY 3.68 (1%) / 3.18 (5%), and the
authors call 3.18 the minimum defensible threshold.
Evidence: "For Bonferroni, the benchmark t-ratio starts at 1.96 and increases to 3.78 by 2012.
It reaches 4.00 in 2032. ... [BHY] stabilize at 3.39 (p-value = 0.07%) after 2010"; "we think
the minimum threshold t-ratio is 3.18, corresponding to BHY's adjustment for M > R at 5%
significance."
Source: https://www.nber.org/system/files/working_papers/w20592/w20592.pdf
Confidence: high

**C21.** Under HLZ's adjustments, of the 296 factors published as significant, 158 are deemed
false discoveries under Bonferroni, 142 under Holm, 132 under BHY at 1%, and 80 under BHY at
5%.
Evidence: "of the 296 published significant factors, 158 would be considered false discoveries
under Bonferonni [sic], 142 under Holm, 132 under BHY (1%) and 80 under BHY (5%)."
Source: https://www.nber.org/system/files/working_papers/w20592/w20592.pdf
Confidence: high

**C22.** Harvey & Liu, "Backtesting" (Journal of Portfolio Management, Fall 2015): the Sharpe
ratio maps to a t-statistic via t = μ̂/(σ̂/√T) and SR = μ̂/σ̂, hence SR = t/√T (per-period; if
SR is annualized, T is in years); the haircut procedure is SR → t-ratio → single-test p-value
p_S = Pr(|t_{T−1}| > t) → multiple-testing-adjusted p-value p_M (via Bonferroni, Holm, or BHY
against the HLZ factor population) → adjusted t-ratio → haircut Sharpe ratio HSR; the haircut
is the percentage difference between SR and HSR.
Evidence: Eqs. (1)–(2) "SR = μ̂/σ̂ which, based on Equation 1, is simply t-ratio/√T" and the
summary "Suppose the adjusted p-value is 0.05. We then calculate an adjusted t-ratio ... With
this new t-ratio, we determine a new Sharpe ratio. The percentage difference ... is the
haircut."
Source: https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF
Confidence: high

**C23.** In the independent-tests case Harvey-Liu use p_M = 1 − (1 − p_S)^N: with N=10 and
p_S=0.05 the multiple-testing p-value is 0.401 (reproduced: 1−0.95¹⁰=0.4013), i.e. a "5%
significant" best-of-10 strategy has ≈40% probability of arising by chance.
Evidence: "When N = 1 (single test) and pS = 0.05, pM = 0.05 ... If N = 10 and we observe a
strategy with pS = 0.05, pM = 0.401."
Source: https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF
Confidence: high

**C24.** The Harvey-Liu haircut is NONLINEAR: with their calibrations the haircut generally
exceeds 50% for annualized SR < 0.4 but is at most ~25% for SR > 1.0, so the industry's flat
50% rule of thumb is "too lenient for relatively small Sharpe ratios (< 0.4) and too harsh for
large ones (> 1.0)"; e.g. at 50 trials the E/P strategy is cut almost 50% while BAB is cut
only 7.9%.
Evidence: "the haircut is almost always more than and sometimes much larger than 50% when the
annualized Sharpe ratio is less than 0.4 ... when the Sharpe ratio is greater than 1.0, the
haircut is at most 25%"; "when the number of trials is 50, the haircut is almost 50% for the
least profitable E/P strategy, but only 7.9% for the most profitable BAB strategy."
Source: https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF
Confidence: high

**C25.** White's Reality Check (Econometrica 68(5), 2000, pp. 1097–1126) tests the composite
null that no candidate beats the benchmark, H₀: max_{k=1..m} E[d_k] ≤ 0, where d_{k,t} is
model k's period-t performance differential relative to the benchmark; the statistic is
RC_n = max_{k=1..m} √n·d̄_k; the null distribution is taken at the least favorable
configuration (μ = 0) as max of a multivariate normal, approximated by (stationary) bootstrap:
resample the d_t series, compute max_k √n(d̄\*_k − d̄_k) in each resample, and reject when the
sample statistic exceeds the bootstrapped critical value (equivalently when the bootstrap
p-value is below α).
Evidence: "a leading example is the RC test of White (2000) with the statistic RC_n = max_k
√n·d̄_k. ... White (2000) chooses the least favorable configuration (LFC), i.e., μ = 0 ... The
limiting distribution of RC_n is thus max{N(0,Ω)} which may be approximated via a (stationary)
bootstrap procedure" (Hsu-Hsu-Kuan restatement); citation metadata via Econometric Society
page.
Source: https://homepage.ntu.edu.tw/~ckuan/pdf/Step-SPA-20090720.pdf and
https://www.econometricsociety.org/publications/econometrica/2000/09/01/reality-check-data-snooping
Confidence: high

**C26.** The Reality Check has been applied at scale to technical trading: Sullivan,
Timmermann & White (1999) evaluated 7,846 trading rules, and Hsu & Kuan (2005) 39,832 rules —
the scale of N that a family-wide max-statistic test is designed to absorb.
Evidence: "Sullivan et al. (1999) evaluate 7,846 technical trading rules, and Hsu and Kuan
(2005) study a total of 39,832 simple technical rules and complex trading strategies."
Source: https://homepage.ntu.edu.tw/~ckuan/pdf/Step-SPA-20090720.pdf
Confidence: high

**C27.** Hansen's SPA test (Journal of Business & Economic Statistics 23(4), 2005,
pp. 365–380) modifies the Reality Check in two ways: (i) a STUDENTIZED statistic,
T^SPA = max[ max_k √n·d̄_k/ω̂_k , 0 ] with ω̂²_k a consistent estimator of var(√n·d̄_k), and
(ii) a sample-dependent null distribution that re-centers the bootstrap using
μ̂_k = d̄_k·1{ √n·d̄_k ≤ −ω̂_k·√(2·log log n) } — a law-of-the-iterated-logarithm threshold
that zeroes out models near the null boundary while letting clearly poor models (μ_k < 0) drop
out, making SPA more powerful and "less sensitive to the inclusion of poor and irrelevant
alternatives" than the Reality Check.
Evidence: "let σ̂²_k ≡ ω̂_kk and A_{n,k} = −σ̂_k√(2 log log n). We define μ̂ as the vector
with the k-th element μ̂_k = d̄_k·1(√n·d̄_k ≤ A_{n,k}) ... Hansen (2005) suggests to add √n·μ̂
to the bootstrapped distribution"; studentization: "Hansen (2005) and Romano and Wolf (2005)
also suggest that using studentized statistics, √n·d̄_k/σ̂_k, would render the test more
powerful."
Source: https://homepage.ntu.edu.tw/~ckuan/pdf/Step-SPA-20090720.pdf (JBES metadata:
https://cdr.lib.unc.edu/concern/articles/hd76s214m)
Confidence: high

**C28.** The Politis-Romano stationary bootstrap (JASA 89(428), 1994, pp. 1303–1313)
resamples blocks B(i,k) = (X_i,...,X_{i+k−1}) from the periodically extended (wrapped) series,
with IID GEOMETRIC block lengths P(J = k) = p·q^{k−1} (k ≥ 1, q = 1−p), IID uniform start
indices on {1,...,n}, and expected block length ℓ = 1/p; conditional on the data the resampled
pseudo-series is itself stationary (the property that names the method). Equivalently, at each
step the next index continues the current block with probability 1−p and jumps to a random
index with probability p.
Evidence: "Let J₁,...,J_n be i.i.d. geometric random variables ... 'J₁ = k' has probability
p·q^{k−1} for p ≡ ℓ⁻¹ ∈ (0,1) ... ℓ = p⁻¹ represents the expected length of a resampled
block. Under this resampling, Politis and Romano [15] show that the SB sample exhibits
stationarity" (Nordman, Annals of Statistics 2009, restating the method); the sequential
description with continuation probability appears in Hsu-Hsu-Kuan.
Source: https://projecteuclid.org/journals/annals-of-statistics/volume-37/issue-1/A-note-on-the-stationary-bootstraps-variance/10.1214/07-AOS567.pdf
(original: https://www.scirp.org/reference/referencespapers?referenceid=1700215)
Confidence: high

**C29.** López de Prado, Advances in Financial Machine Learning (Wiley, 2018), Chapter 7:
purged k-fold cross-validation removes from the TRAINING set every observation whose label
overlaps in time with any label in the test set ("purging"), and additionally drops training
observations that immediately FOLLOW the test window ("embargo") because serially-correlated
features (ARMA-like) leak test information into subsequent training observations.
Evidence: "Purging: removes training observations temporally overlapping with test set
labels. Embargo: excludes observations immediately following test set entries, addressing
serial correlation in financial data (ARMA processes)" (skfolio implementation docs, which
cite AFML 2018); same definitions in QuantInsti's AFML-based tutorial.
Source: https://skfolio.org/generated/skfolio.model_selection.CombinatorialPurgedCV.html and
https://blog.quantinsti.com/cross-validation-embargo-purging-combinatorial/
Confidence: high

**C30.** AFML Chapter 7 recommends a small embargo sized as a fraction of the sample, commonly
implemented as a percentage of T (the book's own suggestion is on the order of 1% of the
observations).
Evidence: implementations expose a percentage embargo parameter (e.g. "with a 5% embargo and
1000 observations, the 50 observations following each test fold are excluded"); the specific
"≈0.01·T" book figure could not be verified against a fetched primary text in this session.
Source: https://github.com/eslazarev/purged-cross-validation/blob/main/paper/paper.md (and
https://skfolio.org/generated/skfolio.model_selection.CombinatorialPurgedCV.html)
Confidence: low (the ~1% number is from memory of the book; only the percentage-parameter
convention was verified online)

**C31.** AFML Chapter 12's Combinatorial Purged Cross-Validation (CPCV): partition the sample
into N ordered groups, test on every combination of k groups → C(N,k) train/test splits; since
the k·C(N,k) tested groups are uniformly distributed over the N group positions, the test
results recombine into φ(N,k) = (k/N)·C(N,k) full-length out-of-sample backtest PATHS,
yielding a distribution of OOS performance rather than a single path. Worked examples: N=6,
k=2 → 15 splits and φ=5 paths; skfolio's default N=10, k=8 → 45 splits and 36 paths (both
reproduced by direct computation).
Evidence: "With N=6 groups and k=2, there are nCr(6,4)=15 possible data splits. Every split
involves k=2 tested groups ... total testing groups 30, uniformly distributed across N=6 →
30/6 = 5 paths"; skfolio: "n_folds=10, n_test_folds=8: Number of splits = C(10,8) = 45,
number of recombined test paths = 36."
Source: https://skfolio.org/generated/skfolio.model_selection.CombinatorialPurgedCV.html and
https://towardsai.com/p/l/the-combinatorial-purged-cross-validation-method
Confidence: high

**C32.** The DSR paper explicitly positions holdout/k-fold validation as insufficient against
backtest overfitting: applying holdout ~20 times at 95% confidence makes false positives
expected rather than unlikely, because holdout "assesses the generality of a model as if a
single trial had taken place."
Evidence: "If we apply the holdout method enough times (say 20 times for a 95% confidence
level), false positives are no longer unlikely: They are expected."
Source: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
Confidence: high

## Synthesis

The literature converges on one non-negotiable requirement: a backtest is uninterpretable
without the number and dispersion of the trials behind it. Bailey & López de Prado state
flatly that a backtest whose search extent is undisclosed is "worthless," and every formula
above is a different operationalization of that principle. This is precisely why the
protocol's engine-level `trials_ledger.csv` (N and V[{SRₖ}] recorded by the backtester itself)
is the load-bearing design choice of the whole project: DSR is only as honest as its N.

For `src/quantlab/stats.py`, the load-bearing implementation facts are: (1) PSR and DSR take
PER-PERIOD (non-annualized) Sharpe inputs, use √(n−1) (Bessel), and RAW kurtosis (Normal=3) —
the protocol's stated formula in §6 matches the primary sources exactly; (2) the DSR benchmark
SR₀ multiplies √V[{SRₖ}] (per-period trial-SR variance) by the two-quantile Euler–Mascheroni
expression, and V must be in the same per-period units as SR̂ — the papers' example converts an
annualized trial variance of 1/2 into √(1/500) per-period; unit conversion is the likeliest
implementation bug. The verified pins for unit tests: DSR example (N=100, T=1250, γ₃=−3,
γ₄=10, SR 2.5 annualized) → SR₀≈0.1132, DSR≈0.9004; E[max₁₀]=1.57 for standard normal trials;
MinTRL=2.73 years (SR 2 vs 1, daily, 95%); MinBTL(N=45)≈5 years; C(16,8)=12,870 (note the PBO
paper's 12,780 misprint — cite carefully). Gate 3's "DSR > 0.95" is exactly the papers' 95%
confidence convention, and Gate 3's pooled |t|>3 is HLZ's headline hurdle — though HLZ's own
floor is 3.18 (BHY, 5%, hidden-trials case), so |t|>3 should be described as "approximately
the HLZ standard," not more.

Two protocol nuances surfaced. First, CPCV path-counting: 8 blocks choose 2 gives 28 SPLITS
but φ(8,2)=7 recombined backtest PATHS; protocol §6's "(28 paths)" conflates the two and the
report should say "28 splits / 7 paths." Second, the family-wide Reality-Check test: White's
p-value comes from re-centered bootstrap maxima (max_k √n(d̄\*_k−d̄_k)), and Hansen's SPA
variant (studentization + √(2 log log n) re-centering) exists specifically because RC's
least-favorable-configuration null loses power when the candidate family contains many bad
strategies — which a G2 evolutionary search family will. If the RC p-value looks weak,
SPA is the defensible upgrade, not a lower bar. The stationary bootstrap's mean-block
parameter (protocol: 20 days) is the geometric-distribution restart probability p=1/20.

Finally, these tools answer different questions and are complementary, not redundant: DSR
(is this SR significant given N trials?), PBO/CSCV (does our selection process pick OOS
losers?), RC/SPA (does the best family member beat a benchmark after snooping?), HLZ/haircut
(what cross-sectional hurdle applies?), purging/embargo/CPCV (is the evaluation itself
leak-free?). A candidate that clears all five families of safeguards has cleared the strongest
prior-art standard the 2014–2018 literature knows how to state.
