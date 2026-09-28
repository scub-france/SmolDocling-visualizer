"""Analysis API router — create, list, get, delete analysis jobs."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from api import deps  # noqa: TC001
from api.schemas import (
    AnalysisResponse,
    AnalysisSummaryResponse,
    ChunkBboxResponse,
    ChunkResponse,
    CreateAnalysisRequest,
    RechunkRequest,
    UpdateChunkTextRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analyses", tags=["analyses"])


def _to_response(job) -> AnalysisResponse:
    return AnalysisResponse(
        id=job.id,
        document_id=job.document_id,
        document_filename=job.document_filename,
        status=job.status.value,
        content_markdown=job.content_markdown,
        content_html=job.content_html,
        pages_json=job.pages_json,
        chunks_json=job.chunks_json,
        has_document_json=job.document_json is not None,
        error_message=job.error_message,
        progress_current=job.progress_current,
        progress_total=job.progress_total,
        started_at=str(job.started_at) if job.started_at else None,
        completed_at=str(job.completed_at) if job.completed_at else None,
        created_at=str(job.created_at),
    )


@router.post("", response_model=AnalysisResponse)
async def create_analysis(
    body: CreateAnalysisRequest, service: deps.AnalysisServiceDep
) -> AnalysisResponse:
    """Create a new analysis job for a document."""
    if not body.documentId or not body.documentId.strip():
        raise HTTPException(status_code=400, detail="documentId is required")

    pipeline_opts = None
    if body.pipelineOptions:
        pipeline_opts = body.pipelineOptions.model_dump()

    chunking_opts = None
    if body.chunkingOptions:
        chunking_opts = body.chunkingOptions.model_dump()

    try:
        job = await service.create(
            body.documentId,
            pipeline_options=pipeline_opts,
            chunking_options=chunking_opts,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return _to_response(job)


@router.get("", response_model=list[AnalysisResponse])
async def list_analyses(
    service: deps.AnalysisServiceDep,
    document_id: str | None = Query(default=None, alias="documentId"),
) -> list[AnalysisResponse]:
    """List analysis jobs, optionally filtered by documentId."""
    if document_id:
        jobs = await service.find_by_document(document_id)
    else:
        jobs = await service.find_all()
    return [_to_response(j) for j in jobs]


# Declared before `/{analysis_id}`, which would otherwise take "summaries" for an id.
@router.get("/summaries", response_model=list[AnalysisSummaryResponse])
async def list_analysis_summaries(
    service: deps.AnalysisServiceDep,
) -> list[AnalysisSummaryResponse]:
    """List analysis jobs without their content, to follow their statuses (#354).

    The full list carries every analysis's markdown, HTML, pages and chunks,
    far too heavy to poll while a batch runs.
    """
    return [
        AnalysisSummaryResponse(
            id=job.id,
            document_id=job.document_id,
            document_filename=job.document_filename,
            status=job.status.value,
            error_message=job.error_message,
            progress_current=job.progress_current,
            progress_total=job.progress_total,
            started_at=str(job.started_at) if job.started_at else None,
            completed_at=str(job.completed_at) if job.completed_at else None,
            created_at=str(job.created_at),
        )
        for job in await service.find_all_summaries()
    ]


@router.get("/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(analysis_id: str, service: deps.AnalysisServiceDep) -> AnalysisResponse:
    """Get a single analysis job."""
    job = await service.find_by_id(analysis_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _to_response(job)


@router.post("/{analysis_id}/rechunk", response_model=list[ChunkResponse])
async def rechunk_analysis(
    analysis_id: str, body: RechunkRequest, service: deps.AnalysisServiceDep
) -> list[ChunkResponse]:
    """Re-chunk a completed analysis with new chunking options."""
    try:
        chunks = await service.rechunk(analysis_id, body.chunkingOptions.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return [
        ChunkResponse(
            text=c.text,
            headings=c.headings,
            source_page=c.source_page,
            token_count=c.token_count,
            bboxes=[ChunkBboxResponse(page=b.page, bbox=b.bbox) for b in c.bboxes],
        )
        for c in chunks
    ]


@router.patch("/{analysis_id}/chunks/{chunk_index}", response_model=list[ChunkResponse])
async def update_chunk_text(
    analysis_id: str,
    chunk_index: int,
    body: UpdateChunkTextRequest,
    service: deps.AnalysisServiceDep,
) -> list[ChunkResponse]:
    """Update the text of a single chunk by index."""
    try:
        chunks = await service.update_chunk_text(analysis_id, chunk_index, body.text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return [
        ChunkResponse(
            text=c["text"],
            headings=c.get("headings", []),
            source_page=c.get("sourcePage"),
            token_count=c.get("tokenCount", 0),
            bboxes=[ChunkBboxResponse(page=b["page"], bbox=b["bbox"]) for b in c.get("bboxes", [])],
            modified=c.get("modified", False),
            deleted=c.get("deleted", False),
        )
        for c in chunks
    ]


@router.delete("/{analysis_id}/chunks/{chunk_index}", response_model=list[ChunkResponse])
async def delete_chunk(
    analysis_id: str, chunk_index: int, service: deps.AnalysisServiceDep
) -> list[ChunkResponse]:
    """Soft-delete a chunk by index (marks it as deleted)."""
    try:
        chunks = await service.delete_chunk(analysis_id, chunk_index)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return [
        ChunkResponse(
            text=c["text"],
            headings=c.get("headings", []),
            source_page=c.get("sourcePage"),
            token_count=c.get("tokenCount", 0),
            bboxes=[ChunkBboxResponse(page=b["page"], bbox=b["bbox"]) for b in c.get("bboxes", [])],
            modified=c.get("modified", False),
            deleted=c.get("deleted", False),
        )
        for c in chunks
    ]


@router.delete("/{analysis_id}", status_code=204, response_model=None)
async def delete_analysis(analysis_id: str, service: deps.AnalysisServiceDep) -> None:
    """Delete an analysis job."""
    deleted = await service.delete(analysis_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Analysis not found")
