#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "docling-agent @ git+https://github.com/docling-project/docling-agent@9c754cf9b581e082e7ac2c45f3638223562f7578",
# ]
# ///
"""docling-agent's own LLM section selector, as a baseline (E3).

Two modes:

    selection  calls DoclingRAGAgent._select_section --k times per question, adding each
               pick to the visited set, with no answer attempt in between: a ranking of
               k sections, comparable with a small model's ranking.
    loop       runs the public run_with_trace(), as docling-agent does by default: a
               selection, then an answer attempt, until the LLM can answer or --k
               rounds are used. The ranking stops where the loop stopped.

Appends one JSONL line per question to --out and skips questions already done:

    {"question_id", "ranked_refs", "confidence": null, "fallbacks", "seconds", ...}

`fallbacks` counts picks where the LLM output failed validation and docling-agent took
the first unvisited ref instead. In loop mode, --qasper-predictions also writes the
answers in the input format of Qasper's official evaluator (scripts/evaluator.py in
allenai/qasper-led-baseline); evidence is left empty, so only Answer F1 is meaningful.

Usage:
    uv run llm_selector.py --gold output/hier/gold.jsonl --docs data/docling/hier \\
        --model granite4:micro-h --out output/hier/llm.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from docling_agent.agent.base_functions import create_document_outline
from docling_agent.agent.rag import DoclingRAGAgent
from docling_agent.backends import create_backend
from docling_agent.task_model import BackendConfig, ModelConfig
from docling_core.experimental.serializer.outline import OutlineFormat
from docling_core.types.doc import DoclingDocument

from qasper import file_stem

USABLE = {"aligned", "partial"}
_PARTIAL_ANSWER = re.compile(r"^\[Partial answer after \d+ iteration\(s\)\]\n\n")


def rank_sections(
    agent: DoclingRAGAgent, doc: DoclingDocument, query: str, k: int
) -> tuple[list[str], int]:
    """Up to k successive picks of the LLM selector, in one reasoning session."""
    m = agent._create_reasoning_session(system_prompt=agent._RAG_SYSTEM_PROMPT)
    outline = create_document_outline(doc, format=OutlineFormat.MARKDOWN)
    valid_refs = agent._extract_section_refs(doc)
    visited: set[str] = set()
    ranked: list[str] = []
    fallbacks = 0
    for _ in range(min(k, len(valid_refs))):
        selection = agent._select_section(
            m=m, query=query, outline_text=outline, valid_refs=valid_refs, visited=visited
        )
        fallbacks += selection.reason == "fallback"
        visited.add(selection.section_ref)
        ranked.append(selection.section_ref)
    return ranked, fallbacks


def run_loop(agent: DoclingRAGAgent, doc: DoclingDocument, query: str) -> dict:
    """One docling-agent run as released: selections interleaved with answer attempts."""
    trace = agent.run_with_trace(task=query, document=doc)
    result = trace.per_document[0]
    return {
        "ranked_refs": [it.section_ref for it in result.iterations],
        "fallbacks": sum(it.reason == "fallback" for it in result.iterations),
        "converged": result.converged,
        "rounds": len(result.iterations),
        "answer": _PARTIAL_ANSWER.sub("", result.answer),
    }


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--gold", type=Path, required=True, help="gold.jsonl from align_gold.py")
    ap.add_argument(
        "--docs", type=Path, required=True, help="dir of <paper_id>.json DoclingDocuments"
    )
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--mode", choices=("selection", "loop"), default="selection")
    ap.add_argument("--model", required=True, help="model id on the backend, e.g. granite4:micro-h")
    ap.add_argument("--backend", default="ollama", help="docling-agent backend type")
    ap.add_argument("--base-url", help="backend URL; the backend's default when omitted")
    ap.add_argument(
        "--k", type=int, default=5, help="picks per question (docling-agent default: 5)"
    )
    ap.add_argument(
        "--all-questions", action="store_true", help="not only questions with aligned gold"
    )
    ap.add_argument("--limit", type=int)
    ap.add_argument(
        "--qasper-predictions", type=Path, help="loop mode: answers for the Qasper evaluator"
    )
    args = ap.parse_args()

    backend = create_backend(
        BackendConfig(
            type=args.backend,
            base_url=args.base_url,
            models=ModelConfig(reasoning=args.model, writing=args.model),
        )
    )
    agent = DoclingRAGAgent(tools=[], backend=backend, max_iterations=args.k)

    done = {r["question_id"] for r in read_jsonl(args.out) if "error" not in r}
    todo = [
        g
        for g in read_jsonl(args.gold)
        if g["question_id"] not in done
        and g.get("status") != "missing_doc"
        and (args.all_questions or g.get("status") in USABLE)
    ][: args.limit]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    doc_cache: dict[str, DoclingDocument] = {}
    with args.out.open("a", encoding="utf-8") as out:
        for n, g in enumerate(todo, start=1):
            paper_id = g["paper_id"]
            if paper_id not in doc_cache:
                doc_cache.clear()  # gold.jsonl is grouped by paper
                doc_cache[paper_id] = DoclingDocument.load_from_json(
                    args.docs / f"{file_stem(paper_id)}.json"
                )
            doc = doc_cache[paper_id]
            row = {
                "question_id": g["question_id"],
                "paper_id": paper_id,
                "mode": args.mode,
                "model": args.model,
                "confidence": None,
            }
            start = time.perf_counter()
            try:
                if args.mode == "selection":
                    row["ranked_refs"], row["fallbacks"] = rank_sections(
                        agent, doc, g["question"], args.k
                    )
                else:
                    row.update(run_loop(agent, doc, g["question"]))
            except Exception as e:  # a failed question is recorded and retried on the next run
                row.update({"ranked_refs": [], "error": f"{type(e).__name__}: {e}"})
            row["seconds"] = round(time.perf_counter() - start, 2)
            out.write(json.dumps(row) + "\n")
            out.flush()
            if args.qasper_predictions and "answer" in row:
                with args.qasper_predictions.open("a", encoding="utf-8") as qf:
                    qf.write(
                        json.dumps(
                            {
                                "question_id": g["question_id"],
                                "predicted_answer": row["answer"],
                                "predicted_evidence": [],
                            }
                        )
                        + "\n"
                    )
            print(
                f"[{n}/{len(todo)}] {g['question_id']}: {row['ranked_refs'][:3]} ({row['seconds']}s)"
            )


if __name__ == "__main__":
    main()
