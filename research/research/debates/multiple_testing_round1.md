# Adversarial verification — multiple_testing.md — round 1

Verifier: independent re-fetch of every primary source; all formulas checked symbol-by-symbol
against rendered page images of the original PDFs (pypdf/PyMuPDF text extraction garbles the
math fonts, so equation pages were rasterized and read visually); all numeric claims re-computed
with scipy. Verification date: 2026-07-19.

Sources fetched by me this round (all re-downloaded, not trusted from the researcher's notes):

- SF = https://www.davidhbailey.com/dhbpapers/sharpe-frontier.pdf (46 pp., SSRN WP of J. Risk 15(2))
- DS = https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf (22 pp.)
- BP = https://www.davidhbailey.com/dhbpapers/backtest-pseudo.pdf (34 pp.)
- PBO = https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf (34 pp.)
- HLZ = https://www.nber.org/system/files/working_papers/w20592/w20592.pdf (101 pp., Oct 2014)
- HL = https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF (JPM Fall 2015)
- HHK = https://homepage.ntu.edu.tw/~ckuan/pdf/Step-SPA-20090720.pdf (Hsu-Hsu-Kuan Step-SPA)
- NORD = https://arxiv.org/pdf/0903.0474 (Nordman, Ann. Statist. 37(1) 2009, 359-370; the
  projecteuclid.org PDF URL cited in the file is Incapsula-blocked from this environment, the
  arXiv version is identical in the quoted passage)
- GARP = https://www.garp.org/hubfs/Whitepapers/a1Z1W0000054x6lUAA.pdf (López de Prado, "The 10
  Reasons Most Machine Learning Funds Fail" — author-primary text for purge/embargo)
- WHITE = https://users.ssc.wisc.edu/~behansen/718/White2000.pdf (published Econometrica scan)
- SKF = https://skfolio.org/generated/skfolio.model_selection.CombinatorialPurgedCV.html and
  https://raw.githubusercontent.com/skfolio/skfolio/main/src/skfolio/model_selection/_combinatorial.py
- TAI = https://towardsai.com/p/l/the-combinatorial-purged-cross-validation-method

Citation-metadata cross-checks: RFS 29(1):5-68 via https://academic.oup.com/rfs/article-abstract/29/1/5/1843824;
J. Risk 15(2) Dec 2012 via https://www.risk.net/journal-of-risk/volume-15-number-2-december-2012;
Notices AMS 61(5):458-471 via https://www.ams.org/notices/201405/rnoti-p458.pdf;
JPM 40(5):94-107 via https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551;
JCF April 2017 DOI 10.21314/JCF.2016.322 via https://scholarworks.wmich.edu/math_pubs/42/;
JBES 23(4):365-380 via https://www.tandfonline.com/doi/abs/10.1198/073500105000000063 and
https://ideas.repec.org/a/bes/jnlbes/v23y2005p365-380.html;
JASA 89(428):1303-1313 via https://www.tandfonline.com/doi/abs/10.1080/01621459.1994.10476870.

## Verdicts

**C1 — PSR formula. CONFIRMED.** SF p.9, Eq. (11), read from page image:
PSR(SR*) = Z[(SR̂ − SR*)√(n−1) / √(1 − γ̂₃SR̂ + ((γ̂₄−1)/4)SR̂²)]. Symbol-for-symbol identical
to the claim, including √(n−1) in the numerator and (γ̂₄−1)/4 (raw-kurtosis form). Journal of
Risk 15(2) (Dec 2012) confirmed via risk.net volume page.

**C2 — SR̂ standard deviation + Bessel. CONFIRMED.** SF p.8 image: σ̂_SR̂ =
√[(1 − γ̂₃SR̂ + ((γ̂₄−1)/4)SR̂²)/(n−1)], "where n − 1 is due to Bessel's correction" (verbatim).
Consistent with Eq. (8): (SR̂−SR) →a N(0, [1 + ½SR² − γ₃SR + ((γ₄−3)/4)SR²]/n); note
½SR² + ((γ₄−3)/4)SR² = ((γ₄−1)/4)SR², so the two forms agree.

**C3 — non-annualized inputs. CONFIRMED.** SF p.9 image, verbatim: "greater SR̂ (in the original
sampling frequency, i.e. non-annualized)"; "All calculations are done in the original frequency
of the data, and there is no annualization."; footnote 5: "SR̂ and SR* are expressed in the same
frequency as the returns time series."

