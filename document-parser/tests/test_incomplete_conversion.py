"""Conversions that come back with pages missing fail the analysis (#348).

Docling stops at its document timeout, or skips pages it cannot read, and
reports a partial success instead of an error. These tests cover the parts
that need no Docling install: the error and its message, the Docling Serve
response, the batched analysis and the message shown to the user. The
local engine's detection is in `test_local_partial_conversion.py`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.exceptions import IncompleteConversionError
from domain.services import classify_error
from domain.value_objects import ConversionResult, PageDetail
from infra.serve_converter import _parse_response
from services.analysis_service import AnalysisService


class TestIncompleteConversionError:
    def test_names_the_pages_the_timeout_dropped(self):
        error = IncompleteConversionError(list(range(20, 29)), timed_out=True)

        assert str(error).startswith(
            "Docling stopped at its document timeout: pages 20-28 were not converted."
        )
        assert "DOCUMENT_TIMEOUT" in str(error)
        assert "BATCH_PAGE_SIZE" in str(error)

    def test_names_the_pages_docling_could_not_read(self):
        error = IncompleteConversionError([7, 3], timed_out=False)

        assert str(error) == (
            "Docling could not convert pages 3, 7. The document may be damaged on those pages."
        )

    def test_groups_page_runs(self):
        error = IncompleteConversionError([9, 3, 4, 5, 11, 12], timed_out=False)

        assert "pages 3-5, 9, 11-12." in str(error)
        assert error.missing_pages == [3, 4, 5, 9, 11, 12]

    def test_speaks_of_a_single_page_in_the_singular(self):
        assert "page 28 was not converted" in str(IncompleteConversionError([28], timed_out=True))
        assert str(IncompleteConversionError([3], timed_out=False)) == (
            "Docling could not convert page 3. The document may be damaged on that page."
        )


class TestClassifyError:
    def test_keeps_the_message_that_names_the_pages(self):
        error = IncompleteConversionError([20, 21], timed_out=True)

        assert classify_error(error) == str(error)


def _serve_response(status: str, errors: list[str]) -> dict:
    return {
        "document": {
            "md_content": "# Doc",
            "html_content": "<h1>Doc</h1>",
            "json_content": {
                "pages": {"1": {"size": {"width": 612.0, "height": 792.0}}},
                "texts": [],
                "tables": [],
                "pictures": [],
            },
        },
        "status": status,
        "errors": [
            {
                "component_type": "pipeline",
                "module_name": "StandardPdfPipeline",
                "error_message": message,
            }
            for message in errors
        ],
    }


class TestServePartialConversion:
    def test_fails_on_pages_dropped_at_the_timeout(self):
        data = _serve_response(
            "partial_success",
            ["Page 2: document timeout exceeded", "Page 3: document timeout exceeded"],
        )

        with pytest.raises(IncompleteConversionError) as caught:
            _parse_response(data)

        assert caught.value.missing_pages == [2, 3]
        assert caught.value.timed_out is True

    def test_fails_on_pages_docling_could_not_read(self):
        data = _serve_response("partial_success", ["Page 4: could not parse page"])

        with pytest.raises(IncompleteConversionError) as caught:
            _parse_response(data)

        assert caught.value.missing_pages == [4]
        assert caught.value.timed_out is False

    def test_keeps_a_partial_result_that_names_no_page(self):
        data = _serve_response("partial_success", ["Picture description failed"])

        result = _parse_response(data)

        assert result.content_markdown == "# Doc"

    def test_keeps_a_successful_result(self):
        result = _parse_response(_serve_response("success", []))

        assert result.content_markdown == "# Doc"


class TestBatchedIncompleteConversion:
    async def test_a_batch_missing_pages_fails_the_analysis_as_is(self):
        """The error reaches the user unchanged, with the absolute page numbers,
        instead of the "Batch 2/2 failed: ..." wrapper other errors get."""
        converter = AsyncMock()
        converter.convert.side_effect = [
            ConversionResult(
                page_count=5,
                content_markdown="# B1",
                content_html="<html><body><p>B1</p></body></html>",
                pages=[PageDetail(page_number=i, width=612, height=792) for i in range(1, 6)],
            ),
            IncompleteConversionError([9, 10], timed_out=True),
        ]
        analysis_repo = MagicMock()
        analysis_repo.find_by_id = AsyncMock(return_value=MagicMock())
        analysis_repo.update_progress = AsyncMock()
        service = AnalysisService(
            converter=converter,
            analysis_repo=analysis_repo,
            document_repo=MagicMock(),
            conversion_timeout=60,
        )

        with pytest.raises(IncompleteConversionError) as caught:
            await service._run_batched_conversion(
                "job-1", "/fake.pdf", MagicMock(), total_pages=10, batch_size=5
            )

        assert caught.value.missing_pages == [9, 10]
