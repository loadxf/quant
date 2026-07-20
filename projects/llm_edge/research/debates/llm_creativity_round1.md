# Adversarial audit — round 1: prior_art/llm_creativity.md

Reviewer: adversarial verifier (final reviewer, recovery path)
Date: 2026-07-20
Target: `research/prior_art/llm_creativity.md` (25 claims, status: draft round 0)

Method: every load-bearing number and every claim about what a named system/paper did
was independently re-fetched this session from a primary source (paper PDF/HTML, publisher
page, or authors' own release). FunSearch figures were extracted from the Nature accepted-version
PDF via pypdf (not trusting the researcher's quotes). SSRN was not needed; abstracts surfaced
via publisher pages and web search.

Bottom line: **25/25 checked. All CONFIRMED.** No WRONG or OVERSTATED load-bearing findings.
Three minor quote-fidelity nitpicks (C1, C3, C24) where quotation marks wrapped a faithful
paraphrase rather than the source's verbatim wording; C3 and C24 tightened for precision (see
target file's revision log). No number, effect size, percentage, year, or attribution was wrong.

---

## Per-claim verdicts

**C1 — FunSearch = LLM proposer + automated evaluator + programs DB; evaluator guards against
hallucinations.** CONFIRMED. DeepMind blog verbatim: pairs "a pre-trained LLM … with an automated
'evaluator', which guards against hallucinations and incorrect ideas." Nitpick: the sub-quote
"searches for programs that describe how to solve a problem, rather than what the solution is" is a
paraphrase — blog actually says "it outputs programs that reveal how its solutions are constructed,
rather than just what the solutions are"; paper says "FunSearch searches for programs generating
those [constructions]." Meaning faithful; not load-bearing.
URL: https://deepmind.google/blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/

**C2 — Cap set of size 512 in n=8, beating best-known 496; returns a program that generates it.**
CONFIRMED from Nature PDF (text-extracted this session). Table (Fig 4a): "Best known 9 20 45 112
236 496 / FunSearch 9 20 45 112 236 512". Verbatim: "we do not just discover the set of 512
8-dimensional vectors in itself, but a program that generates it." Also `def build_512_cap()`
"Returns a cap set of size 512 in `n=8` dimensions."
URL: https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/Mathematical-discoveries-from-program-search-with-large-language-models.pdf

**C3 — Capacity lower bound 2.2180 (Tyrrell 2022) → 2.2202 via A(24,17); upper bound C ≤ 2.756;
largest improvement in ~20 years.** CONFIRMED. Paper capacity table verbatim: "2.2180 I(11,7)
(Tyrrell, 2022) / 2.2184 I(12,7) FunSearch / 2.2194 I(15,10) FunSearch / 2.2202 A(24,17)
FunSearch"; "result of [32] established an upper bound of C ≤ 2.756"; "this is the largest
improvement to the lower bound in the last 20 years"; abstract "the largest improvement in 20 years
to the asymptotic lower bound." Nitpick (fixed): the draft's "Author text" quote was the *blog's*
phrasing about cap-set *size* ("largest increase in the size of cap sets in the past 20 years"),
attached to a claim about the *capacity lower bound*; retargeted to the paper's actual lower-bound
sentence. Also removed unsupported word "breakthrough" before "result of [32]."
URL: same Nature PDF as C2.

**C4 — Bin-packing excess-bins fractions: OR1 FF 6.42% / BF 5.81% / FunSearch 5.30%; Weibull 100k
FF 4.00% / BF 3.79% / FunSearch 0.03%.** CONFIRMED exactly. Table 1 verbatim: "First Fit 6.42%
6.45% 5.74% 5.23% 4.23% 4.20% 4.00% / Best Fit 5.81% 6.06% 5.37% 4.94% 3.98% 3.90% 3.79% /
FunSearch 5.30% 4.19% 3.11% 2.47% 0.68% 0.32% 0.03%." Narrative confirms "0.03% off the lower bound
… for 100 000 items."
URL: same Nature PDF as C2.

**C5 — AlphaEvolve: 4×4 complex-valued matrices in 48 scalar mults, beating Strassen 1969 (49).**
CONFIRMED. Blog verbatim: "found an algorithm to multiply 4x4 complex-valued matrices using 48
scalar multiplications, improving upon Strassen's 1969 algorithm that was previously known as the
best in this setting." "49" is standard (Strassen 2×2→7 recursed to 4×4 = 7²=49); blog does not
print "49" but the arithmetic is correct. Complex-valued / not-a-new-ring-bound / no-exponent-change
nuance is correctly stated and appropriately hedged.
URL: https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/

**C6 — 50+ open math problems: ~75% rediscovered SOTA, ~20% improved.** CONFIRMED. Blog: "over 50
open problems"; "In roughly 75% of cases, it rediscovered state-of-the-art solutions … And in 20%
of cases, AlphaEvolve improved the previously best known solutions." Same URL as C5.

**C7 — Borg heuristic recovers ~0.7% of Google's worldwide compute (>1 yr in prod); matmul kernel
23% faster → ~1% Gemini training reduction.** CONFIRMED verbatim: "now in production for over a
year, continuously recovers, on average, 0.7% of Google's worldwide compute resources"; "sped up
this vital kernel in Gemini's architecture by 23%, leading to a 1% reduction in Gemini's training
time." Same URL as C5.

**C8 — AlphaDev (Mankowitz et al., Nature 2023): up to 70% faster short sequences, ~1.7% faster
>250k elements; merged into LLVM libc++, first change in over a decade.** CONFIRMED. Blog verbatim:
"up to 70% faster for shorter sequences"; "about 1.7% faster for sequences exceeding 250,000
elements"; "the first change to this part of the sorting library in over a decade and the first time
an algorithm designed through reinforcement learning has been added to this library." AlphaZero-style
single-player "assembly game" confirmed.
URL: https://deepmind.google/blog/alphadev-discovers-faster-sorting-algorithms/

**C9 — Google AI co-scientist: Gemini multi-agent, tournament/Elo evolution + test-time compute;
validated in 3 biomedical areas; AML drug-repurposing candidates validated in vitro.** CONFIRMED.
Abstract verbatim: "multi-agent AI system built on Gemini … a tournament evolution process for
self-improving hypotheses generation"; "validation in three biomedical applications: drug
repurposing, novel target discovery, and explaining mechanisms of anti-microbial resistance"; AML
candidates "validated through in vitro experiments."
URL: https://arxiv.org/abs/2502.18864

**C10 — Sakana AI-Scientist-v2 paper passed an ICLR 2025 workshop (avg 6.33), heavily caveated:
3 submitted / 1 accepted, ~60–70% acceptance, none met internal bar, citation errors, withdrawn.**
CONFIRMED. Accepted paper "Compositional Regularization: Unexpected Obstacles in Enhancing Neural
Network Generalization," scores 6/7/6 (avg 6.33). "acceptance rates in the 60-70% range." "none of
the 3 papers passed our internal bar for what we believe would qualify as an accepted ICLR
conference track paper." "we would withdraw them before they were actually published."
URL: https://sakana.ai/ai-scientist-first-publication/

**C11 — Beel, Kan & Baumgart (2025) audit: ~42% of experiments failed due to coding errors; poor
novelty assessment (micro-batching for SGD flagged as novel); "superficially automates" research.**
CONFIRMED. Authors: Joeran Beel, Min-Yen Kan, Moritz Baumgart. Abstract: "42% of experiments failed
due to coding errors"; "misclassifying established concepts (e.g., micro-batching for stochastic
gradient descent) as novel." Paper text confirms it "superficially automates the research process
but fails to perform deep literature reviews, robust experiment validation, or quality manuscript
production."
URL: https://arxiv.org/abs/2502.14297 (full text: https://arxiv.org/html/2502.14297v1)

**C12 — Bender, Gebru et al. (FAccT 2021) "stochastic parrot" — form without meaning.** CONFIRMED
verbatim: an LM is "a system for haphazardly stitching together sequences of linguistic forms it has
observed in its vast training data, according to probabilistic information about how they combine,
but without any reference to meaning: a stochastic parrot."
URL: https://dl.acm.org/doi/10.1145/3442188.3445922 (PDF: https://s10251.pcdn.co/pdf/2021-bender-parrots.pdf)

**C13 — Kambhampati: "universal approximate retrieval"; GPT-4 ~30% Blocksworld; collapses under
obfuscation.** CONFIRMED verbatim from HTML: "What LLMs are good at is a form of universal
approximate retrieval"; "GPT4 reaching 30% empirical accuracy in the Blocks World"; "GPT4's
empirical performance plummeted precipitously, despite the fact that none of the standard off-the-
shelf AI planners have any trouble with such obfuscation."
URL: https://arxiv.org/html/2403.04121v2

**C14 — Self-verification worsens performance; LLM-Modulo pairs generation with sound external
verifier.** CONFIRMED verbatim: "With 'self-verification' performance actually worsens. This is
because LLMs hallucinate both false positives and false negatives while verifying the solutions they
generate"; "Let an external model-based plan verifier … certify the correctness of the final
solution … generate-test-critique framework with guarantees." Same URL as C13.

**C15 — Creativity Index (Lu et al. 2024): human authors 66.2% higher than LLMs on average; 115.3%
for speeches; DJ-Search.** CONFIRMED. Abstract: "the Creativity Index of professional human authors
is on average 66.2% higher than that of LLMs." Full text: "115.3% higher in speech drafting."
DJ-Search: "a novel dynamic programming algorithm that can search verbatim and near-verbatim matches
… against the web."
URL: https://arxiv.org/abs/2410.04265 (full text: https://arxiv.org/html/2410.04265v1)

**C16 — RLHF lowers Creativity Index ~30.1% verbatim (8.9% semantic).** CONFIRMED. Paper uses the
word **"RLHF"** (not merely "alignment"): "the Creativity Index of LLMs reduces by an average of
30.1% after RLHF" (verbatim); "decreases by an average of 8.9% after RLHF" (semantic). Same URL as
C15. (My prior concern that the paper might only say "alignment" was checked and rejected.)

**C17 — Kirk et al. (ICLR 2024): RLHF significantly reduces output diversity vs SFT; generalisation-
diversity tradeoff.** CONFIRMED. Abstract: "RLHF significantly reduces output diversity compared to
SFT across a variety of measures … implying a tradeoff … between generalisation and diversity";
"RLHF generalises better than SFT to new inputs, particularly as the distribution shift … becomes
larger."
URL: https://arxiv.org/abs/2310.06452

**C18 — Padmakumar & He (ICLR 2024): co-writing with InstructGPT (not GPT-3) significantly reduces
content diversity; effect mainly from InstructGPT contributing less diverse text.** CONFIRMED.
Abstract: "writing with InstructGPT (but not the GPT3) results in a statistically significant
reduction in diversity … increases the similarity between the writings of different authors …
mainly attributable to InstructGPT contributing less diverse text to co-written essays."
URL: https://arxiv.org/abs/2309.05196

**C19 — Si, Yang & Hashimoto (2024): 100+-researcher blind study (49 wrote ideas); LLM ideas judged
more novel (p<0.05), slightly weaker on feasibility; flags self-eval failures + lack of diversity.**
CONFIRMED. 49 expert idea-writers, 79 blind reviewers (100+ total). "LLM-generated ideas are judged
as more novel (p < 0.05) than human expert ideas" while "slightly weaker on feasibility"; open
problems "failures of LLM self-evaluation and their lack of diversity in generation."
URL: https://arxiv.org/abs/2409.04109

**C20 — Follow-up "Ideation-Execution Gap" (2025): ~103 hrs/idea; after execution LLM-idea scores
drop far more than human across all metrics (p<0.05); rankings flip.** CONFIRMED verbatim. "Our
execution participants spend an average of 103 hours executing the assigned idea"; "the scores of
the LLM-generated ideas decrease significantly more than expert-written ideas on all evaluation
metrics (novelty, excitement, effectiveness, and overall; p<0.05)"; "for many metrics there is a
flip in rankings where human ideas score higher than LLM ideas." N=43 executed (19 human, 24 LLM).
URL: https://arxiv.org/abs/2506.20803 (full text: https://arxiv.org/html/2506.20803v1)

**C21 — Doshi & Hauser (Science Advances 2024): AI ideas raise individual creativity (esp. less-
creative writers) but make stories more similar; collective-diversity social dilemma.** CONFIRMED.
"Access to generative AI ideas causes stories to be evaluated as more creative … especially among
less creative writers"; "generative AI–enabled stories are more similar to each other than stories
by humans alone."
URL: https://www.science.org/doi/10.1126/sciadv.adn5290

**C22 — Anderson, Shah & Kreminski (C&C 2024), 36-participant study: ChatGPT homogenises ideas at
group level; more/detailed ideas but less ownership.** CONFIRMED (PDF text-extracted this session).
"36-participant comparative user study" (3 excluded → 33 analyzed). "different users tended to
produce less semantically distinct ideas with ChatGPT"; "users of ChatGPT produce a more homogenous
set of ideas at the group level"; RQ3 "Do ChatGPT users feel more or less responsible … (A: less
responsible)"; "generated a greater number of more detailed ideas, but felt less [responsible]."
URL: https://mkremins.github.io/publications/Homogenization_C&C2024.pdf

**C23 — Boden taxonomy: combinational / exploratory / transformational; transformational alters the
conceptual space.** CONFIRMED. Boden's three types are combinational (recombining familiar ideas),
exploratory (searching a structured conceptual space), transformational (changing the rules/
dimensions delimiting the space so previously impossible structures can arise). Attribution to Boden
(*The Creative Mind*, 1990/2004) is correct; cited Aalto page is a faithful secondary summary.
URL: https://divingintoradicalcreativity.aalto.fi/sub-chapter/1-3-aspects-of-radical-creativity/

**C24 — Hughes et al. (ICML 2024): open-ended = produces artifacts both novel and learnable from an
observer's perspective; foundation-model-based open-ended systems as a path to novel discovery.**
CONFIRMED. Verbatim definition (Sec 2.1): "From the perspective of an observer, a system is open-
ended if and only if the sequence of artifacts it produces is both novel and learnable." Abstract:
"a path towards ASI via open-ended systems built on top of foundation models, capable of making
novel, human-relevant discoveries." Nitpick (fixed): draft's quoted definition was a re-ordered
paraphrase inside quotation marks; replaced with the paper's verbatim sentence.
URL: https://arxiv.org/abs/2406.04268 (full text: https://arxiv.org/html/2406.04268v1)

**C25 — Standing counter: every verified system (C1–C9) rides on a cheap, exact, automatic ground-
truth evaluator; LLM proposes, evaluator certifies; approach confined to gradable domains.**
CONFIRMED, and the draft's own hedging (Confidence: medium; strong framing partly secondary) is
appropriate. The quoted language "only operates in domains where correctness or improvement can be
scored automatically … limited only by the availability of robust evaluators" is genuine AlphaEvolve
framing (blog/whitepaper + secondary sources), not fabricated. DeepMind blog: problems must be ones
"whose solution can be described as an algorithm, and automatically verified." Substantive core is
fully supported by the verified C1–C9.
URLs: https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/ ;
https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/AlphaEvolve.pdf

---

## Summary

- Checked: 25 / 25.
- CONFIRMED: 25. OVERSTATED: 0. WRONG: 0. UNVERIFIABLE: 0.
- Every load-bearing figure re-verified against a fetched primary source, including the FunSearch
  cap-set table (496→512, n=8), capacity bounds (2.2180→2.2202, C≤2.756), and full bin-packing
  Table 1 — all extracted from the Nature PDF this session, matching the draft exactly.
- Minor quote-fidelity nitpicks at C1, C3, C24 (quotation marks around faithful paraphrases). C3 and
  C24 tightened to verbatim source wording; C1 left (blog carries near-identical language). None
  affect any claim's truth value.

Nothing load-bearing remains wrong after fixes → target file status set to
"agreed round 1 (adversary-fixed)."
