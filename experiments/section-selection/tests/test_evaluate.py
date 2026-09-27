import pytest

from evaluate import (
    System,
    auroc,
    compare,
    coverage_table,
    mcnemar_exact,
    paired_bootstrap,
    route,
    wilson,
)


def test_wilson_interval_matches_the_numbers_sent_to_peter():
    lo, hi = wilson(785, 1309)  # 60% of 1,309
    assert (round(lo, 3), round(hi, 3)) == (0.573, 0.626)


def test_mcnemar_exact():
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(10, 0) == pytest.approx(2 / 1024)
    assert mcnemar_exact(5, 5) == 1.0


def test_auroc():
    assert auroc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]) == 1.0
    assert auroc([0.1, 0.2, 0.8, 0.9], [1, 1, 0, 0]) == 0.0
    assert auroc([0.5, 0.5], [1, 0]) == 0.5
    assert auroc([0.5, 0.6], [1, 1]) is None


def test_coverage_table_keeps_the_most_confident_first():
    table = coverage_table([0.9, 0.8, 0.3, 0.2], [1, 1, 0, 0])
    assert table["accuracy_by_coverage"]["50%"] == 1.0
    assert table["accuracy_by_coverage"]["100%"] == 0.5
    assert table["aurc"] == pytest.approx((0 + 0 + 1 / 3 + 1 / 2) / 4, abs=1e-4)


def test_paired_bootstrap_is_zero_for_identical_systems():
    assert paired_bootstrap([1, 0, 1], [1, 0, 1], 200, 0) == (0.0, 0.0, 0.0)


GOLD = [
    {"question_id": "a", "paper_id": "p", "gold": ["s1"], "gold_lenient": ["s1", "root"]},
    {"question_id": "b", "paper_id": "p", "gold": ["s2"], "gold_lenient": ["s2", "root"]},
    {"question_id": "c", "paper_id": "p", "gold": ["s3"], "gold_lenient": ["s3"]},
]
CHARS = {("p", "s1"): 100, ("p", "s2"): 200, ("p", "s3"): 300, ("p", "root"): 1000}


def test_system_scores_first_try_within_k_lenient_and_characters():
    preds = {
        "a": {"ranked_refs": ["s1"], "confidence": 0.9},
        "b": {"ranked_refs": ["root", "s2"], "confidence": 0.2},
    }  # "c" is missing: a miss
    s = System("small", preds, GOLD, k=5, chars=CHARS)
    summary = s.summary()
    assert summary["missing_predictions"] == 1
    assert summary["first_try"]["rate"] == pytest.approx(1 / 3, abs=1e-4)
    assert summary["within_5"]["rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert summary["first_try_lenient"]["rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert summary["mean_chars_first_pick"] == 550  # (100 + 1000) / 2
    assert summary["mean_chars_until_hit"] == 650  # (100 + 1200) / 2
    assert summary["confidence"]["auroc"] == 1.0


def test_compare_and_route():
    small = System(
        "small",
        {
            "a": {"ranked_refs": ["s1"], "confidence": 0.9},
            "b": {"ranked_refs": ["x"], "confidence": 0.1},
            "c": {"ranked_refs": ["s3"], "confidence": 0.8},
        },
        GOLD,
        k=5,
        chars={},
    )
    llm = System(
        "llm",
        {q: {"ranked_refs": [g]} for q, g in [("a", "x"), ("b", "s2"), ("c", "x")]},
        GOLD,
        5,
        {},
    )
    pair = compare(small, llm, 200, 0)["first_try"]
    assert (pair["only_small"], pair["only_llm"]) == (2, 1)
    curve = route(small, llm)
    assert curve[0]["first_try"] == pytest.approx(2 / 3, abs=1e-4)  # nothing routed
    assert curve[3]["first_try"] == 1.0  # the least confident question goes to the LLM
    assert curve[-1]["first_try"] == pytest.approx(1 / 3, abs=1e-4)  # everything routed
