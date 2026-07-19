---
status: draft round 0
topic: llm_in_trading
---

# Prior art: LLMs and automated alpha discovery

Scope: (1) LLM news/sentiment trading; (2) LLM-driven factor/alpha generation ("alpha factories"), swept on arXiv through Feb 2026; (3) pre-LLM automated signal search (formulaic alphas, genetic programming, symbolic regression) and its data-snooping critiques. Purpose: method-level prior-art entries for the factor DB, and an explicit record that "grammar/evolutionary search over signal expressions" is documented prior art at the METHOD level.

## Claims

C1. Lopez-Lira & Tang, "Can ChatGPT Forecast Stock Price Movements? Return Predictability and Large Language Models" (arXiv 2304.07619, first posted April 2023, v6 October 2025), show that GPT-4 scoring of news headlines predicts stock returns out-of-sample over October 2021 – May 2024, with roughly 90% portfolio-day hit rates for the (non-tradable) initial price reaction.
Evidence: Abstract (v6): "GPT-4 predicts immediate market movements with approximately 90% portfolio-day hit rates for the non-tradable initial reaction"; paper text: "The sample period begins in October 2021 and ends in May 2024."
Source: https://arxiv.org/abs/2304.07619
Confidence: high

C2. In the same paper, a long-short strategy on next-day drift returns (buy positive-GPT-4-score stocks, sell negative) delivers an annualized Sharpe ratio of 2.97, versus 1.66 for GPT-3.5, 1.26 for DistilBART-MNLI, and negative Sharpe ratios for most basic models (GPT-1, GPT-2, Llama2-7b), i.e., financial return prediction from text appears to be an emergent capability of larger models.
Evidence: "A long-short strategy based on next-day drift returns that buys stocks with positive GPT-4 scores and sells those with negative scores delivers an annualized Sharpe ratio of 2.97 over the sample period, compared with 1.66 for GPT-3.5, 1.26 for DistilBART-MNLI, and negative Sharpe ratios for most basic models." (extracted from the arXiv v6 PDF)
Source: https://arxiv.org/pdf/2304.07619
Confidence: high

C3. Lopez-Lira & Tang document rapid decay of the LLM-news edge as LLM adoption spread: the strategy's annualized Sharpe ratio falls from 6.54 in 2021Q4 to 3.68 in 2022, 2.33 in 2023, and 1.22 over January–May 2024.
Evidence: "its annualized Sharpe ratio drops from 6.54 in 2021Q4 to 3.68 in 2022, 2.33 in 2023, and to 1.22 over January-May 2024." (verbatim from the arXiv v6 PDF)
Source: https://arxiv.org/pdf/2304.07619
Confidence: high

C4. The practice of evaluating LLM trading signals only on post-knowledge-cutoff data to avoid lookahead bias and memorization is itself documented prior art (Lopez-Lira & Tang do this explicitly, citing Sarkar & Vafa 2024 and Lopez-Lira, Tang & Zhu 2025), so our project's post-cutoff provenance discipline is a documented method, not a novel contribution.
Evidence: Footnote in the paper: "Sarkar and Vafa (2024) and Lopez-Lira, Tang, and Zhu (2025) provide strong evidence that one must use a sample period after an LLM's knowledge cutoff date to avoid lookahead bias and memorization problems."
Source: https://arxiv.org/pdf/2304.07619
Confidence: high

C5. BloombergGPT (arXiv 2303.17564, March 2023) is a 50-billion-parameter LLM trained on a 363-billion-token Bloomberg financial corpus plus 345 billion general-purpose tokens, targeting financial NLP tasks (sentiment analysis, NER, question answering) — it is a domain LLM, not a published alpha-mining or trading-signal system.
Evidence: arXiv abstract/page: 50B parameters; "363 billion tokens from Bloomberg financial sources, augmented with 345 billion tokens from general datasets"; tasks "sentiment analysis and named entity recognition to question answering."
Source: https://arxiv.org/abs/2303.17564
Confidence: high

C6. FinGPT (arXiv 2306.06031, June 2023, AI4Finance Foundation) is an open-source, data-centric financial LLM framework positioned as the accessible alternative to BloombergGPT, with stated applications in robo-advising, algorithmic trading, and low-code financial development.
Evidence: Abstract: "a data-centric approach, providing researchers and practitioners with accessible and transparent resources"; applications listed as robo-advising, algorithmic trading, low-code development; presented at the FinLLM Symposium at IJCAI 2023.
Source: https://arxiv.org/abs/2306.06031
Confidence: high

