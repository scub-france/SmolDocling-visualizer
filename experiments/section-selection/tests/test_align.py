import pytest

pytest.importorskip("docling_core")

from sample_docs import hierarchized_paper, paper, ref_of

from align_gold import SectionIndex, label_question
from qasper import Question
from sections import extract_sections

# The Motivation paragraph as S2ORC renders it: citation placeholders, no hyphenation.
MOTIVATION_S2ORC = (
    "Layout analysis and table structure recognition BIBREF4 are the two models that matter "
    "most for faithful conversion of scientific papers into structured documents."
)
UNRELATED = "Our annotators were paid above the minimum wage and could skip any question."


def _question(*evidence: str) -> Question:
    return Question("q1", "p1", "Which models matter most?", evidence, 1, 0)


def _label(doc, *evidence, **kwargs):
    index = SectionIndex(extract_sections(doc), 3)
    params = {"threshold": 0.5, "min_words": 5, "text_evidence_only": False, **kwargs}
    return label_question(_question(*evidence), index, **params)


def test_evidence_is_attributed_to_the_most_specific_section():
    doc = hierarchized_paper()
    row = _label(doc, MOTIVATION_S2ORC)
    assert row["status"] == "aligned"
    assert row["gold"] == [ref_of(doc, "1.1 Motivation")]
    assert ref_of(doc, "1 Introduction") in row["gold_lenient"]


def test_flat_document_has_no_enclosing_sections():
    doc = paper()
    row = _label(doc, MOTIVATION_S2ORC)
    assert row["gold"] == row["gold_lenient"] == [ref_of(doc, "1.1 Motivation")]


def test_unmatched_evidence_makes_the_question_partial_or_unaligned():
    doc = paper()
    assert _label(doc, MOTIVATION_S2ORC, UNRELATED)["status"] == "partial"
    row = _label(doc, UNRELATED)
    assert row["status"] == "unaligned"
    assert row["gold"] == []


def test_short_and_float_evidence_handling():
    doc = paper()
    assert _label(doc, "Yes", MOTIVATION_S2ORC)["too_short"] == 1
    row = _label(doc, "FLOAT SELECTED: Table 2: Scores.", text_evidence_only=True)
    assert row["status"] == "no_evidence"
