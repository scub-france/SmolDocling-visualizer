"""Domain-level exceptions.

Exceptions defined in this module are raised by domain operations and value
objects when an invariant is violated. They have no infrastructure
dependencies and are safe to import from any layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.value_objects import DocumentLifecycleState


class DomainError(Exception):
    """Base class for domain-level errors. Catch this when wiring API
    layers if you want a single hook for any invariant violation."""


class InvalidLifecycleTransitionError(DomainError):
    """Raised when a Document.transition_to() call asks for a (source,
    target) pair that is not in the allowed transition table.

    Carries `source` and `target` so callers can produce a useful error
    message without re-discovering them.
    """

    def __init__(
        self,
        *,
        source: DocumentLifecycleState,
        target: DocumentLifecycleState,
    ) -> None:
        super().__init__(f"Invalid document lifecycle transition: {source.value} -> {target.value}")
        self.source = source
        self.target = target


class IncompleteConversionError(DomainError):
    """Raised when a conversion comes back with pages missing (#348).

    Docling stops at its document timeout, or skips pages it cannot read, and
    reports a partial success. Storing that result would show a complete
    analysis with pages missing, so the analysis fails with this message.
    `missing_pages` are absolute, 1-based page numbers.
    """

    def __init__(self, missing_pages: list[int], *, timed_out: bool) -> None:
        pages = sorted(set(missing_pages))
        single = len(pages) == 1
        which = f"page {pages[0]}" if single else f"pages {_page_runs(pages)}"
        if timed_out:
            message = (
                f"Docling stopped at its document timeout: {which} "
                f"{'was' if single else 'were'} not converted. Raise DOCUMENT_TIMEOUT, "
                "or set BATCH_PAGE_SIZE so each batch gets its own time budget."
            )
        else:
            message = (
                f"Docling could not convert {which}. The document may be damaged on "
                f"{'that page' if single else 'those pages'}."
            )
        super().__init__(message)
        self.missing_pages = pages
        self.timed_out = timed_out


def _page_runs(pages: list[int]) -> str:
    """Group sorted page numbers into runs: `[3, 4, 5, 9]` gives `"3-5, 9"`."""
    runs: list[str] = []
    start = end = pages[0]
    for page in pages[1:]:
        if page == end + 1:
            end = page
            continue
        runs.append(f"{start}-{end}" if end > start else str(start))
        start = end = page
    runs.append(f"{start}-{end}" if end > start else str(start))
    return ", ".join(runs)
