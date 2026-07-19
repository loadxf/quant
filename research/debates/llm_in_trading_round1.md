# Adversarial verification round 1: research/prior_art/llm_in_trading.md

Verifier: independent adversarial pass, 2026-07-19. All sources re-fetched by the verifier
(arXiv abstract pages via WebFetch; arXiv/Fed/journal PDFs downloaded and text-extracted with
pypdf; counts recomputed programmatically). Verdicts: CONFIRMED / OVERSTATED / WRONG / UNVERIFIABLE.

Summary: 30 claims checked. 26 CONFIRMED. 4 not confirmed:
- C9 OVERSTATED (no deep-symbolic-regression baseline in the AlphaGen paper's experiments)
- C21 WRONG (operator counts: decay_linear is in 22 formulas, not 39; IndNeutralize in 16-18 formulas, "17" is an occurrence count)
- C23 OVERSTATED (abstract misquote: actual wording is "high returns and weak correlations")
- C25 OVERSTATED (supporting quote misattributed: it is from AlphaForge 2406.18394, not the warm-start GP paper 2412.00896)

Status header NOT advanced to "agreed" (non-CONFIRMED verdicts exist).

---

## C1 — Lopez-Lira & Tang, arXiv 2304.07619, ~90% hit rates, Oct 2021 – May 2024. CONFIRMED
- arXiv abs page: v1 April 15, 2023; latest v6 October 28, 2025. Abstract (v6): "GPT-4 captures initial
  market responses, achieving approximately 90% portfolio-day hit rates for the non-tradable initial reaction."
- PDF text: "The sample period begins in October 2021 and ends in May 2024." Table: GPT-4 initial-reaction
  hit rate 93.28% overnight / 88.78% intraday (so "roughly 90%" is fair).
- Source: https://arxiv.org/abs/2304.07619 ; https://arxiv.org/pdf/2304.07619

## C2 — Sharpe 2.97 (GPT-4) vs 1.66 (GPT-3.5) vs 1.26 (DistilBART-MNLI); negative for basic models. CONFIRMED
- PDF verbatim: "...delivers an annualized Sharpe ratio of 2.97 over the sample period, compared with 1.66 for
  GPT-3.5, 1.26 for DistilBART-MNLI, and negative Sharpe ratios for most basic models."
- Main results table confirms the parenthetical: GPT-1 Sharpe -0.64, GPT-2 -0.11, Llama2-7b -0.43 (all negative).
- Note: 2.97 is the equal-weighted, zero-cost, overnight-news drift Sharpe (pre-transaction-costs); paper shows it
  falls to 1.29 at 10 bps round-trip and to 0.56 value-weighted. The prior-art file does not claim tradability, so no objection.
- Source: https://arxiv.org/pdf/2304.07619

## C3 — Sharpe decay 6.54 (2021Q4) → 3.68 (2022) → 2.33 (2023) → 1.22 (Jan–May 2024). CONFIRMED
- PDF verbatim (twice, intro and Section discussing Figure 8): "its annualized Sharpe ratio drops from 6.54 in
  2021Q4 to 3.68 in 2022, 2.33 in 2023, and to 1.22 over January-May 2024."
- Source: https://arxiv.org/pdf/2304.07619

## C4 — Post-knowledge-cutoff evaluation as documented method, citing Sarkar & Vafa 2024 and Lopez-Lira, Tang & Zhu 2025. CONFIRMED
- PDF footnote 4 verbatim: "Sarkar and Vafa (2024) and Lopez-Lira, Tang, and Zhu (2025) provide strong evidence
  that one must use a sample period after an LLM's knowledge cutoff date to avoid lookahead bias and memorization problems."
  Also in Section 2: "This sample period ensures that our evaluation is out-of-sample as the training data of the
  ChatGPT models stops in September 2021 (e.g., Sarkar and Vafa (2024) and Lopez-Lira, Tang, and Zhu (2025))."
- Source: https://arxiv.org/pdf/2304.07619

## C5 — BloombergGPT: 50B params, 363B financial + 345B general tokens, financial NLP tasks. CONFIRMED
- arXiv abs page: v1 March 30, 2023; 50 billion parameters; 363B-token Bloomberg financial dataset augmented
  with 345B general-purpose tokens; abstract lists "sentiment analysis and named entity recognition to question
  answering." No alpha-mining/trading-signal system claimed.
- Source: https://arxiv.org/abs/2303.17564

## C6 — FinGPT: open-source data-centric financial LLM, June 2023, robo-advising/algo-trading/low-code. CONFIRMED
- arXiv abs page: v1 June 9, 2023; abstract verbatim: "FinGPT takes a data-centric approach, providing researchers
  and practitioners with accessible and transparent resources"; applications "robo-advising, algorithmic trading,
  and low-code development"; comments field: "Accepted by the FinLLM Symposium at IJCAI 2023."
- Nuance (not an objection): abstract credits the "open-source AI4Finance community"; "AI4Finance Foundation" is the
  GitHub org name.
- Source: https://arxiv.org/abs/2306.06031

## C7 — Alpha-GPT (arXiv 2308.00016, July 2023): interactive alpha-mining copilot paradigm. CONFIRMED
- abs page: v1 July 31, 2023; authors Saizhuo Wang, Hang Yuan, Leon Zhou, Lionel M. Ni, Heung-Yeung Shum, Jian Guo
  (matches "Wang, Yuan, Zhou, Ni, Shum, Guo"). Abstract verbatim matches the quoted text including "algorithmic factor
  mining (e.g., search with genetic programming), have inherent limitations" and "human-AI interaction ... Alpha-GPT,
  a new interactive alpha mining system framework."
- Source: https://arxiv.org/abs/2308.00016

## C8 — Alpha-GPT 2.0 (arXiv 2402.09746, Feb 2024): human-in-the-loop multi-agent, mining/modeling/analysis. CONFIRMED
- abs page: v1 February 15, 2024; authors Hang Yuan, Saizhuo Wang, Jian Guo (matches "Yuan, Wang, Guo").
- Paper PDF verbatim: "we have adopted a Multi-agent architecture, termed Alpha-GPT 2.0. This architecture employs
  specialized agents ... such as alpha mining, alpha modeling, and alpha analysis"; "at every stage, human researchers
  can infuse their insights and ideas into the research cycle."
- Source: https://arxiv.org/abs/2402.09746 ; https://arxiv.org/pdf/2402.09746

## C9 — AlphaGen (KDD 2023): RL with combination-model reward; beats gplearn GP and deep-symbolic-regression baselines on CSI300/CSI500. OVERSTATED
- Confirmed: KDD '23 ADS track; authors Shuo Yu, Hongyan Xue, Xiang Ao, et al.; "prioritizes mining a synergistic set
  of alphas"; combination model's performance as RL reward; experiments on CSI300 and CSI500.
- Confirmed baselines in the paper (PDF, Section 4.2.1): "PPO, GP, MLP, LightGBM, and XGBoost", where GP is
  "a genetic programming model using the alpha's IC as the fitness measure ... implemented upon the gplearn framework."
- NOT confirmed: a deep-symbolic-regression baseline in the paper. The PDF's only DSR content is related-work discussion
  (Petersen et al. 2021 cited as [13]); there is no DSR/DSO row in any results table. The DSO baseline exists only in the
  companion GitHub repo ("a minimal implementation of DSO ... experiment script dso.py"), which postdates/accompanies the
  paper but is not a reported experimental comparison.
- Fix: claim should say the paper beats gplearn-GP, PPO, XGBoost, LightGBM, MLP; the repo additionally ships a DSO baseline.
- Source: https://arxiv.org/pdf/2306.12964 ; https://github.com/RL-MLDM/alphagen

## C10 — AlphaGen signal forms: OHLCV+vwap, small operator grammar, quoted example alphas. CONFIRMED
- HTML version: features are exactly "open, close, high, low, volume, vwap"; cross-section operators include
  Abs/Log/arithmetic/Greater/Less; time-series operators Ref/Mean/Med/Sum/Std/Var/Max/Min/Mad/Delta/WMA/EMA/Cov/Corr;
  case-study alphas include Var(Greater(Greater(Var(low,50),high),open),30) and (Mad(high,50)+0.5)*vwap/close verbatim.
- Source: https://arxiv.org/html/2306.12964

## C11 — QuantAgent (arXiv 2402.03755): two-layer self-improving loop, provably efficient convergence. CONFIRMED
- abs page: v1 February 6, 2024; authors Saizhuo Wang, Hang Yuan, Lionel M. Ni, Jian Guo (matches "Wang, Yuan, Ni, Guo").
  Abstract: inner loop "refines its responses by drawing from its knowledge base"; outer loop responses "tested in
  real-world scenarios to automatically enhance the knowledge base"; "progressively approximate optimal behavior with
  provable efficiency"; "an autonomous agent for mining trading signals named QuantAgent."
- Source: https://arxiv.org/abs/2402.03755

## C12 — AlphaAgent (arXiv 2502.16789): AST originality, LLM hypothesis-factor alignment, AST complexity control. CONFIRMED
- abs page: v1 February 24, 2025; first author Ziyi Tang ("Tang et al." ✓). Abstract: "(i) originality enforcement
  through a similarity measure based on abstract syntax trees (ASTs) against existing alphas, (ii) hypothesis-factor
  alignment via LLM-evaluated semantic consistency ..., (iii) complexity control via AST-based structural constraints,
  preventing over-engineered constructions."
- Source: https://arxiv.org/abs/2502.16789

## C13 — Chain-of-Alpha (arXiv 2508.06312): dual-chain LLM framework, withdrawn by arXiv. CONFIRMED
- abs page: v1 August 8, 2025; author Lang Cao; status: "This version has been removed by arXiv administrators as the
  submitter did not have the rights to agree to the license at the time of submission." Abstract: "dual-chain
  architecture, consisting of a Factor Generation Chain and a Factor Optimization Chain, which iteratively generate,
  evaluate, and refine candidate alpha factors ... leveraging backtest feedback"; "real-world A-share benchmarks."
- Source: https://arxiv.org/abs/2508.06312

## C14 — "Navigating the Alpha Jungle" (arXiv 2505.11122): LLM inside MCTS + frequent subtree avoidance. CONFIRMED
- abs page: v1 May 16, 2025; authors Yu Shi, Yitong Duan, Jian Li ("Shi, Duan, Li" ✓). Abstract: "leverages the LLM's
  instruction-following and reasoning capability to iteratively generate and refine symbolic alpha formulas within an
  MCTS-driven exploration"; "guidance of MCTS exploration by rich, quantitative feedback from financial backtesting";
  "a frequent subtree avoidance mechanism is introduced to enhance search diversity."
- Source: https://arxiv.org/abs/2505.11122

## C15 — RiskMiner (arXiv 2402.07080): reward-dense MDP + risk-seeking MCTS, no LLM. CONFIRMED
- abs page: v1 February 11, 2024; first author Tao Ren ("Ren et al." ✓). Abstract: alpha mining as "a reward-dense
  Markov Decision Process (MDP)" solved by "risk-seeking Monte Carlo Tree Search (MCTS)"; motivates by prior methods
  not considering "the correlation between alphas in the collection." No LLM component.
- Source: https://arxiv.org/abs/2402.07080

## C16 — FactorMiner (arXiv 2602.14670, Feb 16 2026): skills + experience memory, "Correlation Red Sea". CONFIRMED
- abs page: v1 February 16, 2026; first author Yanlong Wang ("Wang et al." ✓). Abstract verbatim: "FactorMiner combines
  a Modular Skill Architecture that encapsulates systematic financial evaluation into executable tools with a structured
  Experience Memory that distills historical mining trials into actionable insights"; "under the 'Correlation Red Sea'
  constraint"; "constructs a diverse library of high-quality factors."
- Source: https://arxiv.org/abs/2602.14670

## C17 — AlphaPROBE (arXiv 2602.11917, Feb 12 2026): factor DAG + Bayesian retriever, beats 8 baselines. CONFIRMED
- abs page: v1 February 12, 2026; first author Taian Guo ("Guo et al." ✓). Abstract: alpha mining as "the strategic
  navigation of a Directed Acyclic Graph" with "factors as nodes and evolutionary links as edges"; "Bayesian Factor
  Retriever" with "a posterior probability model"; DAG-aware generator producing "context-aware, nonredundant
  optimizations"; evaluated against 8 baselines on three Chinese stock market datasets.
- Source: https://arxiv.org/abs/2602.11917

## C18 — QuantEvolve (arXiv 2510.18569): quality-diversity + hypothesis-driven multi-agent, full strategies. CONFIRMED
- abs page: v1 October 21, 2025; authors Junhyeog Yun, Hyoun Jun Lee, Insu Jeon ✓; comments: oral at the 2nd Workshop
  on LLMs and Generative AI for Finance (AI4F) at ACM ICAIF 2025. Abstract: "combines quality-diversity optimization
  with hypothesis-driven strategy generation"; feature map "aligned with investor preferences, such as strategy type,
  risk profile, turnover, and return characteristics"; releases a dataset of evolved strategies.
- Minor nitpick: the paper's feature-map dimensions include turnover in addition to the file's "strategy type, risk,
  and return characteristics" — no objection.
- Source: https://arxiv.org/abs/2510.18569

## C19 — Survey arXiv 2503.21422 (March 2025): three-phase evolution ending in LLM-driven frontier. CONFIRMED
- abs page: v1 March 27, 2025; authors Bokai Cao, Saizhuo Wang, et al. ("Cao, Wang et al." ✓). Abstract traces the
  progression from human-crafted features through deep learning to LLMs "empowering autonomous agents to process
  unstructured data, generate alphas, and support self-iterative workflows."
- Source: https://arxiv.org/abs/2503.21422

## C20 — 101 Formulaic Alphas: SSRN Dec 2015 / arXiv Jan 2016 / Wilmott 2016; 0.6–6.4 day holding; 15.9% correlation; WorldQuant. CONFIRMED
- arXiv abs: v1 January 5, 2016; journal ref "Wilmott Magazine 2016(84) (2016) 72-80". SSRN abstract 2701346 posted
  December 9, 2015.
- PDF verbatim: "Their average holding period approximately ranges 0.6-6.4 days. The average pair-wise correlation of
  these alphas is low, 15.9%. The returns are strongly correlated with volatility, but have no significant dependence
  on turnover"; Section 2: "The alphas are proprietary to WorldQuant LLC and are used here with its express permission."
- Source: https://arxiv.org/abs/1601.00991 ; https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2701346

## C21 — Vocabulary of the 101 alphas; delay-0 list; example formulas; operator counts. WRONG (on the counts only)
- CONFIRMED parts (verified in extracted PDF text):
  - Footnote 11 verbatim: "Four of our 101 alphas in Appendix A, namely, the alphas numbered 42, 48, 53 and 54, are
    delay-0 alphas." Rest delay-1 ✓.
  - Alpha#101 = ((close - open) / ((high - low) + .001)) ✓ verbatim.
  - Alpha#3 = (-1 * correlation(rank(open), rank(volume), 10)) ✓ verbatim.
  - Input vocabulary open/high/low/close/volume/vwap/returns/adv{d} and operators rank, Ts_Rank, correlation, delta,
    sign, log, decay_linear, IndNeutralize ✓ (all present throughout Appendix A).
- WRONG parts (recomputed programmatically from the arXiv PDF, parsing Appendix A into the 101 formulas):
  - "decay_linear (appearing in 39 formulas)": decay_linear appears in 22 formulas (alphas 31, 39, 57, 58, 59, 63, 66,
    71, 72, 73, 76, 77, 82, 87, 88, 89, 91, 92, 93, 96, 97, 98), with 40 total occurrences inside formulas (many
    formulas use it twice; Alpha#91 three times) plus 1 occurrence in the A.1 operator definitions = 41 total.
    Neither 22 (formulas) nor 40/41 (occurrences) equals 39.
  - "IndNeutralize (17 formulas)": case-sensitive "IndNeutralize" appears in 16 formulas (58, 59, 63, 67, 69, 70, 76,
    79, 80, 82, 87, 89, 90, 91, 93, 97) with 17 occurrences (Alpha#67 uses it twice) — the "17" is an occurrence
    count, not a formula count. Counting the lowercase "indneutralize" (the paper states expressions are
    case-insensitive), alphas 48 and 100 also use it, giving 18 formulas / 21 in-formula occurrences.
  - Likely root cause: the researcher's "verified by direct text extraction" counted raw case-sensitive string
    occurrences with a different PDF extractor and mislabeled occurrences as formulas.
- Fix: e.g. "decay_linear (used in 22 of the 101 formulas) and IndNeutralize (16-18 formulas depending on case
  convention)". The qualitative point (both operators are core vocabulary) survives.
- Source: https://arxiv.org/abs/1601.00991 (Appendix A)

## C22 — AutoAlpha (arXiv 2002.08245): hierarchical evolution, root genes warm start, PCA-QD, replacement. CONFIRMED
- abs page: v1 February 9, 2020; authors Tianping Zhang, Yuanqi Li, Yifei Jin, Jian Li ✓. Abstract: hierarchical
  structure, "Quality Diversity search based on the Principal Component Analysis (PCA-QD)", "warm start method and the
  replacement method to prevent the premature convergence problem", Chinese stock market data.
- "Root genes" verified in the PDF body: "gene2 and gene3 are called root genes which are directly attached to their
  root operators"; warm start initializes the depth-2 population from an effective-gene pool ("We enumerate the alphas
  of depth 1 and select the effective ones to set up the gene pool. We use the warm start method and the gene pool to
  initialize the population of depth 2.").
- Source: https://arxiv.org/abs/2002.08245 ; https://arxiv.org/pdf/2002.08245

## C23 — AlphaEvolve (SIGMOD 2021, arXiv 2103.16196): evolved "novel alphas" between formulaic and ML classes. OVERSTATED (misquote)
- Confirmed: authors Can Cui, Wei Wang, Meihui Zhang, Gang Chen, Zhaojing Luo, Beng Chin Ooi; comments field
  "Accepted by SIGMOD 2021 Data Science and Engineering Track"; unrelated to DeepMind's 2025 AlphaEvolve; AutoML-style
  evolutionary search over "scalar, vector, or matrix" operands; new alpha class with strengths of both existing classes.
- Misquote: the file quotes the abstract as "experiments show AlphaEvolve can evolve initial alphas into novel ones with
  high Sharpe ratios and low correlations." The actual abstract sentence (verified verbatim in the PDF and on the abs
  page) is: "Experiments show that AlphaEvolve can evolve initial alphas into the new alphas with high returns and weak
  correlations." The words "Sharpe ratios" and "low correlations" do not appear in the abstract.
- Substance note: the paper's experiments DO report Sharpe ratios (e.g., best evolved alpha Sharpe 21.32 vs 4.11 for a
  domain-expert alpha, Tables 1-6) and low pairwise correlations, so the claim's content is defensible — but the
  quotation as given is fabricated and must be corrected or re-sourced to the experimental tables.
