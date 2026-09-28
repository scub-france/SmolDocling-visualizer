"""Domain ports — abstract interfaces that infrastructure must implement.

These protocols define what the domain NEEDS, not how it's done.
Infrastructure adapters (local Docling, Docling Serve, etc.) implement these.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import datetime

    from domain.app_config import LLMHostProbeResult
    from domain.models import (
        AnalysisJob,
        Chunk,
        ChunkEdit,
        ChunkPush,
        Document,
        DocumentStoreLink,
        Store,
    )
    from domain.value_objects import (
        ChunkingOptions,
        ChunkResult,
        ConversionOptions,
        ConversionResult,
        DocumentLifecycleState,
        GraphPayload,
        LLMProviderType,
        ReasoningResult,
    )
    from domain.vector_schema import IndexedChunk, SearchResult


class ReasoningParseError(Exception):
    """Raised by a `ReasoningRunner` when the upstream LLM couldn't produce a
    parseable answer after retries — e.g. docling-agent's known IndexError on
    `find_json_dicts(...)[0]` when the model fails rejection-sampling.

    Carries the model identifier so the API layer can surface it to the user
    without leaking adapter internals.
    """

    def __init__(self, model_id: str, reason: str = "no parseable answer") -> None:
        super().__init__(f"{model_id}: {reason}")
        self.model_id = model_id
        self.reason = reason


class DocumentConverter(Protocol):
    """Port for document conversion.

    Any implementation (local Docling lib, remote Docling Serve, mock, etc.)
    must satisfy this contract.
    """

    async def convert(
        self,
        file_path: str,
        options: ConversionOptions,
        *,
        page_range: tuple[int, int] | None = None,
    ) -> ConversionResult: ...

    @property
    def supports_page_batching(self) -> bool:
        """True if the orchestrator may slice a long document into page
        batches (calling `convert` with a `page_range`) and merge the
        results. Local in-process converters set this to True; remote
        converters that handle batching themselves return False so the
        orchestrator passes the full document through in one call."""
        ...

    async def merge_batches(self, results: list[ConversionResult]) -> ConversionResult:
        """Merge the results of page-batched `convert` calls, in page order,
        into the result a single call would have produced. Only called when
        `supports_page_batching` is True."""
        ...

    @property
    def max_parallel_conversions(self) -> int | None:
        """How many conversions the engine runs at once, or None when the
        engine queues extra work itself (Docling Serve). The analysis service
        never hands it more, and keeps the rest PENDING in its own queue (#349)."""
        ...


class DocumentChunker(Protocol):
    """Port for document chunking.

    Takes a serialized DoclingDocument (JSON) and returns chunks.
    """

    async def chunk(
        self,
        document_json: str,
        options: ChunkingOptions,
    ) -> list[ChunkResult]: ...


class DocumentRepository(Protocol):
    """Port for document persistence."""

    async def insert(self, doc: Document) -> None: ...

    async def find_all(self, *, limit: int = 200, offset: int = 0) -> list[Document]: ...

    async def find_by_id(self, doc_id: str) -> Document | None: ...

    async def update_page_count(self, doc_id: str, page_count: int) -> None: ...

    async def update_lifecycle(
        self,
        doc_id: str,
        state: DocumentLifecycleState,
        at: datetime,
    ) -> None: ...

    async def delete(self, doc_id: str) -> bool: ...


class StoreRepository(Protocol):
    """Port for `Store` persistence (introduced by #203)."""

    async def insert(self, store: Store) -> None: ...

    async def find_all(self) -> list[Store]: ...

    async def find_by_slug(self, slug: str) -> Store | None: ...

    async def find_by_id(self, store_id: str) -> Store | None: ...

    async def get_default(self) -> Store | None: ...


class DocumentStoreLinkRepository(Protocol):
    """Port for `DocumentStoreLink` persistence (introduced by #203)."""

    async def upsert(self, link: DocumentStoreLink) -> None:
        """Insert or update by (document_id, store_id)."""
        ...

    async def find_for_document(self, document_id: str) -> list[DocumentStoreLink]: ...

    async def find_for_store(self, store_id: str) -> list[DocumentStoreLink]: ...

    async def find_one(self, document_id: str, store_id: str) -> DocumentStoreLink | None: ...

    async def delete(self, document_id: str, store_id: str) -> bool: ...


class ChunkRepository(Protocol):
    """Port for first-class chunk persistence (introduced by #205)."""

    async def insert(self, chunk: Chunk) -> None: ...

    async def insert_many(self, chunks: list[Chunk]) -> None: ...

    async def update(self, chunk: Chunk) -> None: ...

    async def soft_delete(self, chunk_id: str, *, at: datetime) -> bool: ...

    async def find_for_document(
        self,
        document_id: str,
        *,
        include_deleted: bool = False,
    ) -> list[Chunk]: ...

    async def find_by_id(self, chunk_id: str) -> Chunk | None: ...

    async def count_for_document(self, document_id: str) -> int: ...


class ChunkEditRepository(Protocol):
    """Port for the immutable chunk_edits audit log (introduced by #205)."""

    async def insert(self, edit: ChunkEdit) -> None: ...

    async def find_for_document(
        self,
        document_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChunkEdit]: ...

    async def find_for_chunk(self, chunk_id: str) -> list[ChunkEdit]: ...


class ChunkPushRepository(Protocol):
    """Port for chunk_pushes snapshots (introduced by #205)."""

    async def insert(self, push: ChunkPush) -> None: ...

    async def find_by_id(self, push_id: str) -> ChunkPush | None: ...

    async def find_latest(self, document_id: str, store_id: str) -> ChunkPush | None: ...


class AnalysisRepository(Protocol):
    """Port for analysis job persistence."""

    async def insert(self, job: AnalysisJob) -> None: ...

    async def find_all(self, *, limit: int = 200, offset: int = 0) -> list[AnalysisJob]: ...

    async def find_all_summaries(self, *, limit: int = 200, offset: int = 0) -> list[AnalysisJob]:
        """Like `find_all`, without the content: to follow statuses (#354)."""
        ...

    async def find_by_id(self, job_id: str) -> AnalysisJob | None: ...

    async def find_latest_completed(self, document_id: str) -> AnalysisJob | None: ...

    async def find_latest_completed_by_document(self, document_id: str) -> AnalysisJob | None: ...

    async def update_status(self, job: AnalysisJob) -> None: ...

    async def update_progress(self, job_id: str, current: int, total: int) -> None: ...

    async def update_chunks(self, job_id: str, chunks_json: str) -> bool: ...

    async def delete(self, job_id: str) -> bool: ...

    async def delete_by_document(self, document_id: str) -> int: ...


@runtime_checkable
class EmbeddingService(Protocol):
    """Port for text-to-vector embedding.

    Implementations may call a local model, a remote microservice, etc.
    """

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of texts."""
        ...


@runtime_checkable
class VectorStore(Protocol):
    """Port for vector storage and retrieval.

    Implementations (OpenSearch, pgvector, Qdrant, etc.) must satisfy this
    contract. The port uses domain types from vector_schema — no infrastructure
    details leak into the domain.
    """

    async def ensure_index(self, index_name: str, mapping: dict) -> None:
        """Create the index if it does not exist. No-op if it already exists."""
        ...

    async def index_chunks(self, index_name: str, chunks: list[IndexedChunk]) -> int:
        """Bulk-index a list of chunks. Returns the number of successfully indexed chunks."""
        ...

    async def search_similar(
        self,
        index_name: str,
        embedding: list[float],
        *,
        k: int = 10,
        doc_id: str | None = None,
    ) -> list[SearchResult]:
        """Find the k nearest chunks by embedding similarity.

        Args:
            index_name: Target index.
            embedding: Query vector.
            k: Number of results to return.
            doc_id: If provided, restrict search to chunks from this document.
        """
        ...

    async def get_chunks(
        self,
        index_name: str,
        doc_id: str,
        *,
        limit: int = 1000,
    ) -> list[SearchResult]:
        """Retrieve all indexed chunks for a given document, ordered by chunk_index."""
        ...

    async def delete_document(self, index_name: str, doc_id: str) -> int:
        """Delete all chunks for a document from the index. Returns count deleted."""
        ...

    async def ping(self) -> bool:
        """Cheap reachability probe — True if the backing store responds.
        Used by health checks; should not throw."""
        ...


class AppSettingsRepository(Protocol):
    """Port for the namespaced runtime-config override store (#317).

    Values are opaque TEXT — the consuming service owns (de)serialization.
    `reasoning` is the first namespace; the table is groundwork for future
    runtime-configurable domains.
    """

    async def get_namespace(self, namespace: str) -> dict[str, str]: ...

    async def set_many(self, namespace: str, values: dict[str, str]) -> None: ...

    async def delete_namespace(self, namespace: str) -> int:
        """Drop every override in `namespace`. Returns the number of rows removed."""
        ...


@runtime_checkable
class LLMHostProbe(Protocol):
    """Port for probing an LLM host: reachability + installed models (#317).

    Implementations must never raise — transport/protocol failures map to
    `LLMHostProbeResult(reachable=False, error=...)` so the API layer can
    return a plain 200 carrying the outcome.
    """

    async def probe(self, host: str) -> LLMHostProbeResult: ...


@runtime_checkable
class LLMProvider(Protocol):
    """Connection-level abstraction over an LLM backend.

    A provider carries the host/base-URL, the default model identifier, and a
    type tag that adapters can dispatch on. The reasoning runner consumes a
    provider — it doesn't construct one — so the runner stays decoupled from
    Ollama-vs-OpenAI-vs-WatsonX wiring.

    Today only `OllamaProvider` (in `infra/llm/`) is implemented because
    docling-agent v0.1.0 is hardwired to Ollama via mellea's
    `setup_local_session`. Adding a non-Ollama provider requires either
    docling-agent upstream support or a fork (track
    https://github.com/docling-project/docling-agent/issues/26 + provider
    abstraction work upstream).
    """

    @property
    def type(self) -> LLMProviderType: ...

    @property
    def host(self) -> str: ...

    @property
    def default_model_id(self) -> str: ...

    def health_check(self) -> bool:
        """Lightweight reachability probe. Returns True if the provider looks
        usable. Implementations should be cheap (no model load, no inference).
        """
        ...


@runtime_checkable
class DocumentTreeReader(Protocol):
    """Port for walking a `DoclingDocument` JSON tree (#audit-01).

    Exposes the Docling-shape navigation primitives (item iteration,
    inline-group filter, collapse index for nested structures) so callers
    in `services/` can stay format-agnostic and never reach into
    `infra/docling_tree.py` directly. The adapter encapsulates every
    Docling-specific assumption (label taxonomy, parent.$ref/cref shape,
    InlineGroup collapsing, etc.).
    """

    def iter_items(self, doc_data: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
        """Yield `(source_list_key, item)` for every item in
        texts/tables/pictures/groups."""
        ...

    def is_inline_group(self, item: dict[str, Any]) -> bool:
        """True iff `item` is a Docling InlineGroup (paragraph of mixed
        style runs collapsed into a single Paragraph projection)."""
        ...

    def build_collapse_index(
        self, doc_data: dict[str, Any]
    ) -> tuple[set[str], dict[str, dict[str, Any]]]:
        """Return `(skip_refs, inline_meta)` — refs to omit from any
        projection and per-InlineGroup aggregated metadata (text + provs).
        """
        ...


@runtime_checkable
class GraphReader(Protocol):
    """Port for reading a document's graph projection from the graph store.

    Returns a wire-ready `GraphPayload` — the adapter owns both the query
    and the shape conversion so the service layer never sees driver types.
    Returns `None` when the document is unknown to the graph store.
    """

    async def fetch(self, doc_id: str, *, max_pages: int = 200) -> GraphPayload | None: ...


@runtime_checkable
class GraphWriter(Protocol):
    """Port for writing a document and its chunks into a graph store.

    Two distinct write paths exist by design: `write_document_tree` runs
    after analysis (full DoclingDocument tree), `write_chunks` runs after
    ingestion (chunks linked to the tree). Adapters that don't support
    both paths still must implement them (raise `NotImplementedError`
    rather than silently no-op so the caller can decide whether to fail).

    `ping()` mirrors the `VectorStore` port for the test-connection use
    case — `StoreService.test_connection` calls it through the resolver-
    produced `IngestionTargets.graph_writer` so the service layer never
    needs to touch the underlying driver.
    """

    async def write_document_tree(
        self,
        *,
        doc_id: str,
        filename: str,
        document_json: str,
    ) -> None: ...

    async def write_chunks(
        self,
        *,
        doc_id: str,
        chunks_json: str,
    ) -> None: ...

    async def ping(self) -> bool:
        """Cheap reachability probe — True if the graph store responds.
        Should not throw on connection failure; let the adapter map errors
        into False so the caller can return a clean (ok=False, reason)."""
        ...


@runtime_checkable
class ReasoningRunner(Protocol):
    """Port for live reasoning over a previously-converted document.

    Takes the serialized DoclingDocument JSON + a user query + optional
    per-call model override, returns a `ReasoningResult` (answer + iteration
    trace + convergence flag).

    Adapters MUST translate upstream parsing failures into
    `ReasoningParseError`. Other exceptions propagate as-is — the API layer
    maps them to 5xx.
    """

    @property
    def is_available(self) -> bool:
        """True if the runner can serve requests (deps importable + provider
        wired). Used by the API layer to short-circuit with a 503 instead of
        attempting a doomed call."""
        ...

    async def run(
        self,
        *,
        document_json: str,
        query: str,
        model_id: str | None = None,
    ) -> ReasoningResult:
        """Execute the reasoning loop. `model_id` overrides the provider's
        default for this call only."""
        ...
