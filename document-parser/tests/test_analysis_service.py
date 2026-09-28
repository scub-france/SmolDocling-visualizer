"""Tests for AnalysisService — callbacks, concurrency, orchestration, and batching."""

from __future__ import annotations

import asyncio
import functools
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.models import AnalysisStatus
from domain.services import extract_html_body, merge_results
from domain.value_objects import ConversionResult, PageDetail
from services.analysis_service import AnalysisConfig, AnalysisService, _count_pdf_pages


def _make_service(**kwargs) -> AnalysisService:
    """Create an AnalysisService with mock repos for testing."""
    defaults = {
        "converter": MagicMock(),
        "analysis_repo": MagicMock(),
        "document_repo": MagicMock(),
    }
    defaults.update(kwargs)
    return AnalysisService(**defaults)


class TestOnTaskDone:
    """Bug #1: _on_task_done must call _mark_failed when the task raises."""

    @pytest.mark.asyncio
    async def test_exception_marks_job_failed(self):
        """When a background task raises, the job should be marked FAILED."""
        job_id = "job-123"
        service = _make_service()

        async def failing_task():
            raise RuntimeError("unexpected failure")

        task = asyncio.create_task(failing_task())
        await asyncio.sleep(0)

        with patch.object(service, "_mark_failed", new_callable=AsyncMock) as mock_mark:
            service._on_task_done(task, job_id=job_id)
            await asyncio.sleep(0)

        mock_mark.assert_called_once_with(job_id, "unexpected failure")

    @pytest.mark.asyncio
    async def test_exception_uses_classify_error(self):
        """_on_task_done should route exceptions through classify_error."""
        job_id = "job-classify"
        service = _make_service()

        async def timeout_task():
            raise TimeoutError("timeout exceeded while processing")

        task = asyncio.create_task(timeout_task())
        await asyncio.sleep(0)

        with patch.object(service, "_mark_failed", new_callable=AsyncMock) as mock_mark:
            service._on_task_done(task, job_id=job_id)
            await asyncio.sleep(0)

        mock_mark.assert_called_once_with(
            job_id, "Processing took too long — try with fewer pages or simpler options"
        )

    @pytest.mark.asyncio
    async def test_cancelled_task_marks_job_failed(self):
        """When a background task is cancelled, the job should be marked FAILED."""
        job_id = "job-456"
        service = _make_service()

        async def slow_task():
            await asyncio.sleep(999)

        import contextlib

        task = asyncio.create_task(slow_task())
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        with patch.object(service, "_mark_failed", new_callable=AsyncMock) as mock_mark:
            service._on_task_done(task, job_id=job_id)
            await asyncio.sleep(0)

        mock_mark.assert_called_once_with(job_id, "Task was cancelled")

    @pytest.mark.asyncio
    async def test_successful_task_does_not_mark_failed(self):
        """When a background task succeeds, _mark_failed should not be called."""
        job_id = "job-789"
        service = _make_service()

        async def ok_task():
            return "done"

        task = asyncio.create_task(ok_task())
        await task

        with patch.object(service, "_mark_failed", new_callable=AsyncMock) as mock_mark:
            service._on_task_done(task, job_id=job_id)
            await asyncio.sleep(0)

        mock_mark.assert_not_called()


class TestAnalysisServiceCancellation:
    """Verify delete cancels running tasks."""

    @pytest.mark.asyncio
    async def test_delete_cancels_running_task(self):
        """Deleting a job while running should cancel its task."""
        mock_analysis_repo = MagicMock()
        mock_analysis_repo.delete = AsyncMock(return_value=True)
        service = _make_service(analysis_repo=mock_analysis_repo)

        blocker = asyncio.Event()

        async def slow_analysis():
            await blocker.wait()

        task = asyncio.create_task(slow_analysis())
        service._running_tasks["j1"] = task

        result = await service.delete("j1")

        assert result is True
        assert task.cancelling() or task.cancelled()
        assert "j1" not in service._running_tasks

    @pytest.mark.asyncio
    async def test_delete_completed_job_no_error(self):
        """Deleting a completed job should not raise even if no task tracked."""
        mock_analysis_repo = MagicMock()
        mock_analysis_repo.delete = AsyncMock(return_value=True)
        service = _make_service(analysis_repo=mock_analysis_repo)

        result = await service.delete("j-gone")

        assert result is True

    @pytest.mark.asyncio
    async def test_task_cleaned_from_running_on_completion(self):
        """After a task completes, it should be removed from _running_tasks."""
        service = _make_service()

        async def instant():
            pass

        task = asyncio.create_task(instant())
        service._running_tasks["j1"] = task
        task.add_done_callback(functools.partial(service._on_task_done, job_id="j1"))
        await asyncio.gather(task)

        assert "j1" not in service._running_tasks


