from qasper import file_stem, is_float_evidence, iter_questions, normalize


def _paper(*answers: dict) -> dict:
    return {
        "1909.00694": {
            "title": "t",
            "abstract": "a",
            "full_text": [{"section_name": "Introduction", "paragraphs": ["p"]}],
            "qas": [
                {
                    "question": "What is proposed?",
                    "question_id": "q1",
                    "answers": [
                        {"answer": a, "annotation_id": str(i)} for i, a in enumerate(answers)
                    ],
                }
            ],
        }
    }


def _answer(evidence: list[str], unanswerable: bool = False) -> dict:
    return {
        "unanswerable": unanswerable,
        "extractive_spans": [],
        "yes_no": None,
        "free_form_answer": "x",
        "evidence": evidence,
        "highlighted_evidence": [],
    }


def test_evidence_is_the_union_of_annotators_in_first_seen_order():
    papers = _paper(_answer(["B", "A"]), _answer(["A", "C"]), _answer([], unanswerable=True))
    (q,) = list(iter_questions(papers))
    assert q.paper_id == "1909.00694"
    assert q.evidence == ("B", "A", "C")
    assert (q.n_annotations, q.n_unanswerable) == (3, 1)


def test_normalize_removes_s2orc_placeholders_and_pdf_artefacts():
    s2orc = "Prior work BIBREF3 uses the classiﬁer of Table TABREF7 (see INLINEFORM0)."
    pdf = "Prior work [3] uses the classi- fier of Table 7 (see x)."
    assert normalize(s2orc) == "prior work uses the classifier of table see"
    assert normalize(pdf) == "prior work 3 uses the classifier of table 7 see x"


def test_float_evidence_prefix_is_detected_and_stripped():
    text = "FLOAT SELECTED: Table 1: Results on the test set."
    assert is_float_evidence(text)
    assert normalize(text) == "table 1 results on the test set"


def test_file_stem_handles_old_style_arxiv_ids():
    assert file_stem("cs/0101001") == "cs_0101001"
    assert file_stem("1909.00694") == "1909.00694"