C7. Alpha-GPT (Wang, Yuan, Zhou, Ni, Shum, Guo; arXiv 2308.00016, July 2023) established the "LLM as interactive alpha-mining copilot" paradigm: prompt-engineered LLMs translate quant researchers' natural-language ideas into formulaic alphas, explicitly positioned against both hand-crafting and "algorithmic factor mining (e.g., search with genetic programming)."
Evidence: Abstract (verbatim): "Traditional alpha mining methods, either hand-crafted factor synthesizing or algorithmic factor mining (e.g., search with genetic programming), have inherent limitations... we propose a new alpha mining paradigm by introducing human-AI interaction... and develop Alpha-GPT, a new interactive alpha mining system framework."
Source: https://arxiv.org/abs/2308.00016
Confidence: high

C8. Alpha-GPT 2.0 (Yuan, Wang, Guo; arXiv 2402.09746, February 2024) extends this to a human-in-the-loop multi-agent system spanning the full quant pipeline — alpha mining, alpha modeling (combination), and alpha analysis — with specialized LLM agents at each stage.
Evidence: Paper describes "a Multi-agent architecture with specialized agents... such as alpha mining, alpha modeling, and alpha analysis," with human researchers injecting insights at every stage (per arXiv abstract and secondary summaries).
Source: https://arxiv.org/abs/2402.09746
Confidence: high

C9. AlphaGen ("Generating Synergistic Formulaic Alpha Collections via Reinforcement Learning," Yu, Xue, Ao et al., KDD 2023 ADS track; arXiv 2306.12964) mines formulaic alphas with RL where the reward is the performance of the downstream combination model — optimizing a synergistic SET of alphas rather than individual expressions — and beats a gplearn genetic-programming baseline and deep-symbolic-regression baselines on CSI300/CSI500 Chinese A-share data.
Evidence: Paper/abstract: RL "prioritizes mining a synergistic set of alphas"; "the downstream combination model's performance becomes the reward signal"; experiments on CSI300 and CSI500; baselines include "gplearn framework" GP with IC fitness, PPO single-alpha RL, XGBoost, LightGBM, MLP.
Source: https://arxiv.org/abs/2306.12964 ; https://github.com/RL-MLDM/alphagen/
Confidence: high

C10. The signal FORMS produced by AlphaGen-style systems are short algebraic expressions over daily OHLCV+vwap bars using a small operator grammar — cross-section operators (Abs, Log, +, −, ×, ÷, Greater, Less) and time-series operators (Ref, Mean, Med, Sum, Std, Var, Max, Min, Mad, Delta, WMA, EMA, Cov, Corr) — e.g., generated alphas like Var(Greater(Greater(Var(low,50),high),open),30) and (Mad(high,50)+0.5)×vwap/close.
Evidence: Operator/feature tables and the 10-alpha case study in the paper's HTML version list exactly these features (open, close, high, low, volume, vwap) and operators, with the quoted example expressions.
Source: https://arxiv.org/html/2306.12964
Confidence: high

C11. QuantAgent (Wang, Yuan, Ni, Guo; arXiv 2402.03755, February 2024) is an LLM agent for mining trading signals via a two-layer self-improving loop — an inner loop refining outputs against a knowledge base and an outer loop testing outputs in the real world to grow the knowledge base — with a claim of provably efficient convergence toward optimal behavior.
Evidence: Abstract (verbatim): "In the inner loop, the agent refines its responses by drawing from its knowledge base, while in the outer loop, these responses are tested in real-world scenarios to automatically enhance the knowledge base... we instantiate this framework through an autonomous agent for mining trading signals named QuantAgent."
Source: https://arxiv.org/abs/2402.03755
Confidence: high

C12. AlphaAgent (Tang et al.; arXiv 2502.16789, February 2025) targets alpha decay explicitly, generating factors with three regularizers: originality enforcement via abstract-syntax-tree (AST) similarity against existing factors, hypothesis-factor semantic alignment judged by an LLM, and AST-based complexity control to limit overfitting — i.e., automated "novelty checking" of generated alphas is itself published prior art.
Evidence: Paper describes "originality enforcement through a similarity measure based on abstract syntax trees," "hypothesis-factor alignment via LLM evaluation," and "complexity control" preventing "over-engineered constructions that are prone to overfitting."
Source: https://arxiv.org/abs/2502.16789
Confidence: high

