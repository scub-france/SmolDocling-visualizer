"""Document API router — upload, list, get, delete, preview."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response

from api import deps  # noqa: TC001
from api.schemas import DocStoreLinkResponse, DocumentResponse, PageSizeResponse
from services.document_service import DocumentService
from services.export_service import ExportFormat, ExportNotFoundError, build_content_disposition

if TYPE_CHECKING:
    from domain.ports import DocumentStoreLinkRepository, StoreRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])

_READ_CHUNK_SIZE = 64 * 1024  # 64 KB


def _to_response(doc, *, store_links: list[DocStoreLinkResponse] | None = None) -> DocumentResponse:
    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        file_size=doc.file_size,
        page_count=doc.page_count,
        created_at=str(doc.created_at),
        lifecycle_state=doc.lifecycle_state.value,
        lifecycle_state_at=(str(doc.lifecycle_state_at) if doc.lifecycle_state_at else None),
        store_links=store_links,
    )


async def _fetch_store_links(
    doc_id: str,
    link_repo: DocumentStoreLinkRepository,
    store_repo: StoreRepository,
) -> list[DocStoreLinkResponse]:
    """Build the per-store link payload for a single document (#283 fix).

    Joins `document_store_links` with `stores` so the frontend gets the
    store slug (its stable identity) on each link, not the opaque
    store_id. Returns an empty list when no links exist — the frontend
    treats absent vs empty the same.
    """
    links = await link_repo.find_for_document(doc_id)
    if not links:
        return []
    # Resolve store_id → slug in one shot. `find_all()` is fine here —
    # store rows are O(1-10) in practice.
    stores = await store_repo.find_all()
    slug_by_id = {s.id: s.slug for s in stores}
    return [
        DocStoreLinkResponse(
            store=slug_by_id.get(link.store_id, link.store_id),
            state=link.state.value,
            pushed_at=str(link.last_push_at) if link.last_push_at else None,
        )
        for link in links
    ]


@router.post("/upload", response_model=DocumentResponse, status_code=200)
async def upload(file: UploadFile, service: deps.DocumentServiceDep) -> DocumentResponse:
    """Upload a PDF document."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Reject early if Content-Length exceeds limit (before reading body)
    _max = service.max_file_size
    _detail = f"File too large (max {service.max_file_size_mb} MB)"
    if _max > 0 and file.size and file.size > _max:
        raise HTTPException(status_code=413, detail=_detail)

    # Read in chunks to avoid holding the full upload in a single allocation
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_READ_CHUNK_SIZE):
        total += len(chunk)
        if _max > 0 and total > _max:
            raise HTTPException(status_code=413, detail=_detail)
        chunks.append(chunk)
    content = b"".join(chunks)

    try:
        doc = await service.upload(
            filename=file.filename,
            content_type=file.content_type or "application/pdf",
            file_content=content,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return _to_response(doc)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(service: deps.DocumentServiceDep) -> list[DocumentResponse]:
    """List all documents."""
    docs = await service.find_all()
    return [_to_response(d) for d in docs]


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    service: deps.DocumentServiceDep,
    link_repo: deps.DocumentStoreLinkRepoDep,
    store_repo: deps.StoreRepoDep,
) -> DocumentResponse:
    """Get a single document, joined with its per-store ingestion links."""
    doc = await service.find_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    store_links = await _fetch_store_links(doc_id, link_repo, store_repo)
    return _to_response(doc, store_links=store_links)


@router.delete("/{doc_id}", status_code=204, response_model=None)
async def delete_document(doc_id: str, service: deps.DocumentServiceDep) -> None:
    """Delete a document and its file."""
    deleted = await service.delete(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")


@router.get("/{doc_id}/export")
async def export_document(
    doc_id: str,
    service: deps.ExportServiceDep,
    format: ExportFormat = Query(ExportFormat.PDF, description="Format to export"),
    analysis_id: str | None = Query(
        default=None,
        alias="analysisId",
        description="Analysis to export for md/json (defaults to the latest completed)",
    ),
) -> Response:
    """Export the document in the specified format."""
    try:
        export = await service.export(doc_id, format, analysis_id)
    except ExportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if export.file_path is not None:
        return FileResponse(
            export.file_path,
            media_type=export.media_type,
            filename=export.filename,
        )

    return Response(
        content=export.content or "",
        media_type=export.media_type,
        headers={"Content-Disposition": build_content_disposition(export.filename)},
    )


@router.get("/{doc_id}/preview")
async def preview(
    doc_id: str,
    service: deps.DocumentServiceDep,
    page: int = Query(1, ge=1),
    dpi: int = Query(150, ge=72, le=300),
) -> Response:
    """Generate a PNG preview of a specific PDF page."""
    doc = await service.find_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.page_count and page > doc.page_count:
        raise HTTPException(
            status_code=400,
            detail=f"Page {page} out of range (document has {doc.page_count} pages)",
        )

    try:
        # File read + PDF rasterisation are both blocking; offload to a
        # worker thread so the event loop stays free for other requests.
        file_content = await asyncio.to_thread(Path(doc.storage_path).read_bytes)
        png_bytes = await asyncio.to_thread(
            DocumentService.generate_preview, file_content, page=page, dpi=dpi
        )
        return Response(content=png_bytes, media_type="image/png")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="PDF file not found on disk") from exc
    except OSError as exc:
        logger.exception("I/O error generating preview for %s", doc_id)
        raise HTTPException(status_code=422, detail="Failed to read PDF file") from exc
    except Exception as exc:
        logger.exception("Unexpected error generating preview for %s", doc_id)
        raise HTTPException(status_code=422, detail="Failed to generate preview") from exc


@router.get("/{doc_id}/pages", response_model=list[PageSizeResponse])
async def page_sizes(doc_id: str, service: deps.DocumentServiceDep) -> list[PageSizeResponse]:
    """Size of each page of the PDF, so the preview can lay out its pages
    before any analysis (#352)."""
    doc = await service.find_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        file_content = await asyncio.to_thread(Path(doc.storage_path).read_bytes)
        pages = await asyncio.to_thread(DocumentService.page_sizes, file_content)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="PDF file not found on disk") from exc
    except Exception as exc:
        logger.exception("Could not read the page sizes of %s", doc_id)
        raise HTTPException(status_code=422, detail="Failed to read PDF file") from exc
    return [
        PageSizeResponse(page_number=p.page_number, width=p.width, height=p.height) for p in pages
    ]
