#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "laya==0.3.20",
# ]
# ///
"""
Compare ways of letting Laya find the section that answers a question, on the frozen cases.json.

Every variant turns a question into the order in which the leaf sections would be opened; its
score on a case is the number of sections opened until the target (1 = first try). docling-agent
stops after 5 iterations, hence "found within 5".

Variants, fixed before running, each testing a hypothesis from the first run:
  D0  descent as in run_test.py: at each node one `choice` among the child titles, state =
      question + path (paper title included). Leaves are opened depth first, children sorted by
      Laya's probability.
  D1  D0 without the paper title in `path` (the title's words looked like attractors).
  D2  D1 with the options shown in 4 orders and the probabilities averaged (position bias:
      Abstract, the main ScreenParse attractor, is always listed first).
  F1  flat: every leaf scored on its own with the demo's RAG relevance question ("Does `passage`
      help answer `query`?"), passage = breadcrumb › title, all leaves in one batched pass, opened
      by decreasing P(true). No hierarchy, as in docling-agent's flat choice.
  F2  F1 plus the first 400 characters of the section's text in the passage, an extractive
      stand-in for the per-section summaries docling-agent shows its LLM.
  B1  BM25 over breadcrumb + title: keyword baseline, no model.
  B2  BM25 over breadcrumb + title + the same 400 characters.
Random opens the leaves in a random order: (L + 1) / 2 openings expected for L leaves.

Usage:
    uv run experiments/laya-nav-test/run_variants.py [--device cpu|mps|cuda]

Output:
    experiments/laya-nav-test/variants.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("USE_TF", "0")  # laya README: TensorFlow probing can deadlock laya.load()

import laya  # noqa: E402

HERE = Path(__file__).resolve().parent
CHECKPOINT = "convaiinnovations/laya"
QID = "next_section"
INSTRUCTIONS = (
    "`path` is where the reader currently is in the paper. "
    "Which of these sections most likely contains the answer to `question`?"
)
RELEVANT = {"relevant": {"type": "noul", "instructions": "Does `passage` help answer `query`?"}}
VARIANTS = ["D0", "D1", "D2", "F1", "F2", "B1", "B2"]
STOPWORDS = set(
    "a an the of in on for to and or is are was were be been by with from at as that this which what "
    "how why when where who does do did can could would should will it its into their there these those "
    "than then so such not no during used use given many much".split()
)


def kids(node: dict) -> list[dict]:
    return [c for c in node["children"] if "excluded" not in c]


def leaves(root: dict) -> list[tuple[tuple[str, ...], dict]]:
    """(breadcrumb without the paper title, node) for every leaf, in document order."""
    out = []

    def walk(node, crumbs):
        if not kids(node) and crumbs:
            out.append((crumbs, node))
        for c in kids(node):
            walk(c, crumbs + (c["title"],))

    walk(root, ())
    return out


def passage(crumbs: tuple[str, ...], node: dict, with_text: bool) -> str:
    text = " › ".join(crumbs)
    return f"{text}: {node['snippet']}" if with_text and node.get("snippet") else text


# --------------------------------------------------------------------------- descent (D0, D1, D2)
def orders(k: int, permute: bool) -> list[list[int]]:
    base = list(range(k))
    if not permute:
        return [base]
    shuffled = []
    for seed in (1, 2):
        s = base[:]
        random.Random(seed).shuffle(s)
        shuffled.append(s)
    return [base, base[::-1]] + shuffled


def choice_probs(agent, state: dict, opts: list[str], permute: bool) -> dict[str, float]:
    total = Counter()
    runs = orders(len(opts), permute)
    for order in runs:
        criteria = [opts[i] for i in order]
        answer = agent.predict(state, {QID: {"type": "choice", "instructions": INSTRUCTIONS, "criteria": criteria}})
        for o, p in answer["answers"][QID]["probabilities"].items():
            total[o] += p / len(runs)
    return dict(total)


def descent_order(agent, root: dict, question: str, with_title: bool, permute: bool) -> list[tuple[str, ...]]:
    order = []

    def visit(node, path):
        children = kids(node)
        if not children:
            order.append(tuple(path[1:]))
            return
        state = {"question": question, "path": path if with_title else path[1:]}
        probs = choice_probs(agent, state, [c["title"] for c in children], permute)
        for c in sorted(children, key=lambda c: -probs[c["title"]]):
            visit(c, path + [c["title"]])

    visit(root, [root["title"]])
    return order


# --------------------------------------------------------------------------- flat (F1, F2, B1, B2)
def flat_scores(agent, question: str, candidates, with_text: bool) -> list[float]:
    states = [{"query": question, "passage": passage(c, n, with_text)} for c, n in candidates]
    return [r["answers"]["relevant"]["noul"] for r in agent.predict_batch(states, RELEVANT)]


def tokens(text: str) -> list[str]:
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS]
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words]


def bm25(question: str, texts: list[str], k1: float = 1.2, b: float = 0.75) -> list[float]:
    docs = [tokens(t) for t in texts]
    avgdl = sum(len(d) for d in docs) / len(docs) or 1.0
    df = Counter(w for d in docs for w in set(d))
    scores = []
    for d in docs:
        tf, s = Counter(d), 0.0
        for w in tokens(question):
            if w in tf:
                idf = math.log(1 + (len(docs) - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(d) / avgdl))
        scores.append(s)
    return scores


def attempts_from_scores(scores: list[float], target: int) -> float:
    """Openings until the target when opening by decreasing score; ties are opened in random order."""
    t = scores[target]
    higher = sum(s > t for s in scores)
    tied = sum(s == t for s in scores)
    return 1 + higher + (tied - 1) / 2


# --------------------------------------------------------------------------- metrics
def auroc(pairs: list[tuple[float, bool]]) -> float | None:
    right = [s for s, ok in pairs if ok]
    wrong = [s for s, ok in pairs if not ok]
    if not right or not wrong:
        return None
    wins = sum((a > b) + 0.5 * (a == b) for a in right for b in wrong)
    return round(wins / (len(right) * len(wrong)), 4)


def summarize(rows: list[dict], key: str) -> dict:
    values = [r["attempts"][key] for r in rows]
    return {
        "mean_attempts": round(sum(values) / len(values), 2),
        "found_1": sum(v <= 1 for v in values),
        "found_3": sum(v <= 3 for v in values),
        "found_5": sum(v <= 5 for v in values),
        "cases": len(values),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--device", help="cpu, mps or cuda (default: laya picks)")
    args = parser.parse_args()

    cases_bytes = (HERE / "cases.json").read_bytes()
    spec = json.loads(cases_bytes)
    trees = {d: json.loads((HERE / "trees" / f"{d}.json").read_text())["root"] for d in spec["documents"]}
    agent = laya.load(CHECKPOINT, device=args.device)
    agent.predict({"query": "warm-up", "passage": "warm-up"}, RELEVANT)

    rows = []
    for case in spec["cases"]:
        root, q = trees[case["doc"]], case["question"]
        candidates = leaves(root)
        crumbs = [c for c, _ in candidates]
        target = next(i for i, (c, _) in enumerate(candidates) if c[-1] == case["target_path"][-1])
        row = {"case": case["id"], "doc": case["doc"], "type": case["type"], "leaves": len(candidates),
               "target": " › ".join(crumbs[target]), "attempts": {}, "first": {}, "ms": {}}

        for key, with_title, permute in (("D0", True, False), ("D1", False, False), ("D2", False, True)):
            start = time.perf_counter()
            order = descent_order(agent, root, q, with_title, permute)
            row["ms"][key] = round((time.perf_counter() - start) * 1000, 1)
            row["attempts"][key] = order.index(crumbs[target]) + 1
            row["first"][key] = " › ".join(order[0])

        for key, with_text in (("F1", False), ("F2", True)):
            start = time.perf_counter()
            scores = flat_scores(agent, q, candidates, with_text)
            row["ms"][key] = round((time.perf_counter() - start) * 1000, 1)
            row["attempts"][key] = attempts_from_scores(scores, target)
            top = max(range(len(scores)), key=lambda i: scores[i])
            row["first"][key] = " › ".join(crumbs[top])
            row[f"{key}_top_p"], row[f"{key}_target_p"] = scores[top], scores[target]
            row[f"{key}_scores"] = {" › ".join(c): s for c, s in zip(crumbs, scores)}

        for key, with_text in (("B1", False), ("B2", True)):
            scores = bm25(q, [passage(c, n, with_text) for c, n in candidates])
            row["attempts"][key] = attempts_from_scores(scores, target)
            top = max(range(len(scores)), key=lambda i: scores[i])
            row["first"][key] = " › ".join(crumbs[top]) if scores[top] > 0 else "(no keyword match)"

        row["attempts"]["random"] = (len(candidates) + 1) / 2
        rows.append(row)
        print(case["id"], {k: row["attempts"][k] for k in VARIANTS + ["random"]})

    keys = VARIANTS + ["random"]
    metrics = {
        "overall": {k: summarize(rows, k) for k in keys},
        "by_type": {t: {k: summarize([r for r in rows if r["type"] == t], k) for k in keys}
                    for t in sorted({r["type"] for r in rows})},
        "by_doc": {d: {k: summarize([r for r in rows if r["doc"] == d], k) for k in keys}
                   for d in sorted({r["doc"] for r in rows})},
        "random_found": {n: round(sum(min(1, n / r["leaves"]) for r in rows), 2) for n in (1, 3, 5)},
        "auroc_top_p_first_try": {k: auroc([(r[f"{k}_top_p"], r["attempts"][k] <= 1) for r in rows]) for k in ("F1", "F2")},
    }
    out = {
        "meta": {"checkpoint": CHECKPOINT, "laya": laya.__version__, "device": str(agent.device),
                 "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "cases_sha256": hashlib.sha256(cases_bytes).hexdigest(), "relevance_question": RELEVANT},
        "metrics": metrics,
        "cases": rows,
    }
    (HERE / "variants.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"\n{'variant':8} {'mean':>6} {'@1':>4} {'@3':>4} {'@5':>4}")
    for k in keys:
        s = metrics["overall"][k]
        print(f"{k:8} {s['mean_attempts']:>6} {s['found_1']:>4} {s['found_3']:>4} {s['found_5']:>4}")
    print("random expected found@1/3/5:", metrics["random_found"])
    print("AUROC top P(true) -> first try right:", metrics["auroc_top_p_first_try"])
    print(f"wrote {HERE / 'variants.json'}")


if __name__ == "__main__":
    main()
