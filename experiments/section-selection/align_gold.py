#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "docling-core>=2.79.0",
# ]
# ///
"""Label each Qasper question with the Docling sections that hold its evidence (E1, E2).

Each evidence paragraph is matched to the section whose own text contains the
largest share of its word trigrams; below --threshold it stays unaligned. Writes to
--out, for one variant (flat or hier) of the corpus built by build_docling_corpus.py:

    candidates.jsonl  one line per paper: the sections a selector chooses from
    gold.jsonl        one line per question: gold refs + per-evidence alignment detail
    report.json       coverage and heading-structure statistics

Gold refs are "strict" (the most specific section holding the evidence) and
"lenient" (strict plus the enclosing sections, whose text also contains it in a
hierarchized document).

Usage:
    uv run align_gold.py --qasper data/qasper/test.json --docs data/docling/hier --out output/hier
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from docling_core.types.doc import DoclingDocument

from qasper import Question, file_stem, is_float_evidence, iter_questions, load_papers, normalize
from sections import Section, extract_sections


def shingles(words: list[str], n: int) -> set[tuple[str, ...]]:
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def containment(evidence: set[tuple[str, ...]], section: set[tuple[str, ...]]) -> float:
    return len(evidence & section) / len(evidence) if evidence else 0.0


@dataclass(frozen=True)
class Match:
    kind: str  # "text" | "float"
    ref: str | None
    score: float
    runner_up: float
    snippet: str


class SectionIndex:
    def __init__(self, sections: list[Section], n: int):
        self.sections = sections
        self.n = n
        self._shingles = [shingles(normalize(s.own_text).split(), n) for s in sections]

    def match(self, evidence: str, threshold: float) -> Match:
        kind = "float" if is_float_evidence(evidence) else "text"
        ev = shingles(normalize(evidence).split(), self.n)
        scores = sorted(
            ((containment(ev, sh), i) for i, sh in enumerate(self._shingles)),
            key=lambda pair: (-pair[0], pair[1]),  # best score first, then reading order
        )
        best, idx = scores[0] if scores else (0.0, -1)
        runner_up = scores[1][0] if len(scores) > 1 else 0.0
        ref = self.sections[idx].ref if idx >= 0 and best >= threshold else None
        return Match(kind, ref, round(best, 4), round(runner_up, 4), evidence[:100])


def label_question(
    q: Question,
    index: SectionIndex,
    *,
    threshold: float,
    min_words: int,
    text_evidence_only: bool,
) -> dict:
    parents = {s.ref: s.parents for s in index.sections}
    matches: list[Match] = []
    too_short = 0
    for evidence in q.evidence:
        if text_evidence_only and is_float_evidence(evidence):
            continue
        if len(normalize(evidence).split()) < min_words:
            too_short += 1
            continue
        matches.append(index.match(evidence, threshold))

    strict: list[str] = []
    for m in matches:
        if m.ref and m.ref not in strict:
            strict.append(m.ref)
    lenient = list(strict)
    for ref in strict:
        for parent in parents.get(ref, ()):
            if parent not in lenient:
                lenient.append(parent)

    aligned = sum(1 for m in matches if m.ref)
    if not matches:
        status = "no_evidence"
    elif aligned == len(matches):
        status = "aligned"
    elif aligned:
        status = "partial"
    else:
        status = "unaligned"
    return {
        "question_id": q.question_id,
        "paper_id": q.paper_id,
        "question": q.question,
        "status": status,
        "gold": strict,
        "gold_lenient": lenient,
        "too_short": too_short,
        "evidence": [m.__dict__ for m in matches],
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--qasper", type=Path, required=True, help="Qasper split file (JSON)")
    ap.add_argument(
        "--docs", type=Path, required=True, help="dir of <paper_id>.json DoclingDocuments"
    )
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--threshold", type=float, default=0.5, help="min share of trigrams found")
    ap.add_argument("--ngram", type=int, default=3)
    ap.add_argument("--min-words", type=int, default=5, help="shorter evidence is not aligned")
    ap.add_argument(
        "--text-evidence-only", action="store_true", help="ignore FLOAT SELECTED evidence"
    )
    args = ap.parse_args()

    papers = load_papers(args.qasper)
    by_paper: dict[str, list[Question]] = defaultdict(list)
    for q in iter_questions(papers):
        by_paper[q.paper_id].append(q)

    args.out.mkdir(parents=True, exist_ok=True)
    status = Counter()
    evidence_stats: Counter = Counter()
    levels: Counter = Counter()
    missing_docs: list[str] = []
    n_sections: list[int] = []
    all_level_1 = hierarchized = 0
    best_scores: list[float] = []

    with (
        (args.out / "candidates.jsonl").open("w", encoding="utf-8") as cand_f,
        (args.out / "gold.jsonl").open("w", encoding="utf-8") as gold_f,
    ):
        for paper_id in papers:
            doc_path = args.docs / f"{file_stem(paper_id)}.json"
            if not doc_path.exists():
                missing_docs.append(paper_id)
                for q in by_paper[paper_id]:
                    status["missing_doc"] += 1
                    row = {
                        "question_id": q.question_id,
                        "paper_id": paper_id,
                        "status": "missing_doc",
                    }
                    gold_f.write(json.dumps(row) + "\n")
                continue

            doc = DoclingDocument.load_from_json(doc_path)
            sections = extract_sections(doc)
            header_levels = [s.level for s in sections if s.level > 0]
            levels.update(header_levels)
            all_level_1 += bool(header_levels) and set(header_levels) == {1}
            hierarchized += any(s.parents for s in sections)
            n_sections.append(len(sections))
            cand_f.write(
                json.dumps(
                    {
                        "paper_id": paper_id,
                        "sections": [
                            {
                                "ref": s.ref,
                                "heading": s.heading,
                                "level": s.level,
                                "parents": list(s.parents),
                                "n_chars": len(s.text),
                                "text": s.text,
                            }
                            for s in sections
                        ],
                    }
                )
                + "\n"
            )

            index = SectionIndex(sections, args.ngram)
            for q in by_paper[paper_id]:
                row = label_question(
                    q,
                    index,
                    threshold=args.threshold,
                    min_words=args.min_words,
                    text_evidence_only=args.text_evidence_only,
                )
                status[row["status"]] += 1
                evidence_stats["too_short"] += row["too_short"]
                for m in row["evidence"]:
                    evidence_stats[f"{m['kind']}_total"] += 1
                    evidence_stats[f"{m['kind']}_aligned"] += m["ref"] is not None
                    best_scores.append(m["score"])
                gold_f.write(json.dumps(row) + "\n")

    n_docs = len(n_sections)
    report = {
        "qasper": str(args.qasper),
        "docs": str(args.docs),
        "params": {
            "threshold": args.threshold,
            "ngram": args.ngram,
            "min_words": args.min_words,
            "text_evidence_only": args.text_evidence_only,
        },
        "papers": {
            "in_qasper": len(papers),
            "with_doc": n_docs,
            "missing_doc": len(missing_docs),
            "missing_doc_ids": missing_docs[:50],
        },
        "structure": {
            "mean_sections_per_doc": round(sum(n_sections) / n_docs, 2) if n_docs else 0.0,
            "header_levels": dict(sorted(levels.items())),
            "docs_with_all_headers_level_1": all_level_1,
            "docs_hierarchized": hierarchized,
        },
        "questions": {
            "total": sum(status.values()),
            **dict(status),
            "usable": status["aligned"] + status["partial"],
        },
        "evidence": {
            **dict(evidence_stats),
            "mean_best_score": round(sum(best_scores) / len(best_scores), 4)
            if best_scores
            else 0.0,
        },
    }
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["questions"], indent=2))


if __name__ == "__main__":
    main()