C13. Chain-of-Alpha (Lang Cao; arXiv 2508.06312, August 2025; since withdrawn by arXiv for licensing/submission-rights issues) is a fully automated dual-chain LLM framework — a Factor Generation Chain producing candidate formulaic alphas and a Factor Optimization Chain refining them using backtest feedback — evaluated on Chinese A-share benchmarks.
Evidence: Abstract/overview: "dual-chain architecture, consisting of a Factor Generation Chain and a Factor Optimization Chain, which iteratively generate, evaluate, and refine candidate alpha factors... leveraging backtest feedback"; arXiv page notes the paper was withdrawn by administrators.
Source: https://arxiv.org/abs/2508.06312
Confidence: high

C14. "Navigating the Alpha Jungle" (Shi, Duan, Li; arXiv 2505.11122, May 2025) embeds an LLM inside Monte Carlo Tree Search: the LLM iteratively generates and refines symbolic alpha formulas within MCTS-driven exploration guided by quantitative backtest feedback, with a "frequent subtree avoidance" mechanism to force diversity.
Evidence: Abstract: "leverages the LLM's instruction-following and reasoning capability to iteratively generate and refine symbolic alpha formulas within an MCTS-driven exploration," plus "a frequent subtree avoidance mechanism" for diversity.
Source: https://arxiv.org/abs/2505.11122
Confidence: high

C15. Pure-search variants without LLMs continued in parallel: RiskMiner (Ren et al.; arXiv 2402.07080, February 2024) formulates formulaic alpha discovery as a reward-dense MDP solved by risk-seeking Monte Carlo Tree Search, accounting for correlations within the mined alpha collection.
Evidence: Abstract: alpha mining formulated as "a reward-dense Markov Decision Process (MDP) and solves the MDP by the risk-seeking Monte Carlo Tree Search (MCTS)."
Source: https://arxiv.org/abs/2402.07080
Confidence: high

C16. By February 2026 the frontier is self-evolving agent frameworks: FactorMiner (Wang et al.; arXiv 2602.14670, Feb 16 2026) couples a modular skill architecture with an experience memory distilled from past mining trials, explicitly targeting the "Correlation Red Sea" problem (new factors being redundant with existing ones) while producing "a diverse library of high-quality factors."
Evidence: Abstract: "FactorMiner combines a Modular Skill Architecture that encapsulates systematic financial evaluation into executable tools with a structured Experience Memory that distills historical mining trials into actionable insights."
Source: https://arxiv.org/abs/2602.14670
Confidence: high

C17. AlphaPROBE (Guo et al.; arXiv 2602.11917, Feb 12 2026) models the factor-discovery process as a directed acyclic graph of factors with evolutionary relationships as edges, using a Bayesian retriever to pick seed factors and a DAG-aware generator for non-redundant refinements, beating eight baselines on Chinese stock data.
Evidence: Abstract: reformulates alpha mining "as navigating a directed acyclic graph"; "Bayesian Factor Retriever" balancing "exploitation and exploration through a posterior probability model"; tested on Chinese datasets against eight baselines.
Source: https://arxiv.org/abs/2602.11917
Confidence: high

C18. QuantEvolve (Yun, Lee, Jeon; arXiv 2510.18569, October 2025; oral at an ACM ICAIF 2025 workshop) applies quality-diversity evolutionary search with a hypothesis-driven multi-agent LLM system to evolve entire trading strategies (not just factor formulas), maintaining a feature map over strategy type, risk, and return characteristics.
Evidence: Abstract: "combine[s] quality-diversity optimization with hypothesis-driven strategy generation," maintaining diverse strategies via a feature map; released a dataset of evolved strategies.
Source: https://arxiv.org/abs/2510.18569
Confidence: high

