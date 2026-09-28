"""Analysis service — async document parsing orchestration.

Uses injected ports (converter, chunker, repositories) so the service is
decoupled from infrastructure implementations.
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import math
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

import pypdfium2 as pdfium

from domain.exceptions import InvalidLifecycleTransitionError
from domain.models import AnalysisJob, AnalysisStatus
from domain.services import classify_error
from domain.value_objects import (
    ChunkingOptions,
    ChunkResult,
    ConversionOptions,
    ConversionResult,
    DocumentLifecycleState,
)

if TYPE_CHECKING:
    from domain.ports import (
        AnalysisRepository,
        DocumentChunker,
        DocumentConverter,
        DocumentRepository,
        GraphWriter,
    )

logger = logging.getLogger(__name__)


def _chunk_to_dict(c: ChunkResult) -> dict:
    """Serialize ChunkResult to a camelCase dict matching the frontend API contract."""
    return {
        "text": c.text,
        "headings": c.headings,
        "sourcePage": c.source_page,
        "tokenCount": c.token_count,
        "bboxes": [{"page": b.page, "bbox": b.bbox} for b in c.bboxes],
        "docItems": [{"selfRef": d.self_ref, "label": d.label} for d in c.doc_items],
    }


# Maximum number of concurrent analysis jobs to prevent resource exhaustion.
_DEFAULT_MAX_CONCURRENT = 3


def _count_pdf_pages(file_path: str) -> int:
    """Count pages in a PDF. Returns 0 if the file is not a valid PDF."""
    try:
        pdf = pdfium.PdfDocument(file_path)
        count = len(pdf)
        pdf.close()
        return count
    except Exception:
        logger.debug("Cannot open %s as PDF, batching disabled", file_path)
        return 0


@dataclass
class AnalysisConfig:
    """Configuration values needed by AnalysisService, extracted from settings."""

    default_table_mode: str = "accurate"
    batch_page_size: int = 0
    neo4j_required: bool = False  # if True, ingestion fails when Neo4j write fails


class AnalysisService:
    """Orchestrates document analysis using injected ports."""

    def __init__(
        self,
        converter: DocumentConverter,
        analysis_repo: AnalysisRepository,
        document_repo: DocumentRepository,
        chunker: DocumentChunker | None = None,
        conversion_timeout: int = 600,
        max_concurrent: int = _DEFAULT_MAX_CONCURRENT,
        config: AnalysisConfig | None = None,
        graph_writer: GraphWriter | None = None,
    ):
        self._converter = converter
        self._chunker = chunker
        self._analysis_repo = analysis_repo
        self._document_repo = document_repo
        self._conversion_timeout = conversion_timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._background_tasks: set[asyncio.Task] = set()
        self._config = config or AnalysisConfig()
        # `GraphWriter` port (#audit-01) — was a raw `Neo4jDriver` until
        # the hex-arch fix. None when no graph store is wired in.
        self._graph_writer = graph_writer
        # Duck-typed callable injected at startup. Wired in main.py to
        # `ChunkService.promote_from_analysis_if_empty` so the canonical
        # chunkset (#205) is populated on the first successful analysis,
        # making the Doc workspace tab functional immediately (#256).
        # Optional: when None, analysis behaviour is unchanged.
        self._chunk_promoter = None
        # Duck-typed recorder for document versions (#267). Wired in
        # main.py to `VersionService.record_on_analysis` so each
        # successful analysis appends a frozen pair to History.
        self._version_recorder = None

    def set_chunk_promoter(self, chunk_service) -> None:
        """Inject the canonical-chunk promoter (post-construction wiring).

        Kept loosely typed to avoid an import cycle between
        `analysis_service` and `chunk_service`. The contract is a
        coroutine `(document_id: str, chunks_json: str) -> int`.
        """
        self._chunk_promoter = chunk_service

    def set_version_recorder(self, version_service) -> None:
        """Inject the document-version recorder (#267, post-construction
        wiring). Contract: a coroutine
        `(document_id: str, analysis_id: str) -> DocumentVersion`.
        """
        self._version_recorder = version_service

    async def create(
        self,
        document_id: str,
        *,
        pipeline_options: dict | None = None,
        chunking_options: dict | None = None,
    ) -> AnalysisJob:
        """Create a new analysis job and launch background processing."""
        doc = await self._document_repo.find_by_id(document_id)
        if not doc:
            raise ValueError(f"Document not found: {document_id}")

        job = AnalysisJob(document_id=document_id)
        job.document_filename = doc.filename
        await self._analysis_repo.insert(job)

        task = asyncio.create_task(
            self._run_analysis(
                job.id,
                doc.storage_path,
                doc.filename,
                pipeline_options,
                chunking_options,
            )
        )
        self._running_tasks[job.id] = task
        task.add_done_callback(functools.partial(self._on_task_done, job_id=job.id))

        return job

    async def find_all(self) -> list[AnalysisJob]:
        """Return all analysis jobs, newest first."""
        return await self._analysis_repo.find_all()

    async def find_by_document(self, document_id: str) -> list[AnalysisJob]:
        """Return analysis jobs for a given document, newest first."""
        return await self._analysis_repo.find_by_document(document_id)

    async def find_by_id(self, job_id: str) -> AnalysisJob | None:
        """Find an analysis job by ID, or return None."""
        return await self._analysis_repo.find_by_id(job_id)

    async def delete(self, job_id: str) -> bool:
        """Delete an analysis job, cancelling any running task. Returns True if it existed."""
        task = self._running_tasks.pop(job_id, None)
        if task and not task.done():
            task.cancel()
            logger.info("Cancelled running task for job %s", job_id)
        return await self._analysis_repo.delete(job_id)

    async def rechunk(self, job_id: str, chunking_options: dict) -> list[ChunkResult]:
        """Re-chunk an existing completed analysis with new options."""
        job = await self._analysis_repo.find_by_id(job_id)
        if not job:
            raise ValueError(f"Analysis not found: {job_id}")
        if job.status != AnalysisStatus.COMPLETED:
            raise ValueError(f"Analysis is not completed: {job_id}")
        if not job.document_json:
            raise ValueError(f"No document data available for re-chunking: {job_id}")
        if not self._chunker:
            raise ValueError("Chunking is not available")

        options = ChunkingOptions(**chunking_options)
        chunks = await self._chunker.chunk(job.document_json, options)

        chunks_json = json.dumps([_chunk_to_dict(c) for c in chunks])
        await self._analysis_repo.update_chunks(job_id, chunks_json)

        # Re-chunk drives the document into Chunked (idempotent if already
        # Chunked; #204 will mark per-store links Stale separately).
        await self._transition_document(job.document_id, DocumentLifecycleState.CHUNKED)

        return chunks

    async def update_chunk_text(self, job_id: str, chunk_index: int, text: str) -> list[dict]:
        """Update the text of a single chunk by index. Returns the full updated chunks list."""
        job = await self._analysis_repo.find_by_id(job_id)
        if not job:
            raise ValueError(f"Analysis not found: {job_id}")
        if job.status != AnalysisStatus.COMPLETED:
            raise ValueError(f"Analysis is not completed: {job_id}")
        if not job.chunks_json:
            raise ValueError(f"No chunks available: {job_id}")

        chunks = json.loads(job.chunks_json)
        if chunk_index < 0 or chunk_index >= len(chunks):
            raise ValueError(f"Chunk index out of range: {chunk_index}")

        chunks[chunk_index]["text"] = text
        chunks[chunk_index]["modified"] = True

        chunks_json = json.dumps(chunks)
        await self._analysis_repo.update_chunks(job_id, chunks_json)

        return chunks

    async def delete_chunk(self, job_id: str, chunk_index: int) -> list[dict]:
        """Soft-delete a chunk by index. Returns the full updated chunks list."""
        job = await self._analysis_repo.find_by_id(job_id)
        if not job:
            raise ValueError(f"Analysis not found: {job_id}")
        if job.status != AnalysisStatus.COMPLETED:
            raise ValueError(f"Analysis is not completed: {job_id}")
        if not job.chunks_json:
            raise ValueError(f"No chunks available: {job_id}")

        chunks = json.loads(job.chunks_json)
        if chunk_index < 0 or chunk_index >= len(chunks):
            raise ValueError(f"Chunk index out of range: {chunk_index}")

        chunks[chunk_index]["deleted"] = True

        chunks_json = json.dumps(chunks)
        await self._analysis_repo.update_chunks(job_id, chunks_json)

        return chunks

    async def _run_batched_conversion(
        self,
        job_id: str,
        file_path: str,
        options: ConversionOptions,
        total_pages: int,
        batch_size: int,
    ) -> ConversionResult | None:
        """Convert a document in batches using page_range.

        Returns None if the job was deleted mid-batch (caller should abort).
        Raises on batch failure (fail-fast: entire job fails).
        """
        num_batches = math.ceil(total_pages / batch_size)
        await self._analysis_repo.update_progress(job_id, 0, total_pages)
        logger.info(
            "Batched conversion: %d pages in %d batches of %d for job %s",
            total_pages,
            num_batches,
            batch_size,
            job_id,
        )

        results: list[ConversionResult] = []
        for batch_idx in range(num_batches):
            start = batch_idx * batch_size + 1
            end = min(start + batch_size - 1, total_pages)

            if not await self._analysis_repo.find_by_id(job_id):
                logger.info(
                    "Job %s deleted during batch %d/%d, aborting",
                    job_id,
                    batch_idx + 1,
                    num_batches,
                )
                return None

            try:
                batch_result = await asyncio.wait_for(
                    self._converter.convert(file_path, options, page_range=(start, end)),
                    timeout=self._conversion_timeout,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Batch {batch_idx + 1}/{num_batches} (pages {start}-{end}) failed: {exc}"
                ) from exc

            results.append(batch_result)
            await self._analysis_repo.update_progress(job_id, end, total_pages)
            logger.info(
                "Batch %d/%d done (pages %d-%d) for job %s",
                batch_idx + 1,
                num_batches,
                start,
                end,
                job_id,
            )

        return await self._converter.merge_batches(results)

    def _on_task_done(self, task: asyncio.Task, *, job_id: str) -> None:
        """Cleanup running tasks and handle failures."""
        self._running_tasks.pop(job_id, None)
        if task.cancelled():
            logger.warning("Analysis task was cancelled: %s", job_id)
            self._schedule_mark_failed(job_id, "Task was cancelled")
            return
        exc = task.exception()
        if exc:
            logger.error("Unhandled exception in analysis task %s: %s", job_id, exc, exc_info=True)
            self._schedule_mark_failed(job_id, classify_error(exc))

    def _schedule_mark_failed(self, job_id: str, error: str) -> None:
        """Schedule _mark_failed as a tracked background task."""
        t = asyncio.ensure_future(self._mark_failed(job_id, error))
        self._background_tasks.add(t)
        t.add_done_callback(self._background_tasks.discard)

    async def _mark_failed(self, job_id: str, error: str) -> None:
        """Safely mark a job as failed, handling DB errors gracefully."""
        try:
            job = await self._analysis_repo.find_by_id(job_id)
            if job:
                job.mark_failed(error)
                await self._analysis_repo.update_status(job)
                await self._transition_document(job.document_id, DocumentLifecycleState.FAILED)
        except OSError:
            logger.exception("Database I/O error marking job %s as failed", job_id)
        except Exception:
            logger.exception("Unexpected error marking job %s as failed", job_id)

    async def _transition_document(
        self,
        document_id: str,
        target: DocumentLifecycleState,
    ) -> None:
        """Drive a Document lifecycle transition (#202).

        Idempotent on the target — if the document is already in the
        requested state, no write happens. Invalid transitions are
        logged at WARNING and swallowed so a lifecycle hiccup does not
        crash an otherwise-successful pipeline run.
        """
        doc = await self._document_repo.find_by_id(document_id)
        if doc is None:
            return
        if doc.lifecycle_state == target:
            return
        try:
            event = doc.transition_to(target)
        except InvalidLifecycleTransitionError:
            logger.warning(
                "Skipped invalid lifecycle transition for doc %s: %s -> %s",
                document_id,
                doc.lifecycle_state.value,
                target.value,
            )
            return
        await self._document_repo.update_lifecycle(document_id, event.current, event.at)
        logger.info(
            "lifecycle_changed doc_id=%s from=%s to=%s",
            document_id,
            event.previous.value,
            event.current.value,
        )

    async def _run_analysis(
        self,
        job_id: str,
        file_path: str,
        filename: str,
        pipeline_options: dict | None = None,
        chunking_options: dict | None = None,
    ) -> None:
        """Background task: run conversion and optionally chunk.

        Acquires the concurrency semaphore to limit parallel conversions
        and prevent CPU/memory exhaustion on modest hardware.
        """
        async with self._semaphore:
            await self._run_analysis_inner(
                job_id, file_path, filename, pipeline_options, chunking_options
            )

    def _build_conversion_options(self, pipeline_options: dict | None) -> ConversionOptions:
        """Build ConversionOptions, applying default table_mode if not specified."""
        opts_dict = pipeline_options or {}
        if "table_mode" not in opts_dict:
            opts_dict = {**opts_dict, "table_mode": self._config.default_table_mode}
        return ConversionOptions(**opts_dict)

    async def _run_conversion(
        self,
        job_id: str,
        file_path: str,
        options: ConversionOptions,
    ) -> ConversionResult | None:
        """Run batched or single conversion. Returns None if the job was deleted mid-batch.

        Batching is only used for local mode — it limits memory usage when
        Docling runs in-process, and reports progress after each batch. The
        converter merges the batches back into one document (#344). In remote
        mode the Serve instance manages its own resources.
        """
        total_pages = _count_pdf_pages(file_path)
        batch_size = self._config.batch_page_size
        if batch_size > 0 and total_pages > batch_size and self._converter.supports_page_batching:
            return await self._run_batched_conversion(
                job_id, file_path, options, total_pages, batch_size
            )
        return await asyncio.wait_for(
            self._converter.convert(file_path, options),
            timeout=self._conversion_timeout,
        )

    async def _finalize_analysis(
        self,
        job_id: str,
        result: ConversionResult,
        chunking_options: dict | None,
    ) -> None:
        """Serialize results, optionally chunk, mark job completed, update page count."""
        pages_json = json.dumps([asdict(p) for p in result.pages])

        chunks_json = None
        if chunking_options and self._chunker and result.document_json:
            chunk_opts = ChunkingOptions(**chunking_options)
            chunks = await self._chunker.chunk(result.document_json, chunk_opts)
            chunks_json = json.dumps([_chunk_to_dict(c) for c in chunks])
            logger.info("Chunking produced %d chunks for job %s", len(chunks), job_id)

        # Re-read the job so we don't lose progress_current/progress_total
        # written to the DB during batched conversion.
        job = await self._analysis_repo.find_by_id(job_id)
        if not job:
            return
        job.mark_completed(
            markdown=result.content_markdown,
            html=result.content_html,
            pages_json=pages_json,
            document_json=result.document_json,
            chunks_json=chunks_json,
        )

        # Record a frozen (analysis, chunks_snapshot) pair in the
        # workspace History timeline (#267). Done BEFORE the status flip
        # to COMPLETED so the frontend polling never observes a
        # completed analysis without its version row in the DB.
        # Snapshots the LIVE chunks at this moment so user edits since
        # the previous version are preserved alongside the new analysis
        # pointer.
        if self._version_recorder is not None:
            try:
                await self._version_recorder.record_on_analysis(job.document_id, job_id)
            except Exception:
                # Versioning is a best-effort side hook — never fail the
                # analysis itself if the snapshot write hits a snag.
                logger.exception(
                    "Version snapshot failed for doc %s after analysis %s",
                    job.document_id,
                    job_id,
                )

        await self._analysis_repo.update_status(job)

        if result.page_count:
            await self._document_repo.update_page_count(job.document_id, result.page_count)

        # Canonical chunk promotion was previously called here (#256), but
        # the 0.6.1 doc workspace (#266) requires the analysis and chunk
        # actions to be independent — running an analysis must NOT
        # implicitly create chunks. Chunks are now produced explicitly via
        # `POST /api/documents/{id}/rechunk` (driven from the Strategy
        # popover, #268). The promoter hook stays wired in main.py so
        # legacy callers / tests can still trigger it directly, but it is
        # no longer invoked as part of the analysis flow.

        # Drive the document lifecycle (#202): chunks present → Chunked,
        # otherwise → Parsed.
        target_state = (
            DocumentLifecycleState.CHUNKED
            if chunks_json is not None
            else DocumentLifecycleState.PARSED
        )
        await self._transition_document(job.document_id, target_state)

        await self._write_tree_to_graph(job, result.document_json)

        logger.info("Analysis completed: %s (%d pages)", job_id, result.page_count)

    async def _write_tree_to_graph(self, job, document_json: str | None) -> None:
        """Mirror the DoclingDocument tree into the graph store if configured.

        Silent no-op when no `GraphWriter` is wired in. Logs but does not
        fail the analysis when the write fails, unless `config.neo4j_required`
        is set (the flag keeps its historical name for env-var compatibility).
        """
        if self._graph_writer is None or not document_json:
            return
        try:
            await self._graph_writer.write_document_tree(
                doc_id=job.document_id,
                filename=job.document_filename or job.document_id,
                document_json=document_json,
            )
        except Exception:
            logger.exception("GraphWriter TreeWrite failed for doc %s", job.document_id)
            if self._config.neo4j_required:
                raise

    async def _run_analysis_inner(
        self,
        job_id: str,
        file_path: str,
        filename: str,
        pipeline_options: dict | None = None,
        chunking_options: dict | None = None,
    ) -> None:
        """Inner analysis logic — called under the concurrency semaphore."""
        try:
            job = await self._analysis_repo.find_by_id(job_id)
            if not job:
                logger.error("Analysis job %s not found", job_id)
                return

            job.mark_running()
            await self._analysis_repo.update_status(job)
            logger.info("Analysis started: %s (file: %s)", job_id, filename)

            options = self._build_conversion_options(pipeline_options)
            result = await self._run_conversion(job_id, file_path, options)
            if result is None:
                return  # job was deleted mid-batch

            await self._finalize_analysis(job_id, result, chunking_options)

        except TimeoutError:
            logger.error("Analysis timed out after %ds: %s", self._conversion_timeout, job_id)
            await self._mark_failed(
                job_id, f"Conversion timed out after {self._conversion_timeout}s"
            )

        except Exception as e:
            logger.exception("Analysis failed: %s", job_id)
            await self._mark_failed(job_id, classify_error(e))