**C4 — raw kurtosis (Normal = 3). CONFIRMED.** SF p.10 image: "while assuming Normality
(γ̂₃ = 0, γ̂₄ = 3)"; DS p.10 image: "If the strategy had exhibited Normal returns (γ̂₃ = 0,
γ̂₄ = 3)". At γ₃=0, γ₄=3 the variance term reduces to 1 + SR²/2 (Lo's IID-normal value), as the
claim states.

**C5 — MinTRL formula + 2.73-year example. CONFIRMED.** SF p.11 image, Eq. (13): MinTRL = n* =
1 + [1 − γ̂₃SR̂ + ((γ̂₄−1)/4)SR̂²](Z_α/(SR̂−SR*))², exactly as claimed. Verbatim: "a 2.73 years
track record is required for an annualized Sharpe of 2 to be considered greater than 1 at a 95%
confidence level" (daily IID Normal); "MinTRL is expressed in terms of number of observations,
not annual or calendar terms." My scipy reproduction (250 obs/yr, Z₀.₉₅=1.6449): 682.78 obs =
2.731 years. Matches.

**C6 — PSR worked example. CONFIRMED** (and can be upgraded from "medium" to high confidence).
SF p.10 image gives the digits the researcher could not extract: SR̂ = 0.458 (monthly),
PSR(0) = 0.982 assuming Normality; γ̂₃ = −2.448, γ̂₄ = 10.164 → PSR(0) = 0.913; with 3 years
PSR(0) = 0.953. The claim's asserted precision (0.98 / below 0.95 / ≈0.95; γ₃=−2.448,
γ₄=10.164; monthly SR̂≈0.458; annualized 1.59; 2-year monthly record) is exactly right. My scipy
reproduction with the paper's own inputs (SR̂=0.458): 0.9817 / 0.9134 / 0.9535 — reproduces the
paper's printed 0.982 / 0.913 / 0.953. Nitpick (not an objection): the file's reproduction note
says "0.982 / 0.914 / 0.954" (it used 1.59/√12 = 0.459 rather than the paper's rounded 0.458);
the paper's printed values are 0.982/0.913/0.953. Also "HFR-style moments" is loose — the
−2.448/10.164 moments belong to the paper's hedge-fund example (Figure 6); the HFR Aggregate
index moments quoted elsewhere in the paper are γ̂₃=−0.72, γ̂₄=5.78.

**C7 — E[max] approximation. CONFIRMED.** DS p.7 image, Eq. (1): E[max{SR̂ₙ}] ≈ E[{SR̂ₙ}] +
√V[{SR̂ₙ}]·((1−γ)Z⁻¹[1−1/N] + γZ⁻¹[1−(1/N)e⁻¹]), "where γ (approx. 0.5772) is the
Euler-Mascheroni constant, Z is the cumulative function of the standard Normal distribution, and
e is Euler's number", N ≫ 1. Python Snippet 1 verified verbatim in extracted text:
"emc=0.5772156649 # Euler-Mascheroni constant" and
"maxZ=(1-emc)*ss.norm.ppf(1-1./numTrials)+emc*ss.norm.ppf(1-1./(numTrials*np.e))". JPM 40(5)
2014, pp. 94-107 confirmed via SSRN abstract page.

**C8 — DSR definition. CONFIRMED.** DS p.8 image, Eq. (2): DSR̂ ≡ PSR̂(SR̂₀) =
Z[(SR̂−SR̂₀)√(T−1)/√(1−γ̂₃SR̂+((γ̂₄−1)/4)SR̂²)] with SR̂₀ = √V[{SR̂ₙ}]·((1−γ)Z⁻¹[1−1/N] +
γZ⁻¹[1−(1/N)e⁻¹]); "V[{SR̂ₙ}] is the variance across the trials' estimated SR and N is the
number of independent trials." The five-variables quote is verbatim on p.9. SR̂₀ as expected max
under the zero-true-SR null: p.9 verbatim, "Under the null hypothesis that the actual Sharpe
ratio is zero, H₀: SR = 0, we know that the expected maximum SR̂ can be estimated as the SR̂₀ in
Eq.(2)."

**C9 — DSR worked example. CONFIRMED.** DS pp.9-10 images: N=100, V[{SR̂ₙ}]=1/2, T=1250,
γ̂₃=−3, γ̂₄=10, annualized SR̂=2.5 over 5 daily years; SR̂₀ = √(1/(2·250))·(...) ≈ 0.1132
"non-annualized (with 250 observations per year)" — note √(1/(2·250)) = √(1/500) as the claim
says; DSR̂ = Z[((2.5/√250 − 0.1132)√1249)/√(1−(−3)(2.5/√250)+((10−1)/4)(2.5/√250)²)] = 0.9004 <
0.95; "the investor declines ... not a legitimate empirical discovery at a 95% confidence
level." My reproduction: SR₀ = 0.113172, DSR = 0.90036. Matches.

**C10 — sensitivity results. CONFIRMED.** DS p.10 image, verbatim: "Should the strategist have
made his discovery after running only N=46 independent trials ... DSR would have been 0.9505,
above the 95% confidence level"; "If the strategy had exhibited Normal returns (γ̂₃ = 0,
γ̂₄ = 3), DSR = 0.9505 after N=88 independent trials." My reproduction: 0.9505 and 0.9505.

**C11 — effective number of trials. CONFIRMED.** DS Appendix A.3 (pp.14-15 images): Eq. (9)
N̂ = ρ̂ + (1−ρ̂)M; "as ρ → 1, then N → 1. Similarly, as ρ → 0, then N → M. Given an estimated
average correlation ρ̂, we could therefore interpolate between these two extreme outcomes";
equal-weighted average correlation Eq. (8) with bound "ρ ∈ (−1/(M−1), 1]"; entropy alternative
verbatim: "An alternative and more direct path is to use information theory to determine N̂.
Entropy relates to a much deeper concept of redundancy than correlation" (cites data
compression, total correlation, multiinformation). Nitpick: the file's quote reverses the order
of the two limit clauses relative to the paper; content identical. The compact Eq. (9) is now
verified directly from the page image, so the "medium" confidence can be raised.