- Source: https://arxiv.org/abs/2103.16196 ; https://arxiv.org/pdf/2103.16196

## C24 — AlphaForge (arXiv 2406.18394, AAAI 2025): generative-predictive network + dynamic reweighting. CONFIRMED
- abs page: v1 June 26, 2024; first author Hao Shi ("Shi et al." ✓); comments: accepted by AAAI 2025. Abstract:
  "a generative-predictive neural network to generate factors"; combination model "incorporates the temporal performance
  of factors for selection and dynamically adjusts the weights."
- Source: https://arxiv.org/abs/2406.18394

## C25 — gplearn-style GP as the standard baseline; Lin et al. (2019) as first GP method; still refined (arXiv 2412.00896). OVERSTATED (evidence misattributed; substance true)
- Substance CONFIRMED from multiple primary sources:
  - AlphaForge (arXiv 2406.18394v3), Related Work, verbatim: "Early advancements, notably within the GPLearn package,
    (Lin et al. [2019a]) introduced time series operators, establishing the first genetic programming method for mining
    alpha factors."
  - AlphaGen paper: "[10] augmented the gplearn library with formulaic-alpha-specific time-series operators, upon which
    an alpha-mining framework is built", where [10] = Xiaoming Lin, Ye Chen, Ziyu Li, Kang He, 2019, Huatai Securities
    Research Center technical report.
  - "Navigating the Alpha Jungle" (2505.11122), Appendix B: "Early work like GPLearn (Lin et al. 2019) applies GP with a
    pre-defined set of time-series operators."
  - alphagen repo README: ships modified gplearn GP and a minimal DSO implementation as baselines.
  - arXiv 2412.00896 (v1, Dec 1 2024) confirmed: warm-start GP with structural constraints, "Analysis of 2020-2024
    Chinese stock market data."
