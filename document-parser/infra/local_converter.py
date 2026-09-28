"""Local Docling converter — runs Docling as a Python library in-process.

This adapter implements the DocumentConverter port using the Docling library
directly. It wraps the blocking DocumentConverter in asyncio.to_thread for
non-blocking execution.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading

from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableFormerMode,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter as DoclingConverter
from docling.document_converter import PdfFormatOption
from docling_core.types.doc import (
    CodeItem,
    DocItem,
    DoclingDocument,
    FloatingItem,
    FormulaItem,
    GroupItem,
    ListItem,
    PictureItem,
    SectionHeaderItem,
    TableItem,
    TextItem,
    TitleItem,
)

from domain.exceptions import IncompleteConversionError
from domain.services import merge_results
from domain.value_objects import (
    DEFAULT_PAGE_HEIGHT,
    DEFAULT_PAGE_WIDTH,
    ConversionOptions,
    ConversionResult,
    PageDetail,
    PageElement,
)
from infra.bbox import to_topleft_list
from infra.settings import settings

logger = logging.getLogger(__name__)

# Thread lock — DoclingConverter is not thread-safe.
# Uses a timeout to prevent a frozen conversion from blocking all others.
_converter_lock = threading.Lock()

# Default converter (lazy-init on first request)
_default_converter: DoclingConverter | None = None


# ---------------------------------------------------------------------------
# Element type detection
# ---------------------------------------------------------------------------

_ELEMENT_TYPE_MAP: list[tuple[type, str]] = [
    (TableItem, "table"),
    (PictureItem, "picture"),
    (TitleItem, "title"),
    (SectionHeaderItem, "section_header"),
    (ListItem, "list"),
    (FormulaItem, "formula"),
    (CodeItem, "code"),
    (FloatingItem, "floating"),
    (TextItem, "text"),
]


def _get_element_type(item: DocItem) -> str:
    for cls, type_name in _ELEMENT_TYPE_MAP:
        if isinstance(item, cls):
            return type_name
    return "text"


# ---------------------------------------------------------------------------
# Pipeline factory
# ---------------------------------------------------------------------------


def _build_docling_converter(options: ConversionOptions) -> DoclingConverter:
    table_options = TableStructureOptions(
        do_cell_matching=True,
        mode=TableFormerMode.ACCURATE if options.table_mode == "accurate" else TableFormerMode.FAST,
    )

    pipeline_options = PdfPipelineOptions(
        do_ocr=options.do_ocr,
        do_table_structure=options.do_table_structure,
        table_structure_options=table_options,
        do_code_enrichment=options.do_code_enrichment,
        do_formula_enrichment=options.do_formula_enrichment,
        do_picture_classification=options.do_picture_classification,
        do_picture_description=options.do_picture_description,
        generate_page_images=options.generate_page_images,
        generate_picture_images=options.generate_picture_images,
        images_scale=options.images_scale,
        document_timeout=settings.document_timeout,
    )

    return DoclingConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


def _ensure_default_converter() -> DoclingConverter:
    global _default_converter
    if _default_converter is None:
        try:
            _default_converter = _build_docling_converter(ConversionOptions())
        except Exception:
            raise
    return _default_converter


def _select_converter(options: ConversionOptions) -> DoclingConverter:
    if options.is_default():
        return _ensure_default_converter()
    return _build_docling_converter(options)


# ---------------------------------------------------------------------------
# Page extraction
# ---------------------------------------------------------------------------


def _extract_pages_detail(document: DoclingDocument) -> tuple[list[PageDetail], int]:
    pages: dict[int, PageDetail] = {}
    skipped = 0

    for page_key, page_obj in document.pages.items():
        page_no = int(page_key) if isinstance(page_key, str) else page_key
        pages[page_no] = PageDetail(
            page_number=page_no,
            width=page_obj.size.width,
            height=page_obj.size.height,
        )

    for item, level in document.iterate_items():
        ok = _process_content_item(item, level, pages)
        if not ok:
            skipped += 1

    sorted_pages = sorted(pages.values(), key=lambda p: p.page_number)
    return sorted_pages, skipped


def _process_content_item(
    item: DocItem | GroupItem,
    level: int,
    pages: dict[int, PageDetail],
) -> bool:
    if isinstance(item, GroupItem):
        return True

    if not isinstance(item, DocItem) or not item.prov:
        return False

    for prov in item.prov:
        try:
            page_no = prov.page_no
            if page_no not in pages:
                logger.warning(
                    "Page %d not found in document metadata — using US Letter fallback (%sx%s pt)",
                    page_no,
                    DEFAULT_PAGE_WIDTH,
                    DEFAULT_PAGE_HEIGHT,
                )
                pages[page_no] = PageDetail(
                    page_number=page_no, width=DEFAULT_PAGE_WIDTH, height=DEFAULT_PAGE_HEIGHT
                )

            page_height = pages[page_no].height

            bbox = [0.0, 0.0, 0.0, 0.0]
            if prov.bbox:
                bbox = to_topleft_list(prov.bbox, page_height)

            element_type = _get_element_type(item)

            content = getattr(item, "text", "") or ""
            if isinstance(item, TableItem):
                with contextlib.suppress(AttributeError, ValueError):
                    content = item.export_to_markdown()

            pages[page_no].elements.append(
                PageElement(
                    type=element_type,
                    bbox=bbox,
                    content=content,
                    level=level,
                    self_ref=getattr(item, "self_ref", "") or "",
                )
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            logger.warning(
                "Skipping item %s on page %s",
                type(item).__name__,
                getattr(prov, "page_no", "?"),
                exc_info=True,
            )
            return False

    return True


# ---------------------------------------------------------------------------
# Synchronous conversion (called via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _convert_sync(
    file_path: str,
    options: ConversionOptions,
    *,
    page_range: tuple[int, int] | None = None,
) -> ConversionResult:
    acquired = _converter_lock.acquire(timeout=settings.lock_timeout)
    if not acquired:
        raise TimeoutError(
            f"Could not acquire converter lock within {settings.lock_timeout}s — "
            "a previous conversion may be frozen"
        )
    try:
        conv = _select_converter(options)
        kwargs: dict = {}
        if settings.max_page_count > 0:
            kwargs["max_num_pages"] = settings.max_page_count
        if settings.max_file_size > 0:
            kwargs["max_file_size"] = settings.max_file_size
        if page_range is not None:
            kwargs["page_range"] = page_range
        result = conv.convert(file_path, **kwargs)
    finally:
        _converter_lock.release()

    _raise_if_pages_missing(result)
    return _to_conversion_result(result.document)


def _raise_if_pages_missing(result) -> None:
    """Fail a partial conversion that dropped pages rather than store it (#348).

    Docling raises on a failure only. On a partial success it keeps the pages
    it processed in `result.pages` and records an error per page it dropped;
    at its document timeout, it drops every page it had not reached.
    """
    if result.status != ConversionStatus.PARTIAL_SUCCESS:
        return
    first, last = result.input.limits.page_range
    last = min(last, result.input.page_count)
    converted = {page.page_no for page in result.pages}
    missing = [page_no for page_no in range(first, last + 1) if page_no not in converted]
    errors = [error.error_message for error in result.errors]
    if not missing:
        logger.warning("Partial conversion, every page converted: %s", errors)
        return
    timed_out = any("timeout" in error.lower() for error in errors)
    raise IncompleteConversionError(missing, timed_out=timed_out)


def _to_conversion_result(doc: DoclingDocument) -> ConversionResult:
    """Everything the app stores about a conversion, derived from its document."""
    page_count = len(doc.pages)
    pages_detail, skipped = _extract_pages_detail(doc)

    if not pages_detail and page_count > 0:
        pages_detail = [
            PageDetail(
                page_number=i + 1,
                width=doc.pages[i + 1].size.width if (i + 1) in doc.pages else DEFAULT_PAGE_WIDTH,
                height=doc.pages[i + 1].size.height
                if (i + 1) in doc.pages
                else DEFAULT_PAGE_HEIGHT,
            )
            for i in range(page_count)
        ]

    if skipped > 0:
        logger.info("Parsed: %d pages, %d items skipped", page_count, skipped)

    return ConversionResult(
        page_count=page_count or len(pages_detail) or 1,
        content_markdown=doc.export_to_markdown(),
        content_html=doc.export_to_html(),
        pages=pages_detail,
        skipped_items=skipped,
        document_json=json.dumps(doc.export_to_dict()),
    )


def _merge_batches_sync(results: list[ConversionResult]) -> ConversionResult:
    """Merge page batches into the result a single pass would have produced.

    The batch documents are concatenated, then everything is derived from the
    merged document again, page details included: concatenation renumbers the
    refs of the second batch onwards (`#/texts/0` becomes `#/texts/<n>`), so
    page details kept per batch would point at the wrong items of the tree.
    When a batch has no document, or the concatenation fails, the merge falls
    back to `merge_results`, which keeps no document.
    """
    document_jsons = [r.document_json for r in results]
    if not all(document_jsons):
        if results:
            logger.warning("A batch has no Docling document, the merged analysis keeps none")
        return merge_results(results)
    try:
        documents = [DoclingDocument.model_validate_json(j) for j in document_jsons if j]
        return _to_conversion_result(DoclingDocument.concatenate(documents))
    except Exception:
        # Any failure of the third-party merge must not fail an analysis
        # whose batches all converted: keep the merge without a document.
        logger.warning("Could not merge the batch documents, keeping none", exc_info=True)
        return merge_results(results)


# ---------------------------------------------------------------------------
# Public adapter class
# ---------------------------------------------------------------------------


class LocalConverter:
    """Adapter that runs Docling locally as a Python library."""

    # In-process — the orchestrator may slice long docs into page batches
    # and merge results (cf. AnalysisService._run_batched_conversion).
    supports_page_batching: bool = True

    async def convert(
        self,
        file_path: str,
        options: ConversionOptions,
        *,
        page_range: tuple[int, int] | None = None,
    ) -> ConversionResult:
        return await asyncio.to_thread(_convert_sync, file_path, options, page_range=page_range)

    async def merge_batches(self, results: list[ConversionResult]) -> ConversionResult:
        return await asyncio.to_thread(_merge_batches_sync, results)