**C12 — Proposition 2.1 + 1.57 example. CONFIRMED.** BP p.9 image: E[max_N] ≈
(1−γ)Z⁻¹[1−1/N] + γZ⁻¹[1−(1/N)e⁻¹], γ ≈ 0.5772156649, N ≫ 1; upper bound √(2 ln N) stated just
below ("An upper bound to Eq.(2.4) is √(2 ln[N])"); verbatim: "if the researcher tries only
N = 10 alternative configurations of an investment strategy, he or she is expected to find a
strategy with a Sharpe ratio IS of 1.57, despite the fact that all strategies are expected to
deliver a Sharpe ratio of zero OOS." My reproduction: 1.5746. Notices AMS 61(5), May 2014,
pp. 458-471 confirmed (rnoti-p458.pdf).

**C13 — MinBTL Theorem 3.1. CONFIRMED.** BP p.11 image: "The Minimum Backtest Length (MinBTL,
in years) needed to avoid selecting a strategy with an IS Sharpe ratio of E̅[max_N] among N
independent strategies with an expected OOS Sharpe ratio of zero is MinBTL ≈
[((1−γ)Z⁻¹[1−1/N] + γZ⁻¹[1−(1/N)e⁻¹])/E̅[max_N]]² < 2 ln[N]/E̅[max_N]²" (Eq. 3.2); "the reader
may find helpful to remember the upper bound to the minimum backtest length (in years), MinBTL <
2 ln[N]/E̅[max_N]²"; "MinBTL should be considered a necessary, non-sufficient condition to avoid
overfitting." All verbatim.

**C14 — MinBTL calibrations. CONFIRMED.** BP pp.11-12 images, verbatim: "if only 5 years of data
are available, no more than 45 independent model configurations should be tried, or we are
almost guaranteed to produce strategies with an annualized Sharpe ratio IS of 1, but an expected
Sharpe ratio OOS of zero"; "After trying only 7 independent strategy configurations, the
expected maximum SR IS is 1 for a 2-year long backtest, while the expected SR OOS is 0." My
reproduction at E[max]=1: MinBTL(45) = 4.998 y, MinBTL(7) = 1.923 y. Matches.

**C15 — PBO definition + publication. CONFIRMED.** PBO paper Definitions 2.1-2.2 (extracted
text): overfit iff Σₙ E[r̄ₙ | r ∈ Ω*ₙ]Prob[r ∈ Ω*ₙ] ≤ N/2; PBO = Σₙ Prob[r̄ₙ < N/2 | r ∈ Ω*ₙ]
Prob[r ∈ Ω*ₙ]; "we refer to overfitting in relation to the strategy selection process, not a
strategy's model calibration"; "our procedure to estimate PBO is model-free ... It is also
non-parametric." WMU repository page confirms Journal of Computational Finance, April 2017, DOI
10.21314/JCF.2016.322.

