"""Robustness tests — verify pipeline failure scenarios and protective mechanisms.

Tests cover: document_timeout (C1), lock timeout (C2), convert limits (C3),
default table_mode (H1), converter reset on failure (H5), error classification (M1).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.models import AnalysisJob
from domain.services import classify_error
from domain.value_objects import ConversionOptions, ConversionResult, PageDetail
from infra.settings import Settings
from services.analysis_service import AnalysisConfig, AnalysisService

# ---------------------------------------------------------------------------
# M1 — _classify_error: user-friendly error messages
# ---------------------------------------------------------------------------


class TestClassifyError:
    """Verify _classify_error maps exceptions to user-friendly messages."""

    def test_cxx_compiler_error(self):
        exc = RuntimeError("InvalidCxxCompiler: No working C++ compiler found")
        assert "Missing C++ compiler" in classify_error(exc)

    def test_no_working_compiler(self):
        exc = RuntimeError("no working c++ compiler found in torch")
        assert "Missing C++ compiler" in classify_error(exc)

    def test_out_of_memory(self):
        exc = MemoryError("Out of memory allocating tensor")
        assert "Out of memory" in classify_error(exc)

    def test_oom_shorthand(self):
        exc = RuntimeError("OOM during inference on page 5")
        assert "Out of memory" in classify_error(exc)

    def test_lock_timeout(self):
        exc = TimeoutError("Could not acquire converter lock within 300s")
        assert "Server busy" in classify_error(exc)

    def test_pipeline_failed(self):
        exc = RuntimeError("Pipeline StandardPdfPipeline failed on page 3")
        assert "Document processing failed" in classify_error(exc)

    def test_timeout_generic(self):
        exc = TimeoutError("timeout exceeded while processing")
        assert "Processing took too long" in classify_error(exc)

    def test_unknown_short_error(self):
        exc = ValueError("something weird happened")
        assert classify_error(exc) == "something weird happened"

    def test_unknown_long_error_truncated(self):
        long_msg = "x" * 300
        exc = ValueError(long_msg)
        result = classify_error(exc)
        assert len(result) <= 201
        assert result.endswith("…")


# ---------------------------------------------------------------------------
# H1 — default table_mode injection
# ---------------------------------------------------------------------------


class TestDefaultTableMode:
    """Verify _run_analysis_inner injects settings.default_table_mode."""

    @pytest.fixture
    def mock_job(self):
        return AnalysisJob(id="j1", document_id="d1", document_filename="test.pdf")

    def _make_result(self) -> ConversionResult:
        return ConversionResult(
            page_count=1,
            content_markdown="# Test",
            content_html="<h1>Test</h1>",
            pages=[PageDetail(page_number=1, width=612.0, height=792.0)],
        )

    def _make_service(self, converter, *, default_table_mode="accurate"):
        mock_analysis_repo = MagicMock()
        mock_analysis_repo.find_by_id = AsyncMock()
        mock_analysis_repo.update_status = AsyncMock()
        mock_document_repo = MagicMock()
        mock_document_repo.update_page_count = AsyncMock()
        config = AnalysisConfig(default_table_mode=default_table_mode)
        return AnalysisService(
            converter=converter,
            analysis_repo=mock_analysis_repo,
            document_repo=mock_document_repo,
            config=config,
        )

    @pytest.mark.asyncio
    async def test_default_table_mode_injected_when_missing(self, mock_job):
        mock_converter = AsyncMock()
        mock_converter.convert.return_value = self._make_result()
        svc = self._make_service(mock_converter)
        svc._analysis_repo.find_by_id = AsyncMock(return_value=mock_job)

        await svc._run_analysis("j1", "/tmp/test.pdf", "test.pdf", {})

        opts = mock_converter.convert.call_args[0][1]
        assert opts.table_mode == "accurate"

    @pytest.mark.asyncio
    async def test_default_table_mode_injected_when_none(self, mock_job):
        mock_converter = AsyncMock()
        mock_converter.convert.return_value = self._make_result()
        svc = self._make_service(mock_converter)
        svc._analysis_repo.find_by_id = AsyncMock(return_value=mock_job)

        await svc._run_analysis("j1", "/tmp/test.pdf", "test.pdf", None)

        opts = mock_converter.convert.call_args[0][1]
        assert opts.table_mode == "accurate"

    @pytest.mark.asyncio
    async def test_user_table_mode_preserved(self, mock_job):
        mock_converter = AsyncMock()
        mock_converter.convert.return_value = self._make_result()
        svc = self._make_service(mock_converter)
        svc._analysis_repo.find_by_id = AsyncMock(return_value=mock_job)

        await svc._run_analysis("j1", "/tmp/test.pdf", "test.pdf", {"table_mode": "fast"})

        opts = mock_converter.convert.call_args[0][1]
        assert opts.table_mode == "fast"

    @pytest.mark.asyncio
    async def test_custom_default_from_settings(self, mock_job):
        mock_converter = AsyncMock()
        mock_converter.convert.return_value = self._make_result()
        svc = self._make_service(mock_converter, default_table_mode="fast")
        svc._analysis_repo.find_by_id = AsyncMock(return_value=mock_job)

        await svc._run_analysis("j1", "/tmp/test.pdf", "test.pdf", {})

        opts = mock_converter.convert.call_args[0][1]
        assert opts.table_mode == "fast"


# ---------------------------------------------------------------------------
# Docling-dependent tests — skip if docling is not installed
# ---------------------------------------------------------------------------

docling = pytest.importorskip("docling", reason="docling library not installed")

from docling.datamodel.base_models import InputFormat  # noqa: E402

import infra.local_converter as lc_mod  # noqa: E402

build_converter = lc_mod._build_docling_converter
convert_sync = lc_mod._convert_sync
get_default_converter = lc_mod._ensure_default_converter

# ---------------------------------------------------------------------------
# C1 — document_timeout in PdfPipelineOptions
# ---------------------------------------------------------------------------


class TestDocumentTimeout:
    """Verify document_timeout from settings is wired into PdfPipelineOptions."""

    def _get_pipeline_options(self, converter):
        fmt_opt = converter.format_to_options[InputFormat.PDF]
        return fmt_opt.pipeline_options

    def test_document_timeout_from_settings(self):
        conv = build_converter(ConversionOptions())
        opts = self._get_pipeline_options(conv)
        assert opts.document_timeout == 780.0

    @patch("infra.local_converter.settings", Settings(document_timeout=45.0))
    def test_custom_document_timeout(self):
        conv = build_converter(ConversionOptions())
        opts = self._get_pipeline_options(conv)
        assert opts.document_timeout == 45.0


# ---------------------------------------------------------------------------
# C2 — converter lock timeout
# ---------------------------------------------------------------------------


def _mock_docling_result():
    """Create a minimal mock that satisfies _convert_sync's result processing."""
    mock_result = MagicMock()
    mock_result.document.pages = {}
    mock_result.document.iterate_items.return_value = []
    mock_result.document.export_to_markdown.return_value = ""
    mock_result.document.export_to_html.return_value = ""
    mock_result.document.export_to_dict.return_value = {}
    return mock_result


