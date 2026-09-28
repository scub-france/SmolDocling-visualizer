"""Pydantic schemas — API request/response DTOs.

All responses use camelCase serialization to match the existing frontend contract
(originally served by the Spring Boot backend).
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, RootModel, field_validator

from domain.app_config import (
    MAX_ITERATIONS_MAX,
    MAX_ITERATIONS_MIN,
    ConfigSource,
    LLMHostProbeResult,
    ReasoningConfigView,
)
from domain.value_objects import (
    ReasoningStep,
    ReasoningStepKind,
    ReasoningStepPayload,
    ReasoningTrace,
)

# Document lifecycle status — currently single-state (uploaded). Kept as a
# constant so future statuses (e.g. "archived", "deleted") can extend the
# vocabulary without hunting magic strings across the codebase.
DOCUMENT_STATUS_UPLOADED = "uploaded"


def _to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(w.capitalize() for w in parts[1:])


class _CamelModel(BaseModel):
    """Base model that serializes field names to camelCase."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class HealthResponse(_CamelModel):
    status: str
    version: str
    engine: str
    deployment_mode: str
    database: str
    max_page_count: int | None = None
    max_file_size_mb: int | None = None
    max_paste_image_size_mb: int | None = None
    paste_allowed_image_types: list[str] = Field(default_factory=list)
    ingestion_available: bool = False
    # True when the live-reasoning runner (docling-agent + Ollama) is
    # available: REASONING_ENABLED=true AND deps importable. Doesn't imply
    # Ollama itself is reachable — that's checked per-call.
    reasoning_available: bool = False
    # 0.6.1 — Surface flags (#257). Master flags select which surface(s)
    # the frontend exposes. Defaults match the production target (RAG only).
    studio_mode_enabled: bool = False
    rag_pipeline_enabled: bool = True
    # 0.6.0 — RAG-pipeline sub-flags (#210, renamed in #257). Default true
    # so frontends pointed at an older backend keep every mode visible.
    inspect_mode_enabled: bool = True
    linked_mode_enabled: bool = True


class DocStoreLinkResponse(_CamelModel):
    """Per-store ingestion link surfaced on a document (#283 fix).

    The frontend has shipped a `Document.storeLinks` type since #224
    but the backend was never actually populating it — only the
    audit log (`chunk_pushes`) was. The Ingest tab redesign uncovered
    this gap (modal showed NotPushed even when history listed pushes).
    The `store` field carries the store slug (stable identity used
    by the frontend's `link.store` lookup); `state` mirrors the
    `DocumentStoreLinkState` enum values.
    """

    store: str
    state: str
    pushed_at: str | None = None


class DocumentResponse(_CamelModel):
    id: str
    filename: str
    status: str = DOCUMENT_STATUS_UPLOADED
    content_type: str | None = None
    file_size: int | None = None
    page_count: int | None = None
    created_at: str | datetime
    # 0.6.0 — Document lifecycle state machine (#202). The lifecycle
    # describes the document as a whole; `status` above is kept for
    # backwards compat and currently still maps to `DOCUMENT_STATUS_UPLOADED`.
    lifecycle_state: str = "Uploaded"
    lifecycle_state_at: str | datetime | None = None
    # 0.6.1 (#283) — per-store ingestion state. Always present on
    # `GET /api/documents/{id}`; the list endpoint omits it to keep
    # the listing payload light (callers that need it can drill in).
    store_links: list[DocStoreLinkResponse] | None = None


class PageSizeResponse(_CamelModel):
    """Size of one page of a document's PDF, in points (#352)."""

    page_number: int
    width: float
    height: float


class AnalysisResponse(_CamelModel):
    id: str
    document_id: str = ""
    document_filename: str | None = None
    status: str
    content_markdown: str | None = None
    content_html: str | None = None
    pages_json: str | None = None
    chunks_json: str | None = None
    has_document_json: bool = False
    error_message: str | None = None
    progress_current: int | None = None
    progress_total: int | None = None
    started_at: str | datetime | None = None
    completed_at: str | datetime | None = None
    created_at: str | datetime


class AnalysisSummaryResponse(_CamelModel):
    """An analysis without its content, to follow many statuses at once (#354)."""

    id: str
    document_id: str
    document_filename: str | None = None
    status: str
    error_message: str | None = None
    progress_current: int | None = None
    progress_total: int | None = None
    started_at: str | datetime | None = None
    completed_at: str | datetime | None = None
    created_at: str | datetime