class TestAnalysisServiceConcurrency:
    """Verify that the semaphore limits concurrent analysis jobs."""

    def test_semaphore_initialized_with_max_concurrent(self):
        service = _make_service(max_concurrent=5)
        assert service._semaphore._value == 5

    def test_default_max_concurrent(self):
        service = _make_service()
        assert service._semaphore._value == 3

    @pytest.mark.asyncio
    async def test_semaphore_limits_parallel_jobs(self):
        """Only max_concurrent jobs should run in parallel; others must wait."""
        call_order: list[str] = []
        blocker = asyncio.Event()

        service = _make_service(max_concurrent=1)

        async def fake_inner(self, *args, **kwargs):
            call_order.append("start")
            await blocker.wait()
            call_order.append("end")

        with patch.object(AnalysisService, "_run_analysis_inner", fake_inner):
            t1 = asyncio.create_task(service._run_analysis("j1", "/f", "f.pdf"))
            t2 = asyncio.create_task(service._run_analysis("j2", "/f", "f.pdf"))
            await asyncio.sleep(0.05)

            # With max_concurrent=1, only one task should have started
            assert call_order.count("start") == 1

            blocker.set()
            await asyncio.gather(t1, t2)

            # Both should have completed
            assert call_order.count("start") == 2
            assert call_order.count("end") == 2


# ---------------------------------------------------------------------------
# Batch helper tests
# ---------------------------------------------------------------------------


class TestCountPdfPages:
    def test_valid_pdf(self, tmp_path):
        """A real (minimal) PDF should return its page count."""
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument.new()
        pdf.new_page(612, 792)
        path = tmp_path / "test.pdf"
        pdf.save(str(path))
        pdf.close()

        assert _count_pdf_pages(str(path)) == 1

    def test_non_pdf_file(self, tmp_path):
        """A non-PDF file should return 0."""
        path = tmp_path / "test.docx"
        path.write_bytes(b"PK\x03\x04 not a pdf")
        assert _count_pdf_pages(str(path)) == 0

    def test_nonexistent_file(self):
        """A nonexistent file should return 0."""
        assert _count_pdf_pages("/no/such/file.pdf") == 0

    def test_empty_file(self, tmp_path):
        """An empty file should return 0."""
        path = tmp_path / "empty.pdf"
        path.write_bytes(b"")
        assert _count_pdf_pages(str(path)) == 0


class TestExtractHtmlBody:
    def test_extracts_body(self):
        html = '<html><head></head><body class="x"><p>Hello</p></body></html>'
        assert extract_html_body(html) == "<p>Hello</p>"

    def test_no_body_tag_returns_raw(self):
        html = "<p>No body tag</p>"
        assert extract_html_body(html) == html

    def test_empty_body(self):
        html = "<html><body></body></html>"
        assert extract_html_body(html) == ""


class TestMergeResults:
    def test_empty_list(self):
        result = merge_results([])
        assert result.page_count == 0
        assert result.content_markdown == ""
        assert result.pages == []
        assert result.document_json is None

    def test_single_result_passthrough(self):
        r = ConversionResult(
            page_count=3,
            content_markdown="# Page 1",
            content_html="<html><body><p>Page 1</p></body></html>",
            pages=[PageDetail(page_number=1, width=612, height=792)],
            document_json='{"pages": {}}',
        )
        merged = merge_results([r])
        assert merged.page_count == 3
        assert merged.content_markdown == "# Page 1"
        assert merged.pages == [PageDetail(page_number=1, width=612, height=792)]
        assert merged.document_json is None  # intentionally dropped

    def test_merges_multiple_results(self):
        r1 = ConversionResult(
            page_count=2,
            content_markdown="# Batch 1",
            content_html="<html><body><p>B1</p></body></html>",
            pages=[
                PageDetail(page_number=1, width=612, height=792),
                PageDetail(page_number=2, width=612, height=792),
            ],
            skipped_items=1,
        )
        r2 = ConversionResult(
            page_count=2,
            content_markdown="# Batch 2",
            content_html="<html><body><p>B2</p></body></html>",
            pages=[
                PageDetail(page_number=3, width=612, height=792),
                PageDetail(page_number=4, width=612, height=792),
            ],
            skipped_items=2,
        )
        merged = merge_results([r1, r2])
        assert merged.page_count == 4
        assert merged.content_markdown == "# Batch 1\n\n# Batch 2"
        assert len(merged.pages) == 4
        assert merged.pages[0].page_number == 1
        assert merged.pages[3].page_number == 4
        assert merged.skipped_items == 3
        assert merged.document_json is None
        assert "<p>B1</p>" in merged.content_html
        assert "<p>B2</p>" in merged.content_html
        # Valid HTML structure
        assert merged.content_html.startswith("<!DOCTYPE html>")
        assert "</body></html>" in merged.content_html


