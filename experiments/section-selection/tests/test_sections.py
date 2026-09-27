import pytest

pytest.importorskip("docling_core")

from sample_docs import INTRO, MOTIVATION, hierarchized_paper, paper, ref_of

from sections import agent_section_text, extract_sections


def test_flat_document_sections_stop_at_the_next_heading():
    doc = paper()
    sections = {s.heading: s for s in extract_sections(doc)}
    assert list(sections) == [
        "A Small Model for Section Selection",
        "Abstract",
        "1 Introduction",
        "1.1 Motivation",
        "2 Method",
    ]
    intro = sections["1 Introduction"]
    assert intro.text == f"1 Introduction\n\n{INTRO}"
    assert intro.own_text == intro.text
    assert intro.parents == ()
    assert sections["A Small Model for Section Selection"].level == 0


def test_hierarchized_document_nests_subsections_in_the_parent_text():
    doc = hierarchized_paper()
    sections = {s.heading: s for s in extract_sections(doc)}
    intro, motivation = sections["1 Introduction"], sections["1.1 Motivation"]
    assert MOTIVATION in intro.text  # docling-agent hands the whole subtree to the LLM
    assert MOTIVATION not in intro.own_text  # evidence goes to the most specific section
    assert motivation.parents[-1] == ref_of(doc, "1 Introduction")


@pytest.mark.parametrize("make_doc", [paper, hierarchized_paper])
def test_parity_with_docling_agent(make_doc):
    rag = pytest.importorskip("docling_agent.agent.rag")
    agent = rag.DoclingRAGAgent.__new__(rag.DoclingRAGAgent)  # no backend needed
    agent.use_page_level = False
    doc = make_doc()
    sections = extract_sections(doc)
    assert {s.ref for s in sections} == agent._extract_section_refs(doc)
    for s in sections:
        assert s.text == agent._get_section_content(doc, s.ref)
        assert agent_section_text(doc, s.ref) == s.text
