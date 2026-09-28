"""Adapter + service factories for the composition root (#306 review).

Every binding between a configuration value and a concrete adapter lives here,
so `bootstrap.builder` reads as a wiring sequence rather than a pile of
conditionals. Split out of a single `bootstrap.py` to hold the project's
300-line-per-file standard.
"""

from __future__ import annotations

import logging

from domain.app_config import ReasoningConfig
from infra.docling_agent_reasoning import (
    DoclingAgentReasoningRunner,
    deps_present,
    deps_provenance,
)
from infra.llm.ollama_provider import OllamaProvider
from infra.settings import settings
from persistence.database import get_connection
from services.analysis_service import AnalysisConfig, AnalysisService
from services.chunk_service import ChunkService
from services.document_service import DocumentConfig, DocumentService
from services.ingestion_service import IngestionConfig, IngestionService
from services.store_backend_resolver import StoreBackendResolver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adapter factories — the infra bindings the services are constructed with.
# ---------------------------------------------------------------------------


def build_converter():
    """Build the converter adapter based on configuration."""
    if settings.conversion_engine == "remote":
        from infra.serve_converter import ServeConverter

        logger.info("Using remote Docling Serve at %s", settings.docling_serve_url)
        return ServeConverter(
            base_url=settings.docling_serve_url,
            api_key=settings.docling_serve_api_key,
            timeout=settings.conversion_timeout,
            document_timeout=settings.document_timeout,
        )
    from infra.local_converter import LocalConverter

    logger.info("Using local Docling converter")
    return LocalConverter()


def build_chunker():
    """Build the chunker adapter.

    Uses LocalChunker in all modes — in remote mode it chunks the
    DoclingDocument JSON returned by Docling Serve, so docling-core
    (lightweight) is the only local dependency needed.
    """
    from infra.local_chunker import LocalChunker

    return LocalChunker()


def env_reasoning_config() -> ReasoningConfig:
    """Bootstrap defaults for the runtime-configurable reasoning knobs (#317).

    Env vars seed the config; `app_settings` rows override them at runtime via
    `AppConfigService`.
    """
    return ReasoningConfig(
        enabled=settings.reasoning_enabled,
        ollama_host=settings.ollama_host,
        model_id=settings.reasoning_model_id,
        max_iterations=settings.reasoning_max_iterations,
    )


def build_reasoning_runner(config: ReasoningConfig) -> DoclingAgentReasoningRunner | None:
    """Wire the reasoning runner for `config` if enabled and deps are
    importable. Today only `LLM_PROVIDER_TYPE=ollama` is supported (cf. the
    `LLMProvider` docstring); other values fall through to a logged warning +
    None so the rest of the app boots cleanly.
    """
    if not config.enabled:
        return None
    if not deps_present():
        logger.warning(
            "Reasoning is enabled but the stack is unusable (%s) — runner "
            "disabled, /api/reasoning will 503. Expected docling-agent >= 0.6.0 + mellea; "
            "a bare `uvicorn` resolves against the ambient interpreter, not the project venv.",
            deps_provenance(),
        )
        return None
    if settings.llm_provider_type != "ollama":
        logger.warning(
            "Unsupported LLM_PROVIDER_TYPE=%s — reasoning runner disabled (only "
            "'ollama' is realizable today, see "
            "https://github.com/docling-project/docling-agent/issues/26)",
            settings.llm_provider_type,
        )
        return None

    provider = OllamaProvider(host=config.ollama_host, default_model_id=config.model_id)
    logger.info("Reasoning runner enabled (%s)", deps_provenance())
    return DoclingAgentReasoningRunner(provider=provider, max_iterations=config.max_iterations)


async def check_store_secret_key() -> None:
    """Refuse to boot if sealed credentials exist but no key is set.

    0.6.1 (#279) — store passwords are sealed with a Fernet key from
    `STORE_SECRET_KEY`. Sealed values are unreadable without the key, so any
    boot that has them and no key would surface as a hard "wrong password" the
    moment a push tries to use a store. Better to fail fast at boot than wait
    for the first user action.

    Stores with NULL `connection_password_sealed` (e.g. the seeded `default`
    row) don't require the key — booting without it is fine for a fresh
    install or a Neo4j-only stack that has not yet set per-store passwords.
    """
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) AS n FROM stores WHERE connection_password_sealed IS NOT NULL"
        )
        row = await cursor.fetchone()
    sealed_count = row["n"] if row else 0
    if sealed_count == 0:
        return
    if not settings.store_secret_key:
        raise RuntimeError(
            f"STORE_SECRET_KEY is required: {sealed_count} store row(s) hold "
            "encrypted credentials and cannot be opened without the key. "
            "Set STORE_SECRET_KEY in the backend environment before "
            "booting, or null the connection_password_sealed columns "
            "manually if the seal is lost."
        )


