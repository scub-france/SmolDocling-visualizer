"""Merging page batches back into one Docling document (#344).

A batched analysis converts `page_range` slices of the PDF, then the local
converter concatenates the batch documents. These tests build small batch
documents by hand, run them through the same projection `_convert_sync`
uses, and check the merged result keeps the document and aligns the page
details with it.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("docling", reason="docling library not installed")

from docling_core.types.doc import (
    BoundingBox,
    CoordOrigin,
    DocItemLabel,
    DoclingDocument,
    ProvenanceItem,
    RefItem,
    Size,
)

import infra.local_converter as lc_mod

if TYPE_CHECKING:
    from domain.value_objects import ConversionResult


def _prov(page_no: int, top: float) -> ProvenanceItem:
    return ProvenanceItem(
        page_no=page_no,
        bbox=BoundingBox(l=72, t=top, r=540, b=top - 20, coord_origin=CoordOrigin.BOTTOMLEFT),
        charspan=(0, 10),
    )


def _batch(first_page: int, last_page: int) -> ConversionResult:
    """A batch as `_convert_sync` returns it: a heading and a paragraph per
    page, page numbers kept absolute as Docling does with `page_range`."""
    doc = DoclingDocument(name="batch")
    for page_no in range(first_page, last_page + 1):
        doc.add_page(page_no=page_no, size=Size(width=612, height=792))
        doc.add_heading(text=f"Section {page_no}", prov=_prov(page_no, top=740))
        doc.add_text(label=DocItemLabel.TEXT, text=f"Body {page_no}", prov=_prov(page_no, top=700))
    return lc_mod._to_conversion_result(doc)


class TestMergeBatches:
    def test_keeps_the_docling_document(self):
        merged = lc_mod._merge_batches_sync([_batch(1, 2), _batch(3, 4)])

        assert merged.document_json is not None
        doc = DoclingDocument.model_validate_json(merged.document_json)
        assert sorted(doc.pages) == [1, 2, 3, 4]
        assert [t.text for t in doc.texts] == [
            "Section 1",
            "Body 1",
            "Section 2",
            "Body 2",
            "Section 3",
            "Body 3",
            "Section 4",
            "Body 4",
        ]
        assert merged.page_count == 4
        assert "Section 3" in merged.content_markdown

    def test_rebuilds_the_page_details_against_the_merged_refs(self):
        second = _batch(3, 4)
        merged = lc_mod._merge_batches_sync([_batch(1, 2), second])
        doc = DoclingDocument.model_validate_json(merged.document_json)

        # The first heading of the second batch is #/texts/0 in its own
        # document, and #/texts/4 once the batches are concatenated.
        assert second.pages[0].elements[0].self_ref == "#/texts/0"
        page_3 = next(p for p in merged.pages if p.page_number == 3)
        assert page_3.elements[0].self_ref == "#/texts/4"

        # Every element points at the merged item it was drawn from.
        for page in merged.pages:
            for element in page.elements:
                item = RefItem(cref=element.self_ref).resolve(doc)
                assert any(prov.page_no == page.page_number for prov in item.prov)
                assert item.text == element.content

    def test_falls_back_without_a_document_when_a_batch_has_none(self, caplog):
        second = replace(_batch(3, 4), document_json=None)

        merged = lc_mod._merge_batches_sync([_batch(1, 2), second])

        assert merged.document_json is None
        assert [p.page_number for p in merged.pages] == [1, 2, 3, 4]
        assert "keeps none" in caplog.text

    def test_falls_back_without_a_document_when_the_merge_fails(self, caplog):
        second = replace(_batch(3, 4), document_json="{not json")

        merged = lc_mod._merge_batches_sync([_batch(1, 2), second])

        assert merged.document_json is None
        assert [p.page_number for p in merged.pages] == [1, 2, 3, 4]
        assert "Could not merge the batch documents" in caplog.text

    async def test_the_local_converter_merges_its_batches(self):
        merged = await lc_mod.LocalConverter().merge_batches([_batch(1, 1), _batch(2, 2)])

        assert merged.document_json is not None
        assert [p.page_number for p in merged.pages] == [1, 2]