class PipelineOptionsRequest(BaseModel):
    """Docling pipeline configuration options."""

    model_config = ConfigDict(populate_by_name=True)

    do_ocr: bool = Field(default=True, validation_alias=AliasChoices("do_ocr", "doOcr"))
    do_table_structure: bool = Field(
        default=True, validation_alias=AliasChoices("do_table_structure", "doTableStructure")
    )
    table_mode: str = Field(
        default="accurate", validation_alias=AliasChoices("table_mode", "tableMode")
    )
    do_code_enrichment: bool = Field(
        default=False, validation_alias=AliasChoices("do_code_enrichment", "doCodeEnrichment")
    )
    do_formula_enrichment: bool = Field(
        default=False, validation_alias=AliasChoices("do_formula_enrichment", "doFormulaEnrichment")
    )
    do_picture_classification: bool = Field(
        default=False,
        validation_alias=AliasChoices("do_picture_classification", "doPictureClassification"),
    )
    do_picture_description: bool = Field(
        default=False,
        validation_alias=AliasChoices("do_picture_description", "doPictureDescription"),
    )
    generate_picture_images: bool = Field(
        default=False,
        validation_alias=AliasChoices("generate_picture_images", "generatePictureImages"),
    )
    generate_page_images: bool = Field(
        default=False, validation_alias=AliasChoices("generate_page_images", "generatePageImages")
    )
    images_scale: float = Field(
        default=1.0, validation_alias=AliasChoices("images_scale", "imagesScale")
    )

    @field_validator("table_mode")
    @classmethod
    def validate_table_mode(cls, v: str) -> str:
        if v not in ("accurate", "fast"):
            raise ValueError('table_mode must be "accurate" or "fast"')
        return v

    @field_validator("images_scale")
    @classmethod
    def validate_images_scale(cls, v: float) -> float:
        if v <= 0 or v > 10:
            raise ValueError("images_scale must be between 0 (exclusive) and 10")
        return v


class ChunkingOptionsRequest(BaseModel):
    """Docling chunking configuration options."""

    model_config = ConfigDict(populate_by_name=True)

    chunker_type: str = Field(
        default="hybrid", validation_alias=AliasChoices("chunker_type", "chunkerType")
    )
    max_tokens: int = Field(default=512, validation_alias=AliasChoices("max_tokens", "maxTokens"))
    merge_peers: bool = Field(
        default=True, validation_alias=AliasChoices("merge_peers", "mergePeers")
    )
    repeat_table_header: bool = Field(
        default=True, validation_alias=AliasChoices("repeat_table_header", "repeatTableHeader")
    )

    @field_validator("chunker_type")
    @classmethod
    def validate_chunker_type(cls, v: str) -> str:
        if v not in ("hybrid", "hierarchical"):
            raise ValueError('chunker_type must be "hybrid" or "hierarchical"')
        return v

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, v: int) -> int:
        if v < 64 or v > 8192:
            raise ValueError("max_tokens must be between 64 and 8192")
        return v


class ChunkBboxResponse(_CamelModel):
    page: int
    bbox: list[float]


class ChunkResponse(_CamelModel):
    text: str
    headings: list[str] = []
    source_page: int | None = None
    token_count: int = 0
    bboxes: list[ChunkBboxResponse] = []
    modified: bool = False
    deleted: bool = False


class UpdateChunkTextRequest(BaseModel):
    text: str


class CreateAnalysisRequest(BaseModel):
    documentId: str = Field(validation_alias=AliasChoices("documentId", "document_id"))
    pipelineOptions: PipelineOptionsRequest | None = Field(
        default=None, validation_alias=AliasChoices("pipelineOptions", "pipeline_options")
    )
    chunkingOptions: ChunkingOptionsRequest | None = Field(
        default=None, validation_alias=AliasChoices("chunkingOptions", "chunking_options")
    )


class RechunkRequest(BaseModel):
    chunkingOptions: ChunkingOptionsRequest = Field(
        validation_alias=AliasChoices("chunkingOptions", "chunking_options")
    )


class IngestionResponse(_CamelModel):
    doc_id: str
    chunks_indexed: int
    embedding_dimension: int