**C16 — CSCV algorithm. CONFIRMED.** PBO §11-13 (extracted text): even S disjoint equal
submatrices; all C(S,S/2) combinations; train J joined "in their original order", T/2×N; test J̄
complement; IS winner n*; "relative rank of r̄ᶜ_{n*} by ω̄c := r̄ᶜ_{n*}/(N+1) ∈ (0,1)"; "logit
λc = ln(ω̄c/(1−ω̄c))"; "The PBO defined in Section 2.1 may now be estimated using the CSCV
method with φ = ∫₋₀^0 f(λ)dλ [∫₋∞⁰]. This represents the rate at which optimal IS strategies
underperform the median of the OOS trials." All verbatim.

**C17 — 12,780 vs 12,870 typo. CONFIRMED.** PBO extracted text, twice: "For instance, if S = 16,
we will form 12, 780 combinations" and "S = 16 we will obtain 12, 780 [logits]". C(16,8) = 12,870
(scipy comb). The printed figure is arithmetically wrong; the claim's characterization as a typo
to be ignored by implementations is sound.

**C18 — determinism/symmetry/0.05 convention. CONFIRMED.** Verbatim: "CSCV ensures that the
training and testing sets are of equal size"; "CSCV is symmetric, in the sense that all training
sets are re-used as testing sets and vice versa"; "running CSCV twice on the same inputs
generates identical results"; "In accordance with standard applications of the Neyman-Pearson
framework, a customary approach would be to reject models for which PBO is estimated to be
greater than 0.05."

**C19 — HLZ headline. CONFIRMED.** HLZ WP 20592 (October 2014 on title page): "We begin with 313
papers that study cross-sectional return patterns"; "we focus on 313 published works and
selected working papers. We catalogue 316 different factors"; abstract verbatim: "a newly
discovered factor needs to clear a much higher hurdle, with a t-ratio greater than 3.0" and "we
argue that most claimed research findings in financial economics are likely false." RFS 29(1),
2016, pp. 5-68 confirmed via OUP.

**C20 — specific t-hurdles. CONFIRMED.** All verbatim in HLZ: "For Bonferroni, the benchmark
t-ratio starts at 1.96 and increases to 3.78 by 2012. It reaches 4.00 in 2032"; "the Holm at 113
factors is 3.29 (p-value = 0.10%) while Holm at 316 factors is 3.64"; BHY "stabilize at 3.39
(p-value = 0.07%) after 2010" [1% significance] and "2.78 (p-value = 0.54%) in 2012" [5%];
"Based on our estimates, 71% of all tried factors are missing. The new benchmark t-ratios for
Bonferroni and Holm are estimated to be 4.01 and 3.96 ... The BHY implied t-ratio increases from
3.39 to 3.68 at 1% significance and from 2.78 to 3.18 at 5% significance"; "we think the minimum
threshold t-ratio is 3.18, corresponding to BHY's adjustment [for M > R at 5%]." Minor note: the
claim's "1965-era single test" gloss — the paper's Figure 3 axis runs 1965-2032 while the
abstract dates the first empirical tests to 1967; harmless.

**C21 — false-discovery counts. CONFIRMED.** HLZ verbatim: "of the 296 published significant
factors, 158 would be considered false discoveries under Bonferonni [sic in original], 142 under
Holm, 132 under BHY (1%) and 80 under BHY (5%)."

**C22 — SR↔t mapping + haircut pipeline. CONFIRMED.** HL Eq. (1): t-statistic = μ̂/(σ̂/√T),
t-distribution with T−1 dof under IID normal null; Eq. (2): SR = μ̂/σ̂ "which, based on Equation
1, is simply t-ratio/√T"; intro verbatim: "Suppose the adjusted p-value is 0.05. We then
calculate an adjusted t-ratio; in this case, it is 2.0. With this new t-ratio, we determine a
new Sharpe ratio. The percentage difference between the original Sharpe ratio and the new Sharpe
ratio is the haircut." The claim's per-period/annualized gloss is consistent with the paper's
own worked example (T=240 monthly, annual SR 0.75 → p=0.0008, i.e. t = 0.75√20 = 0.2165√240 =
3.35): both conventions give the same t.

**C23 — independent-case pM. CONFIRMED.** HL verbatim: "When N = 1 (single test) and pS = 0.05,
pM = 0.05, so there is no multiple testing adjustment. If N = 10 and we observe a strategy with
pS = 0.05, pM = 0.401, implying a probability of about 40% in finding an investment strategy
that generates a t-statistic that is at least as large as the observed t-ratio." My
reproduction: 1 − 0.95¹⁰ = 0.4013.