class TestConverterLockTimeout:
    """Verify _convert_sync raises TimeoutError when lock cannot be acquired."""

    @patch("infra.local_converter._converter_lock")
    def test_lock_timeout_raises(self, mock_lock):
        mock_lock.acquire.return_value = False

        with pytest.raises(TimeoutError, match="Could not acquire converter lock"):
            convert_sync("/tmp/test.pdf", ConversionOptions())

        mock_lock.release.assert_not_called()

    @patch("infra.local_converter._select_converter")
    @patch("infra.local_converter._converter_lock")
    def test_lock_released_on_success(self, mock_lock, mock_select):
        mock_lock.acquire.return_value = True
        mock_conv = MagicMock()
        mock_conv.convert.return_value = _mock_docling_result()
        mock_select.return_value = mock_conv

        convert_sync("/tmp/test.pdf", ConversionOptions())

        mock_lock.release.assert_called_once()

    @patch("infra.local_converter._select_converter")
    @patch("infra.local_converter._converter_lock")
    def test_lock_released_on_error(self, mock_lock, mock_select):
        mock_lock.acquire.return_value = True
        mock_conv = MagicMock()
        mock_conv.convert.side_effect = RuntimeError("boom")
        mock_select.return_value = mock_conv

        with pytest.raises(RuntimeError, match="boom"):
            convert_sync("/tmp/test.pdf", ConversionOptions())

        mock_lock.release.assert_called_once()


