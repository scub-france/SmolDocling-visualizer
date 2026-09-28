"""Domain services — pure business logic with no infrastructure dependencies."""

from __future__ import annotations

import re

from domain.exceptions import IncompleteConversionError
from domain.value_objects import ConversionResult, PageDetail

# Regex to extract <body> content from Docling's well-formed HTML output.
_BODY_RE = re.compile(r"<body[^>]*>(.*)</body>", re.DOTALL | re.IGNORECASE)


def extract_html_body(html: str) -> str:
    """Extract content between <body> tags.

    Docling produces well-formed HTML — regex is safe for this controlled output.
    Returns raw html as fallback if no <body> tag is found.
    """
    match = _BODY_RE.search(html)
    return match.group(1).strip() if match else html


def merge_results(results: list[ConversionResult]) -> ConversionResult:
    """Merge multiple batch ConversionResults into a single consolidated result.

    document_json is set to None: merging the Docling documents needs Docling,
    which the domain does not import. The converter that batches merges them
    (`DocumentConverter.merge_batches`, #344) and falls back to this merge when
    it cannot, leaving an analysis without tree, chunks or Ask.
    """
    if not results:
        return ConversionResult(page_count=0, content_markdown="", content_html="", pages=[])

    all_pages: list[PageDetail] = []
    all_md: list[str] = []
    html_bodies: list[str] = []
    total_skipped = 0

    for r in results:
        all_pages.extend(r.pages)
        all_md.append(r.content_markdown)
        html_bodies.append(extract_html_body(r.content_html))
        total_skipped += r.skipped_items

    merged_body = "\n".join(html_bodies)
    merged_html = (
        f'<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>{merged_body}</body></html>'
    )

    return ConversionResult(
        page_count=sum(r.page_count for r in results),
        content_markdown="\n\n".join(all_md),
        content_html=merged_html,
        pages=all_pages,
        skipped_items=total_skipped,
        document_json=None,
    )


def classify_error(exc: Exception) -> str:
    """Return a user-friendly error message based on the exception type/content."""
    if isinstance(exc, IncompleteConversionError):
        # Already written for the user, and it names the missing pages: the
        # generic "timeout" rule below would drop them.
        return str(exc)

    msg = str(exc).lower()

    if "invalidcxxcompiler" in msg or "no working c++ compiler" in msg:
        return "Missing C++ compiler — set TORCHDYNAMO_DISABLE=1 to work around this"

    if "out of memory" in msg or "oom" in msg:
        return "Out of memory — try a smaller document or disable table structure analysis"

    if "could not acquire converter lock" in msg:
        return "Server busy — a previous conversion is still running. Please retry later"

    if "pipeline" in msg and "failed" in msg:
        return "Document processing failed — the document may be corrupted or unsupported"

    if "timeout" in msg:
        return "Processing took too long — try with fewer pages or simpler options"

    # Fallback: truncate raw error to something reasonable
    raw = str(exc)
    if len(raw) > 200:
        raw = raw[:200] + "…"
    return raw