# ---------------------------------------------------------------------------
# Batched conversion integration tests
# ---------------------------------------------------------------------------


class TestBatchedConversion:
    @pytest.mark.asyncio
    async def test_batched_conversion_produces_merged_result(self):
        """When batch_page_size is set and document exceeds it, the converter
        merges the batch results, in page order (#344)."""
        converter = AsyncMock()
        converter.merge_batches.side_effect = merge_results

        # Simulate 2 batches: pages 1-5 and 6-8
        converter.convert.side_effect = [
            ConversionResult(
                page_count=5,
                content_markdown="# Batch 1",
                content_html="<html><body><p>B1</p></body></html>",
                pages=[PageDetail(page_number=i, width=612, height=792) for i in range(1, 6)],
            ),
            ConversionResult(
                page_count=3,
                content_markdown="# Batch 2",
                content_html="<html><body><p>B2</p></body></html>",
                pages=[PageDetail(page_number=i, width=612, height=792) for i in range(6, 9)],
            ),
        ]

        mock_analysis_repo = MagicMock()
        mock_analysis_repo.find_by_id = AsyncMock(return_value=MagicMock())
        mock_analysis_repo.update_progress = AsyncMock()

        service = _make_service(
            converter=converter,
            analysis_repo=mock_analysis_repo,
            conversion_timeout=60,
        )

        result = await service._run_batched_conversion(
            "job-1",
            "/fake.pdf",
            MagicMock(),
            total_pages=8,
            batch_size=5,
        )

        assert result is not None
        assert result.page_count == 8
        assert len(result.pages) == 8
        assert converter.convert.call_count == 2
        converter.merge_batches.assert_awaited_once()
        batches = converter.merge_batches.await_args.args[0]
        assert [b.content_markdown for b in batches] == ["# Batch 1", "# Batch 2"]

        # Verify page_range was passed correctly
        call1_kwargs = converter.convert.call_args_list[0].kwargs
        call2_kwargs = converter.convert.call_args_list[1].kwargs
        assert call1_kwargs["page_range"] == (1, 5)
        assert call2_kwargs["page_range"] == (6, 8)

    @pytest.mark.asyncio
    async def test_batch_failure_raises_with_enriched_message(self):
        """If a batch fails, RuntimeError is raised with batch info."""
        converter = AsyncMock()
        converter.convert.side_effect = [
            ConversionResult(
                page_count=5,
                content_markdown="ok",
                content_html="<html><body>ok</body></html>",
                pages=[PageDetail(page_number=i, width=612, height=792) for i in range(1, 6)],
            ),
            RuntimeError("OOM"),
        ]

        mock_analysis_repo = MagicMock()
        mock_analysis_repo.find_by_id = AsyncMock(return_value=MagicMock())
        mock_analysis_repo.update_progress = AsyncMock()

        service = _make_service(
            converter=converter,
            analysis_repo=mock_analysis_repo,
            conversion_timeout=60,
        )

        with pytest.raises(RuntimeError, match=r"Batch 2/2 \(pages 6-8\) failed: OOM"):
            await service._run_batched_conversion(
                "job-fail",
                "/fake.pdf",
                MagicMock(),
                total_pages=8,
                batch_size=5,
            )

    @pytest.mark.asyncio
    async def test_progress_preserved_through_full_analysis_flow(self):
        """Progress written during batches must survive the final update_status.

        Regression: _run_analysis_inner used to re-read the job from DB at the
        start, then call update_status(job) at the end — overwriting
        progress_current/progress_total with None because the in-memory object
        was stale.  The fix re-reads the job before mark_completed.
        """
        from domain.models import AnalysisJob, AnalysisStatus

        converter = AsyncMock()
        converter.merge_batches.side_effect = merge_results
        converter.convert.side_effect = [
            ConversionResult(
                page_count=5,
                content_markdown="# B1",
                content_html="<html><body><p>B1</p></body></html>",
                pages=[PageDetail(page_number=i, width=612, height=792) for i in range(1, 6)],
            ),
            ConversionResult(
                page_count=3,
                content_markdown="# B2",
                content_html="<html><body><p>B2</p></body></html>",
                pages=[PageDetail(page_number=i, width=612, height=792) for i in range(6, 9)],
            ),
        ]

        # Simulated DB state: find_by_id is called 4 times:
        #   1) start of _run_analysis_inner (initial load)
        #   2) batch 1 mid-flight deletion check
        #   3) batch 2 mid-flight deletion check
        #   4) re-read before mark_completed (must carry progress)
        initial_job = AnalysisJob(
            id="job-progress",
            document_id="doc-1",
            status=AnalysisStatus.PENDING,
        )
        batch_check_job = AnalysisJob(
            id="job-progress",
            document_id="doc-1",
            status=AnalysisStatus.RUNNING,
        )
        refreshed_job = AnalysisJob(
            id="job-progress",
            document_id="doc-1",
            status=AnalysisStatus.RUNNING,
            progress_current=8,
            progress_total=8,
        )

        saved_jobs: list[AnalysisJob] = []

        async def capture_update_status(job):
            saved_jobs.append(job)

        mock_analysis_repo = MagicMock()
        mock_analysis_repo.find_by_id = AsyncMock(
            side_effect=[initial_job, batch_check_job, batch_check_job, refreshed_job]
        )
        mock_analysis_repo.update_status = AsyncMock(side_effect=capture_update_status)
        mock_analysis_repo.update_progress = AsyncMock()

        mock_document_repo = MagicMock()
        mock_document_repo.update_page_count = AsyncMock()

        config = AnalysisConfig(default_table_mode="accurate", batch_page_size=5)

        service = AnalysisService(
            converter=converter,
            analysis_repo=mock_analysis_repo,
            document_repo=mock_document_repo,
            conversion_timeout=60,
            config=config,
        )

        with patch("services.analysis_service._count_pdf_pages", return_value=8):
            await service._run_analysis_inner("job-progress", "/fake.pdf", "fake.pdf")

        # The last update_status call is the COMPLETED one
        completed_job = saved_jobs[-1]
        assert completed_job.status == AnalysisStatus.COMPLETED
        assert completed_job.progress_current == 8, (
            "progress_current must be preserved (was the bug: got None)"
        )
        assert completed_job.progress_total == 8, (
            "progress_total must be preserved (was the bug: got None)"
        )

    @pytest.mark.asyncio
    async def test_job_deleted_mid_batch_returns_none(self):
        """If the job is deleted between batches, conversion aborts with None."""
        converter = AsyncMock()
        converter.convert.return_value = ConversionResult(
            page_count=5,
            content_markdown="ok",
            content_html="<html><body>ok</body></html>",
            pages=[PageDetail(page_number=i, width=612, height=792) for i in range(1, 6)],
        )

        mock_analysis_repo = MagicMock()
        # First check returns job, second returns None (deleted)
        mock_analysis_repo.find_by_id = AsyncMock(side_effect=[MagicMock(), None])
        mock_analysis_repo.update_progress = AsyncMock()

        service = _make_service(
            converter=converter,
            analysis_repo=mock_analysis_repo,
            conversion_timeout=60,
        )

        result = await service._run_batched_conversion(
            "job-del",
            "/fake.pdf",
            MagicMock(),
            total_pages=10,
            batch_size=5,
        )

        assert result is None
        # Only first batch should have been converted
        assert converter.convert.call_count == 1