C19. A March 2025 survey ("From Deep Learning to LLMs: A Survey of AI in Quantitative Investment," Cao, Wang et al.; arXiv 2503.21422) codifies LLM-driven alpha generation as an established research phase — tracing quant AI from hand-crafted features through deep learning to an "LLM-driven frontier" of agents that generate alpha signals in self-iterative workflows — confirming the method space is well mapped, not exotic.
Evidence: The survey "traces the evolution of AI in quant finance" through three phases ending in LLM agents that "handle unstructured data, generate alpha signals, and support self-iterative workflows," using alpha strategy generation as its primary case study.
Source: https://arxiv.org/abs/2503.21422
Confidence: high

C20. Kakushadze's "101 Formulaic Alphas" (SSRN Dec 2015; arXiv 1601.00991, Jan 2016; Wilmott 2016) published explicit formulas for 101 real-life trading alphas proprietary to WorldQuant LLC (used with express permission), with average holding periods of roughly 0.6–6.4 days, average pairwise correlation 15.9%, and returns strongly correlated with volatility but not turnover.
Evidence: Abstract: "explicit formulas - that are also computer code - for 101 real-life quantitative trading alphas... average holding period approximately ranges 0.6-6.4 days... average pair-wise correlation of these alphas is low, 15.9%"; paper Section 2: "The alphas are proprietary to WorldQuant LLC and are used here with its express permission." (verified in the PDF)
Source: https://arxiv.org/abs/1601.00991
Confidence: high

C21. The 101 alphas define the canonical signal-form vocabulary for daily cross-sectional price-volume alphas: 4 of 101 are delay-0 (numbers 42, 48, 53, 54) and the rest delay-1; formulas combine rank, Ts_Rank, correlation, delta, sign, log, decay_linear (appearing in 39 formulas) and IndNeutralize (17 formulas) over open/high/low/close/volume/vwap/returns/adv{d} — e.g., Alpha#101 = ((close − open) / ((high − low) + .001)) and Alpha#3 = (−1 × correlation(rank(open), rank(volume), 10)).
Evidence: Paper footnote 11: "Four of our 101 alphas in Appendix A, namely, the alphas numbered 42, 48, 53 and 54, are delay-0 alphas"; Appendix A formulas as quoted; operator counts verified by direct text extraction from the arXiv PDF (decay_linear 39 occurrences, IndNeutralize 17).
Source: https://arxiv.org/abs/1601.00991
Confidence: high

C22. AutoAlpha (Zhang, Li, Jin, Li; arXiv 2002.08245, February 2020) is a pre-LLM hierarchical evolutionary algorithm for mining formulaic alphas, using warm-start initialization from "root genes," PCA-based Quality-Diversity search (PCA-QD) to push exploration away from already-mined regions, and replacement to avoid premature convergence, evaluated on Chinese stock data.
Evidence: Abstract: "a hierarchical structure to quickly locate the promising part of space for search," "Quality Diversity search based on the Principal Component Analysis (PCA-QD)," and "warm start method and the replacement method to prevent the premature convergence problem."
Source: https://arxiv.org/abs/2002.08245
Confidence: high

C23. AlphaEvolve (Cui, Wang, Zhang et al.; SIGMOD 2021; arXiv 2103.16196) — unrelated to DeepMind's later system of the same name — used AutoML-style evolutionary search over scalar/vector/matrix operators to evolve "novel alphas" that sit between formulaic and machine-learning alphas, reporting evolved alphas "with high Sharpe ratios and low correlations" to existing sets.
Evidence: Abstract: "a new class of alphas... which possess the strengths of these two existing classes"; "AlphaEvolve... searches from a large space of operators operating on scalar, vector, or matrix operands"; "experiments show AlphaEvolve can evolve initial alphas into novel ones with high Sharpe ratios and low correlations."
Source: https://arxiv.org/abs/2103.16196 ; https://dl.acm.org/doi/10.1145/3448016.3457324
Confidence: high

C24. AlphaForge (Shi et al.; arXiv 2406.18394; AAAI 2025) mines formulaic alphas with a generative-predictive neural network (deep-learning search over formula space) and then dynamically re-weights the mined factors over time based on recent performance, rather than using fixed combination weights.
Evidence: Abstract: "a two-stage formulaic alpha generating framework" with "a generative-predictive neural network to generate factors"; the combination model "incorporates the temporal performance of factors for selection and dynamically adjusts the weights."
Source: https://arxiv.org/abs/2406.18394
Confidence: high

