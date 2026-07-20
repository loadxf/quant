---
status: agreed round 1 (adversary-fixed)
topic: llm_creativity
---

# Prior art: computational creativity and novelty in large language models

Scope: an academic literature survey on whether an LLM (weights alone) or an LLM-plus-tools
system can originate something genuinely new. Covers (a) systems with peer- or ground-truth-
verified new results, (b) the skeptical measurement literature, and (c) analytic frames for
"novelty." Feeds the pre-registered novelty scale (`research/methodology/novelty_scale.md`,
risk R7) and the report's literature-review section. Every load-bearing number below was pulled
from a fetched primary source (paper PDF, publisher page, or authors' own release), not memory;
numbers that could not be pinned to a fetched source are marked Confidence: low.

## Claims

**C1.** FunSearch (Romera-Paredes et al., *Nature*, published online Dec 2023, issue 2024) is an
evolutionary loop that pairs a pretrained LLM (proposer of *programs*, not answers) with an
automated, problem-specific evaluator and a programs database; the evaluator is what makes it
sound, because it discards hallucinated or incorrect programs before they enter the population.
Evidence: "an automated 'evaluator', which guards against hallucinations and incorrect ideas …
Unsuccessful programs are discarded, while a successful program is added to the programs
database." FunSearch "searches for programs that describe how to solve a problem, rather than
what the solution is."
Source: https://deepmind.google/blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/ and https://www.nature.com/articles/s41586-023-06924-6
Confidence: high

**C2.** On the cap-set problem, FunSearch found a cap set of size **512 in dimension n=8**,
beating the previous best-known admissible-set-derived construction of 496, and it returned a
*program* that generates the set (not just the set), giving human-interpretable structure.
Evidence: table in the paper — "n … 8 / Best known … 496 / FunSearch … 512"; "we do not just
discover the set of 512 8-dimensional vectors in itself, but a program that generates it."
Source: https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/Mathematical-discoveries-from-program-search-with-large-language-models.pdf (Nature accepted version; PDF text-extracted this session)
Confidence: high

**C3.** FunSearch pushed the **lower bound on the cap-set capacity C from 2.2180 (Tyrrell, 2022)
up to 2.2202** (via an A(24,17) admissible set), described as the largest improvement to this
asymptotic lower bound in ~20 years; the known upper bound is C ≤ 2.756.
Evidence: capacity table — "2.2180 I(11,7) (Tyrrell, 2022) / 2.2184 I(12,7) FunSearch / 2.2194
I(15,10) FunSearch / 2.2202 A(24,17) FunSearch"; "result of [32] established an
upper bound of C ≤ 2.756." Author text (of this lower-bound gain): "this is the largest
improvement to the lower bound in the last 20 years" (abstract: "the largest improvement in 20
years to the asymptotic lower bound").
Source: same Nature PDF as C2; https://deepmind.google/blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/
Confidence: high

**C4.** FunSearch also discovered online-bin-packing heuristics that beat the standard first-fit
and best-fit baselines across OR-Library and Weibull instances, measured as fraction of excess
bins over the L2 lower bound (lower is better): e.g. OR1 — First Fit 6.42%, Best Fit 5.81%,
FunSearch 5.30%; Weibull 100k — First Fit 4.00%, Best Fit 3.79%, FunSearch **0.03%**.
Evidence: "Table 1: Fraction of excess bins (lower is better) … FunSearch outperforms first fit
and best fit across problems and instance sizes." Row values as quoted.
Source: same Nature PDF as C2
Confidence: high

**C5.** AlphaEvolve (DeepMind, 2025) — a Gemini-powered evolutionary coding agent — found an
algorithm to multiply two **4×4 complex-valued matrices using 48 scalar multiplications**,
improving on Strassen's 1969 method (49) that had stood as best-known in this setting for ~56
years. (Nuance: the result is for complex-valued / characteristic-appropriate matrices, not a
new bound over arbitrary rings, and does not change the asymptotic matrix-multiplication
exponent.)
Evidence: "AlphaEvolve's procedure found an algorithm to multiply 4x4 complex-valued matrices
using 48 scalar multiplications, improving upon Strassen's 1969 algorithm that was previously
known as the best in this setting."
Source: https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/ ; verification: https://github.com/PhialsBasement/AlphaEvolve-MatrixMul-Verification
Confidence: high

**C6.** Across a corpus of 50+ open mathematics problems, AlphaEvolve **rediscovered the
state-of-the-art in ~75% of cases and improved on the best-known solution in ~20%**.
Evidence: "In roughly 75% of cases, it rediscovered state-of-the-art solutions, to the best of
our knowledge. And in 20% of cases, AlphaEvolve improved the previously best known solutions."
Source: https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/
Confidence: high

**C7.** AlphaEvolve produced deployed engineering wins: a Borg scheduling heuristic that
**recovers ~0.7% of Google's worldwide compute** (in production >1 year), and a matrix-multiply
kernel **23% faster**, cutting Gemini training time ~1%.
Evidence: "continuously recovers, on average, 0.7% of Google's worldwide compute resources";
"sped up this vital kernel in Gemini's architecture by 23%, leading to a 1% reduction in
Gemini's training time."
Source: https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/
Confidence: high

**C8.** AlphaDev (Mankowitz et al., *Nature* 2023) used deep RL (an AlphaZero-style single-player
"assembly game") to find sorting routines **up to 70% faster for short sequences and ~1.7%
faster for sequences >250,000 elements**; the routines were merged into the LLVM libc++ standard
C++ sort — the first change to that part of the library in over a decade.
Evidence: "up to 70% faster for shorter sequences"; "about 1.7% faster for sequences exceeding
250,000 elements"; "the first change to this part of the sorting library in over a decade and
the first time an algorithm designed through reinforcement learning has been added to this
library."
Source: https://deepmind.google/blog/alphadev-discovers-faster-sorting-algorithms/ and https://www.nature.com/articles/s41586-023-06004-9
Confidence: high

**C9.** Google's "AI co-scientist" (2025) is a Gemini-based multi-agent system that generates,
debates, ranks (tournament/Elo self-play), and refines hypotheses with scaled test-time compute;
it was validated in three biomedical areas, and its drug-repurposing candidates for acute
myeloid leukemia (AML) were confirmed in vitro.
Evidence: "multi-agent architecture … tournament evolution process for self-improving hypotheses
generation … scaling test-time compute"; "validated in three biomedical applications: drug
repurposing, novel target discovery, and explaining mechanisms of anti-microbial resistance";
"drug repurposing candidates and synergistic combination therapies for acute myeloid leukemia,
which were validated through in vitro experiments."
Source: https://arxiv.org/abs/2502.18864
Confidence: high

**C10.** Sakana AI's AI-Scientist-v2 generated a fully autonomous paper that passed peer review
at an ICLR 2025 workshop (avg reviewer score **6.33**, above the acceptance threshold) — but the
claim is heavily caveated by Sakana itself: **3 papers were submitted and 1 accepted**, the
workshop's acceptance rate is ~60–70%, none of the 3 met Sakana's own internal bar for a main-
conference paper, the system made citation errors, and Sakana withdrew the paper before
publication.
Evidence: accepted paper "Compositional Regularization…" scored 6, 7, 6 (avg 6.33); Sakana:
"workshops … have acceptance rates in the 60-70% range"; "we concluded that none of the 3 papers
passed our internal bar…"; "even if papers by The AI Scientist were accepted, we would withdraw
them before they were actually published."
Source: https://sakana.ai/ai-scientist-first-publication/
Confidence: high

**C11.** An independent evaluation (Beel, Kan & Baumgart, 2025) of Sakana's first-generation AI
Scientist found substantive failures: poor novelty assessment (e.g. flagging micro-batching for
SGD as novel) and **~42% of experiments failing due to coding errors**, concluding the system
"superficially automates" research without deep literature review or robust validation.
Evidence: "42% of experiments failed due to coding errors, while others produced flawed or
misleading results"; literature reviews "often misclassifying established concepts … as novel."
Source: https://arxiv.org/abs/2502.14297
Confidence: high

**C12.** Bender, Gebru et al. (*FAccT* 2021, "On the Dangers of Stochastic Parrots") frame an LLM
as a system that stitches together linguistic forms by corpus statistics "without any reference
to meaning" — the canonical skeptical claim that fluent output is form without understanding.
Evidence: an LM is "a system for haphazardly stitching together sequences of linguistic forms …
according to probabilistic information about how they combine, but without any reference to
meaning."
Source: https://dl.acm.org/doi/10.1145/3442188.3445922
Confidence: high

**C13.** Kambhampati (*Annals NYAS* 2024, "Can LLMs Reason and Plan?") argues LLMs perform
"universal approximate retrieval," not principled reasoning/planning: GPT-4 reached only ~30%
accuracy on Blocksworld planning and collapsed when action/object names were obfuscated (which
classical planners handle trivially).
Evidence: "What LLMs are good at is a form of universal approximate retrieval"; "GPT4 reaching
30% empirical accuracy in the Blocks World"; under obfuscation "GPT4's empirical performance
plummeted precipitously."
Source: https://arxiv.org/abs/2403.04121 (also DOI 10.1111/nyas.15125)
Confidence: high

**C14.** Kambhampati further reports that LLM **self-verification worsens performance** (they
hallucinate false positives and negatives when checking their own solutions), motivating an
"LLM-Modulo" architecture that pairs the LLM's idea generation with *sound external verifiers* in
a generate–test–critique loop — i.e. the epistemic guarantee comes from the external checker, not
the model.
Evidence: "with 'self-verification' performance actually worsens … LLMs hallucinate both false
positives and false negatives while verifying the solutions they generate"; LLM-Modulo lets "an
external model-based plan verifier … certify the correctness of the final solution."
Source: https://arxiv.org/abs/2403.04121
Confidence: high

**C15.** The "Creativity Index" (Lu et al., "AI as Humanity's Salieri", 2024) measures textual
originality as n-gram / near-verbatim non-overlap with web corpora via the DJ-Search algorithm;
it finds the **Creativity Index of professional human authors is on average 66.2% higher than
that of LLMs** (with the gap ranging by domain, e.g. 115.3% higher for speeches).
Evidence: "the Creativity Index of professional human authors is on average 66.2% higher than
that of LLMs"; DJ-Search "can search verbatim and near-verbatim matches of text snippets from a
given document against the web."
Source: https://arxiv.org/abs/2410.04265
Confidence: high

**C16.** The same paper finds **RLHF alignment lowers the Creativity Index by ~30.1% on average**
(verbatim matches), i.e. preference tuning measurably reduces the originality (n-gram novelty) of
generated text.
Evidence: "the Creativity Index of LLMs reduces by an average of 30.1% after RLHF" (verbatim
30.1% vs semantic 8.9%).
Source: https://arxiv.org/abs/2410.04265
Confidence: high

**C17.** Kirk et al. (*ICLR* 2024) show **RLHF significantly reduces output diversity relative to
supervised fine-tuning** across measures, exposing a generalisation-vs-diversity trade-off in
current alignment methods (RLHF generalises better OOD but at the cost of per-input diversity).
Evidence: "RLHF significantly reduces output diversity compared to SFT across a variety of
measures, implying a tradeoff … between generalisation and diversity."
Source: https://arxiv.org/abs/2310.06452
Confidence: high

**C18.** Padmakumar & He (*ICLR* 2024) show in a controlled writing experiment that co-writing
with a feedback-tuned model (**InstructGPT, but not base GPT-3**) produces a statistically
significant reduction in content diversity — different authors' essays become more similar —
mainly because InstructGPT contributes less diverse text.
Evidence: "writing with InstructGPT (but not GPT3) resulted in a statistically significant
reduction in diversity … increased the similarity between writings of different authors."
Source: https://arxiv.org/abs/2309.05196
Confidence: high

**C19.** Si, Yang & Hashimoto (2024, "Can LLMs Generate Novel Research Ideas?") ran a
100+-researcher blind study (49 experts wrote ideas; ideas from an LLM ideation agent were
compared) and found **LLM ideas were judged more novel than expert ideas (p < 0.05) but slightly
weaker on feasibility**; they flag failures of LLM self-evaluation and lack of diversity in
generation.
Evidence: "LLM-generated ideas are judged as more novel (p < 0.05) than human expert ideas" while
"judged slightly weaker on feasibility"; open problems include "failures of LLM self-evaluation
and their lack of diversity in generation."
Source: https://arxiv.org/abs/2409.04109
Confidence: high

**C20.** The authors' 2025 follow-up ("The Ideation–Execution Gap") had researchers actually
execute the ideas (~103 hours each): **once executed, LLM-idea scores dropped far more than
human-idea scores across novelty/excitement/effectiveness/overall (p < 0.05), and rankings often
flipped so human ideas scored higher** — i.e. the apparent novelty advantage did not survive
execution.
Evidence: "LLM ideas score much lower in the execution evaluation compared to the ideation
evaluation, whereas human expert ideas only incur small drops"; participants "spent an average of
103 hours executing the assigned idea"; "in many metrics there was even a flip in rankings."
Source: https://arxiv.org/abs/2506.20803
Confidence: high

**C21.** Doshi & Hauser (*Science Advances* 2024) find in a story-writing experiment that access
to generative-AI ideas **raises individual creativity ratings (especially for less-creative
writers) but makes stories more similar to one another** — a social dilemma in which collective
diversity falls even as individual output improves.
Evidence: "Access to generative AI ideas causes stories to be evaluated as more creative … 
especially among less creative writers"; "generative AI–enabled stories are more similar to each
other than stories by humans alone."
Source: https://www.science.org/doi/10.1126/sciadv.adn5290 (also https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4535536)
Confidence: high

**C22.** Anderson, Shah & Kreminski (*Creativity & Cognition* 2024) — a 36-participant study —
find that ChatGPT-assisted ideation **homogenises ideas at the group level**: different users
produced less semantically distinct ideas with ChatGPT, generated more (and more detailed) ideas
but felt less ownership, with no commensurate gain in per-user diversity.
Evidence: "different users tended to produce less semantically distinct ideas with ChatGPT";
"users of ChatGPT produced a more homogenous set of ideas at the group level"; "felt less
responsible for the ideas they generated."
Source: https://mkremins.github.io/publications/Homogenization_C&C2024.pdf
Confidence: high

**C23.** Boden's taxonomy of creativity distinguishes **combinational** (novel improbable
combinations of familiar ideas), **exploratory** (generating novelty by searching within a
structured conceptual space), and **transformational** (altering a dimension of the conceptual
space itself, enabling ideas previously impossible in it) — with transformational treated as the
deepest. This is the frame for grading what kind of "new" a system produces.
Evidence: "combinational (familiar ideas are recombined …); exploratory (exploring a conceptual
space); and transformational (transforming a conceptual space)"; transformational "involves the
transformation of some … dimension of the space, so that new structures can be generated which
could not have arisen before."
Source: https://divingintoradicalcreativity.aalto.fi/sub-chapter/1-3-aspects-of-radical-creativity/ (summarising Boden, *The Creative Mind*, 1990/2004)
Confidence: high

