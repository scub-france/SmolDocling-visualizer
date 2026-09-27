#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "docling>=2.129.0",
# ]
# ///
"""Fetch the arXiv PDFs of Qasper papers and convert them with Docling (E1, E2).

Two variants per paper:

    flat  Docling's default PDF conversion: every heading at level 1, flat tree.
    hier  heading-hierarchy inference on (HeadingHierarchyOptions: PDF bookmarks, then
          numbering, then font style), then the tree rebuilt from those levels with
          DoclingDocument._hierarchize(), as docling-agent's perfs/agentic_rag_eval.py does.

Layout under --out:

    pdfs/<paper_id>.pdf
    docling/<variant>/<paper_id>.json
    manifest.json    library versions, options and per-paper status

Qasper's text comes from the papers' LaTeX sources (S2ORC); the PDF fetched here is
arXiv's current version, which can differ. align_gold.py reports how much evidence
it could match. Re-running skips what is already on disk.

Usage:
    uv run build_docling_corpus.py --qasper data/qasper/test.json --out data --limit 20
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import HeadingHierarchyOptions, PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

from qasper import file_stem, load_papers

VARIANTS = ("flat", "hier")
USER_AGENT = "docling-studio-section-selection/0.1 (research experiment)"


def fetch_pdf(paper_id: str, dest: Path, url_template: str, timeout: float) -> str:
    if dest.exists() and dest.stat().st_size > 0:
        return "cached"
    request = urllib.request.Request(
        url_template.format(id=paper_id), headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
    if not data.startswith(b"%PDF"):
        raise ValueError("response is not a PDF")
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(dest)
    return "downloaded"


def make_converter(variant: str, ocr: bool) -> DocumentConverter:
    options = PdfPipelineOptions()
    options.do_ocr = ocr
    if variant == "hier":
        options.heading_hierarchy_options = HeadingHierarchyOptions(enabled=True)
        # The font-style signal reads the parsed PDF cells, which are dropped unless kept.
        options.generate_parsed_pages = True
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def convert(converter: DocumentConverter, pdf: Path, dest: Path, variant: str) -> dict:
    start = time.perf_counter()
    result = converter.convert(pdf, raises_on_error=False)
    if result.status == ConversionStatus.FAILURE:
        return {"status": "failure", "errors": [e.error_message for e in result.errors][:3]}
    doc = result.document
    if variant == "hier":
        doc._hierarchize()
        doc.validate_tree(doc.body, raise_on_error=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save_as_json(dest)
    return {
        "status": result.status.value,
        "pages": len(doc.pages),
        "seconds": round(time.perf_counter() - start, 1),
    }


def package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def process(paper_id: str, entry: dict, converters: dict[str, DocumentConverter], args) -> None:
    """Fetch one paper and convert it for each variant; failures land in `entry`."""
    pdf = args.out / "pdfs" / f"{file_stem(paper_id)}.pdf"
    try:
        entry["pdf"] = fetch_pdf(paper_id, pdf, args.pdf_url, args.timeout)
    except Exception as e:  # network or HTTP error: keep going, the manifest records it
        entry["pdf"] = f"error: {e}"
        return
    if entry["pdf"] == "downloaded":
        time.sleep(args.delay)
    for variant, converter in converters.items():
        dest = args.out / "docling" / variant / f"{file_stem(paper_id)}.json"
        if dest.exists():
            continue
        try:
            entry[variant] = convert(converter, pdf, dest, variant)
        except Exception as e:
            entry[variant] = {"status": "error", "error": str(e)[:300]}


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--qasper", type=Path, required=True, help="Qasper split file (JSON)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--variants", default="flat,hier", help="comma-separated: flat, hier")
    ap.add_argument("--limit", type=int, help="first N papers only")
    ap.add_argument(
        "--ocr", action="store_true", help="arXiv PDFs are born-digital: OCR off by default"
    )
    ap.add_argument("--pdf-url", default="https://arxiv.org/pdf/{id}", help="template with {id}")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between two downloads")
    ap.add_argument("--timeout", type=float, default=60.0)
    args = ap.parse_args()

    variants = [v for v in args.variants.split(",") if v]
    unknown = set(variants) - set(VARIANTS)
    if unknown:
        ap.error(f"unknown variants: {sorted(unknown)}")

    paper_ids = list(load_papers(args.qasper))[: args.limit]
    manifest_path = args.out / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"papers": {}}
    manifest.update(
        {
            "qasper": str(args.qasper),
            "versions": {
                p: package_version(p) for p in ("docling", "docling-slim", "docling-core")
            },
            "options": {"ocr": args.ocr, "pdf_url": args.pdf_url},
        }
    )
    converters = {v: make_converter(v, args.ocr) for v in variants}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    for n, paper_id in enumerate(paper_ids, start=1):
        entry = manifest["papers"].setdefault(paper_id, {})
        try:
            process(paper_id, entry, converters, args)
        finally:
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        states = [f"pdf={entry['pdf']}"]
        if not entry["pdf"].startswith("error"):
            states += [f"{v}={entry.get(v, {}).get('status', 'cached')}" for v in variants]
        print(f"[{n}/{len(paper_ids)}] {paper_id}: " + ", ".join(states))


if __name__ == "__main__":
    main()
