#!/usr/bin/env python3
"""
Rebuild the section tree of every document of cases.json and check every case's target_path.

Docling returns all section headers of both papers at level 1, so the hierarchy is rebuilt from
the numbering (1, 1.1, 7.6.1; appendix letters A, B after References). Unnumbered headers found
inside a numbered section (figure column labels, prompt-box titles, the author line) are kept in
the tree but excluded from the options.

A document's source is either a Docling-Studio analysis job (`studio_job`, read from Studio's
SQLite) or a DoclingDocument JSON file (`docling_json`, e.g. written by parse_pdf.py). A document
can list `title_fixes` (OCR misreads corrected against the rendered page).

Usage:
    python3 experiments/laya-nav-test/build_trees.py

Output:
    experiments/laya-nav-test/trees/<doc>.json
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DB_PATH = REPO / "document-parser" / "data" / "docling_studio.db"

NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")
APPENDIX = re.compile(r"^([A-Z])((?:\.\d+)*)\.?\s+\S")
PROSE = {"text", "paragraph", "list_item"}
SNIPPET_CHARS = 400  # extractive stand-in for the per-section summaries docling-agent shows its LLM
TOP_LEVEL_UNNUMBERED = {
    "abstract", "references", "appendix", "acknowledgements", "acknowledgments", "impact statement",
    "ethics statement", "reproducibility statement", "author contributions", "use of generative ai",
}


def load_doc(source: dict) -> dict:
    if "docling_json" in source:
        return json.loads((HERE / source["docling_json"]).read_text())
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT document_json FROM analysis_jobs WHERE id = ?", (source["studio_job"],)).fetchone()
    con.close()
    if row is None or not row[0]:
        sys.exit(f"No document_json for analysis job {source['studio_job']}")
    return json.loads(row[0])


def headers_in_reading_order(doc: dict, title_fixes: dict[str, str]) -> list[dict]:
    """Headers in reading order, each with `snippet`: the first SNIPPET_CHARS of prose that follow it."""
    def resolve(ref: str) -> dict:
        _, kind, idx = ref.split("/")
        return doc[kind][int(idx)]

    def walk(node: dict):
        for child in node.get("children", []):
            item = resolve(child["$ref"])
            yield child["$ref"], item
            yield from walk(item)

    headers = []
    for ref, item in walk(doc["body"]):
        if item.get("label") in ("title", "section_header"):
            prov = item.get("prov") or [{}]
            text = item["text"].strip()
            headers.append({"title": title_fixes.get(text, text), "ref": ref, "page": prov[0].get("page_no"),
                            "docling_level": item.get("level"), "snippet": ""})
        elif headers and item.get("label") in PROSE and len(item.get("text", "")) >= 40:
            snippet = headers[-1]["snippet"]
            if len(snippet) < SNIPPET_CHARS:
                headers[-1]["snippet"] = (snippet + " " + item["text"].strip()).strip()[:SNIPPET_CHARS]
    return headers


def header_level(title: str, after_references: bool) -> int | None:
    if match := NUMBERED.match(title):
        return match.group(1).count(".") + 1
    if after_references and (match := APPENDIX.match(title)):
        return match.group(2).count(".") + 1
    if title.lower().rstrip(".") in TOP_LEVEL_UNNUMBERED:
        return 1
    return None


def build_tree(headers: list[dict]) -> dict:
    """Nest headers by their numbering; the first header is the paper title (Docling labels it section_header)."""
    root = {**headers[0], "children": []}
    stack = [(0, root)]
    after_references = False
    for header in headers[1:]:
        node = {**header, "children": []}
        after_references = after_references or header["title"].lower() == "references"
        level = header_level(header["title"], after_references)
        if level is None:
            node["excluded"] = "unnumbered header inside a numbered section (figure label, prompt box, author line)"
            stack[-1][1]["children"].append(node)
            continue
        while stack[-1][0] >= level:
            stack.pop()
        stack[-1][1]["children"].append(node)
        stack.append((level, node))
    return root


def options(node: dict) -> list[str]:
    return [c["title"] for c in node["children"] if "excluded" not in c]


def walk_path(root: dict, path: list[str]) -> list[dict]:
    if path[0] != root["title"]:
        sys.exit(f"target_path must start at the root {root['title']!r}, got {path[0]!r}")
    nodes = [root]
    for title in path[1:]:
        child = next((c for c in nodes[-1]["children"] if c["title"] == title and "excluded" not in c), None)
        if child is None:
            sys.exit(f"{title!r} is not a child of {nodes[-1]['title']!r}")
        nodes.append(child)
    return nodes


def render(node: dict, depth: int = 0) -> list[str]:
    lines = []
    for child in node["children"]:
        mark = "  (excluded)" if "excluded" in child else ""
        lines.append(f"{'  ' * depth}- {child['title']}  p{child['page']}{mark}")
        lines.extend(render(child, depth + 1))
    return lines


def main() -> None:
    spec = json.loads((HERE / "cases.json").read_text())
    (HERE / "trees").mkdir(exist_ok=True)
    roots = {}
    for doc_id, meta in spec["documents"].items():
        fixes = meta.get("title_fixes", {})
        headers = headers_in_reading_order(load_doc(meta["source"]), fixes)
        roots[doc_id] = root = build_tree(headers)
        tree = {"doc": doc_id, "source": meta["source"], "hierarchy": "rebuilt from section numbering",
                "docling_levels": sorted({str(h["docling_level"]) for h in headers}),
                "title_fixes": fixes, "root": root}
        (HERE / "trees" / f"{doc_id}.json").write_text(json.dumps(tree, indent=2, ensure_ascii=False) + "\n")
        print(f"\n{doc_id}: {root['title']}  ({len(headers)} headers, Docling levels {tree['docling_levels']})")
        print("\n".join(render(root)))

    for case in spec["cases"]:
        nodes = walk_path(roots[case["doc"]], case["target_path"])
        ks = [len(options(n)) for n in nodes[:-1]]
        print(f"{case['id']} {case['type']:16} k per decision {ks}  -> {case['target_path'][-1]}")


if __name__ == "__main__":
    main()