class IngestionStatusResponse(_CamelModel):
    available: bool
    opensearch_connected: bool = False


class SearchResultItem(_CamelModel):
    """A single search result with content and metadata."""

    doc_id: str
    filename: str
    content: str
    chunk_index: int
    page_number: int
    score: float
    headings: list[str] = []
    highlights: list[str] = []


class SearchResponse(_CamelModel):
    results: list[SearchResultItem]
    total: int
    query: str


# ---------------------------------------------------------------------------
# Stores (#251)
# ---------------------------------------------------------------------------


class StoreInfoResponse(_CamelModel):
    """Read model for `GET /api/stores`."""

    name: str
    slug: str
    type: str
    embedder: str
    is_default: bool
    document_count: int
    chunk_count: int
    connected: bool
    error_message: str | None = None


class StoreResponse(_CamelModel):
    """Detailed read model for `GET /api/stores/{slug}`.

    Connection identity (#279) is exposed via `connectionUri` /
    `connectionUsername`. The password is **never** serialised — the
    response carries a `hasConnectionPassword` boolean indicator so
    the UI can show "password set" without ever seeing the value.
    """

    id: str
    name: str
    slug: str
    kind: str
    embedder: str
    is_default: bool
    config: dict
    connection_uri: str | None = None
    connection_username: str | None = None
    has_connection_password: bool = False
    created_at: str | datetime


class StoreCreateRequest(_CamelModel):
    """Create a store (#251) + optional connection identity (#279).

    `connectionPassword` is write-only — it never appears on a
    response. Empty string is treated as "no password" (= NULL on
    the column).
    """

    name: str
    slug: str
    kind: str
    embedder: str
    config: dict = Field(default_factory=dict)
    is_default: bool = False
    connection_uri: str | None = None
    connection_username: str | None = None
    connection_password: str | None = None


class StoreUpdateRequest(_CamelModel):
    """Partial update — every field is optional. Use `slug` to rename.

    For `connectionPassword` (#279):
      - `None` (field absent) → leave the existing seal untouched
      - empty string `""` → clear the password (NULL the column)
      - non-empty string → seal the new value
    """

    name: str | None = None
    slug: str | None = None
    kind: str | None = None
    embedder: str | None = None
    config: dict | None = None
    is_default: bool | None = None
    connection_uri: str | None = None
    connection_username: str | None = None
    connection_password: str | None = None


class StoreTestConnectionResponse(_CamelModel):
    """Result of `POST /api/stores/{slug}/test-connection` (#279)."""

    ok: bool
    error_message: str | None = None


class StoreDocEntryResponse(_CamelModel):
    doc_id: str
    filename: str
    state: str
    chunk_count: int
    pushed_at: str | None = None


# ---------------------------------------------------------------------------
# Doc-centric chunks (#256) — canonical chunkset, distinct from analysis chunks
# ---------------------------------------------------------------------------


class ChunkDocItemResponse(_CamelModel):
    """Wire shape for a chunk's source element reference (Docling `self_ref` + label)."""

    self_ref: str
    label: str


class DocChunkResponse(_CamelModel):
    """Canonical doc chunk — wire shape consumed by `features/chunks` on the front.

    Carries `bboxes` and `docItems` (#264) so the Linked view can correlate
    a chunk card with the element bboxes drawn on the page preview.
    """

    id: str
    doc_id: str
    sequence: int
    text: str
    headings: list[str] = []
    source_page: int | None = None
    token_count: int | None = None
    bboxes: list[ChunkBboxResponse] = []
    doc_items: list[ChunkDocItemResponse] = []
    created_at: str | datetime
    updated_at: str | datetime


class AddChunkRequest(_CamelModel):
    text: str
    after_id: str | None = None


class UpdateChunkRequest(_CamelModel):
    """Either or both fields. Empty body is a 400 — handled in the router."""

    text: str | None = None
    title: str | None = None  # surfaced as first heading; future: dedicated field


class SplitChunkRequest(_CamelModel):
    cursor_offset: int


class MergeChunksRequest(_CamelModel):
    ids: list[str]


class DocRechunkRequest(_CamelModel):
    """Optional chunking options. Empty body uses defaults."""

    chunking_options: ChunkingOptionsRequest | None = None


class DocTreeNodeResponse(_CamelModel):
    ref: str
    type: str
    label: str
    children: list[DocTreeNodeResponse] = []


