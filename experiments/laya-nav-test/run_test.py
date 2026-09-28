#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "laya==0.3.20",
# ]
# ///
"""
Run the Laya navigation test on cases.json (brief steps 4 and 5) and save the raw outputs.

1. Node by node: at every node of a case's target_path, Laya picks one child section. The correct
   path is always followed, so each decision is scored on its own.
2. History: a wrong decision is replayed with 'Branch "<choice>" was explored, the answer was not
   found there.' added to the state.
3. Greedy walk: Laya descends from the root on its own, always taking its top choice.

Trees come from build_trees.py. Checkpoint: convaiinnovations/laya (English root, ~808 MB,
downloaded on first run).

Usage:
    uv run experiments/laya-nav-test/run_test.py [--device cpu|mps|cuda] [--repeats 5]
    uv run experiments/laya-nav-test/run_test.py --doc unfolding --ask "Which GPUs were used?"

Output:
    experiments/laya-nav-test/results.json (not written with --ask)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("USE_TF", "0")  # laya README: TensorFlow probing can deadlock laya.load()

import laya  # noqa: E402
import torch  # noqa: E402
from laya.common import QTYPES, temp_bucket  # noqa: E402

HERE = Path(__file__).resolve().parent
CHECKPOINT = "convaiinnovations/laya"
QID = "next_section"
INSTRUCTIONS = (
    "`path` is where the reader currently is in the paper. "
    "Which of these sections most likely contains the answer to `question`?"
)


def options(node: dict) -> list[str]:
    return [c["title"] for c in node["children"] if "excluded" not in c]


def child(node: dict, title: str) -> dict:
    return next(c for c in node["children"] if "excluded" not in c and c["title"] == title)


def budget(agent, state: dict, opts: list[str]) -> dict:
    """Mirror of laya.common.build_sequence: options + instructions share head_max_len, the state gets the rest."""
    def encode(text: str, **kwargs) -> list[int]:
        return agent.tok(text, add_special_tokens=False, **kwargs)["input_ids"]

    head_max_len, max_len = agent.cfg["head_max_len"], agent.cfg["max_len"]
    instruction_tokens = len(encode(f"choice question: {INSTRUCTIONS}"))
    option_tokens = sum(1 + len(encode(" " + o, truncation=True, max_length=48)) for o in opts)
    head_room = head_max_len - option_tokens
    state_tokens = len(encode(json.dumps(state, ensure_ascii=False)))
    total = 2 + min(instruction_tokens, max(8, head_room)) + option_tokens + 1 + state_tokens + 1
    return {"instruction_tokens": instruction_tokens, "option_tokens": option_tokens, "state_tokens": state_tokens,
            "total": total, "ok": head_room >= 16 and instruction_tokens <= head_room and total <= max_len}


def ask(agent, state: dict, opts: list[str], repeats: int) -> dict:
    """One choice question; latency is the median over `repeats` identical calls."""
    questions = {QID: {"type": "choice", "instructions": INSTRUCTIONS, "criteria": opts}}
    timings = []
    for _ in range(repeats):
        start = time.perf_counter()
        answer = agent.predict(state, questions)["answers"][QID]
        timings.append((time.perf_counter() - start) * 1000)
    bucket = temp_bucket(QTYPES["choice"], len(opts))
    return {
        "choice": answer["choice"],
        "probabilities": answer["probabilities"],
        "confidence": answer["confidence"],
        "answer_confidence": answer["answer_confidence"],
        "bucket": bucket.split(":")[1],
        "temperature": agent.temperature_by_options.get(bucket, agent.temperature[QTYPES["choice"]]),
        "latency_ms": round(statistics.median(timings), 1),
    }


def score(out: dict, opts: list[str], expected: str) -> dict:
    ranked = sorted(opts, key=lambda o: -out["probabilities"][o])
    return {
        "k": len(opts),
        "chance": round(1 / len(opts), 4),
        "expected": expected,
        "correct": out["choice"] == expected,
        "expected_rank": ranked.index(expected) + 1,
        "p_expected": out["probabilities"][expected],
        **out,
    }


def node_by_node(agent, trees: dict, cases: list[dict], repeats: int) -> tuple[list[dict], list[dict]]:
    rows, replays = [], []
    for case in cases:
        node = trees[case["doc"]]
        for i, expected in enumerate(case["target_path"][1:], 1):
            opts = options(node)
            state = {"question": case["question"], "path": case["target_path"][:i]}
            row = {"case": case["id"], "doc": case["doc"], "type": case["type"], "step": i, "node": node["title"],
                   "state": state, "budget": budget(agent, state, opts),
                   **score(ask(agent, state, opts, repeats), opts, expected)}
            rows.append(row)
            if not row["correct"]:
                history = f'Branch "{row["choice"]}" was explored, the answer was not found there.'
                replay_state = {**state, "history": [history]}
                replays.append({"case": case["id"], "step": i, "node": node["title"], "first_choice": row["choice"],
                                "state": replay_state, **score(ask(agent, replay_state, opts, repeats), opts, expected)})
            node = child(node, expected)
    return rows, replays


def greedy_walk(agent, root: dict, question: str) -> dict:
    node, path, steps = root, [root["title"]], []
    while opts := options(node):
        out = ask(agent, {"question": question, "path": list(path)}, opts, repeats=1)
        steps.append({"node": node["title"], "options": opts, **out})
        node = child(node, out["choice"])
        path.append(node["title"])
    return {"question": question, "path": path, "steps": steps}


def mean(values) -> float | None:
    values = list(values)
    return round(sum(values) / len(values), 4) if values else None


def auroc(rows: list[dict], key: str) -> float | None:
    """Probability that a right decision carries a higher `key` than a wrong one (ties count half)."""
    right = [r[key] for r in rows if r["correct"]]
    wrong = [r[key] for r in rows if not r["correct"]]
    if not right or not wrong:
        return None
    wins = sum((a > b) + 0.5 * (a == b) for a in right for b in wrong)
    return round(wins / (len(right) * len(wrong)), 4)


def summary(rows: list[dict]) -> dict:
    right = [r for r in rows if r["correct"]]
    wrong = [r for r in rows if not r["correct"]]
    return {
        "decisions": len(rows),
        "correct": len(right),
        "top1": mean(r["correct"] for r in rows),
        "chance_mean": mean(r["chance"] for r in rows),
        "top2": mean(r["expected_rank"] <= 2 for r in rows),
        "answer_confidence_correct": mean(r["answer_confidence"] for r in right),
        "answer_confidence_wrong": mean(r["answer_confidence"] for r in wrong),
        "confidence_correct": mean(r["confidence"] for r in right),
        "confidence_wrong": mean(r["confidence"] for r in wrong),
        "auroc_answer_confidence": auroc(rows, "answer_confidence"),
        "auroc_confidence": auroc(rows, "confidence"),
    }


def metrics(rows: list[dict], replays: list[dict], walks: list[dict], cases: list[dict]) -> dict:
    def group(key: str) -> dict:
        return {v: summary([r for r in rows if r[key] == v]) for v in sorted({r[key] for r in rows})}

    return {
        "overall": summary(rows),
        "by_doc": group("doc"),
        "by_type": group("type"),
        "by_bucket": group("bucket"),
        "by_step": group("step"),
        "full_paths_correct": mean(all(r["correct"] for r in rows if r["case"] == c["id"]) for c in cases),
        "greedy_reaches_target": mean(w["path"][-1] == c["target_path"][-1] for w, c in zip(walks, cases)),
        "history_replays": len(replays),
        "history_replays_fixed": sum(r["correct"] for r in replays),
        "history_choice_unchanged": sum(r["choice"] == r["first_choice"] for r in replays),
        "budget_all_ok": all(r["budget"]["ok"] for r in rows),
        "latency_ms_mean": mean(r["latency_ms"] for r in rows),
    }


def print_walk(walk: dict) -> None:
    print(f"\n{walk['question']}")
    for step in walk["steps"]:
        top = sorted(step["probabilities"].items(), key=lambda kv: -kv[1])[:3]
        print(f"  at {step['node'][:50]!r} (k={len(step['options'])}, max p {step['answer_confidence']:.2f})")
        for title, p in top:
            print(f"    {'→' if title == step['choice'] else ' '} {p:.3f}  {title}")
    print(f"  ends at {walk['path'][-1]!r}")


def print_summary(results: dict) -> None:
    print(f"\n{'decision':9} {'k':>2} {'ok':2} {'p(exp)':>6} {'rank':>4} {'maxp':>5} {'conf':>5} {'ms':>5}  expected → choice")
    for r in results["decisions"]:
        print(f"{r['case']}.{r['step']:<6} {r['k']:>2} {'✓' if r['correct'] else '✗':2} {r['p_expected']:>6.3f} "
              f"{r['expected_rank']:>4} {r['answer_confidence']:>5.2f} {r['confidence']:>5.2f} {r['latency_ms']:>5.1f}  "
              f"{r['expected']} → {r['choice']}")
    for r in results["history_replays"]:
        print(f"history {r['case']}.{r['step']}: {r['first_choice']!r} explored → {r['choice']!r} "
              f"({'fixed' if r['correct'] else 'still wrong'}, p(expected) {r['p_expected']:.3f})")
    for case, walk in zip(results["cases"], results["greedy_walks"]):
        ok = "✓" if walk["path"][-1] == case["target_path"][-1] else "✗"
        print(f"greedy {case['id']} {ok}: " + " › ".join(walk["path"][1:]))
    print(json.dumps(results["metrics"], indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--device", help="cpu, mps or cuda (default: laya picks)")
    parser.add_argument("--repeats", type=int, default=5, help="calls per decision, latency is the median")
    parser.add_argument("--ask", help="greedy walk for this question, printed only")
    parser.add_argument("--doc", default="screenparse", help="document for --ask (a key of cases.json documents)")
    args = parser.parse_args()

    cases_bytes = (HERE / "cases.json").read_bytes()
    spec = json.loads(cases_bytes)
    trees = {d: json.loads((HERE / "trees" / f"{d}.json").read_text())["root"] for d in spec["documents"]}

    agent = laya.load(CHECKPOINT, device=args.device)
    first = next(iter(trees.values()))
    ask(agent, {"question": "warm-up", "path": [first["title"]]}, options(first), repeats=2)

    if args.ask:
        print_walk(greedy_walk(agent, trees[args.doc], args.ask))
        return

    cases = spec["cases"]
    rows, replays = node_by_node(agent, trees, cases, args.repeats)
    walks = [greedy_walk(agent, trees[case["doc"]], case["question"]) for case in cases]
    results = {
        "meta": {
            "checkpoint": CHECKPOINT,
            "laya": laya.__version__,
            "torch": torch.__version__,
            "device": str(agent.device),
            "machine": f"{platform.system()} {platform.machine()}",
            "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "repeats": args.repeats,
            "cases_sha256": hashlib.sha256(cases_bytes).hexdigest(),
            "instructions": INSTRUCTIONS,
            "temperature_by_options_applied": agent.temperature_by_options,
            "temperature_by_options_shipped": agent.temperature_by_options_raw,
        },
        "documents": spec["documents"],
        "cases": cases,
        "metrics": metrics(rows, replays, walks, cases),
        "decisions": rows,
        "history_replays": replays,
        "greedy_walks": walks,
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    print_summary(results)
    print(f"\nwrote {HERE / 'results.json'}")


if __name__ == "__main__":
    main()