class TestUpdateChunkText:
    """Tests for AnalysisService.update_chunk_text."""

    @pytest.mark.asyncio
    async def test_update_chunk_text_success(self):
        chunks = [
            {"text": "original", "headings": [], "sourcePage": 1, "tokenCount": 5, "bboxes": []},
            {"text": "second", "headings": [], "sourcePage": 2, "tokenCount": 3, "bboxes": []},
        ]
        job = MagicMock()
        job.status = AnalysisStatus.COMPLETED
        job.chunks_json = json.dumps(chunks)

        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=job)
        repo.update_chunks = AsyncMock(return_value=True)

        service = _make_service(analysis_repo=repo)
        result = await service.update_chunk_text("j1", 0, "updated text")

        assert result[0]["text"] == "updated text"
        assert result[0]["modified"] is True
        assert result[1]["text"] == "second"
        assert result[1].get("modified", False) is False
        repo.update_chunks.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_chunk_text_not_found(self):
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=None)
        service = _make_service(analysis_repo=repo)

        with pytest.raises(ValueError, match="Analysis not found"):
            await service.update_chunk_text("missing", 0, "text")

    @pytest.mark.asyncio
    async def test_update_chunk_text_not_completed(self):
        job = MagicMock()
        job.status = AnalysisStatus.RUNNING

        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=job)
        service = _make_service(analysis_repo=repo)

        with pytest.raises(ValueError, match="not completed"):
            await service.update_chunk_text("j1", 0, "text")

    @pytest.mark.asyncio
    async def test_update_chunk_text_index_out_of_range(self):
        chunks = [
            {"text": "only one", "headings": [], "sourcePage": 1, "tokenCount": 5, "bboxes": []}
        ]
        job = MagicMock()
        job.status = AnalysisStatus.COMPLETED
        job.chunks_json = json.dumps(chunks)

        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=job)
        service = _make_service(analysis_repo=repo)

        with pytest.raises(ValueError, match="out of range"):
            await service.update_chunk_text("j1", 5, "text")

    @pytest.mark.asyncio
    async def test_update_chunk_text_no_chunks(self):
        job = MagicMock()
        job.status = AnalysisStatus.COMPLETED
        job.chunks_json = None

        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=job)
        service = _make_service(analysis_repo=repo)

        with pytest.raises(ValueError, match="No chunks available"):
            await service.update_chunk_text("j1", 0, "text")