**C24.** Hughes et al. (*ICML* 2024, "Open-Endedness is Essential for ASI") give a formal notion
supporting the "system, not weights" view: a system is **open-ended if it produces a sequence of
artifacts that are both novel and learnable from an observer's perspective**, and they argue
foundation-model-based open-ended systems are a path to novel, human-relevant discovery — the
published articulation that a fixed-weight model embedded in a search/evaluation loop can be
epistemically open.
Evidence (verbatim, Sec. 2.1): "From the perspective of an observer, a system is open-ended if
and only if the sequence of artifacts it produces is both novel and learnable"; abstract: "a path
towards ASI via open-ended systems built on top of foundation models, capable of making novel,
human-relevant discoveries."
Source: https://arxiv.org/abs/2406.04268
Confidence: high

**C25.** The standing counter to C24: every verified-novelty system in this survey (C1–C9)
depends on a **cheap, automatic, ground-truth evaluator** — a machine-gradable objective. The LLM
only *proposes*; the external evaluator does the load-bearing epistemic work of certifying that a
candidate is correct and new. This both explains the openness (results can exceed the training
corpus because truth is checked outside the model) and bounds it: the approach is confined to
domains with hard, cheap executable feedback (math, algorithms, systems), and degrades where no
such evaluator exists.
Evidence: FunSearch's evaluator "guards against hallucinations" (C1); AlphaEvolve "only operates
in domains where correctness or improvement can be scored automatically … limited only by the
availability of robust evaluators"; the generator/evaluator split "does not invoke another LLM."
Source: https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/ ; commentary https://www.hpcwire.com/2025/06/02/can-alphaevolve-change-how-we-solve-problems-a-look-inside-deepminds-latest-breakthrough/
Confidence: medium (the "requires an evaluator" fact is high; the strong "limited to gradable domains" framing is partly from secondary commentary)

