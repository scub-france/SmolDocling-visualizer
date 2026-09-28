#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "laya==0.3.20",
# ]
# ///
"""
Evaluate section scorers on held-out Qasper questions and on the 13 hand-checked cases.

For each question every section of its paper is scored, and sections are opened by decreasing
score. Found within k: one of the question's evidence sections is among the first k opened.
The 13 cases (ScreenParse and Unfolding, Docling trees from ../trees) never enter training; they
check transfer from Qasper's S2ORC sections to Docling structure.

Scorers (repeat --scorer):
    laya:<hub id or checkpoint dir>   P(true) of the F2 relevance question
    granite                           ibm-granite/granite-embedding-reranker-english-r2 logit
    bm25                              keyword baseline on the same passages
Random order is reported analytically.

Usage:
    uv run experiments/laya-nav-test/finetune/evaluate.py --scorer laya:convaiinnovations/laya --scorer bm25 --name zero-shot
    uv run experiments/laya-nav-test/finetune/evaluate.py --scorer laya:checkpoints/qasper-v1 --name finetuned

Output:
    experiments/laya-nav-test/finetune/results/<name>.json
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("USE_TF", "0")  # laya README: TensorFlow probing can deadlock laya.load()

import torch  # noqa: E402

from shared import RELEVANT, attempts, auroc, bm25, ece, passage, random_attempts, random_found  # noqa: E402

HERE = Path(__file__).resolve().parent
NAV = HERE.parent
GRANITE = "ibm-granite/granite-embedding-reranker-english-r2"


def qasper_questions(split: str, limit: int | None, seed: int) -> list[dict]:
    rows = [json.loads(line) for line in (HERE / "data" / f"{split}.questions.jsonl").open()]
    if limit and limit < len(rows):
        rows = random.Random(seed).sample(rows, limit)
    return [{"id": r["question_id"], "question": r["question"], "passages": r["passages"],
             "targets": {i for i, v in enumerate(r["relevance"]) if v > 0}} for r in rows]


def hand_cases() -> list[dict]:
    """The 13 cases of ../cases.json over the Docling trees, passages built as in run_variants.py (F2)."""
    spec = json.loads((NAV / "cases.json").read_text())
    trees = {d: json.loads((NAV / "trees" / f"{d}.json").read_text())["root"] for d in spec["documents"]}

    def leaves(node, crumbs=()):
        kids = [c for c in node["children"] if "excluded" not in c]
        if not kids and crumbs:
            yield list(crumbs), node
        for c in kids:
            yield from leaves(c, crumbs + (c["title"],))

    out = []
    for case in spec["cases"]:
        cand = list(leaves(trees[case["doc"]]))
        target = next(i for i, (c, _) in enumerate(cand) if c[-1] == case["target_path"][-1])
        out.append({"id": case["id"], "question": case["question"],
                    "passages": [passage(c, n.get("snippet", "")) for c, n in cand], "targets": {target}})
    return out


class LayaScorer:
    def __init__(self, ref: str, device: str | None):
        import laya

        path = HERE / ref
        self.agent = laya.load(str(path) if path.exists() else ref, device=device)
        self.name = f"laya:{ref}"
        self.calibrated = True

    def __call__(self, question: str, passages: list[str]) -> list[float]:
        states = [{"query": question, "passage": p} for p in passages]
        return [r["answers"]["relevant"]["noul"] for r in self.agent.predict_batch(states, RELEVANT)]


class GraniteScorer:
    def __init__(self, device: str | None):
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"))
        self.model = AutoModelForSequenceClassification.from_pretrained(GRANITE).eval().to(self.device)
        self.tok = AutoTokenizer.from_pretrained(GRANITE)
        self.name = "granite"
        self.calibrated = False

    @torch.no_grad()
    def __call__(self, question: str, passages: list[str]) -> list[float]:
        batch = self.tok([[question, p] for p in passages], padding=True, truncation=True, max_length=512, return_tensors="pt")
        return self.model(**batch.to(self.device)).logits.view(-1).float().cpu().tolist()


class BM25Scorer:
    name = "bm25"
    calibrated = False

    def __call__(self, question: str, passages: list[str]) -> list[float]:
        return bm25(question, passages)


def evaluate(scorer, questions: list[dict], duty_cycle: float = 1.0) -> dict:
    rows, compute = [], 0.0
    for q in questions:
        start = time.perf_counter()
        scores = scorer(q["question"], q["passages"])
        spent = time.perf_counter() - start
        compute += spent
        if duty_cycle < 1:
            time.sleep(spent * (1 - duty_cycle) / duty_cycle)
        top = max(range(len(scores)), key=lambda i: scores[i])
        rows.append({"id": q["id"], "sections": len(scores), "targets": len(q["targets"]),
                     "attempts": attempts(scores, q["targets"]), "top_score": scores[top]})
    n = len(rows)
    summary = {
        "questions": n,
        "found_1": sum(r["attempts"] <= 1 for r in rows) / n,
        "found_3": sum(r["attempts"] <= 3 for r in rows) / n,
        "found_5": sum(r["attempts"] <= 5 for r in rows) / n,
        "mean_attempts": sum(r["attempts"] for r in rows) / n,
        "mrr": sum(1 / r["attempts"] for r in rows) / n,
        "seconds": round(compute, 1),
    }
    if scorer.calibrated:  # P(true) of the section opened first, against "that section was right"
        pairs = [(r["top_score"], r["attempts"] <= 1) for r in rows]
        summary["auroc_top_p"] = auroc(pairs)
        summary["ece_top_p"] = ece(pairs)
        summary["mean_top_p"] = sum(p for p, _ in pairs) / n
    return {"summary": summary, "rows": rows}


def random_baseline(questions: list[dict]) -> dict:
    n = len(questions)
    sizes = [(len(q["passages"]), len(q["targets"])) for q in questions]
    return {"summary": {
        "questions": n,
        "found_1": sum(random_found(L, t, 1) for L, t in sizes) / n,
        "found_3": sum(random_found(L, t, 3) for L, t in sizes) / n,
        "found_5": sum(random_found(L, t, 5) for L, t in sizes) / n,
        "mean_attempts": sum(random_attempts(L, t) for L, t in sizes) / n,
    }}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scorer", action="append", required=True, help="laya:<ref>, granite or bm25")
    parser.add_argument("--split", default="test", help="Qasper split to evaluate (test or validation)")
    parser.add_argument("--max-questions", type=int, help="random subset of Qasper questions, for quick runs")
    parser.add_argument("--device", help="cuda, mps or cpu (default: best available)")
    parser.add_argument("--name", default="eval", help="results file name")
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--duty-cycle", type=float, default=1.0,
                        help="share of wall time spent computing; below 1 the run pauses after each question")
    args = parser.parse_args()

    datasets = {f"qasper_{args.split}": qasper_questions(args.split, args.max_questions, args.seed), "hand_13": hand_cases()}
    results = {"meta": {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "split": args.split,
                        "max_questions": args.max_questions, "seed": args.seed, "relevance_question": RELEVANT},
               "datasets": {d: {"random": random_baseline(qs)} for d, qs in datasets.items()}}
    for ref in args.scorer:
        if ref.startswith("laya:"):
            scorer = LayaScorer(ref.split(":", 1)[1], args.device)
        elif ref == "granite":
            scorer = GraniteScorer(args.device)
        elif ref == "bm25":
            scorer = BM25Scorer()
        else:
            raise SystemExit(f"unknown scorer {ref!r}")
        for dname, qs in datasets.items():
            res = evaluate(scorer, qs, args.duty_cycle)
            results["datasets"][dname][scorer.name] = res
            s = res["summary"]
            extra = f" | AUROC {s['auroc_top_p']:.2f} ECE {s['ece_top_p']:.2f}" if "auroc_top_p" in s and s["auroc_top_p"] is not None else ""
            print(f"{dname:14} {scorer.name:40} @1 {s['found_1']:.3f} @3 {s['found_3']:.3f} @5 {s['found_5']:.3f} "
                  f"mean {s['mean_attempts']:.2f} ({s['questions']} q, {s['seconds']}s){extra}", flush=True)
    for dname in datasets:
        s = results["datasets"][dname]["random"]["summary"]
        print(f"{dname:14} {'random':40} @1 {s['found_1']:.3f} @3 {s['found_3']:.3f} @5 {s['found_5']:.3f} mean {s['mean_attempts']:.2f}")

    (HERE / "results").mkdir(exist_ok=True)
    out = HERE / "results" / f"{args.name}.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