async def init_neo4j():
    """Warm the env-based Neo4j driver and bootstrap schema.

    Returns the env-based driver so legacy callers (`AnalysisService`,
    `IngestionService` service-level defaults) keep working. New per-store
    callers go through the pool directly (#279) — schema bootstrap is now the
    pool's job and runs once per (uri, user).
    """
    if not settings.neo4j_uri:
        logger.info("Neo4j disabled (NEO4J_URI not set)")
        return None

    if settings.neo4j_password == "changeme":
        # The dev compose stack ships with "changeme" so `docker compose up`
        # works immediately. Anyone running the backend against a non-dev
        # Neo4j with this password almost certainly forgot to override it.
        logger.warning(
            "Neo4j is configured with the dev default password 'changeme'. "
            "Override NEO4J_PASSWORD before deploying outside localhost."
        )

    from infra.neo4j import get_driver

    try:
        return await get_driver(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    except Exception:
        logger.exception("Neo4j init failed — continuing without graph storage")
        return None


def build_backend_resolver(store_repo) -> StoreBackendResolver:
    """0.6.1 (#279) — bridges per-store CRUD to the (uri, user)-keyed
    driver pools. Env vars feed the transitional fallback for the seeded
    `default` store and any pre-#279 row without its own credentials."""
    from infra.neo4j.driver_pool import get_pool as get_neo4j_pool
    from infra.neo4j.graph_adapter import Neo4jGraphWriter
    from infra.opensearch_pool import get_pool as get_opensearch_pool

    return StoreBackendResolver(
        store_repo=store_repo,
        neo4j_pool=get_neo4j_pool(),
        opensearch_pool=get_opensearch_pool(),
        # Injected as a factory so services/ never has to import infra at
        # runtime (#audit-01) — the composition root owns the binding.
        graph_writer_factory=Neo4jGraphWriter,
        env_neo4j_uri=settings.neo4j_uri,
        env_neo4j_user=settings.neo4j_user,
        env_neo4j_password=settings.neo4j_password,
        env_opensearch_url=settings.opensearch_url,
    )


def build_analysis_service(document_repo, analysis_repo, graph_writer) -> AnalysisService:
    return AnalysisService(
        converter=build_converter(),
        analysis_repo=analysis_repo,
        document_repo=document_repo,
        chunker=build_chunker(),
        conversion_timeout=settings.conversion_timeout,
        max_concurrent=settings.max_concurrent_analyses,
        config=AnalysisConfig(
            default_table_mode=settings.default_table_mode,
            batch_page_size=settings.batch_page_size,
        ),
        graph_writer=graph_writer,
    )


def build_document_service(document_repo, analysis_repo) -> DocumentService:
    return DocumentService(
        document_repo=document_repo,
        analysis_repo=analysis_repo,
        config=DocumentConfig(
            upload_dir=settings.upload_dir,
            max_file_size_mb=settings.max_file_size_mb,
            max_page_count=settings.max_page_count,
        ),
    )


def build_chunk_service(**repos) -> ChunkService:
    """Doc-centric chunks (#256) on top of the chunk / chunk_edit /
    chunk_push repos introduced by #205."""
    from infra.docling_tree import DoclingTreeReader

    return ChunkService(
        tree_reader=DoclingTreeReader(),
        chunker=build_chunker(),
        **repos,
    )


def build_ingestion_service(graph_writer) -> IngestionService | None:
    """Ingestion (#199) — available as soon as `EMBEDDING_URL` is set AND
    at least one store backend is configured (`OPENSEARCH_URL` and/or
    `NEO4J_URI`). The historical precondition required both embedding +
    OpenSearch, which conflated the embedding pipeline with the store."""
    if not settings.embedding_url:
        logger.info("Ingestion disabled (EMBEDDING_URL not set)")
        return None

    has_opensearch = bool(settings.opensearch_url)
    if not has_opensearch and graph_writer is None:
        logger.info(
            "Ingestion disabled (no store backend configured — set OPENSEARCH_URL or NEO4J_URI)"
        )
        return None

    from infra.embedding_client import EmbeddingClient

    vector_store = None
    if has_opensearch:
        from infra.opensearch_store import OpenSearchStore

        vector_store = OpenSearchStore(
            settings.opensearch_url,
            default_limit=settings.opensearch_default_limit,
        )

    logger.info(
        "Ingestion enabled (embedding=%s, opensearch=%s, neo4j=%s)",
        settings.embedding_url,
        settings.opensearch_url or "off",
        "on" if graph_writer is not None else "off",
    )
    return IngestionService(
        EmbeddingClient(settings.embedding_url),
        vector_store,
        IngestionConfig(embedding_dimension=settings.embedding_dimension),
        graph_writer=graph_writer,
    )