C25. gplearn-style genetic programming (symbolic regression evolving expression trees by mutation/crossover, extended with time-series operators) is the standard practitioner and academic baseline for formulaic alpha mining — attributed in the literature to Lin et al. (2019) as the first GP method for alpha factors — and is still being refined (e.g., warm-start GP with structural constraints on 2020–2024 Chinese A-share data, arXiv 2412.00896, Dec 2024).
Evidence: Warm-start GP paper: "Early advancements, notably within the GPLearn package (Lin et al., 2019a), introduced time series operators, establishing the first genetic programming method for mining alpha factors"; the alphagen repo ships "modified versions of Genetic Programming (gplearn) and Deep Symbolic Regression (DSO) baselines."
Source: https://arxiv.org/abs/2412.00896 ; https://github.com/RL-MLDM/alphagen/
Confidence: high

C26. Allen & Karjalainen ("Using genetic algorithms to find technical trading rules," Journal of Financial Economics 51(2), 1999, 245–271) used genetic programming to evolve ex-ante technical trading rules for the S&P 500 and found no evidence the rules earned excess returns over buy-and-hold after transaction costs (baseline one-way cost 0.25%), though the rules showed some predictive ability.
Evidence: JFE 51(2) 245-271; summaries: GP-evolved rules for the S&P 500 index show "no evidence that the returns to these rules were higher than buy-and-hold returns but some evidence that the rules had predictive ability"; one-way transaction costs of 0.25% used.
Source: https://ideas.repec.org/a/eee/jfinec/v51y1999i2p245-271.html ; https://www.cs.montana.edu/courses/spring2007/536/materials/Lopez/genetic.pdf
Confidence: high

C27. Neely, Weller & Dittmar ("Is Technical Analysis in the Foreign Exchange Market Profitable? A Genetic Programming Approach," JFQA 32, 1997, 405–426) found economically significant out-of-sample excess returns (roughly 1–7% per year) to GP-evolved trading rules for each of six dollar exchange rates over 1981–1995 — the canonical positive result for evolutionary rule search, in FX rather than equities.
Evidence: "strong evidence of economically significant out-of-sample excess returns to those rules for each of six exchange rates over the period 1981-1995... out-of-sample annual excess returns in the one to seven percent range" (per journal listing and Fed working-paper summaries).
Source: https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/is-technical-analysis-in-the-foreign-exchange-market-profitable-a-genetic-programming-approach/D959AD60856CECB9DB136AEFF6AD48FF
Confidence: medium (journal page and secondary Fed sources agree on the 1–7% range, but I could not fetch the paywalled primary abstract text directly)

C28. Sullivan, Timmermann & White ("Data-Snooping, Technical Trading Rule Performance, and the Bootstrap," Journal of Finance 54(5), 1999, 1647–1691) applied White's Reality Check bootstrap to a universe of 7,846 technical trading rules on 100 years of DJIA data and found that while Brock-Lakonishok-LeBaron's best rule survives an in-sample snooping adjustment, its "superior performance ... is not repeated in the out-of-sample experiment covering the 10-year period 1987–1996," and no rule outperforms on S&P 500 futures (1984–1996).
Evidence: Abstract and text verified from the PDF: "We consider a very large number (7,846) of trading rules"; "the superior performance of the best technical trading rule is not repeated in the out-of-sample experiment covering the 10-year period 1987–1996"; "Again there is no evidence that any trading rule outperforms over the sample period" (S&P 500 futures).
Source: https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Sullivan_Timmermann_White.pdf
Confidence: high

C29. Ready ("Profits from Technical Trading Rules," Financial Management, 2002) re-examined Allen & Karjalainen's GP rules and the BLL moving-average rules, arguing reported profits were likely unachievable due to price slippage between signal measurement and execution and understated transaction costs, and concluding that the apparent after-cost success of the BLL rules "is a spurious result of data snooping."
Evidence: Paper summaries: Ready "found that profits reported in these studies may not have been achievable due to price slippage between when trading signals are measured and when trades could actually be executed," and his comparison "lends support to the hypothesis that the apparent success (after transaction costs) of the Brock et al. (1992) moving average rules is a spurious result of data snooping."
Source: https://ideas.repec.org/a/fma/fmanag/ready02.html ; https://www.ssrn.com/abstract=64168
Confidence: medium (consistent secondary summaries; SSRN/primary full text not fetchable)

