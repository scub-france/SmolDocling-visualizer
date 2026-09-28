#!/usr/bin/env python3
"""
Parse a PDF with Docling, forcing full-page OCR, and save the DoclingDocument JSON.

For PDFs whose text layer is unusable: "Unfolding the Leech Lattice" was saved from a browser
through macOS Quartz, with subset fonts and no ToUnicode map, so both docling-parse and poppler
read shifted letters ("Tmenkchmf sgd Iddbg" for "Unfolding the Leech"). The rendered glyphs are
fine, so OCR recovers the text. Same pipeline options as Docling-Studio's local converter, plus
Tesseract (local binary, English) on every page.

Usage (docling is installed in the backend venv; nothing is added to it):
    document-parser/.venv/bin/python experiments/laya-nav-test/parse_pdf.py PDF OUTPUT_JSON
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
from docling.document_converter import DocumentConverter, PdfFormatOption


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        ocr_options=TesseractCliOcrOptions(lang=["eng"], force_full_page_ocr=True),
    )
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})

    start = time.perf_counter()
    document = converter.convert(args.pdf).document
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document.export_to_dict(), ensure_ascii=False))
    print(f"{args.pdf.name}: {len(document.pages)} pages in {time.perf_counter() - start:.0f}s -> {args.output}")


if __name__ == "__main__":
    main()
