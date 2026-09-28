"""The local engine fails a conversion that dropped pages (#348).

Docling's `convert` raises on a failure only. On a partial success, at its
document timeout or on pages it cannot read, it keeps the processed pages in
`result.pages` and records one error per dropped page. `_convert_sync` must
turn that into an `IncompleteConversionError` instead of storing the result.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("docling", reason="docling library not installed")

from docling.datamodel.base_models import ConversionStatus

import infra.local_converter as lc_mod
from domain.exceptions import IncompleteConversionError
from domain.value_objects import ConversionOptions


def _result(
    status: ConversionStatus,
    converted: list[int],
    errors: list[str],
    *,
    page_count: int = 5,
    page_range: tuple[int, int] = (1, 2**31),
) -> SimpleNamespace:
    """The parts of a Docling ConversionResult the check reads."""
    return SimpleNamespace(
        status=status,
        input=SimpleNamespace(page_count=page_count, limits=SimpleNamespace(page_range=page_range)),
        pages=[SimpleNamespace(page_no=n) for n in converted],
        errors=[SimpleNamespace(error_message=message) for message in errors],
    )


class TestRaiseIfPagesMissing:
    def test_fails_on_the_pages_dropped_at_the_timeout(self):
        result = _result(
            ConversionStatus.PARTIAL_SUCCESS,
            converted=[1, 2, 3],
            errors=["Page 4: document timeout exceeded", "Page 5: document timeout exceeded"],
        )

        with pytest.raises(IncompleteConversionError) as caught:
            lc_mod._raise_if_pages_missing(result)

        assert caught.value.missing_pages == [4, 5]
        assert caught.value.timed_out is True

    def test_fails_on_the_pages_docling_could_not_read(self):
        result = _result(
            ConversionStatus.PARTIAL_SUCCESS,
            converted=[1, 2, 4, 5],
            errors=["Page 3: could not parse page"],
        )

        with pytest.raises(IncompleteConversionError) as caught:
            lc_mod._raise_if_pages_missing(result)

        assert caught.value.missing_pages == [3]
        assert caught.value.timed_out is False

    def test_counts_only_the_pages_of_the_batch(self):
        """A batch covers `page_range`: pages outside it are not missing."""
        result = _result(
            ConversionStatus.PARTIAL_SUCCESS,
            converted=[11, 12],
            errors=["Page 13: document timeout exceeded"],
            page_count=25,
            page_range=(11, 13),
        )

        with pytest.raises(IncompleteConversionError) as caught:
            lc_mod._raise_if_pages_missing(result)

        assert caught.value.missing_pages == [13]

    def test_keeps_a_partial_result_with_every_page(self, caplog):
        result = _result(
            ConversionStatus.PARTIAL_SUCCESS,
            converted=[1, 2, 3, 4, 5],
            errors=["Picture description failed"],
        )

        lc_mod._raise_if_pages_missing(result)

        assert "every page converted" in caplog.text

    def test_keeps_a_successful_result(self):
        lc_mod._raise_if_pages_missing(
            _result(ConversionStatus.SUCCESS, converted=[1, 2, 3, 4, 5], errors=[])
        )


class TestConvertSync:
    @patch("infra.local_converter._select_converter")
    @patch("infra.local_converter._converter_lock")
    def test_does_not_store_a_conversion_that_dropped_pages(self, mock_lock, mock_select):
        mock_lock.acquire.return_value = True
        converter = MagicMock()
        converter.convert.return_value = _result(
            ConversionStatus.PARTIAL_SUCCESS,
            converted=[1, 2],
            errors=["Page 3: document timeout exceeded"],
            page_count=3,
        )
        mock_select.return_value = converter

        with pytest.raises(IncompleteConversionError, match="page 3 was not converted"):
            lc_mod._convert_sync("/tmp/test.pdf", ConversionOptions())
