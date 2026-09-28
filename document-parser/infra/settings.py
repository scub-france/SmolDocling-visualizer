"""Centralized application settings — loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from domain.app_config import MAX_ITERATIONS_MAX as _MAX_ITERATIONS_MAX
from domain.app_config import MAX_ITERATIONS_MIN as _MAX_ITERATIONS_MIN


def _derived_timeouts(conversion_timeout: int) -> tuple[float, int]:
    """Defaults for DOCUMENT_TIMEOUT and LOCK_TIMEOUT, from the analysis budget (#349).

    Docling stops cleanly two minutes before the analysis gives up, and the
    converter lock outlasts it by one. Under a 4-minute budget those margins
    would go negative, so they shrink to a half and three quarters: the
    cascade document < lock < conversion holds for any budget.
    """
    document = max(conversion_timeout - 120, conversion_timeout / 2)
    lock = int(max(conversion_timeout - 60, conversion_timeout * 3 / 4))
    return float(document), lock


@dataclass(frozen=True)
class Settings:
    app_version: str = "dev"
    conversion_engine: str = "local"  # "local" or "remote"
    deployment_mode: str = "self-hosted"  # "self-hosted" or "huggingface"
    docling_serve_url: str = "http://localhost:5001"
    docling_serve_api_key: str | None = None
    conversion_timeout: int = 900  # budget of one analysis, once out of the queue
    document_timeout: float = 780.0  # Docling-level per-document timeout (seconds)
    lock_timeout: int = 840  # converter lock acquisition timeout (seconds)
    max_concurrent_analyses: int = 3
    default_table_mode: str = "accurate"  # "accurate" or "fast"
    max_page_count: int = 0  # 0 = unlimited (upload validation)
    max_file_size: int = 0  # 0 = unlimited (Docling-level, bytes)
    max_file_size_mb: int = 50  # upload limit in MB (0 = unlimited)
    rate_limit_rpm: int = 100  # requests per minute per IP (0 = disabled)
    batch_page_size: int = 0  # 0 = disabled, > 0 = pages per batch
    opensearch_url: str = ""  # empty = disabled
    embedding_url: str = ""  # empty = disabled (e.g. http://localhost:8001)
    neo4j_uri: str = ""  # empty = disabled (e.g. bolt://neo4j:7687)
    neo4j_user: str = "neo4j"
    # DEV DEFAULT — the dev compose stack uses "changeme" so `docker compose
    # up` works out of the box. The backend logs a loud warning at boot if
    # Neo4j is wired (NEO4J_URI set) AND the password is still the default,
    # so prod operators notice if they inherited it by accident. Real
    # deployments must override NEO4J_PASSWORD.
    neo4j_password: str = "changeme"
    # 0.6.1 (#279) — Fernet key sealing per-store connection passwords
    # in SQLite. Empty by default; the backend refuses to boot if any
    # store row has a non-NULL `connection_password_sealed` and this
    # key is missing. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    store_secret_key: str = ""
    # Live reasoning via docling-agent — off by default (heavy deps, needs an
    # Ollama host reachable from the backend). Toggle REASONING_ENABLED=true +
    # point OLLAMA_HOST at a running instance (default http://localhost:11434).
    reasoning_enabled: bool = False
    # LLM backend the reasoning runner talks to. Today only "ollama" is
    # realizable (docling-agent is hardwired to Ollama via mellea); kept as a
    # config knob to make the LLMProvider abstraction visible and prepare the
    # ground for additional backends.
    llm_provider_type: str = "ollama"
    ollama_host: str = "http://localhost:11434"
    reasoning_model_id: str = "gpt-oss:20b"  # matches docling-agent's example_05
    # RAG loop iteration cap threaded into DoclingRAGAgent (#317). Like the
    # other reasoning vars this is a bootstrap default — the admin panel can
    # override it at runtime via the `app_settings` store.
    reasoning_max_iterations: int = 5
    opensearch_default_limit: int = 1000  # max chunks returned by get_chunks
    embedding_dimension: int = 384  # Granite Embedding 30M / all-MiniLM-L6-v2
    upload_dir: str = "./uploads"
    db_path: str = "./data/docling_studio.db"
    max_paste_image_size_mb: int = 10  # clipboard-paste image limit in MB (0 = unlimited)
    paste_allowed_image_types: list[str] = field(
        default_factory=lambda: ["image/png", "image/jpeg", "image/webp"]
    )
    cors_origins: list[str] = field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )
    # 0.6.1 — Surface flags (#257). Two master flags select which UI surface
    # is exposed: STUDIO_MODE_ENABLED (legacy OCR-debug) and
    # RAG_PIPELINE_ENABLED (new doc-centric ingestion + visualization).
    # At least one must be enabled. Sub-flags below gate individual modes
    # inside the RAG pipeline surface.
    studio_mode_enabled: bool = False
    rag_pipeline_enabled: bool = True
    # 0.6.0 — Doc workspace mode flags (#210, renamed in #257).
    # Sub-flags effective only when rag_pipeline_enabled is true.
    inspect_mode_enabled: bool = True
    linked_mode_enabled: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if self.document_timeout <= 0:
            errors.append(f"document_timeout must be > 0 (got {self.document_timeout})")
        if self.conversion_timeout <= 0:
            errors.append(f"conversion_timeout must be > 0 (got {self.conversion_timeout})")
        if self.lock_timeout <= 0:
            errors.append(f"lock_timeout must be > 0 (got {self.lock_timeout})")
        if self.max_concurrent_analyses < 1:
            errors.append(
                f"max_concurrent_analyses must be >= 1 (got {self.max_concurrent_analyses})"
            )
        if self.max_page_count < 0:
            errors.append(f"max_page_count must be >= 0 (got {self.max_page_count})")
        if self.max_file_size < 0:
            errors.append(f"max_file_size must be >= 0 (got {self.max_file_size})")
        if self.max_file_size_mb < 0:
            errors.append(f"max_file_size_mb must be >= 0 (got {self.max_file_size_mb})")
        if self.max_paste_image_size_mb < 0:
            errors.append(
                f"max_paste_image_size_mb must be >= 0 (got {self.max_paste_image_size_mb})"
            )
        if not self.paste_allowed_image_types:
            errors.append("paste_allowed_image_types must not be empty")
        if self.rate_limit_rpm < 0:
            errors.append(f"rate_limit_rpm must be >= 0 (got {self.rate_limit_rpm})")
        if self.batch_page_size < 0:
            errors.append(f"batch_page_size must be >= 0 (got {self.batch_page_size})")
        if self.opensearch_default_limit < 1:
            errors.append(
                f"opensearch_default_limit must be >= 1 (got {self.opensearch_default_limit})"
            )
        if self.embedding_dimension < 1:
            errors.append(f"embedding_dimension must be >= 1 (got {self.embedding_dimension})")
        if not (self.studio_mode_enabled or self.rag_pipeline_enabled):
            errors.append("at least one of STUDIO_MODE_ENABLED / RAG_PIPELINE_ENABLED must be true")
        if not (_MAX_ITERATIONS_MIN <= self.reasoning_max_iterations <= _MAX_ITERATIONS_MAX):
            errors.append(
                f"reasoning_max_iterations must be between {_MAX_ITERATIONS_MIN} and "
                f"{_MAX_ITERATIONS_MAX} (got {self.reasoning_max_iterations})"
            )
        if self.default_table_mode not in ("accurate", "fast"):
            errors.append(
                f"default_table_mode must be 'accurate' or 'fast' (got '{self.default_table_mode}')"
            )
        # Timeout cascade: document_timeout < lock_timeout < conversion_timeout
        if self.document_timeout > 0 and self.lock_timeout > 0 and self.conversion_timeout > 0:
            if self.document_timeout >= self.lock_timeout:
                errors.append(
                    f"document_timeout ({self.document_timeout}s) must be "
                    f"< lock_timeout ({self.lock_timeout}s)"
                )
            if self.lock_timeout >= self.conversion_timeout:
                errors.append(
                    f"lock_timeout ({self.lock_timeout}s) must be "
                    f"< conversion_timeout ({self.conversion_timeout}s)"
                )
        if errors:
            raise ValueError("Invalid settings:\n  " + "\n  ".join(errors))

    @classmethod
    def from_env(cls) -> Settings:
        """Build a Settings instance from environment variables."""
        cors_raw = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
        paste_types_raw = os.environ.get(
            "PASTE_ALLOWED_IMAGE_TYPES", "image/png,image/jpeg,image/webp"
        )
        conversion_timeout = int(os.environ.get("CONVERSION_TIMEOUT", "900"))
        document_default, lock_default = _derived_timeouts(conversion_timeout)
        return cls(
            app_version=os.environ.get("APP_VERSION", "dev"),
            conversion_engine=os.environ.get("CONVERSION_ENGINE", "local"),
            deployment_mode=os.environ.get("DEPLOYMENT_MODE", "self-hosted"),
            docling_serve_url=os.environ.get("DOCLING_SERVE_URL", "http://localhost:5001"),
            docling_serve_api_key=os.environ.get("DOCLING_SERVE_API_KEY"),
            conversion_timeout=conversion_timeout,
            document_timeout=float(os.environ.get("DOCUMENT_TIMEOUT", document_default)),
            lock_timeout=int(os.environ.get("LOCK_TIMEOUT", lock_default)),
            max_concurrent_analyses=int(os.environ.get("MAX_CONCURRENT_ANALYSES", "3")),
            default_table_mode=os.environ.get("DEFAULT_TABLE_MODE", "accurate"),
            max_page_count=int(os.environ.get("MAX_PAGE_COUNT", "0")),
            max_file_size=int(os.environ.get("MAX_FILE_SIZE", "0")),
            max_file_size_mb=int(os.environ.get("MAX_FILE_SIZE_MB", "50")),
            rate_limit_rpm=int(os.environ.get("RATE_LIMIT_RPM", "100")),
            # 0 = batching disabled (matches dataclass default). Batching
            # preserves memory on very large docs and reports progress after
            # each batch; the local converter merges the batch documents back
            # into one (#344). Enable explicitly for memory-bound deploys.
            batch_page_size=int(os.environ.get("BATCH_PAGE_SIZE", "0")),
            opensearch_url=os.environ.get("OPENSEARCH_URL", ""),
            embedding_url=os.environ.get("EMBEDDING_URL", ""),
            neo4j_uri=os.environ.get("NEO4J_URI", ""),
            neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
            neo4j_password=os.environ.get("NEO4J_PASSWORD", "changeme"),
            store_secret_key=os.environ.get("STORE_SECRET_KEY", ""),
            reasoning_enabled=os.environ.get("REASONING_ENABLED", "false").lower()
            in ("1", "true", "yes", "on"),
            llm_provider_type=os.environ.get("LLM_PROVIDER_TYPE", "ollama"),
            ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            reasoning_model_id=os.environ.get("REASONING_MODEL_ID", "gpt-oss:20b"),
            reasoning_max_iterations=int(os.environ.get("REASONING_MAX_ITERATIONS", "5")),
            opensearch_default_limit=int(os.environ.get("OPENSEARCH_DEFAULT_LIMIT", "1000")),
            embedding_dimension=int(os.environ.get("EMBEDDING_DIMENSION", "384")),
            upload_dir=os.environ.get("UPLOAD_DIR", "./uploads"),
            db_path=os.environ.get("DB_PATH", "./data/docling_studio.db"),
            max_paste_image_size_mb=int(os.environ.get("MAX_PASTE_IMAGE_SIZE_MB", "10")),
            paste_allowed_image_types=[t.strip() for t in paste_types_raw.split(",") if t.strip()],
            cors_origins=[o.strip() for o in cors_raw.split(",")],
            # 0.6.1 — Surface flags (#257).
            studio_mode_enabled=os.environ.get("STUDIO_MODE_ENABLED", "false").lower()
            in ("1", "true", "yes", "on"),
            rag_pipeline_enabled=os.environ.get("RAG_PIPELINE_ENABLED", "true").lower()
            in ("1", "true", "yes", "on"),
            # 0.6.0 — RAG-pipeline sub-flags (#210, renamed in #257).
            inspect_mode_enabled=os.environ.get("INSPECT_MODE_ENABLED", "true").lower()
            in ("1", "true", "yes", "on"),
            linked_mode_enabled=os.environ.get("LINKED_MODE_ENABLED", "true").lower()
            in ("1", "true", "yes", "on"),
        )


# Module-level singleton — import this from other modules.
settings = Settings.from_env()