## Synthesis

The evidence splits cleanly along the seam the pre-registration already drew (risk R7):
*weights alone* versus *the system*. On weights-alone, the skeptical literature is consistent and
quantitative. Free-running LLM text carries heavy n-gram overlap with its corpus — human authors
score ~66% higher on the Creativity Index (C15) — and the very training step that makes models
useful, preference tuning, measurably erodes originality and diversity: RLHF drops the Creativity
Index ~30% (C16), reduces output diversity versus SFT (C17), and feedback-tuned assistants
homogenise what different people write and ideate (C18, C21, C22). Bender's "form without meaning"
(C12) and Kambhampati's "approximate retrieval, not reasoning," with self-verification that
actively worsens performance (C13–C14), give the mechanism. The idea-generation results sharpen
rather than soften this: LLM research ideas *read* as more novel than experts' (C19), but that
edge is an artifact of judging ideas on paper — once executed, the advantage inverts (C20). For a
distributional-novelty question, weights-alone the honest answer is: mostly recombination, with
diversity actively compressed by alignment.

The system-level evidence points the other way, but narrowly. FunSearch (C1–C4), AlphaEvolve
(C5–C7), and AlphaDev (C8) are genuine existence proofs that an LLM-proposer plus a ground-truth
evaluator can produce artifacts outside all prior human constructions — a larger cap set, a lower
bound unimproved in 20 years, a matrix-multiplication scheme unbeaten since 1969, sorting code now
shipping in libc++. These are not rated novel by fallible human judges; they are *verified* by
computation. Hughes et al. (C24) supply the formal reading: a fixed-weight model inside a
search-and-selection loop can be open-ended — novel and learnable — precisely because novelty is a
property of the whole loop, not the frozen distribution. This is the strongest available support
for the project's design of using out-of-sample data as the evaluator.

But the same evidence carries its own discount. Every verified result rides on a cheap, exact,
automatic evaluator (C25); the LLM contributes proposals, and the external checker contributes the
epistemic guarantee. Where the evaluator is weak or the objective is soft, the system reverts to
weights-alone behaviour: the Sakana case shows autonomous "discovery" clearing a low peer bar
(C10) while an independent audit finds 42% of its experiments broken and its novelty judgments
unreliable (C11). In Boden's terms (C23), the verified wins are best read as powerful
*exploratory* creativity inside well-defined conceptual spaces of programs — not *transformational*
redefinition of the space. For this project, the transfer is therefore conditional: markets are a
far noisier, adversarial, weakly-gradable evaluator than a cap-set checker, so an LLM-plus-tools
system *can* in principle originate something genuinely new, but only as strongly as its external
evaluator can certify it — which is exactly why the locked holdout and multiple-testing harness,
not the model's fluency, must carry any novelty verdict.