C30. DeepMind's FunSearch (published in Nature, December 2023) and AlphaEvolve (announced May 14, 2025) are existence proofs that an LLM-proposer + automated-evaluator evolutionary loop can exceed the known state of the art in domains with exact evaluators: FunSearch found new cap-set constructions ("the largest increase in the size of cap sets in the past 20 years") and better bin-packing heuristics, and AlphaEvolve found a 4x4 complex-matrix multiplication algorithm using 48 scalar multiplications, improving on best-known solutions in ~20% of 50+ open math problems.
Evidence: DeepMind: FunSearch made "the first discoveries in open problems in mathematical sciences using LLMs," "the largest increase in the size of cap sets in the past 20 years"; AlphaEvolve "discovered an algorithm for multiplying 4x4 complex-valued matrices using 48 scalar multiplications" and "improved upon previously best-known solutions in about 20%" of over 50 open problems.
Source: https://deepmind.google/discover/blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/ ; https://deepmind.google/discover/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/
Confidence: high

## Synthesis

The central fact this sweep establishes: **automated search over formulaic signal expressions is saturated, documented prior art at the method level, continuously from 1997 through February 2026.** The lineage runs: GP-evolved trading rules (Neely-Weller-Dittmar 1997 in FX; Allen & Karjalainen 1999 in equities) → published formulaic-alpha grammars (Kakushadze/WorldQuant 2015) → gplearn-style symbolic regression with time-series operators (Lin et al. 2019) → hierarchical/quality-diversity evolution (AutoAlpha 2020; AlphaEvolve-SIGMOD 2021) → RL and MCTS over expression grammars (AlphaGen KDD 2023; RiskMiner 2024) → LLM-in-the-loop variants (Alpha-GPT 2023; QuantAgent, Alpha-GPT 2.0, 2024; AlphaAgent, LLM-MCTS, Chain-of-Alpha 2025; QuantEvolve 2025; FactorMiner and AlphaPROBE, Feb 2026). Therefore our planned mechanism — grammar/evolutionary search over signal expressions, with or without an LLM proposer — is **T1 at best at the method level** under the frozen novelty scale. Any novelty claim must attach to a specific surviving SIGNAL, never to the search machinery. Even sub-components we might have thought distinctive are published: AST-similarity originality screening (AlphaAgent), diversity forcing (frequent-subtree avoidance; PCA-QD; quality-diversity maps), experience memory (FactorMiner), and backtest-feedback optimization loops (Chain-of-Alpha).

For later novelty checks, the signal forms these systems emit are highly stereotyped: short algebraic expressions over daily OHLCV/vwap/adv bars using rank, ts_rank, correlation, delta, decay_linear, std/var, min/max, industry neutralization; holding periods of days (101-alphas average 0.6–6.4 days); mostly cross-sectional mean-reversion and momentum composites. A candidate expressible in the 101-alphas/AlphaGen operator grammar over price-volume inputs should be presumed crowded (T0/T1) unless it uses a data source or structural mechanism outside that vocabulary. Note also that nearly all LLM-alpha-factory papers evaluate on Chinese A-shares with IC/RankIC metrics — a candidate's asset class and evaluation regime do not confer novelty by themselves.

On the LLM-sentiment side, Lopez-Lira & Tang is decisive prior art for "LLM reads news, trade the score" (Sharpe 2.97 for GPT-4, decaying from 6.54 in 2021Q4 to 1.22 by early 2024), and their decay curve is a warning that even genuine LLM edges are arbitraged within quarters. BloombergGPT and FinGPT are domain-LLM infrastructure, not signals.

Two project-level lessons. First, the pre-LLM GP literature already ran our full epistemic arc: early positive results (NWD 1997), equity-market failure after costs (Allen & Karjalainen 1999), then data-snooping demolition (Sullivan-Timmermann-White 1999 — best of 7,846 rules fails out-of-sample; Ready 2002). Our DSR/Newey-West gates are the modern descendants of Reality Check, and prior art predicts most mined candidates will die there. Second, FunSearch/AlphaEvolve show LLM+evaluator loops CAN exceed training corpora — but only against exact evaluators; whether a noisy, adversarial market evaluator permits the same is precisely our open question, and it remains open because none of the alpha-factory papers above attempts a pre-registered novelty audit of what they mine. That audit — not the mining method — is where this project can differ.
