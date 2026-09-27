#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Score section selectors against gold.jsonl (E1, E3, E5, E6). Standard library only.

A prediction file is JSONL, one line per question; confidence is optional:

    {"question_id": "...", "ranked_refs": ["#/texts/7", "#/texts/3"], "confidence": 0.93}

Per system: hit rate on the first try and within --k tries, against strict and lenient
gold, with 95% Wilson intervals; characters read (with --candidates); and, when
confidence is given, accuracy by coverage, AURC and AUROC. For each pair of systems:
exact McNemar test and a paired bootstrap interval on the difference. A missing
prediction counts as a miss.

--route SMALL:LLM simulates confidence routing (E5): the least confident questions of
SMALL take LLM's pick instead, for shares of 0% to 100% of the questions.

Usage:
    uv run evaluate.py --gold output/hier/gold.jsonl --candidates output/hier/candidates.jsonl \\
        --pred laya=output/hier/laya.jsonl --pred llm=output/hier/llm.jsonl --route laya:llm
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

Z95 = 1.959964


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (centre - half, centre + half)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the discordant counts b and c."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1))
    return min(1.0, 2 * tail / 2**n)


def paired_bootstrap(
    a: list[int], b: list[int], n_boot: int, seed: int
) -> tuple[float, float, float]:
    """Mean of a - b and its 95% percentile interval over question resamples."""
    diffs = [x - y for x, y in zip(a, b, strict=True)]
    n = len(diffs)
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(n_boot))
    lo = means[int(0.025 * (n_boot - 1))]
    hi = means[int(0.975 * (n_boot - 1))]
    return (sum(diffs) / n, lo, hi)


def auroc(scores: list[float], labels: list[int]) -> float | None:
    """Probability that a hit gets a higher confidence than a miss (ties count half)."""
    pos = sum(labels)
    neg = len(labels) - pos
    if pos == 0 or neg == 0:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        for t in range(i, j + 1):
            ranks[order[t]] = (i + j) / 2 + 1
        i = j + 1
    rank_sum = sum(r for r, y in zip(ranks, labels, strict=True) if y)
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def by_confidence(scores: list[float], labels: list[int]) -> list[int]:
    """Labels sorted from the most to the least confident prediction."""
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    return [labels[i] for i in order]


def coverage_table(scores: list[float], labels: list[int]) -> dict:
    ranked = by_confidence(scores, labels)
    n = len(ranked)
    cumulative = 0
    risks = []
    for i, y in enumerate(ranked, start=1):
        cumulative += y
        risks.append(1 - cumulative / i)
    table = {}
    for cov in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        m = max(1, math.ceil(cov * n))
        table[f"{cov:.0%}"] = round(sum(ranked[:m]) / m, 4)
    return {"accuracy_by_coverage": table, "aurc": round(sum(risks) / n, 4)}


class System:
    def __init__(self, name: str, preds: dict[str, dict], gold: list[dict], k: int, chars: dict):
        self.name = name
        self.k = k
        self.missing = 0
        self.top1: list[int] = []
        self.topk: list[int] = []
        self.top1_lenient: list[int] = []
        self.topk_lenient: list[int] = []
        self.conf: list[float | None] = []
        self.chars_top1: list[int] = []
        self.chars_until_hit: list[int] = []
        for g in gold:
            p = preds.get(g["question_id"])
            ranked = list(p.get("ranked_refs") or []) if p else []
            if p is None:
                self.missing += 1
            gold_strict, gold_lenient = set(g["gold"]), set(g["gold_lenient"])
            self.top1.append(int(bool(ranked) and ranked[0] in gold_strict))
            self.topk.append(int(any(r in gold_strict for r in ranked[:k])))
            self.top1_lenient.append(int(bool(ranked) and ranked[0] in gold_lenient))
            self.topk_lenient.append(int(any(r in gold_lenient for r in ranked[:k])))
            self.conf.append(p.get("confidence") if p else None)
            if chars and ranked:
                sizes = [chars.get((g["paper_id"], r), 0) for r in ranked[:k]]
                self.chars_top1.append(sizes[0])
                read = 0
                for r, size in zip(ranked[:k], sizes, strict=True):
                    read += size
                    if r in gold_strict:
                        break
                self.chars_until_hit.append(read)

    def summary(self) -> dict:
        n = len(self.top1)
        out: dict = {"n": n, "missing_predictions": self.missing}
        for key, vec in (
            ("first_try", self.top1),
            (f"within_{self.k}", self.topk),
            ("first_try_lenient", self.top1_lenient),
            (f"within_{self.k}_lenient", self.topk_lenient),
        ):
            k = sum(vec)
            lo, hi = wilson(k, n)
            out[key] = {"rate": round(k / n, 4) if n else 0.0, "ci95": [round(lo, 4), round(hi, 4)]}
        if self.chars_top1:
            out["mean_chars_first_pick"] = round(sum(self.chars_top1) / len(self.chars_top1))
            out["mean_chars_until_hit"] = round(
                sum(self.chars_until_hit) / len(self.chars_until_hit)
            )
        scored = [(c, y) for c, y in zip(self.conf, self.top1, strict=True) if c is not None]
        if scored:
            scores, labels = [c for c, _ in scored], [y for _, y in scored]
            out["confidence"] = {
                "n": len(scored),
                **coverage_table(scores, labels),
                "auroc": None if (a := auroc(scores, labels)) is None else round(a, 4),
            }
        return out


