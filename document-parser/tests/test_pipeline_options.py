"""Tests for pipeline options — build_converter, convert_document routing, service forwarding.

Requires the ``docling`` library (heavy, includes torch). Tests are skipped
automatically when docling is not installed (e.g. in lightweight CI environments
that only install docling-core).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

docling = pytest.importorskip("docling", reason="docling library not installed")

from docling.datamodel.base_models import InputFormat  # noqa: E402
from docling.datamodel.pipeline_options import (  # noqa: E402
    PdfPipelineOptions,
    TableFormerMode,
)

from domain.value_objects import ConversionOptions  # noqa: E402
from infra.local_converter import (  # noqa: E402
    _build_docling_converter as build_converter,
)
from infra.local_converter import (  # noqa: E402
    _convert_sync as convert_document,
)

# ---------------------------------------------------------------------------
# build_converter — verifies Docling pipeline options are wired correctly
# ---------------------------------------------------------------------------


class TestBuildConverter:
    """Verify that build_converter produces a DocumentConverter with the right PdfPipelineOptions."""

    def _get_pipeline_options(self, converter) -> PdfPipelineOptions:
        """Extract PdfPipelineOptions from a DocumentConverter."""
        fmt_opt = converter.format_to_options[InputFormat.PDF]
        return fmt_opt.pipeline_options

    def test_defaults(self):
        conv = build_converter(ConversionOptions())
        opts = self._get_pipeline_options(conv)
        assert opts.do_ocr is True
        assert opts.do_table_structure is True
        assert opts.table_structure_options.mode == TableFormerMode.ACCURATE
        assert opts.do_code_enrichment is False
        assert opts.do_formula_enrichment is False
        assert opts.do_picture_classification is False
        assert opts.do_picture_description is False
        assert opts.generate_page_images is False
        assert opts.generate_picture_images is False
        assert opts.images_scale == 1.0
        # default document timeout: 2 min under CONVERSION_TIMEOUT (cf. infra/settings.py, #349)
        assert opts.document_timeout == 780.0

    def test_ocr_disabled(self):
        conv = build_converter(ConversionOptions(do_ocr=False))
        opts = self._get_pipeline_options(conv)
        assert opts.do_ocr is False

    def test_table_mode_fast(self):
        conv = build_converter(ConversionOptions(table_mode="fast"))
        opts = self._get_pipeline_options(conv)
        assert opts.table_structure_options.mode == TableFormerMode.FAST

    def test_table_mode_accurate(self):
        conv = build_converter(ConversionOptions(table_mode="accurate"))
        opts = self._get_pipeline_options(conv)
        assert opts.table_structure_options.mode == TableFormerMode.ACCURATE

    def test_table_structure_disabled(self):
        conv = build_converter(ConversionOptions(do_table_structure=False))
        opts = self._get_pipeline_options(conv)
        assert opts.do_table_structure is False

    def test_code_enrichment_enabled(self):
        conv = build_converter(ConversionOptions(do_code_enrichment=True))
        opts = self._get_pipeline_options(conv)
        assert opts.do_code_enrichment is True

    def test_formula_enrichment_enabled(self):
        conv = build_converter(ConversionOptions(do_formula_enrichment=True))
        opts = self._get_pipeline_options(conv)
        assert opts.do_formula_enrichment is True

    def test_picture_classification_enabled(self):
        conv = build_converter(ConversionOptions(do_picture_classification=True))
        opts = self._get_pipeline_options(conv)
        assert opts.do_picture_classification is True

    def test_picture_description_enabled(self):
        conv = build_converter(ConversionOptions(do_picture_description=True))
        opts = self._get_pipeline_options(conv)
        assert opts.do_picture_description is True

    def test_generate_picture_images(self):
        conv = build_converter(ConversionOptions(generate_picture_images=True))
        opts = self._get_pipeline_options(conv)
        assert opts.generate_picture_images is True

    def test_generate_page_images(self):
        conv = build_converter(ConversionOptions(generate_page_images=True))
        opts = self._get_pipeline_options(conv)
        assert opts.generate_page_images is True

    def test_images_scale(self):
        conv = build_converter(ConversionOptions(images_scale=2.0))
        opts = self._get_pipeline_options(conv)
        assert opts.images_scale == 2.0

    def test_all_options_combined(self):
        conv = build_converter(
            ConversionOptions(
                do_ocr=False,
                do_table_structure=True,
                table_mode="fast",
                do_code_enrichment=True,
                do_formula_enrichment=True,
                do_picture_classification=True,
                do_picture_description=True,
                generate_picture_images=True,
                generate_page_images=True,
                images_scale=1.5,
            )
        )
        opts = self._get_pipeline_options(conv)
        assert opts.do_ocr is False
        assert opts.do_table_structure is True
        assert opts.table_structure_options.mode == TableFormerMode.FAST
        assert opts.do_code_enrichment is True
        assert opts.do_formula_enrichment is True
        assert opts.do_picture_classification is True
        assert opts.do_picture_description is True
        assert opts.generate_picture_images is True
        assert opts.generate_page_images is True
        assert opts.images_scale == 1.5


# ---------------------------------------------------------------------------
# convert_document — default vs custom converter routing
# ---------------------------------------------------------------------------


class TestConvertDocumentRouting:
    """Verify convert_document uses default converter for default opts, custom otherwise."""

    @patch("infra.local_converter._ensure_default_converter")
    @patch("infra.local_converter._build_docling_converter")
    def test_uses_default_converter_with_all_defaults(self, mock_build, mock_get_default):
        mock_conv = MagicMock()
        mock_result = MagicMock()
        mock_result.document.pages = {}
        mock_result.document.iterate_items.return_value = []
        mock_result.document.export_to_markdown.return_value = ""
        mock_result.document.export_to_html.return_value = ""
        mock_result.document.export_to_dict.return_value = {}
        mock_conv.convert.return_value = mock_result
        mock_get_default.return_value = mock_conv

        convert_document("/tmp/test.pdf", ConversionOptions())

        mock_get_default.assert_called_once()
        mock_build.assert_not_called()

    @patch("infra.local_converter._ensure_default_converter")
    @patch("infra.local_converter._build_docling_converter")
    def test_uses_custom_converter_when_ocr_disabled(self, mock_build, mock_get_default):
        mock_conv = MagicMock()
        mock_result = MagicMock()
        mock_result.document.pages = {}
        mock_result.document.iterate_items.return_value = []
        mock_result.document.export_to_markdown.return_value = ""
        mock_result.document.export_to_html.return_value = ""
        mock_result.document.export_to_dict.return_value = {}
        mock_conv.convert.return_value = mock_result
        mock_build.return_value = mock_conv

        convert_document("/tmp/test.pdf", ConversionOptions(do_ocr=False))

        mock_build.assert_called_once()
        mock_get_default.assert_not_called()

    @patch("infra.local_converter._ensure_default_converter")
    @patch("infra.local_converter._build_docling_converter")
    def test_uses_custom_converter_when_table_mode_fast(self, mock_build, mock_get_default):
        mock_conv = MagicMock()
        mock_result = MagicMock()
        mock_result.document.pages = {}
        mock_result.document.iterate_items.return_value = []
        mock_result.document.export_to_markdown.return_value = ""
        mock_result.document.export_to_html.return_value = ""
        mock_result.document.export_to_dict.return_value = {}
        mock_conv.convert.return_value = mock_result
        mock_build.return_value = mock_conv

        opts = ConversionOptions(table_mode="fast")
        convert_document("/tmp/test.pdf", opts)

        mock_build.assert_called_once_with(opts)

    @patch("infra.local_converter._ensure_default_converter")
    @patch("infra.local_converter._build_docling_converter")
    def test_uses_custom_converter_when_code_enrichment_on(self, mock_build, mock_get_default):
        mock_conv = MagicMock()
        mock_result = MagicMock()
        mock_result.document.pages = {}
        mock_result.document.iterate_items.return_value = []
        mock_result.document.export_to_markdown.return_value = ""
        mock_result.document.export_to_html.return_value = ""
        mock_result.document.export_to_dict.return_value = {}
        mock_conv.convert.return_value = mock_result
        mock_build.return_value = mock_conv

        opts = ConversionOptions(do_code_enrichment=True)
        convert_document("/tmp/test.pdf", opts)

        mock_build.assert_called_once_with(opts)

    @patch("infra.local_converter._ensure_default_converter")
    @patch("infra.local_converter._build_docling_converter")
    def test_uses_custom_converter_when_formula_enrichment_on(self, mock_build, mock_get_default):
        mock_conv = MagicMock()
        mock_result = MagicMock()
        mock_result.document.pages = {}
        mock_result.document.iterate_items.return_value = []
        mock_result.document.export_to_markdown.return_value = ""
        mock_result.document.export_to_html.return_value = ""
        mock_result.document.export_to_dict.return_value = {}
        mock_conv.convert.return_value = mock_result
        mock_build.return_value = mock_conv

        convert_document("/tmp/test.pdf", ConversionOptions(do_formula_enrichment=True))

        mock_build.assert_called_once()

    @patch("infra.local_converter._ensure_default_converter")
    @patch("infra.local_converter._build_docling_converter")
    def test_uses_custom_converter_when_picture_options_on(self, mock_build, mock_get_default):
        mock_conv = MagicMock()
        mock_result = MagicMock()
        mock_result.document.pages = {}
        mock_result.document.iterate_items.return_value = []
        mock_result.document.export_to_markdown.return_value = ""
        mock_result.document.export_to_html.return_value = ""
        mock_result.document.export_to_dict.return_value = {}
        mock_conv.convert.return_value = mock_result
        mock_build.return_value = mock_conv

        convert_document("/tmp/test.pdf", ConversionOptions(do_picture_classification=True))

        mock_build.assert_called_once()

    @patch("infra.local_converter._ensure_default_converter")
    @patch("infra.local_converter._build_docling_converter")
    def test_uses_custom_converter_when_generate_images_on(self, mock_build, mock_get_default):
        mock_conv = MagicMock()
        mock_result = MagicMock()
        mock_result.document.pages = {}
        mock_result.document.iterate_items.return_value = []
        mock_result.document.export_to_markdown.return_value = ""
        mock_result.document.export_to_html.return_value = ""
        mock_result.document.export_to_dict.return_value = {}
        mock_conv.convert.return_value = mock_result
        mock_build.return_value = mock_conv

        convert_document("/tmp/test.pdf", ConversionOptions(generate_picture_images=True))

        mock_build.assert_called_once()

    @patch("infra.local_converter._ensure_default_converter")
    @patch("infra.local_converter._build_docling_converter")
    def test_uses_custom_converter_when_images_scale_changed(self, mock_build, mock_get_default):
        mock_conv = MagicMock()
        mock_result = MagicMock()
        mock_result.document.pages = {}
        mock_result.document.iterate_items.return_value = []
        mock_result.document.export_to_markdown.return_value = ""
        mock_result.document.export_to_html.return_value = ""
        mock_result.document.export_to_dict.return_value = {}
        mock_conv.convert.return_value = mock_result
        mock_build.return_value = mock_conv

        opts = ConversionOptions(images_scale=2.0)
        convert_document("/tmp/test.pdf", opts)

        mock_build.assert_called_once_with(opts)

    @patch("infra.local_converter._ensure_default_converter")
    @patch("infra.local_converter._build_docling_converter")
    def test_forwards_all_options_to_build_converter(self, mock_build, mock_get_default):
        mock_conv = MagicMock()
        mock_result = MagicMock()
        mock_result.document.pages = {}
        mock_result.document.iterate_items.return_value = []
        mock_result.document.export_to_markdown.return_value = ""
        mock_result.document.export_to_html.return_value = ""
        mock_result.document.export_to_dict.return_value = {}
        mock_conv.convert.return_value = mock_result
        mock_build.return_value = mock_conv

        opts = ConversionOptions(
            do_ocr=False,
            do_table_structure=False,
            table_mode="fast",
            do_code_enrichment=True,
            do_formula_enrichment=True,
            do_picture_classification=True,
            do_picture_description=True,
            generate_picture_images=True,
            generate_page_images=True,
            images_scale=1.5,
        )
        convert_document("/tmp/test.pdf", opts)

        mock_build.assert_called_once_with(opts)


# ---------------------------------------------------------------------------
# Service layer — pipeline options forwarding
# ---------------------------------------------------------------------------


class TestServiceForwardsPipelineOptions:
    """Verify analysis_service.create and _run_analysis forward pipeline options."""

    def _make_service(self, converter):
        from services.analysis_service import AnalysisService

        mock_analysis_repo = MagicMock()
        mock_analysis_repo.find_by_id = AsyncMock()
        mock_analysis_repo.insert = AsyncMock()
        mock_analysis_repo.update_status = AsyncMock()
        mock_document_repo = MagicMock()
        mock_document_repo.find_by_id = AsyncMock()
        mock_document_repo.update_page_count = AsyncMock()
        return AnalysisService(
            converter=converter,
            analysis_repo=mock_analysis_repo,
            document_repo=mock_document_repo,
        )

    @pytest.fixture
    def mock_doc(self):
        from domain.models import Document

        return Document(id="d1", filename="test.pdf", storage_path="/tmp/test.pdf")

    @pytest.fixture
    def mock_job(self):
        from domain.models import AnalysisJob

        return AnalysisJob(id="j1", document_id="d1", document_filename="test.pdf")

    @pytest.mark.asyncio
    async def test_create_passes_pipeline_options_to_run(self, mock_doc):
        mock_converter = AsyncMock()
        svc = self._make_service(mock_converter)
        svc._document_repo.find_by_id = AsyncMock(return_value=mock_doc)

        opts = {"do_ocr": False, "table_mode": "fast"}

        with patch("services.analysis_service.asyncio.create_task") as mock_task:
            await svc.create("d1", pipeline_options=opts)
            mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_passes_none_when_no_options(self, mock_doc):
        mock_converter = AsyncMock()
        svc = self._make_service(mock_converter)
        svc._document_repo.find_by_id = AsyncMock(return_value=mock_doc)

        with patch("services.analysis_service.asyncio.create_task") as mock_task:
            await svc.create("d1")
            mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_analysis_forwards_options_to_convert(self, mock_job):
        from domain.value_objects import ConversionResult, PageDetail

        mock_converter = AsyncMock()
        mock_converter.convert.return_value = ConversionResult(
            page_count=1,
            content_markdown="# Test",
            content_html="<h1>Test</h1>",
            pages=[PageDetail(page_number=1, width=612.0, height=792.0)],
        )

        svc = self._make_service(mock_converter)
        svc._analysis_repo.find_by_id = AsyncMock(return_value=mock_job)

        opts = {
            "do_ocr": False,
            "table_mode": "fast",
            "do_code_enrichment": True,
            "do_formula_enrichment": False,
            "do_picture_classification": False,
            "do_picture_description": False,
            "generate_picture_images": True,
            "generate_page_images": False,
            "images_scale": 2.0,
        }

        await svc._run_analysis("j1", "/tmp/test.pdf", "test.pdf", opts)

        mock_converter.convert.assert_called_once()
        call_args = mock_converter.convert.call_args
        assert call_args[0][0] == "/tmp/test.pdf"
        conv_opts = call_args[0][1]
        assert conv_opts.do_ocr is False
        assert conv_opts.table_mode == "fast"
        assert conv_opts.do_code_enrichment is True
        assert conv_opts.generate_picture_images is True
        assert conv_opts.images_scale == 2.0

    @pytest.mark.asyncio
    async def test_run_analysis_uses_defaults_when_no_options(self, mock_job):
        from domain.value_objects import ConversionResult, PageDetail

        mock_converter = AsyncMock()
        mock_converter.convert.return_value = ConversionResult(
            page_count=1,
            content_markdown="",
            content_html="",
            pages=[PageDetail(page_number=1, width=612.0, height=792.0)],
        )

        svc = self._make_service(mock_converter)
        svc._analysis_repo.find_by_id = AsyncMock(return_value=mock_job)

        await svc._run_analysis("j1", "/tmp/test.pdf", "test.pdf", None)

        mock_converter.convert.assert_called_once()
        call_args = mock_converter.convert.call_args
        assert call_args[0][0] == "/tmp/test.pdf"
        assert call_args[0][1] == ConversionOptions()

    @pytest.mark.asyncio
    async def test_run_analysis_marks_failed_on_error(self, mock_job):
        mock_converter = AsyncMock()
        mock_converter.convert.side_effect = RuntimeError("Docling crashed")

        svc = self._make_service(mock_converter)
        svc._analysis_repo.find_by_id = AsyncMock(return_value=mock_job)

        await svc._run_analysis("j1", "/tmp/test.pdf", "test.pdf", {"do_ocr": False})

        # Should have called update_status twice: RUNNING then FAILED
        assert svc._analysis_repo.update_status.call_count == 2
        last_job = svc._analysis_repo.update_status.call_args_list[-1][0][0]
        assert last_job.status.value == "FAILED"
        assert "Docling crashed" in last_job.error_message


# ---------------------------------------------------------------------------
# API endpoint — full request/response with pipeline options
# ---------------------------------------------------------------------------


class TestAnalysisEndpointPipelineOptions:
    """Integration-level tests for the analysis creation endpoint with pipeline options."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from main import app

        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def mock_svc(self, client):
        from unittest.mock import MagicMock

        from main import app
        from tests.app_state import state_override

        mock = MagicMock()
        with state_override(app, analysis_service=mock):
            yield mock

    def test_no_pipeline_options_sends_none(self, client, mock_svc):
        from domain.models import AnalysisJob

        mock_svc.create = AsyncMock(return_value=AnalysisJob(id="j1", document_id="d1"))

        client.post("/api/analyses", json={"documentId": "d1"})

        mock_svc.create.assert_called_once_with("d1", pipeline_options=None, chunking_options=None)

    def test_empty_pipeline_options_object_uses_defaults(self, client, mock_svc):
        from domain.models import AnalysisJob

        mock_svc.create = AsyncMock(return_value=AnalysisJob(id="j1", document_id="d1"))

        client.post(
            "/api/analyses",
            json={
                "documentId": "d1",
                "pipelineOptions": {},
            },
        )

        opts = mock_svc.create.call_args.kwargs["pipeline_options"]
        assert opts["do_ocr"] is True
        assert opts["do_table_structure"] is True
        assert opts["table_mode"] == "accurate"
        assert opts["do_code_enrichment"] is False
        assert opts["do_formula_enrichment"] is False
        assert opts["images_scale"] == 1.0

    def test_partial_pipeline_options_merges_with_defaults(self, client, mock_svc):
        from domain.models import AnalysisJob

        mock_svc.create = AsyncMock(return_value=AnalysisJob(id="j1", document_id="d1"))

        client.post(
            "/api/analyses",
            json={
                "documentId": "d1",
                "pipelineOptions": {"do_ocr": False, "images_scale": 1.5},
            },
        )

        opts = mock_svc.create.call_args.kwargs["pipeline_options"]
        assert opts["do_ocr"] is False
        assert opts["images_scale"] == 1.5
        assert opts["do_table_structure"] is True
        assert opts["table_mode"] == "accurate"
        assert opts["do_code_enrichment"] is False
        assert opts["do_formula_enrichment"] is False
        assert opts["do_picture_classification"] is False
        assert opts["do_picture_description"] is False
        assert opts["generate_picture_images"] is False
        assert opts["generate_page_images"] is False

    def test_full_pipeline_options(self, client, mock_svc):
        from domain.models import AnalysisJob

        mock_svc.create = AsyncMock(return_value=AnalysisJob(id="j1", document_id="d1"))

        payload = {
            "documentId": "d1",
            "pipelineOptions": {
                "do_ocr": False,
                "do_table_structure": False,
                "table_mode": "fast",
                "do_code_enrichment": True,
                "do_formula_enrichment": True,
                "do_picture_classification": True,
                "do_picture_description": True,
                "generate_picture_images": True,
                "generate_page_images": True,
                "images_scale": 2.0,
            },
        }

        resp = client.post("/api/analyses", json=payload)
        assert resp.status_code == 200

        opts = mock_svc.create.call_args.kwargs["pipeline_options"]
        assert opts == payload["pipelineOptions"]

    def test_invalid_pipeline_option_type_rejected(self, client, mock_svc):
        resp = client.post(
            "/api/analyses",
            json={
                "documentId": "d1",
                "pipelineOptions": {"do_ocr": "not-a-bool"},
            },
        )
        assert resp.status_code == 422

    def test_unknown_pipeline_option_ignored(self, client, mock_svc):
        from domain.models import AnalysisJob

        mock_svc.create = AsyncMock(return_value=AnalysisJob(id="j1", document_id="d1"))

        resp = client.post(
            "/api/analyses",
            json={
                "documentId": "d1",
                "pipelineOptions": {"do_ocr": True, "unknown_field": True},
            },
        )
        assert resp.status_code == 200
