#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyarrow",
# ]
# ///
"""
Build section-selection data for Laya from Qasper (allenai/qasper, CC BY 4.0).

Qasper pairs questions written by NLP practitioners with the paragraphs that answer them
("evidence"), over 1,585 arXiv papers already split into sections (S2ORC). Each evidence paragraph
is mapped to its section, so every question gets a relevance per section with no annotation on
our side:

    relevance(section) = share of the question's annotators whose evidence falls in that section

Evidence pointing at a figure or a table ("FLOAT SELECTED: ...") is not a section and is skipped;
questions whose annotators all answered "unanswerable" or only cited floats are dropped.

Sections are shown to Laya as in the F2 variant of ../run_variants.py:
    passage = "Section › Subsection: <first 400 characters of the section text>"

Usage:
    uv run experiments/laya-nav-test/finetune/build_qasper.py [--negatives 6]

Output, in experiments/laya-nav-test/finetune/data/:
    raw/<split>.parquet          Qasper as converted to Parquet by Hugging Face
    <split>.questions.jsonl      one line per question: its paper's sections, relevance per section
    train.items.jsonl, validation.items.jsonl
                                 one line per (question, section) pair: every relevant section plus
                                 sampled negatives, half the closest by BM25, half at random
"""
from __future__ import annotations

import argparse
import json
import random
import re
import urllib.request
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

from shared import bm25, passage

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
PARQUET = "https://huggingface.co/datasets/allenai/qasper/resolve/refs%2Fconvert%2Fparquet/qasper/{split}/0000.parquet"
SPLITS = ("train", "validation", "test")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def download(split: str) -> Path:
    path = DATA / "raw" / f"{split}.parquet"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(PARQUET.format(split=split), path)
    return path


def paper_sections(row: dict) -> list[dict]:
    sections = []
    if norm(row.get("abstract")):
        sections.append({"crumbs": ["Abstract"], "paragraphs": [norm(row["abstract"])]})
    full = row.get("full_text") or {}
    for name, paragraphs in zip(full.get("section_name") or [], full.get("paragraphs") or []):
        paragraphs = [norm(p) for p in (paragraphs or []) if norm(p)]
        if not paragraphs:
            continue
        crumbs = [c.strip() for c in (name or "").split(":::") if c.strip()] or ["(untitled)"]
        sections.append({"crumbs": crumbs, "paragraphs": paragraphs})
    return sections


def locate(evidence: str, sections: list[dict], exact: dict[str, int]) -> int | None:
    """Section holding an evidence paragraph: exact paragraph first, then containment either way."""
    if evidence in exact:
        return exact[evidence]
    for i, s in enumerate(sections):
        if any(evidence in p or (len(p) > 40 and p in evidence) for p in s["paragraphs"]):
            return i
    return None


def build_split(split: str, negatives: int, stats: Counter) -> tuple[list[dict], list[dict]]:
    questions, items = [], []
    for row in pq.read_table(download(split)).to_pylist():
        stats[f"{split}.papers"] += 1
        sections = paper_sections(row)
        if not sections:
            continue
        exact = {p: i for i, s in enumerate(sections) for p in s["paragraphs"]}
        passages = [passage(s["crumbs"], " ".join(s["paragraphs"])) for s in sections]
        qas = row.get("qas") or {}
        for question, qid, answers in zip(qas.get("question") or [], qas.get("question_id") or [], qas.get("answers") or []):
            stats[f"{split}.questions"] += 1
            hits = Counter()
            annotators = 0
            for answer in (answers or {}).get("answer") or []:
                if answer.get("unanswerable"):
                    continue
                found = set()
                for ev in answer.get("evidence") or []:
                    ev = norm(ev)
                    if not ev:
                        continue
                    if ev.startswith("FLOAT SELECTED"):
                        stats[f"{split}.evidence_float"] += 1
                        continue
                    idx = locate(ev, sections, exact)
                    stats[f"{split}.evidence_mapped" if idx is not None else f"{split}.evidence_unmapped"] += 1
                    if idx is not None:
                        found.add(idx)
                if found:
                    annotators += 1
                    hits.update(found)
            if not annotators:
                stats[f"{split}.questions_dropped"] += 1
                continue
            relevance = [round(hits[i] / annotators, 4) for i in range(len(sections))]
            record = {"paper_id": row["id"], "question_id": qid, "question": norm(question),
                      "passages": passages, "relevance": relevance, "annotators": annotators}
            questions.append(record)
            stats[f"{split}.questions_kept"] += 1
            stats[f"{split}.sections"] += len(sections)
            stats[f"{split}.relevant_sections"] += sum(r > 0 for r in relevance)

            if split == "test":
                continue
            positives = [i for i, r in enumerate(relevance) if r > 0]
            pool = [i for i, r in enumerate(relevance) if r == 0]
            scores = bm25(record["question"], [passages[i] for i in pool])
            by_bm25 = [i for _, i in sorted(zip(scores, pool), key=lambda x: -x[0])]
            hard = by_bm25[: (negatives + 1) // 2]
            rest = [i for i in pool if i not in hard]
            easy = random.Random(qid).sample(rest, min(len(rest), negatives - len(hard)))
            for i in positives + hard + easy:
                items.append({"paper_id": row["id"], "question_id": qid, "query": record["question"],
                              "passage": passages[i], "p_true": relevance[i]})
    return questions, items


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--negatives", type=int, default=6, help="negative sections sampled per question")
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)
    stats = Counter()
    for split in SPLITS:
        questions, items = build_split(split, args.negatives, stats)
        write_jsonl(DATA / f"{split}.questions.jsonl", questions)
        if items:
            write_jsonl(DATA / f"{split}.items.jsonl", items)
            stats[f"{split}.items"] = len(items)
            stats[f"{split}.items_positive"] = sum(i["p_true"] > 0 for i in items)
    for split in SPLITS:
        kept = stats[f"{split}.questions_kept"] or 1
        print(f"{split:10} papers {stats[f'{split}.papers']:4}  questions {stats[f'{split}.questions']:5}  "
              f"kept {stats[f'{split}.questions_kept']:5}  dropped {stats[f'{split}.questions_dropped']:4}  "
              f"sections/question {stats[f'{split}.sections'] / kept:5.1f}  "
              f"relevant/question {stats[f'{split}.relevant_sections'] / kept:4.2f}  "
              f"items {stats[f'{split}.items']:6} ({stats[f'{split}.items_positive']} positive)")
        print(f"{'':10} evidence mapped {stats[f'{split}.evidence_mapped']}, float {stats[f'{split}.evidence_float']}, "
              f"unmapped {stats[f'{split}.evidence_unmapped']}")
    (DATA / "stats.json").write_text(json.dumps(dict(stats), indent=2) + "\n")


if __name__ == "__main__":
    main()
