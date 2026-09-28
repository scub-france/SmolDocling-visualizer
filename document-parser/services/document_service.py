"""Document service — file upload, storage, and preview orchestration."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pypdfium2 as pdfium
from pdf2image import convert_from_bytes, pdfinfo_from_bytes

from domain.models import Document
from domain.value_objects import PageDetail

if TYPE_CHECKING:
    from domain.ports import AnalysisRepository, DocumentRepository

logger = logging.getLogger(__name__)


# PDF magic bytes: %PDF
_PDF_MAGIC = b"%PDF"

_UPLOAD_CHUNK_SIZE = 64 * 1024  # 64 KB chunks for streaming writes


@dataclass
class DocumentConfig:
    """Configuration values needed by DocumentService, extracted from settings."""

    upload_dir: str = "uploads"
    max_file_size_mb: int = 0
    max_page_count: int = 0


class DocumentService:
    """Orchestrates document upload, storage, and preview."""

    def __init__(
        self,
        document_repo: DocumentRepository,
        analysis_repo: AnalysisRepository,
        config: DocumentConfig,
    ):
        self._document_repo = document_repo
        self._analysis_repo = analysis_repo
        self._config = config
        self._upload_dir = config.upload_dir
        self._max_file_size = (
            config.max_file_size_mb * 1024 * 1024 if config.max_file_size_mb > 0 else 0
        )
        self._max_page_count = config.max_page_count

    @property
    def max_file_size(self) -> int:
        return self._max_file_size

    @property
    def max_file_size_mb(self) -> int:
        return self._config.max_file_size_mb

    async def upload(self, filename: str, content_type: str, file_content: bytes) -> Document:
        """Save uploaded file to disk and persist metadata.

        Writes the file in fixed-size chunks to keep peak memory usage low.
        The blocking disk write and the poppler subprocess (`pdfinfo`) are
        offloaded to a worker thread so the FastAPI event loop stays free
        for other requests during large uploads.
        """
        if self._max_file_size > 0 and len(file_content) > self._max_file_size:
            raise ValueError(f"File too large (max {self._config.max_file_size_mb} MB)")

        if not file_content[:4].startswith(_PDF_MAGIC):
            raise ValueError("Invalid file: not a PDF document")

        ext = ".pdf"  # Content already validated as PDF
        safe_name = f"{uuid.uuid4()}{ext}"
        file_path = os.path.join(self._upload_dir, safe_name)

        # Disk write + poppler subprocess — both blocking. Offload together
        # so we cross the thread boundary once instead of twice.
        page_count = await asyncio.to_thread(
            _persist_and_count, self._upload_dir, file_path, file_content
        )

        if (
            self._max_page_count > 0
            and page_count is not None
            and page_count > self._max_page_count
        ):
            await asyncio.to_thread(os.unlink, file_path)
            raise ValueError(
                f"Too many pages ({page_count}). Maximum allowed: {self._max_page_count}"
            )

        doc = Document(
            filename=filename,
            content_type=content_type,
            file_size=len(file_content),
            page_count=page_count,
            storage_path=os.path.abspath(file_path),
        )
        await self._document_repo.insert(doc)
        return doc

    async def find_all(self) -> list[Document]:
        """Return all documents, newest first."""
        return await self._document_repo.find_all()

    async def find_by_id(self, doc_id: str) -> Document | None:
        """Find a document by its ID, or return None."""
        return await self._document_repo.find_by_id(doc_id)

    async def delete(self, doc_id: str) -> bool:
        """Delete document file, associated analyses, and database record."""
        doc = await self._document_repo.find_by_id(doc_id)
        if not doc:
            return False

        # Delete associated analyses first (cascade)
        await self._analysis_repo.delete_by_document(doc_id)

        # Delete file from disk (only if inside upload dir)
        try:
            real_path = os.path.realpath(doc.storage_path)
            real_upload_dir = os.path.realpath(self._upload_dir)
            if real_path.startswith(real_upload_dir + os.sep) and os.path.exists(real_path):
                os.unlink(real_path)
            elif os.path.exists(doc.storage_path):
                logger.warning("Refused to delete file outside upload dir: %s", doc.storage_path)
        except FileNotFoundError:
            logger.info("File already removed: %s", doc.storage_path)
        except PermissionError:
            logger.error("Permission denied deleting file: %s", doc.storage_path)
        except OSError:
            logger.warning("Could not delete file: %s", doc.storage_path, exc_info=True)

        return await self._document_repo.delete(doc_id)

    @staticmethod
    def generate_preview(file_content: bytes, page: int = 1, dpi: int = 150) -> bytes:
        """Generate a PNG preview of a specific PDF page."""
        images = convert_from_bytes(file_content, first_page=page, last_page=page, dpi=dpi)
        if not images:
            raise ValueError(f"Page {page} not found")

        buf = io.BytesIO()
        images[0].save(buf, format="PNG")
        return buf.getvalue()

    @staticmethod
    def page_sizes(file_content: bytes) -> list[PageDetail]:
        """Size of each page of a PDF, in points, without its elements (#352).

        Lets the page preview reserve each page's box before any analysis.
        """
        pdf = pdfium.PdfDocument(file_content)
        try:
            sizes: list[PageDetail] = []
            for index in range(len(pdf)):
                page = pdf[index]
                try:
                    width, height = page.get_size()
                finally:
                    page.close()
                sizes.append(PageDetail(page_number=index + 1, width=width, height=height))
            return sizes
        finally:
            pdf.close()


def _persist_and_count(upload_dir: str, file_path: str, file_content: bytes) -> int | None:
    """Write the uploaded bytes to disk and return the page count.

    Synchronous helper meant to be invoked through `asyncio.to_thread` so
    the chunked write loop and the poppler subprocess never block the
    FastAPI event loop.
    """
    os.makedirs(upload_dir, exist_ok=True)
    with open(file_path, "wb") as f:
        for offset in range(0, len(file_content), _UPLOAD_CHUNK_SIZE):
            f.write(file_content[offset : offset + _UPLOAD_CHUNK_SIZE])
    return _count_pages(file_content)


def _count_pages(file_content: bytes) -> int | None:
    """Count PDF pages using poppler via pdf2image."""
    try:
        info = pdfinfo_from_bytes(file_content)
        return info.get("Pages")
    except (FileNotFoundError, OSError) as exc:
        logger.warning("Could not count pages: %s", exc)
        return None
    except Exception:
        logger.warning("Unexpected error counting pages", exc_info=True)
        return None
