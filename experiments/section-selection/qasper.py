"""Qasper loading and evidence normalisation (standard library only).

A Qasper split file (https://allenai.org/data/qasper) maps an arXiv id to
``{title, abstract, full_text: [{section_name, paragraphs}], qas: [...]}``. Each qa
holds ``question_id``, ``question`` and ``answers``; each answer holds
``answer.{unanswerable, evidence, ...}``. Figure and table evidence starts with
``FLOAT SELECTED`` (same convention as the official evaluator in
allenai/qasper-led-baseline, ``scripts/evaluator.py``).
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

FLOAT_PREFIX = "FLOAT SELECTED"

# S2ORC replaces citations, cross-references and formulas with placeholders
# (BIBREF3, FIGREF0, INLINEFORM1, ...). A PDF parse has the rendered text instead.
_PLACEHOLDER = re.compile(r"\b(?:BIBREF|FIGREF|TABREF|SECREF|INLINEFORM|DISPLAYFORM)\d+\b")
_LINE_BREAK_HYPHEN = re.compile(r"(\w)-\s+(\w)")
_NON_WORD = re.compile(r"[^0-9a-z]+")


@dataclass(frozen=True)
class Question:
    question_id: str
    paper_id: str
    question: str
    # Union of the annotators' evidence, deduplicated, first-seen order.
    evidence: tuple[str, ...]
    n_annotations: int
    n_unanswerable: int


def file_stem(paper_id: str) -> str:
    """File name for a paper id; old-style arXiv ids contain a slash."""
    return paper_id.replace("/", "_")


def load_papers(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def iter_questions(papers: dict[str, dict]) -> Iterator[Question]:
    for paper_id, paper in papers.items():
        for qa in paper.get("qas", []):
            evidence: list[str] = []
            n_unanswerable = 0
            for annotation in qa.get("answers", []):
                answer = annotation["answer"]
                if answer.get("unanswerable"):
                    n_unanswerable += 1
                    continue
                for text in answer.get("evidence", []):
                    if text and text not in evidence:
                        evidence.append(text)
            yield Question(
                question_id=qa["question_id"],
                paper_id=paper_id,
                question=qa["question"],
                evidence=tuple(evidence),
                n_annotations=len(qa.get("answers", [])),
                n_unanswerable=n_unanswerable,
            )


def is_float_evidence(text: str) -> bool:
    return text.startswith(FLOAT_PREFIX)


def normalize(text: str) -> str:
    """Lower-case ASCII word stream, comparable between S2ORC text and a PDF parse."""
    if text.startswith(FLOAT_PREFIX):
        text = text[len(FLOAT_PREFIX) :].lstrip(": ")
    text = _PLACEHOLDER.sub(" ", text)
    # NFKD splits ligatures (U+FB01 -> "fi") and accents; the ASCII pass drops the marks.
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    # Words hyphenated across a PDF line break: "repre- sentation" -> "representation".
    text = _LINE_BREAK_HYPHEN.sub(r"\1\2", text)
    return " ".join(_NON_WORD.sub(" ", text.lower()).split())
