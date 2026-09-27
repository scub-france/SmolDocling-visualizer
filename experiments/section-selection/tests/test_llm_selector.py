"""Runs the baseline against a scripted backend: checks the wiring, not a model."""

import ast
import json

import pytest

pytest.importorskip("docling_agent")

from docling_agent.agent.rag import DoclingRAGAgent
from sample_docs import hierarchized_paper, paper, ref_of

from llm_selector import rank_sections, run_loop

_UNVISITED = "Unvisited section refs to choose from: "


class ScriptedSession:
    """Picks the last unvisited ref; can answer once it reads the Method section."""

    def __init__(self, valid: bool):
        self.valid = valid

    def instruct(self, prompt, *, requirements=None, retry_budget=1):
        if _UNVISITED in prompt:
            if not self.valid:
                return "no json here"
            refs = ast.literal_eval(prompt.split(_UNVISITED)[1].split("\n")[0])
            return (
                "```json\n" + json.dumps({"reason": "scripted", "section_ref": refs[-1]}) + "\n```"
            )
        can_answer = "fine-tune a small decision model" in prompt
        return "```json\n" + json.dumps({"can_answer": can_answer, "response": "done"}) + "\n```"

    def debug_context_rows(self):
        return None


class ScriptedBackend:
    def __init__(self, valid: bool = True):
        self.valid = valid

    class models:  # noqa: N801 - mirrors the ModelConfig attribute
        reasoning = writing = "scripted"

    def create_session(self, *, model, system_prompt=None):
        return ScriptedSession(self.valid)


def test_selection_mode_returns_k_distinct_picks_in_order():
    agent = DoclingRAGAgent(tools=[], backend=ScriptedBackend(), max_iterations=3)
    ranked, fallbacks = rank_sections(agent, paper(), "What is the method?", 3)
    assert len(ranked) == len(set(ranked)) == 3
    assert fallbacks == 0


def test_invalid_llm_output_is_counted_as_a_fallback():
    agent = DoclingRAGAgent(tools=[], backend=ScriptedBackend(valid=False), max_iterations=2)
    _, fallbacks = rank_sections(agent, paper(), "What is the method?", 2)
    assert fallbacks == 2


def test_loop_mode_stops_when_the_llm_can_answer():
    doc = hierarchized_paper()
    agent = DoclingRAGAgent(tools=[], backend=ScriptedBackend(), max_iterations=5)
    row = run_loop(agent, doc, "What is the method?")
    assert row["converged"] is True
    assert row["ranked_refs"][-1] == ref_of(doc, "2 Method")
    assert row["answer"] == "done"