- Misattribution: the file's evidence line attributes the "Early advancements ... GPLearn package (Lin et al., 2019a) ...
  first genetic programming method" quote to the warm-start GP paper (2412.00896). That paper (single version v1)
  never mentions GPLearn or that sentence; it cites "Lin & Chen, 2019a;b" only in passing. The quote is from
  AlphaForge (arXiv 2406.18394). The citation in the evidence must be corrected before REPORT.md cites it.
- Minor note: "Lin et al. (2019)" is a Huatai Securities technical report ("Stock Alpha Mining Based On Genetic
  Algorithm"), i.e., practitioner gray literature, not a peer-reviewed paper — worth stating in the prior-art entry.
- Source: https://arxiv.org/html/2406.18394v3 ; https://arxiv.org/pdf/2306.12964 ; https://arxiv.org/html/2412.00896v1 ;
  https://github.com/RL-MLDM/alphagen

## C26 — Allen & Karjalainen (JFE 51(2), 1999, 245–271): GP rules, no excess return over buy-and-hold after costs, 0.25% one-way. CONFIRMED
- PDF (full text) verbatim: "We use a genetic algorithm to learn technical trading rules for the S&P 500 index using
  daily prices from 1928 to 1995. After transaction costs, the rules do not earn consistent excess returns over a simple
  buy-and-hold strategy in the out-of-sample test periods. The rules are able to identify periods to be in the index when
  daily returns are positive and volatility is low..." ; "Initially, we use one-way transaction costs of 0.25%. We also
  investigate the robustness of the results with transaction costs of 0.1% or 0.5%." Journal ref "Journal of Financial
  Economics 51 (1999) 245-271" printed on the pages.
- Source: https://www.cs.montana.edu/courses/spring2007/536/materials/Lopez/genetic.pdf ;
  https://ideas.repec.org/a/eee/jfinec/v51y1999i2p245-271.html

## C27 — Neely, Weller & Dittmar (JFQA 32, 1997, 405–426): significant OOS excess returns ~1–7%/yr, six dollar exchange rates, 1981–1995. CONFIRMED
- Fed working paper 96-006 (the paper's WP version) abstract verbatim: "we find strong evidence of economically
  significant out-of-sample excess returns to those rules for each of six exchange rates, over the period 1981-1995."
- Table 1 mean annual excess returns by currency: $/DM 6.05%, $/¥ 2.34%, $/£ 2.28%, $/SF 1.42%, DM/¥ 4.10%, £/SF 1.02%
  — i.e., means span 1.02–6.05%/yr (median portfolio rules up to 7.11%), consistent with "roughly 1–7% per year".
- Journal citation verified via Neely-Weller 2011 Fed review reference list: JFQA 32, 405-426.
- Caveat (already flagged medium-confidence in the file): the exact phrase "one to seven percent" is a secondary-source
  gloss; primary mean range is 1.0-6.0%. Acceptable under "roughly".
- Source: https://files.stlouisfed.org/files/htdocs/wp/1996/96-006.pdf ;
  https://files.stlouisfed.org/files/htdocs/wp/2011/2011-001.pdf ;
  https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/is-technical-analysis-in-the-foreign-exchange-market-profitable-a-genetic-programming-approach/D959AD60856CECB9DB136AEFF6AD48FF

## C28 — Sullivan, Timmermann & White (JoF 54(5), 1999, 1647–1691): 7,846 rules, 100 years DJIA, OOS failure 1987–1996, futures 1984–1996. CONFIRMED
- PDF verbatim: "We consider a very large number ~7,846! of trading rules"; "apply the rules to 100 years of daily data
  on the Dow Jones Industrial Average"; "certain trading rules did indeed outperform the benchmark, even after adjustment
  is made for data-snooping" (in-sample, 1897-1986); "the superior performance of the best technical trading rule is not
  repeated in the out-of-sample experiment covering the 10-year period 1987-1996"; S&P 500 futures (Jan 1984 - Dec 1996):
  "Again there is no evidence that any trading rule outperforms over the sample period." Journal header: THE JOURNAL OF
  FINANCE VOL. LIV, NO. 5, OCTOBER 1999, first page 1647.
- Source: https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Sullivan_Timmermann_White.pdf

## C29 — Ready (Financial Management, 2002): slippage + understated costs; BLL success "spurious result of data snooping". CONFIRMED
- Published Financial Management Vol. 31, No. 3, Autumn 2002. Search-verified summaries (SSRN id 321946 / ideas.repec):
  Ready finds reported profits "may not have been achievable due to price slippage between when trading signals are
  measured and when trades could actually be executed"; the A&K 0.1%-cost case "appears too low"; and the comparison
  "lends support to the hypothesis that the apparent success (after transaction costs) of the Brock et al. (1992) moving
  average rules is a spurious result of data snooping." Matches the claim. (Primary full text paywalled; consistent
  across SSRN abstract, RePEc, ProQuest listings — file's medium confidence is appropriate.)
- Source: https://www.ssrn.com/abstract=321946 ; https://ideas.repec.org/a/fma/fmanag/ready02.html

## C30 — FunSearch (Nature, Dec 2023) and DeepMind AlphaEvolve (May 14, 2025). CONFIRMED
- FunSearch blog (December 14, 2023): published in Nature (DOI 10.1038/s41586-023-06924-6); cap sets: "This represents
  the largest increase in the size of cap sets in the past 20 years"; bin-packing heuristics outperforming established
  ones; "the first time a new discovery has been made for challenging open problems in science or mathematics using LLMs."
  (File's paraphrase "first discoveries in open problems in mathematical sciences using LLMs" is a fair rendering.)
- AlphaEvolve blog (May 14, 2025): "an algorithm to multiply 4x4 complex-valued matrices using 48 scalar multiplications";
  tested on over 50 open problems; "in 75% of cases, it rediscovered state-of-the-art solutions"; "in 20% of cases,
  AlphaEvolve improved the previously best known solutions."
- Source: https://deepmind.google/discover/blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/ ;
  https://deepmind.google/discover/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/

---

## Minor nitpicks (not objections)
1. C2/C3: the 2.97 Sharpe and the 6.54→1.22 decay series are pre-transaction-cost, equal-weighted figures; the paper
   itself shows 1.29 at 10 bps round-trip and 0.56 value-weighted. The Synthesis section quotes 2.97 without the
   pre-cost qualifier — recommend adding "pre-cost" there since REPORT.md will inherit the number.
2. C6: "AI4Finance Foundation" vs the abstract's "AI4Finance community" (the Foundation is the GitHub org). Harmless.
3. C18: the QuantEvolve feature map also includes turnover among its dimensions.
4. C25: Lin et al. 2019 is a broker (Huatai Securities) technical report, not peer-reviewed literature.
5. C27: primary mean-return range is 1.02–6.05%/yr; "1–7%" leans on the median-portfolio upper end (7.11%).
6. Synthesis line "Sharpe 2.97 for GPT-4, decaying from 6.54 in 2021Q4 to 1.22 by early 2024" mixes the full-sample
   Sharpe (2.97) with the subperiod series — fine as written, but keep the two series distinct if quoted in REPORT.md.

## Required fixes before "agreed"
- C9: drop or re-scope "deep-symbolic-regression baselines" (repo-only, not in the paper's experiments).
- C21: correct operator counts (decay_linear: 22 formulas / 41 total occurrences; IndNeutralize: 16 formulas
  case-sensitive, 18 case-insensitive, 17 is a case-sensitive occurrence count).
- C23: replace the abstract "quote" with the true sentence ("high returns and weak correlations") or cite the
  experimental tables for the Sharpe-ratio statement.
- C25: re-attribute the GPLearn/Lin-et-al. quote to AlphaForge (arXiv 2406.18394), not arXiv 2412.00896.