# Forward-ref resolution (children references the same class).
DocTreeNodeResponse.model_rebuild()


class ChunkDiffResponse(_CamelModel):
    chunk_id: str
    status: str  # 'added' | 'modified' | 'removed' | 'unchanged'
    text_diff: str | None = None


class PushSummaryResponse(_CamelModel):
    embeds: int
    tokens: int


class PushChunksResponse(_CamelModel):
    push_id: str
    summary: PushSummaryResponse


class PushChunksRequest(_CamelModel):
    store: str


# ---------------------------------------------------------------------------
# Push history (#283) — newest-first paginated feed for the Ingest tab.
# ---------------------------------------------------------------------------


class ChunkPushEntryResponse(_CamelModel):
    """One row of the document's push history.

    `storeSlug` / `storeName` / `storeKind` are None when the store
    row was deleted after the push — the audit log survives, the
    UI shows a "deleted store" badge.
    """

    id: str
    document_id: str
    store_id: str
    store_slug: str | None = None
    store_name: str | None = None
    store_kind: str | None = None
    chunkset_hash: str
    chunk_count: int
    pushed_at: str | None = None


class ChunkPushListResponse(_CamelModel):
    """Paginated envelope for `GET /api/documents/{id}/chunks/pushes`."""

    items: list[ChunkPushEntryResponse]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Document versions (#267) — frozen (analysis_id, chunks_snapshot) pairs.
# ---------------------------------------------------------------------------


class DocumentVersionResponse(_CamelModel):
    """Frozen pair surfaced by the workspace History drawer."""

    id: str
    document_id: str
    kind: str  # "analysis" | "chunks"
    analysis_id: str | None = None
    chunks_snapshot_size: int = 0  # number of chunks captured, not the raw JSON
    summary: str = ""
    created_at: str | datetime


# ---------------------------------------------------------------------------
# Reasoning (#303) — Parse-view trace timeline contract.
# ---------------------------------------------------------------------------


class ReasoningRunRequest(_CamelModel):
    """Body for `POST /api/documents/{id}/reasoning`.

    `modelId` is an optional per-run override; it falls back to the runner's
    configured default model. `_CamelModel` accepts both `modelId` (wire) and
    `model_id` (populate_by_name).
    """

    query: str
    model_id: str | None = None


class StepId(RootModel[str]):
    """Identifier of a trace step — `s{iteration}` ("s1", "s2", …).

    A `RootModel` rather than a bare `str` (#306 review): the id becomes a
    named type in the OpenAPI schema instead of yet another anonymous string,
    while serializing transparently as the string itself.
    """

    root: str


class ReasoningStepPayloadResponse(_CamelModel):
    """Raw iteration fields behind a trace step — what the debugger drawer
    expands. 1:1 mirror of `domain.value_objects.ReasoningStepPayload`;
    `_CamelModel` owns the snake_case → camelCase wire aliasing, so the UI
    still binds `payload.canAnswer`.
    """

    iteration: int = Field(description="1-based index of the loop iteration")
    section_ref: str = Field(description="Docling self_ref of the visited section")
    reason: str = Field(description="The model's stated motivation for this section")
    section_text_length: int = Field(description="Characters read from the section")
    can_answer: bool = Field(description="Whether the model could answer from this section")
    response: str = Field(description="The answer attempt produced at this step")
    duration_ms: int = Field(
        default=0,
        description="Step duration in milliseconds; 0 when upstream reported no timing",
    )

    @classmethod
    def from_payload(cls, payload: ReasoningStepPayload) -> ReasoningStepPayloadResponse:
        return cls(**asdict(payload))


class ReasoningStepResponse(_CamelModel):
    """One projected reasoning step rendered as a trace-timeline row."""

    id: StepId
    kind: ReasoningStepKind
    title: str = Field(description="Step label — the model's reason, truncated to 96 chars")
    summary: str
    payload: ReasoningStepPayloadResponse
    duration_ms: int = Field(default=0, description="Step duration in milliseconds")
    token_count: int = Field(
        default=0, description="Tokens consumed by the step; 0 until mellea exposes usage"
    )
    citations: list[str] = Field(
        default_factory=list, description="Docling self_refs this step cites"
    )

    @classmethod
    def from_step(cls, step: ReasoningStep) -> ReasoningStepResponse:
        return cls(
            id=StepId(step.id),
            kind=step.kind,
            title=step.title,
            summary=step.summary,
            payload=ReasoningStepPayloadResponse.from_payload(step.payload),
            duration_ms=step.duration_ms,
            token_count=step.token_count,
            citations=step.citations,
        )


class ReasoningTraceResponse(_CamelModel):
    """Wire shape for a completed reasoning run — answer + ordered steps +
    run-level timing/usage/model metadata."""

    answer: str
    converged: bool
    steps: list[ReasoningStepResponse]
    total_duration_ms: int = Field(description="Total run duration in milliseconds")
    tokens_in: int = 0
    tokens_out: int = 0
    model_id: str = ""

    @classmethod
    def from_trace(cls, trace: ReasoningTrace) -> ReasoningTraceResponse:
        """Project a domain `ReasoningTrace` onto its wire shape — the router
        maps no fields of its own (#306 review: keep the mapping with the
        model it produces)."""
        return cls(
            answer=trace.answer,
            converged=trace.converged,
            steps=[ReasoningStepResponse.from_step(step) for step in trace.steps],
            total_duration_ms=trace.total_duration_ms,
            tokens_in=trace.tokens_in,
            tokens_out=trace.tokens_out,
            model_id=trace.model_id,
        )


class ReasoningDiagnosticsResponse(_CamelModel):
    """Read-only reasoning-stack diagnostics (#317) — docling-agent
    provenance + effective availability, mirrored from
    `domain.app_config.ReasoningDiagnostics`."""

    deps_present: bool
    provenance: str
    available: bool


class ReasoningConfigSourcesResponse(_CamelModel):
    """Where each effective config value comes from — `env` (bootstrap
    default) or `db` (persisted override).

    A model rather than a `dict[str, str]` (#306 review): the four keys are
    known and closed, the `ConfigSource` literal is enforced instead of a bare
    `str`, and `_CamelModel` aliases the keys to camelCase for free — Pydantic
    does not alias dict *contents*, which previously forced the router to
    rename every key by hand.
    """

    enabled: ConfigSource
    ollama_host: ConfigSource
    model_id: ConfigSource
    max_iterations: ConfigSource


class ReasoningConfigResponse(_CamelModel):
    """Effective reasoning runtime config (#317)."""

    enabled: bool
    ollama_host: str
    model_id: str
    max_iterations: int = Field(
        ge=MAX_ITERATIONS_MIN,
        le=MAX_ITERATIONS_MAX,
        description="RAG loop iteration cap (count, not a duration)",
    )
    sources: ReasoningConfigSourcesResponse
    provider_type: str
    read_only: bool
    diagnostics: ReasoningDiagnosticsResponse

    @classmethod
    def from_view(cls, view: ReasoningConfigView) -> ReasoningConfigResponse:
        """Project the service's `ReasoningConfigView` onto its wire shape."""
        return cls(
            enabled=view.config.enabled,
            ollama_host=view.config.ollama_host,
            model_id=view.config.model_id,
            max_iterations=view.config.max_iterations,
            # Keys are the `ReasoningConfig` field names, which are exactly
            # this model's field names — `populate_by_name` accepts them.
            sources=ReasoningConfigSourcesResponse(**view.sources),
            provider_type=view.provider_type,
            read_only=view.read_only,
            diagnostics=ReasoningDiagnosticsResponse(**asdict(view.diagnostics)),
        )


class ReasoningConfigUpdateRequest(_CamelModel):
    """Body for `PUT /api/config/reasoning` — full-state replace (#317).

    All four knobs are required by design: the panel submits the whole form,
    sparse PATCH semantics were rejected in the design doc (§6-B).
    """

    enabled: bool
    ollama_host: str
    model_id: str
    max_iterations: int


class ReasoningProbeRequest(_CamelModel):
    """Body for `POST /api/config/reasoning/test`."""

    host: str


class ReasoningProbeResponse(_CamelModel):
    """Probe outcome — an unreachable host is a 200 with `reachable: false`."""

    reachable: bool
    models: list[str] = Field(default_factory=list)
    error: str | None = None

    @classmethod
    def from_result(cls, result: LLMHostProbeResult) -> ReasoningProbeResponse:
        return cls(**asdict(result))
