"""Analysis job repository — SQLite CRUD for analysis_jobs table."""

from __future__ import annotations

from datetime import UTC, datetime

from domain.models import AnalysisJob, AnalysisStatus
from persistence.database import get_connection


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO-format datetime string back into a datetime object."""
    if not value:
        return None
    return datetime.fromisoformat(value)


def _row_to_job(row) -> AnalysisJob:
    keys = row.keys()
    return AnalysisJob(
        id=row["id"],
        document_id=row["document_id"],
        status=AnalysisStatus(row["status"]),
        content_markdown=row["content_markdown"] if "content_markdown" in keys else None,
        content_html=row["content_html"] if "content_html" in keys else None,
        pages_json=row["pages_json"] if "pages_json" in keys else None,
        document_json=row["document_json"] if "document_json" in keys else None,
        chunks_json=row["chunks_json"] if "chunks_json" in keys else None,
        error_message=row["error_message"],
        progress_current=row["progress_current"] if "progress_current" in keys else None,
        progress_total=row["progress_total"] if "progress_total" in keys else None,
        started_at=_parse_dt(row["started_at"]),
        completed_at=_parse_dt(row["completed_at"]),
        created_at=_parse_dt(row["created_at"]) or datetime.now(UTC),
        document_filename=row["filename"] if "filename" in keys else None,
    )


_SELECT_WITH_DOC = """
    SELECT aj.*, d.filename
    FROM analysis_jobs aj
    JOIN documents d ON d.id = aj.document_id
"""

# Everything but the content (markdown, HTML, pages, chunks, Docling document):
# what following the statuses of many analyses needs (#354).
_SELECT_SUMMARY = """
    SELECT aj.id, aj.document_id, aj.status, aj.error_message, aj.progress_current,
           aj.progress_total, aj.started_at, aj.completed_at, aj.created_at, d.filename
    FROM analysis_jobs aj
    JOIN documents d ON d.id = aj.document_id
"""


class SqliteAnalysisRepository:
    """SQLite implementation of the AnalysisRepository port."""

    async def insert(self, job: AnalysisJob) -> None:
        """Persist a new analysis job record."""
        async with get_connection() as db:
            await db.execute(
                """INSERT INTO analysis_jobs (id, document_id, status, created_at)
                   VALUES (?, ?, ?, ?)""",
                (job.id, job.document_id, job.status.value, str(job.created_at)),
            )
            await db.commit()

    async def find_all(self, *, limit: int = 200, offset: int = 0) -> list[AnalysisJob]:
        """Return analysis jobs with document info, newest first."""
        async with get_connection() as db:
            cursor = await db.execute(
                f"{_SELECT_WITH_DOC} ORDER BY aj.created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = await cursor.fetchall()
            return [_row_to_job(r) for r in rows]

    async def find_all_summaries(self, *, limit: int = 200, offset: int = 0) -> list[AnalysisJob]:
        """Return analysis jobs without their content, newest first (#354)."""
        async with get_connection() as db:
            cursor = await db.execute(
                f"{_SELECT_SUMMARY} ORDER BY aj.created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = await cursor.fetchall()
            return [_row_to_job(r) for r in rows]

    async def find_by_document(
        self, document_id: str, *, limit: int = 200, offset: int = 0
    ) -> list[AnalysisJob]:
        """Return analysis jobs for a given document, newest first."""
        async with get_connection() as db:
            cursor = await db.execute(
                f"{_SELECT_WITH_DOC} WHERE aj.document_id = ? "
                "ORDER BY aj.created_at DESC LIMIT ? OFFSET ?",
                (document_id, limit, offset),
            )
            rows = await cursor.fetchall()
            return [_row_to_job(r) for r in rows]

    async def find_by_id(self, job_id: str) -> AnalysisJob | None:
        """Find an analysis job by ID (with document filename), or return None."""
        async with get_connection() as db:
            cursor = await db.execute(f"{_SELECT_WITH_DOC} WHERE aj.id = ?", (job_id,))
            row = await cursor.fetchone()
            return _row_to_job(row) if row else None

    async def find_latest_completed(self, document_id: str) -> AnalysisJob | None:
        """Latest COMPLETED analysis for a doc, regardless of which fields are populated."""
        async with get_connection() as db:
            cursor = await db.execute(
                f"{_SELECT_WITH_DOC} WHERE aj.document_id = ? "
                "AND aj.status = 'COMPLETED' "
                "ORDER BY aj.completed_at DESC LIMIT 1",
                (document_id,),
            )
            row = await cursor.fetchone()
            return _row_to_job(row) if row else None

    async def find_latest_completed_by_document(self, document_id: str) -> AnalysisJob | None:
        """Latest COMPLETED analysis with a non-null `document_json` for a doc.

        Used by the reasoning-trace tunnel to prime Neo4j from an existing
        analysis when the graph doesn't yet exist (e.g. analysis ran before
        Neo4j was wired in).
        """
        async with get_connection() as db:
            cursor = await db.execute(
                f"{_SELECT_WITH_DOC} WHERE aj.document_id = ? "
                "AND aj.status = 'COMPLETED' AND aj.document_json IS NOT NULL "
                "ORDER BY aj.completed_at DESC LIMIT 1",
                (document_id,),
            )
            row = await cursor.fetchone()
            return _row_to_job(row) if row else None

    async def update_status(self, job: AnalysisJob) -> None:
        """Persist all mutable fields of an analysis job (status, results, timestamps)."""
        async with get_connection() as db:
            await db.execute(
                """UPDATE analysis_jobs
                   SET status = ?, content_markdown = ?, content_html = ?,
                       pages_json = ?, document_json = ?, chunks_json = ?,
                       error_message = ?, progress_current = ?, progress_total = ?,
                       started_at = ?, completed_at = ?
                   WHERE id = ?""",
                (
                    job.status.value,
                    job.content_markdown,
                    job.content_html,
                    job.pages_json,
                    job.document_json,
                    job.chunks_json,
                    job.error_message,
                    job.progress_current,
                    job.progress_total,
                    str(job.started_at) if job.started_at else None,
                    str(job.completed_at) if job.completed_at else None,
                    job.id,
                ),
            )
            await db.commit()

    async def update_progress(self, job_id: str, current: int, total: int) -> None:
        """Update only the progress columns for a running analysis."""
        async with get_connection() as db:
            await db.execute(
                "UPDATE analysis_jobs SET progress_current = ?, progress_total = ? WHERE id = ?",
                (current, total, job_id),
            )
            await db.commit()

    async def update_chunks(self, job_id: str, chunks_json: str) -> bool:
        """Update only the chunks_json column for a completed analysis."""
        async with get_connection() as db:
            cursor = await db.execute(
                "UPDATE analysis_jobs SET chunks_json = ? WHERE id = ?",
                (chunks_json, job_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete(self, job_id: str) -> bool:
        """Delete an analysis job by ID. Returns True if a row was removed."""
        async with get_connection() as db:
            cursor = await db.execute("DELETE FROM analysis_jobs WHERE id = ?", (job_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def delete_by_document(self, document_id: str) -> int:
        """Delete all analysis jobs for a given document. Returns count deleted."""
        async with get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM analysis_jobs WHERE document_id = ?", (document_id,)
            )
            await db.commit()
            return cursor.rowcount