def compare(a: System, b: System, n_boot: int, seed: int) -> dict:
    out = {}
    for key, va, vb in (
        ("first_try", a.top1, b.top1),
        (f"within_{a.k}", a.topk, b.topk),
    ):
        only_a = sum(1 for x, y in zip(va, vb, strict=True) if x and not y)
        only_b = sum(1 for x, y in zip(va, vb, strict=True) if y and not x)
        diff, lo, hi = paired_bootstrap(va, vb, n_boot, seed)
        out[key] = {
            "difference": round(diff, 4),
            "ci95": [round(lo, 4), round(hi, 4)],
            f"only_{a.name}": only_a,
            f"only_{b.name}": only_b,
            "mcnemar_p": mcnemar_exact(only_a, only_b),
        }
    return out


def route(small: System, llm: System) -> list[dict]:
    """Send the least confident questions of `small` to `llm`, in 10% steps."""
    idx = [i for i, c in enumerate(small.conf) if c is not None]
    if not idx:
        return []
    order = sorted(idx, key=lambda i: small.conf[i])  # least confident first
    n = len(order)
    rows = []
    for step in range(11):
        routed = set(order[: round(step / 10 * n)])
        top1 = sum(llm.top1[i] if i in routed else small.top1[i] for i in idx) / n
        topk = sum(llm.topk[i] if i in routed else small.topk[i] for i in idx) / n
        rows.append(
            {
                "share_to_llm": step / 10,
                "first_try": round(top1, 4),
                f"within_{small.k}": round(topk, 4),
            }
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--pred", action="append", required=True, metavar="NAME=PATH")
    ap.add_argument("--candidates", type=Path, help="candidates.jsonl, for characters read")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument(
        "--include-partial",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="keep questions with only part of their evidence aligned",
    )
    ap.add_argument("--route", metavar="SMALL:LLM")
    ap.add_argument("--bootstrap", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    keep = {"aligned", "partial"} if args.include_partial else {"aligned"}
    gold = [g for g in read_jsonl(args.gold) if g.get("status") in keep and g.get("gold")]
    if not gold:
        ap.error(f"no question with aligned gold in {args.gold}")
    chars: dict[tuple[str, str], int] = {}
    if args.candidates:
        for paper in read_jsonl(args.candidates):
            for s in paper["sections"]:
                chars[(paper["paper_id"], s["ref"])] = s["n_chars"]

    systems: dict[str, System] = {}
    for spec in args.pred:
        name, _, path = spec.partition("=")
        preds = {p["question_id"]: p for p in read_jsonl(Path(path))}
        systems[name] = System(name, preds, gold, args.k, chars)

    report: dict = {"n_questions": len(gold), "k": args.k, "systems": {}, "pairs": {}}
    for name, system in systems.items():
        report["systems"][name] = system.summary()
    names = list(systems)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            report["pairs"][f"{a} vs {b}"] = compare(
                systems[a], systems[b], args.bootstrap, args.seed
            )
    if args.route:
        small, _, llm = args.route.partition(":")
        report["routing"] = {
            "small": small,
            "llm": llm,
            "n_with_confidence": sum(c is not None for c in systems[small].conf),
            "curve": route(systems[small], systems[llm]),
        }

    text = json.dumps(report, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