**C24 — nonlinear haircut. CONFIRMED.** HL verbatim: "the haircut is almost always more than and
sometimes much larger than 50% when the annualized Sharpe ratio is less than 0.4. On the other
hand, when the Sharpe ratio is greater than 1.0, the haircut is at most 25% ... 50% is too
lenient for relatively small Sharpe ratios (< 0.4) and too harsh for large ones (> 1.0)"; "when
the number of trials is 50, the haircut is almost 50% for the least profitable E/P strategy, but
only 7.9% for the most profitable BAB strategy."

**C25 — White's Reality Check. CONFIRMED.** HHK pp.3-5: joint null Hᵏ₀: μₖ ≤ 0, k=1..m
(equivalent to max_k E[dₖ] ≤ 0); "RCₙ = max_{k=1,...,m} √n d̄ₖ"; "White (2000) chooses the least
favorable configuration (LFC), i.e., μ = 0 ... The limiting distribution of RCₙ is thus
max{N(0,Ω)} which may be approximated via a (stationary) bootstrap procedure. The null
hypothesis (1) would be rejected when the bootstrapped p-value is smaller than a pre-specified
significance level or, equivalently, when the test statistic RCₙ is greater than the
bootstrapped critical value." The bootstrap-centering form max_k √n(d̄*ₖ − d̄ₖ) is confirmed by
HHK's Eq. (3) quantile expression (√n max_k(d̄*ₖ − d̄ₖ + μ̂ₖ), with μ̂ = 0 reducing to the RC
case). Citation verified against the published scan: "Econometrica, Vol. 68, No. 5 (September,
2000), 1097-1126. A REALITY CHECK FOR DATA SNOOPING by Halbert White."

**C26 — scale of application. CONFIRMED.** HHK p.4 verbatim: "Sullivan et al. (1999) evaluate
7,846 technical trading rules, and Hsu and Kuan (2005) study a total of 39,832 simple technical
rules and complex trading strategies."

**C27 — Hansen SPA. CONFIRMED.** JBES 23(4), 2005, pp. 365-380 confirmed (Taylor & Francis /
RePEc). Hansen's two modifications per the JBES abstract: a studentized test statistic and a
sample-dependent null distribution; the abstract states the SPA test "is more powerful and less
sensitive to [the inclusion of] poor and irrelevant alternatives" than the Reality Check. HHK
p.5 verbatim: "let σ̂²ₖ ≡ ω̂ₖₖ and A_{n,k} = −σ̂ₖ√(2 log log n). We define μ̂ as the vector with
the k-th element: μ̂ₖ = d̄ₖ1(√n d̄ₖ ≤ A_{n,k}) ... Hansen (2005) suggests to add √n μ̂ to the
bootstrapped distribution"; and "Hansen (2005) and Romano and Wolf (2005) also suggest that
using studentized statistics, √n d̄ₖ/σ̂ₖ, would render the test more powerful." μ̂ₖ zeroes
models near the boundary while poor models (μₖ<0) get μ̂ₖ → μₖ, exactly as the claim describes.
Nitpick (not an objection): Hansen's own JBES abstract could not be fetched verbatim from this
environment (publisher pages 403); secondary restatements render the key phrase both with and
without "the inclusion of", so the file's quotation marks around that fragment are not pinned to
an exact fetch. Substance fully verified.

**C28 — stationary bootstrap. CONFIRMED.** NORD (arXiv:0903.0474, p.3) verbatim: "denote a data
block as B(i,k) = (Xi,...,Xi+k−1) for i,k ≥ 1 where the data are periodically extended as Xi =
Xi−n for i > n. Let J1,...,Jn be i.i.d. geometric random variables ... 'J1 = k', k ≥ 1, has
probability pq^{k−1} for p ≡ ℓ⁻¹ ∈ (0,1), q = 1 − p ... let I1,...,IK be i.i.d. uniform
variables on {1,...,n} ... ℓ = p⁻¹ represents the expected length of a resampled block. Under
this resampling, Politis and Romano [15] show that the SB sample exhibits stationarity." The
sequential continuation/restart description is verbatim in HHK p.6-7: "nb,1 is randomly chosen
from {1,...,n} ... for any t > 1, nb,t = nb,t−1 + 1 with probability Q; otherwise, nb,t is
chosen randomly from {1,...,n}" (their Q is the continuation probability 1−p). JASA 89(428),
1994, pp. 1303-1313 confirmed via tandfonline. Nitpick: the file's "(original: ...)" URL is a
scirp.org citation-index page, not the paper itself; and the projecteuclid PDF link is
bot-blocked (Incapsula) — the arXiv mirror is the fetchable source.