class TestDeleteChunk:
    """Tests for AnalysisService.delete_chunk."""

    @pytest.mark.asyncio
    async def test_delete_chunk_success(self):
        chunks = [
            {"text": "chunk1", "headings": [], "sourcePage": 1, "tokenCount": 5, "bboxes": []},
            {"text": "chunk2", "headings": [], "sourcePage": 2, "tokenCount": 3, "bboxes": []},
        ]
        job = MagicMock()
        job.status = AnalysisStatus.COMPLETED
        job.chunks_json = json.dumps(chunks)

        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=job)
        repo.update_chunks = AsyncMock(return_value=True)

        service = _make_service(analysis_repo=repo)
        result = await service.delete_chunk("j1", 0)

        assert result[0]["deleted"] is True
        assert result[1].get("deleted", False) is False
        repo.update_chunks.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_chunk_not_found(self):
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=None)
        service = _make_service(analysis_repo=repo)

        with pytest.raises(ValueError, match="Analysis not found"):
            await service.delete_chunk("missing", 0)

    @pytest.mark.asyncio
    async def test_delete_chunk_index_out_of_range(self):
        chunks = [{"text": "only", "headings": [], "sourcePage": 1, "tokenCount": 5, "bboxes": []}]
        job = MagicMock()
        job.status = AnalysisStatus.COMPLETED
        job.chunks_json = json.dumps(chunks)

        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=job)
        service = _make_service(analysis_repo=repo)

        with pytest.raises(ValueError, match="out of range"):
            await service.delete_chunk("j1", 5)

    @pytest.mark.asyncio
    async def test_delete_chunk_no_chunks(self):
        job = MagicMock()
        job.status = AnalysisStatus.COMPLETED
        job.chunks_json = None

        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=job)
        service = _make_service(analysis_repo=repo)

        with pytest.raises(ValueError, match="No chunks available"):
            await service.delete_chunk("j1", 0)


class TestFindAllSummaries:
    async def test_reads_the_light_listing(self):
        # #354 — polled while a batch runs, so it must not load the content.
        analysis_repo = MagicMock()
        analysis_repo.find_all_summaries = AsyncMock(return_value=["summary"])
        service = _make_service(analysis_repo=analysis_repo)

        assert await service.find_all_summaries() == ["summary"]
        analysis_repo.find_all_summaries.assert_awaited_once()
