# Section selection with a small model: experiments

Can a small decision model take over the section-selection step of docling-agent's
RAG loop, leaving the LLM to answer? These scripts build the evaluation around that
question: Docling parses of Qasper papers, gold section labels on Docling output,
docling-agent's own LLM selector as the baseline, and paired statistics.

Isolated from the Studio backend, like `experiments/reasoning-trace`: each script
declares its own dependencies (PEP 723) and runs with `uv run`.

## Pipeline

| Step | Script | Output | Experiments |
| --- | --- | --- | --- |
| 1 | `build_docling_corpus.py` | `data/pdfs/`, `data/docling/{flat,hier}/`, `data/manifest.json` | E1, E2 |
| 2 | `align_gold.py` | `output/<variant>/candidates.jsonl`, `gold.jsonl`, `report.json` | E1, E2 |
| 3 | `llm_selector.py` | `output/<variant>/llm.jsonl` | E3, E4 (`--mode loop`) |
| 4 | your selector | `output/<variant>/<name>.jsonl` | |
| 5 | `evaluate.py` | report JSON | E1, E3, E5, E6 |

`flat` is Docling's default PDF conversion (every heading at level 1). `hier` turns on
heading-hierarchy inference (`HeadingHierarchyOptions`) and rebuilds the tree from the
levels, as docling-agent's `perfs/agentic_rag_eval.py` does.

From this directory, with a Qasper split file (JSON) from
<https://allenai.org/data/qasper> saved as `data/qasper/test.json`:

```sh
uv run build_docling_corpus.py --qasper data/qasper/test.json --out data --limit 20
uv run align_gold.py --qasper data/qasper/test.json --docs data/docling/flat --out output/flat
uv run align_gold.py --qasper data/qasper/test.json --docs data/docling/hier --out output/hier
uv run llm_selector.py --gold output/hier/gold.jsonl --docs data/docling/hier \
    --model granite4:micro-h --out output/hier/llm.jsonl
# your selector: read output/hier/candidates.jsonl, write output/hier/laya.jsonl
uv run evaluate.py --gold output/hier/gold.jsonl --candidates output/hier/candidates.jsonl \
    --pred laya=output/hier/laya.jsonl --pred llm=output/hier/llm.jsonl --route laya:llm \
    --out output/hier/report.json
```

`data/` and `output/` are git-ignored.

## Formats

`candidates.jsonl`, one line per paper: the sections a selector chooses from, in
reading order. `text` is exactly what docling-agent hands to the LLM for that section.

```json
{"paper_id": "1909.00694", "sections": [{"ref": "#/texts/12", "heading": "3.1 Data", "level": 2, "parents": ["#/texts/9"], "n_chars": 1455, "text": "..."}]}
```

Predictions, from any selector, one line per question. `confidence` is optional and
only used for routing.

```json
{"question_id": "...", "ranked_refs": ["#/texts/12", "#/texts/30"], "confidence": 0.93}
```

`gold.jsonl`, one line per question: `gold` (strict: the most specific section holding
the evidence), `gold_lenient` (strict plus the enclosing sections), `status`
(`aligned`, `partial`, `unaligned`, `no_evidence`, `missing_doc`) and the score of each
evidence paragraph.

## Reading the numbers

- **Parents contain their subsections.** In a hierarchized document docling-agent reads
  a section with its whole subtree, and the first heading can hold the entire paper.
  Strict gold is the main metric; lenient hits are reported with the characters read.
- **The PDF is not Qasper's text.** Qasper's text comes from the papers' LaTeX sources
  (S2ORC), and arXiv serves the current version of each paper. `report.json` gives the
  share of evidence matched (trigram containment of at least 0.5 by default); report it
  with the results.
- **Two LLM baselines.** `--mode selection` ranks k sections with no answer attempt in
  between, comparable with a small model's ranking. `--mode loop` is docling-agent as
  released: the LLM stops once it can answer. `fallbacks` counts picks where
  docling-agent replaced invalid LLM output with the first unvisited section.
- **Answer F1 only.** In loop mode, `--qasper-predictions` writes answers for Qasper's
  official evaluator (`scripts/evaluator.py` in allenai/qasper-led-baseline) with empty
  evidence, so Evidence F1 does not apply.
- **arXiv downloads** wait `--delay` seconds (3 by default) between two PDFs.

`sections.py` mirrors `DoclingRAGAgent` at docling-agent `9c754cf`, the commit
`llm_selector.py` pins. The corpus manifest records the Docling versions used.

## Tests

```sh
uv run --with pytest --with "docling-core>=2.79" pytest tests
```

The parity tests against docling-agent and the LLM-selector wiring tests (scripted
backend, no model) run only when docling-agent is installed; otherwise they are skipped.

Status: the test suite passes with docling-agent `9c754cf` installed, and steps 2, 3
(scripted backend) and 5 ran end to end on the Docling technical report JSON shipped
in docling-agent's tests. Step 1 (Docling conversion of arXiv PDFs) and step 3 with a
real LLM have not been run yet.