**C29 — purging and embargo. CONFIRMED.** skfolio page verbatim: "Purging consist of removing
from the training set all observations whose labels overlapped in time with those labels
included in the testing set. Embargoing consist of removing from the training set all
observations that immediately follow an observation in the testing set, since financial features
often incorporate series that exhibit serial correlation (like ARMA processes)"; cites AFML
(López de Prado, 2018). Stronger author-primary confirmation found this round — GARP whitepaper
(López de Prado), verbatim: "Since financial features often incorporate series that exhibit
serial correlation (like ARMA processes), we should eliminate from the training set observations
that immediately follow an observation in the testing set. I call this process embargo."
Recommend adding the GARP URL to the file's evidence. Nitpick: the file's "Evidence" quote is a
paraphrase of the skfolio wording presented in quotation marks.

**C30 — embargo ≈1% of T. CONFIRMED** (upgrade from the file's "low" confidence; primary-source
evidence found). GARP whitepaper (López de Prado, same text as AFML Ch.7 §7.4.3), verbatim: "We
can implement this embargo period h by setting Yj = f[[tj,0, tj,1 + h]] before purging. A small
value h ≈ .01T, where T is the number of bars, often suffices to prevent all leakage."
(https://www.garp.org/hubfs/Whitepapers/a1Z1W0000054x6lUAA.pdf, p.14 of 21.) The file should
cite this URL and can drop the "from memory" caveat.

**C31 — CPCV split/path counting. CONFIRMED.** Formula and both worked examples reproduced by
direct computation: C(6,2) = 15 splits, φ(6,2) = (2/6)·15 = 5 paths; C(10,8) = 45 splits,
φ(10,8) = (8/10)·45 = 36 paths. TAI article verbatim: "That is nCr(6, (6–2)) = 15" splits;
"these tested groups are uniformly distributed across all N. Therefore, there is a total number
of paths 30 / 6 = 5 paths"; "each group is a member of φ[6, 2] = 5 testing sets". skfolio
defaults confirmed on the page (n_folds=10, n_test_folds=8) and in source:
_n_splits = math.comb(n_folds, n_test_folds); _n_test_paths = n_splits · n_test_folds // n_folds
— i.e. exactly φ(N,k) = (k/N)·C(N,k), giving 45 and 36 at the defaults. Nitpick (not an
objection): the file's evidence line renders the 45/36 example as a quotation from skfolio
("Number of splits = C(10,8) = 45, number of recombined test paths = 36"); that sentence does
not appear on the current page — the numbers follow from the page's defaults plus the source
formula. Rephrase as a computation, not a quote.

**C32 — holdout insufficiency. CONFIRMED.** DS p.6 image, verbatim: "Holdout assesses the
generality of a model as if a single trial had taken place, again ignoring the rise in false
positives as more trials occur. If we apply the holdout method enough times (say 20 times for a
95% confidence level), false positives are no longer unlikely: They are expected."

## Synthesis spot-checks

- "a backtest whose search extent is undisclosed is 'worthless'": DS extracted text, "has not
  controlled for the extent of the search involved in his or her finding is worthless" — supported.
- CPCV 8-choose-2: C(8,2) = 28 splits, φ(8,2) = (2/8)·28 = 7 paths — the synthesis's correction of
  protocol §6's "(28 paths)" is arithmetically right.
- DSR unit conversion (annualized trial variance 1/2 → √(1/500) per-period): matches DS p.10's own
  √(1/(2·250)).
- Stationary-bootstrap restart probability p = 1/(mean block length): matches NORD (p ≡ ℓ⁻¹) and
  HHK (Q = 1−p continuation).
- "Gate 3's pooled |t|>3 ≈ HLZ headline, HLZ's own floor 3.18": matches C19/C20 as verified.

## Summary

32/32 claims CONFIRMED; no OVERSTATED / WRONG / UNVERIFIABLE verdicts on load-bearing claims.
Minor nitpicks (quote-provenance and rounding notes on C6, C11, C20, C27, C28, C29, C31; C30
confidence upgrade with new primary URL) are recorded above for the researcher to fold into a
revision; none changes a number, formula, year, or attribution.
