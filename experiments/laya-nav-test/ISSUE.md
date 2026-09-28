# Can a calibrated decision model select sections, keeping the LLM for the final answer only?

## Context

`DoclingRAGAgent` answers a question by consulting one section at a time. At each iteration, the LLM reads the document outline (headers with per-section summaries or keyphrases), picks one unvisited section, reads it and tries to answer. It stops after 5 iterations (`_select_section`, `_attempt_answer`).

Every selection costs an LLM call, and the pick carries no confidence signal. A misleading header leads to a confident wrong pick, and a retry knows which sections were visited but not how close the alternatives were.

## Question

Two ways to select sections in the same loop:

- **LLM selection (current):** the LLM picks the next section from the outline at each iteration and answers at the end.
- **Decision-model selection:** a small non-generative decision model scores the sections and returns a probability for each. Sections are opened in that order, and the probabilities tell how many to open at once and when to stop. The LLM is only called to answer from the opened sections.

1. Do we get comparable answer quality?
2. At what cost (LLM calls, tokens, latency)?

The expected outcome is a quality / cost trade-off curve rather than a single winner. A negative result would also be useful: it would show that the LLM is hard to replace inside the selection loop.

## Candidate model

[Laya](https://huggingface.co/convaiinnovations/laya): ModernBERT-based decision model (421M parameters), Apache 2.0, one forward pass per call (~33 ms reported on GPU). It answers typed questions over a free-text or JSON state: `choice` returns a probability per option, `noul` a yes/no probability. This connects with the exploration history work in #54, with one caveat from the early test below: a decision model does not read "this branch was explored" the way an LLM does.

## Early signal (feasibility test, zero-shot)

Setup: English checkpoint (`laya` 0.3.20), no fine-tuning, no temperature fitting. Two arXiv papers parsed with Docling: [ScreenParse](https://arxiv.org/abs/2602.14276) (48 headers) and [Unfolding the Leech Lattice](https://arxiv.org/abs/2609.02652) (24 headers). 13 questions, each answered in one known section (checked against the text): 4 lexical, 5 paraphrase, 4 misleading header. Metric: sections opened until the target is reached, following each method's order (docling-agent stops at 5).

| Method | Target first | Within 5 | Mean sections opened |
|---|---|---|---|
| Laya, node by node: `choice` over child headers | 2/13 | 5/13 | 8.6 |
| Laya, flat: one `noul` per section, header only | 6/13 | 8/13 | 6.4 |
| **Laya, flat: one `noul` per section, header + first 400 characters** | **8/13** | **12/13** | **2.5** |
| BM25 over the same header + 400 characters | 9/13 | 10/13 | 3.5 |
| Random order | 0.55 | 2.75 | 12.7 |

What the test suggests:

- **Headers alone are not enough.** Node by node, 7 of 24 decisions are right against 0.16 for random, and nearly all of it comes from lexical overlap (lexical 5/9, paraphrase 2/8, misleading 0/7). The model is also pulled toward options that share words with the paper title in the path; removing the title from the path helps.
- **Scoring each section on its own works much better.** One yes/no question per section, all sections in one batched pass (~0.4 s for 20 to 28 sections on an Apple GPU), finds 12 of 13 targets within 5 openings.
- **The probability becomes usable.** The P(yes) of the top section separates first-try hits from misses (AUROC 0.80), against 0.61 for the max probability of the node-by-node `choice`.
- **Free-text history backfires.** Adding "Branch X was explored, the answer was not found there." to the state raised X's probability in 14 of 17 replays. Excluding visited sections from the ranking works natively.
- **Lexical retrieval is a strong baseline.** BM25 on the same text is close, so most of the gain comes from giving the model section content. The decision model's value has to be shown against it.
- **A flat distribution, for example:** "In the structure-aware loss, what weight values are given to tag tokens and location tokens?" is only answered in the last line of `7.2 Training Details`. At the root, Laya puts 0.34 on `Abstract` and 0.06 on `7. Appendix`. Inside `7. Appendix` its distribution is nearly flat (max 0.15, target third of 9). No method finds this one within 5 openings.

13 questions, zero-shot, uncalibrated, and method variants designed after a first run on the same questions: this is a signal, not a result.

## Proposed evaluation (draft)

| Arm | Selection | Opening policy |
|---|---|---|
| A | LLM, current docling-agent loop | One section per iteration, up to 5 |
| B | LLM ranks all sections once | Fixed top-N, no calibrated signal |
| C | Decision model, one yes/no per section (header + summary) | By decreasing P(yes), N driven by the probabilities |
| L | BM25 or embeddings over the same text | Fixed top-N |

Ablations: node-by-node descent against flat scoring, header only against header + summary, history as exclusion against history as text.

Metrics:
- answer correctness, and whether the target section was reached;
- cost: number of LLM calls, tokens, wall-clock latency.

## Known risks

- **Zero-shot quality.** The authors report the base checkpoint near chance zero-shot on their typed-decisions benchmark (0.362), and 0.766 after fine-tuning on its training split. The early test shows the same pattern on headers alone.
- **Calibration.** The checkpoint ships over-confident. The authors report that refitting one temperature per (question type, option count) brings mean ECE from 0.466 to 0.081, which needs held-out decisions from the target documents. The shipped temperature for 11+ options is 0.10, which sharpens probabilities about tenfold: the `laya` package clamps it to 0.5, the Hugging Face demo does not.
- **Token budget.** 512 tokens per question on the English checkpoint, 192 of them shared by the instructions and all options. Per-section scoring gives each section its own budget.
- **Header structure.** On both papers Docling returned every `section_header` at level 1, so the hierarchy had to be rebuilt from the numbering, and figure column labels and prompt-box titles also came out as headers. Any header-based navigation depends on this.
- **Answers buried in a section.** A summary or the first lines of a section miss details at its end; passage-level scoring may be needed.

## Open questions

- Which public benchmark fits best: document QA sets where the answer location is annotated, or long-PDF QA suites?
- How to define an equal budget across arms: LLM calls, tokens, or latency?
- Where should section summaries come from: Docling enrichment, one LLM pass per document, or extractive text?
- Could docling-agent traces (#39, #42) provide training data to fine-tune the decision model on section selection?
- Which ablations matter most: opening policy, history format, temperature fitting?

## Proposal

I'd be happy to implement this as an optional selection strategy in docling-agent, behind a flag, together with the evaluation harness. The feasibility scripts already exist and replay in a few minutes. Before going further, I'd value your view on the question and the protocol, and would be glad if someone on the team were interested in looking at this with me.

cc @PeterStaar-IBM @ceberam
