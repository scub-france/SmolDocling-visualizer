"""Helpers shared by build_qasper.py, train.py and evaluate.py (standard library only).

The relevance question and the passage format are the F2 variant of ../run_variants.py, so the
fine-tuned model is asked exactly what the zero-shot model was asked.
"""
from __future__ import annotations

import math
import re
from collections import Counter

RELEVANT = {"relevant": {"type": "noul", "instructions": "Does `passage` help answer `query`?"}}
SNIPPET_CHARS = 400
STOPWORDS = set(
    "a an the of in on for to and or is are was were be been by with from at as that this which what "
    "how why when where who does do did can could would should will it its into their there these those "
    "than then so such not no during used use given many much".split()
)


def passage(crumbs: list[str], text: str) -> str:
    """'Section › Subsection: first SNIPPET_CHARS characters of the section text'."""
    head = " › ".join(crumbs)
    snippet = " ".join(text.split())[:SNIPPET_CHARS]
    return f"{head}: {snippet}" if snippet else head


def tokens(text: str) -> list[str]:
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS]
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words]


def bm25(question: str, texts: list[str], k1: float = 1.2, b: float = 0.75) -> list[float]:
    docs = [tokens(t) for t in texts]
    avgdl = sum(len(d) for d in docs) / max(1, len(docs)) or 1.0
    df = Counter(w for d in docs for w in set(d))
    query = tokens(question)
    scores = []
    for d in docs:
        tf, s = Counter(d), 0.0
        for w in query:
            if w in tf:
                idf = math.log(1 + (len(docs) - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(d) / avgdl))
        scores.append(s)
    return scores


def attempts(scores: list[float], targets: set[int]) -> float:
    """Sections opened until the first target, opening by decreasing score; ties in random order."""
    best = max(scores[t] for t in targets)
    higher = sum(s > best for s in scores)
    tied = [i for i, s in enumerate(scores) if s == best]
    tied_targets = sum(i in targets for i in tied)
    return higher + (len(tied) + 1) / (tied_targets + 1)


def random_attempts(n: int, t: int) -> float:
    return (n + 1) / (t + 1)


def random_found(n: int, t: int, k: int) -> float:
    """Probability that a random order puts one of t targets among the first k of n sections."""
    if k >= n:
        return 1.0
    return 1.0 - math.comb(n - t, k) / math.comb(n, k)


def auroc(pairs: list[tuple[float, bool]]) -> float | None:
    right = [s for s, ok in pairs if ok]
    wrong = [s for s, ok in pairs if not ok]
    if not right or not wrong:
        return None
    wins = sum((a > b) + 0.5 * (a == b) for a in right for b in wrong)
    return wins / (len(right) * len(wrong))


def ece(pairs: list[tuple[float, bool]], bins: int = 10) -> float | None:
    """Expected calibration error of a confidence against a hit, equal-width bins."""
    if not pairs:
        return None
    total, err = len(pairs), 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(c, ok) for c, ok in pairs if lo <= c < hi or (b == bins - 1 and c == 1.0)]
        if sel:
            err += len(sel) / total * abs(sum(c for c, _ in sel) / len(sel) - sum(ok for _, ok in sel) / len(sel))
    return err