# ---------------------------------------------------------------------------
# C3 — max_num_pages and max_file_size forwarding
# ---------------------------------------------------------------------------


class TestConvertSyncLimits:
    """Verify _convert_sync forwards limit settings to conv.convert()."""

    @patch("infra.local_converter._select_converter")
    @patch("infra.local_converter._converter_lock")
    @patch("infra.local_converter.settings", Settings(max_page_count=10, max_file_size=0))
    def test_max_page_count_forwarded(self, mock_lock, mock_select):
        mock_lock.acquire.return_value = True
        mock_conv = MagicMock()
        mock_conv.convert.return_value = _mock_docling_result()
        mock_select.return_value = mock_conv

        convert_sync("/tmp/test.pdf", ConversionOptions())

        kwargs = mock_conv.convert.call_args.kwargs
        assert kwargs["max_num_pages"] == 10
        assert "max_file_size" not in kwargs

    @patch("infra.local_converter._select_converter")
    @patch("infra.local_converter._converter_lock")
    @patch("infra.local_converter.settings", Settings(max_page_count=0, max_file_size=5_000_000))
    def test_max_file_size_forwarded(self, mock_lock, mock_select):
        mock_lock.acquire.return_value = True
        mock_conv = MagicMock()
        mock_conv.convert.return_value = _mock_docling_result()
        mock_select.return_value = mock_conv

        convert_sync("/tmp/test.pdf", ConversionOptions())

        kwargs = mock_conv.convert.call_args.kwargs
        assert kwargs["max_file_size"] == 5_000_000
        assert "max_num_pages" not in kwargs

    @patch("infra.local_converter._select_converter")
    @patch("infra.local_converter._converter_lock")
    @patch(
        "infra.local_converter.settings",
        Settings(max_page_count=20, max_file_size=10_000_000),
    )
    def test_both_limits_forwarded(self, mock_lock, mock_select):
        mock_lock.acquire.return_value = True
        mock_conv = MagicMock()
        mock_conv.convert.return_value = _mock_docling_result()
        mock_select.return_value = mock_conv

        convert_sync("/tmp/test.pdf", ConversionOptions())

        kwargs = mock_conv.convert.call_args.kwargs
        assert kwargs["max_num_pages"] == 20
        assert kwargs["max_file_size"] == 10_000_000

    @patch("infra.local_converter._select_converter")
    @patch("infra.local_converter._converter_lock")
    @patch("infra.local_converter.settings", Settings(max_page_count=0, max_file_size=0))
    def test_zero_limits_not_forwarded(self, mock_lock, mock_select):
        mock_lock.acquire.return_value = True
        mock_conv = MagicMock()
        mock_conv.convert.return_value = _mock_docling_result()
        mock_select.return_value = mock_conv

        convert_sync("/tmp/test.pdf", ConversionOptions())

        kwargs = mock_conv.convert.call_args.kwargs
        assert "max_num_pages" not in kwargs
        assert "max_file_size" not in kwargs


# ---------------------------------------------------------------------------
# H5 — _default_converter reset on init failure
# ---------------------------------------------------------------------------


class TestGetDefaultConverterReset:
    """Verify _ensure_default_converter resets on failure and retries on next call."""

    @pytest.fixture(autouse=True)
    def reset_default_converter(self):
        original = lc_mod._default_converter
        lc_mod._default_converter = None
        yield
        lc_mod._default_converter = original

    @patch("infra.local_converter._build_docling_converter")
    def test_init_failure_resets_to_none(self, mock_build):
        mock_build.side_effect = RuntimeError("torch not found")

        with pytest.raises(RuntimeError, match="torch not found"):
            get_default_converter()

        assert lc_mod._default_converter is None

    @patch("infra.local_converter._build_docling_converter")
    def test_retry_after_failure_succeeds(self, mock_build):
        mock_conv = MagicMock()
        mock_build.side_effect = [RuntimeError("torch not found"), mock_conv]

        with pytest.raises(RuntimeError):
            get_default_converter()

        result = get_default_converter()
        assert result is mock_conv
        assert mock_build.call_count == 2

    @patch("infra.local_converter._build_docling_converter")
    def test_success_caches_converter(self, mock_build):
        mock_conv = MagicMock()
        mock_build.return_value = mock_conv

        result1 = get_default_converter()
        result2 = get_default_converter()

        assert result1 is result2 is mock_conv
        mock_build.assert_called_once()
