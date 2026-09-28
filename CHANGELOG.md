# Changelog

All notable changes to Docling Studio will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Parse view — Show all** (#338): selecting an element dims every other bbox, and nothing in the UI led back out. A **Show all** button in the LAYERS bar now clears the selection — tree row, Properties panel and Ask trace step — so every visible bbox is drawn at full strength with its label again. Hidden layers stay hidden, and the preview keeps its scroll position.

### Changed

- **Documentation rewritten** (#340): one short page per need (get started, user guide, configuration, troubleshooting, architecture, contributing, maintainers), checked against the 0.7.3 code, with small Mermaid diagrams. Duplicated and outdated pages are gone. Audit reports, design docs and demo scripts stay in the repo but are no longer published on the docs site.
- **Long PDFs keep their structure when analysed in batches** (#344): with `BATCH_PAGE_SIZE` set (10 in Docker Compose), a PDF longer than one batch lost its Docling document, and with it the tree, the chunks, Ask and the JSON export. The local converter now concatenates the batch documents and rebuilds the page details from the merged one, so a batched analysis matches a single-pass one. The document workspace also shows the progress of a running analysis: percentage and pages done when it runs in batches, time elapsed otherwise. `docling-core` 2.65.2 or later is required.

### Deprecated

- **Ingestion** (OpenSearch, Neo4j): deprecated, removed in 0.8.0. This covers sending chunks to OpenSearch or Neo4j, the embedding service, the stores, the chunk search, the Neo4j graph view, the `ingestion` and `graph` compose profiles and `docker-compose.ingestion.yml`. The documentation flags each of them.

## [0.7.2] - 2026-09-22

### Fixed

- **Preview scroll — focus the element once, without the page collapsing** (#336): selecting a node in the structure tree made the stacked preview flicker and land somewhere other than the element. Only pages inside the render window mounted their raster and nothing reserved the box of the others, so an off-window card collapsed to its header and re-inflated when its image decoded — every scroll target was computed against a layout shifting underneath it. Each frame now holds the page's own aspect ratio and natural raster width, so a card keeps its height with no image mounted. The focus scroll measures the frame instead of the image (a bbox on a far page is centred on the first click, not on a later `load` event), the three watchers a single focus wakes coalesce into one scroll per flush instead of three competing smooth scrolls, and the page carrying the highlight keeps its raster — and its overlay — while it is the target.

### Changed

- **Development stack made worktree friendly** (#324): `docker-compose.dev.yml` no longer binds fixed host ports or named volumes, so several worktrees can run their stack side by side. The parser is reached over the compose network (`expose` instead of `ports`) with uploads and SQLite state bind-mounted under `document-parser/`, and the frontend host port comes from `FRONTEND_HOST_PORT` (default `3000`). A new `.development_scripts/worktree_setup.sh` prepares dependencies and copies local state into a fresh worktree, driven either by flags or by environment variables so it stays independent of any one workspace tool; `paseo.json` wires it up for Paseo users.

## [0.7.1] - 2026-08-24

### Fixed

- **The published `local` image now ships the reasoning stack** (`release.yml`): the release build never passed `WITH_REASONING`, so `docling-agent` + `mellea` were absent from `ghcr.io/scub-france/docling-studio:0.7.0-local` and `POST /api/documents/{id}/reasoning` answered `503` — the 0.7.0 headline feature was unreachable from the image users pull. The runtime panel (#317) can toggle reasoning, but it cannot install packages. `release.yml` now passes `WITH_REASONING=true` on the `local` target; the lightweight `remote` image is unchanged (its stage does not declare the ARG), and source builds stay opt-in.
- **README reasoning section corrected**: it still described the v1 graph overlay that 0.7.0 removed, and still called the stack "disabled by default". It now documents the Parse-view timeline, the published-image behaviour, and the two upstream limits (docling-agent 0.6.0 emits only `READ` steps and reports no per-step timing).

### Known gap

- The release gate has **no reasoning coverage at all** — no workflow builds a `WITH_REASONING` image and `release-gate.yml` contains no reasoning job, so a fully green gate says nothing about this feature. The `e2e-ui-reasoning` job specified in `docs/design/303-reasoning-trace-v2-parse-view.md` was never created. Tracked as follow-up.

## [0.7.0] - 2026-08-24

### Added

- **Analyses workspace**: a dedicated Analyses navigation item lists every run and opens its saved visualization independently of the document preview. This makes document source management separate from analysis-result inspection and supports multiple analyses per document.
- **Reasoning Trace v2 — timeline + Ask panel in the Parse view** (#303): live reasoning now runs inline in the document Parse tab instead of a standalone page. A typed trace timeline renders each step (`PLAN/RETRIEVE/RERANK/READ/VERIFY/ANSWER/MAP`) with per-step durations and citations, degrading gracefully to a uniform "step order" layout when the agent reports no timing. A conversational Ask panel (composer + turn cards) drives the runs. Focusing a step reveals and scrolls the linked element across the PDF, the document tree, and the Parse view.
- **Backend trace projection** (#303): a pure `domain.trace_builder` projects the raw docling-agent `ReasoningResult` onto the debugger-facing `ReasoningTrace`; a new `ReasoningService` orchestrates the run (query validation, latest-analysis lookup, timing) so `api/reasoning.py` no longer reaches into `app.state` directly. Backed by docling-agent's public `run_with_trace()` API.
- **Runtime reasoning configuration from the admin panel** (#317): a **Reasoning** section in `/settings` enables/disables reasoning and sets the Ollama URL, default model and RAG `max_iterations` **without a backend restart** — the runner and service are rebuilt in place and `/api/health` follows, so the Ask tab appears/disappears live. Overrides persist in a new SQLite `app_settings` table (env vars become bootstrap defaults, each field reports its `env`/`db` source, "reset to environment" drops them). A test-connection action probes the host and turns the model field into a select of the installed models; read-only diagnostics (docling-agent version + import path, provider, availability) make boot failures visible from the UI. New endpoints `GET`/`PUT`/`DELETE /api/config/reasoning` + `POST /api/config/reasoning/test`; writes are refused (403) on HuggingFace deployments. `max_iterations` is now actually threaded into `DoclingRAGAgent` (new `REASONING_MAX_ITERATIONS` bootstrap var, default 5).

### Changed

- **Simplified document workflow**: the Documents page now focuses on source files, preview, PDF download, and deletion. Chunking and ingestion controls were removed from the document workspace; associated analyses are shown separately and document deletion explicitly confirms the analysis cascade.
- **Lean development stack**: the default compose profile starts only the frontend and SQLite-backed parser. Optional `ingestion`, `graph`, and `remote` profiles enable their respective dependencies.
- **Reasoning backend ported to the public `run_with_trace()` surface** (#303): docling-agent pinned to `0.6.0`; an unusable / missing agent is now detected at boot rather than on the first Ask, and an empty agent result maps to a parse error (`502`).

### Removed

- **Standalone v1 reasoning surface retired** (#303): the graph-overlay reasoning workspace and its `/reasoning` page are removed in favour of the Parse-view timeline. The old `/reasoning` and `/reasoning/:docId` routes are kept as redirects so shared URLs don't 404.

## [0.6.2] - 2026-06-05

### Added

- **Docling Serve container wired into compose** (`#audit-10`, `dd1962e`, `bc9b4f8`): new `docling-serve` service under the `remote` compose profile, pinned to `quay.io/docling-project/docling-serve-cpu:v1.21.0`. Pairs with `CONVERSION_MODE=remote` so the backend image stays slim and talks to a Docling Serve container over HTTP — no HF Hub dep on the build or runtime path. CI/release-gate E2E jobs now use this combo.
- **HuggingFace dependency map** (`docs/architecture/huggingface-dependency-map.md`): exhaustive list of every HF call site in the project, the single sanctioned touch point (`release.yml` → `latest-local`), and the maintenance rule that every new HF dep must be opt-in.

### Changed

- **Backend + embedding-service migrated from pip to uv** (#254, `4d9bcf6`): `document-parser/requirements*.txt` and `embedding-service/requirements.txt` removed; `uv.lock` plus `pyproject.toml`'s `[project]` / `[dependency-groups]` blocks are now the single source of truth. Dev workflow becomes `uv sync --group dev` (backend) / `uv sync --group local` (local Docling). PyTorch is redirected to the explicit CPU index via `[tool.uv.sources]` to avoid pulling the ~3 GB CUDA wheels into `latest-local`.
- **`latest-local` ships with Docling model checkpoints baked at build time** (#254, `9d62337`): suppresses the cold-start HF Hub download on the first `/api/convert`. End users get an instant first-convert from the pulled GHCR image.
- **`.dockerignore` hardened** (#254, `fe1dc16`): tests, audit reports, `.claude/`, `docker-compose*.yml` and other build-irrelevant paths excluded — leaner build context, smaller intermediate layers.
- **Reasoning stack made opt-in via `WITH_REASONING` build-arg** (#254, `d1ed61e`, `bb2fe2b`): `docling-agent` and `mellea` moved out of `[project.dependencies]` into `[dependency-groups.reasoning]`. The default `latest-local` image no longer carries them — `/api/reasoning` responds `503` (graceful degrade). Building with `--build-arg WITH_REASONING=true` restores the 0.6.1 behaviour.
- **`BAKE_MODELS` and `BAKE_MODEL` default to `false`** (`#audit-10`): both `document-parser/Dockerfile` and `embedding-service/Dockerfile` now opt out of HuggingFace Hub by default at build time. The only sanctioned bake is `release.yml` → `latest-local` GHCR image, which sets `BAKE_MODELS=true` explicitly on the `local` matrix entry. See the new HF dependency map for details.

### Fixed

- **Remote-mode bbox overlay — second pass** (`3936166`, follow-up to the 0.6.1 fix): a code path the 0.6.1 patch missed still dropped `self_ref` in `ServeConverter`. The Linked-view canvas overlay now lights up consistently in remote mode.
- **Architecture test excludes generated files** (`d29360d`): `tests/test_architecture.py` no longer scans `uploads/`, `data/` or other runtime artifacts — keeps the layering rules clean without false positives.

### CI

- **`STUDIO_MODE_ENABLED` opted in on the main CI too** (`8a61c22`): the `@critical` UI suite needs the legacy `/studio` surface; previously only `release-gate.yml` set the flag, leaving `ci.yml` E2E UI silently exercising the wrong surface.
- **Docling model bake skipped during CI builds** (`051ac4a`, `#audit-10`): both `ci.yml` E2E jobs and both `release-gate.yml` E2E jobs (`e2e-api`, `e2e-ui`) now build the image with `BAKE_MODELS=false` to avoid HuggingFace Hub 429 rate limits on shared GHA runners. `release.yml` keeps `BAKE_MODELS=true` so the published image still carries the baked checkpoints.
- **Unit test no longer pulls HF tokenizer** (`#audit-10`): `test_rechunk_with_serve_document_json` was instantiating a real `LocalChunker`, forcing `HybridChunker` to download `sentence-transformers/all-MiniLM-L6-v2`. Now mocks the `DocumentChunker` port — same intent, no public network in a unit test.

### BREAKING CHANGES

- **Backend dev workflow migrated to uv**: `pip install -r document-parser/requirements*.txt` / `pip install -r embedding-service/requirements.txt` no longer work — these files are gone. Use `uv sync` (`--group dev` for tests, `--group local` for local Docling mode). Any third-party CI / IDE bootstrap script that relies on the old `requirements*.txt` layout must migrate.
- **Reasoning runtime made opt-in**: building `latest-local` without `--build-arg WITH_REASONING=true` produces an image where `/api/reasoning` responds `503`. Operators who depended on the 0.6.1 default-on reasoning stack must add the build-arg to their pipeline.
- **`BAKE_MODELS` default flipped from `true` to `false`** in both `document-parser/Dockerfile` and `embedding-service/Dockerfile`. Operators who build their own `local` image from source and rely on the "instant first `/api/convert`" behaviour must now pass `--build-arg BAKE_MODELS=true` explicitly. The published `ghcr.io/.../docling-studio:latest-local` image is unaffected — `release.yml` opts in. Pulling that image (the documented path) continues to work as before. See `docs/architecture/huggingface-dependency-map.md` for the rationale and the full HF call-site map.

## [0.6.1] - 2026-05-25

### Added

- **Per-document workspace** (#263, #264, #265, #266, #267, #268): `DocWorkspacePage` shell with a Parse / Chunk / Inspect / Compare tab switcher replaces the legacy `/studio` single-page editor. Parse view (#264) introduces LAYERS filters, focus mode, tree color-coding and centered scroll; Properties panel (#265) plus inline chunk edit; Strategy popover (#268) for inline rechunk from the Chunk view; dedicated "Generate chunks" button decouples chunk creation from the analysis run.
- **Version history** (#267): paired `(analysis, chunks)` version snapshots with a History drawer for switching the active analysis. Race on new-analysis creation closed and pre-existing data backfilled.
- **Chunk service + routes** (#256, #269): backend `ChunkService` exposing 9 DDD-granular routes under `/api/documents/{id}/chunks/*`. Every existing `/api/*` route classified against the no-UX-shaped-routes rule (`docs/design/269-backend-ddd-audit.md`).
- **Ingest tab redesign** (#225, #283, #285): workspace Ingest view with CTA + history-driven shell, push-history endpoint `GET /api/documents/{id}/chunks/pushes`, pending-push badge on the launch CTA, hierarchical doc tree with per-tab CTAs and ingest-targets popover.
- **Store connection credentials** (#279): per-store backend dispatch through a resolver + pool layer, Neo4j driver pool keyed by `(uri, user)`, OpenSearch client pool with basic-auth, Neo4j as a connectable store backend. Store form gets a connection sub-form + test-connection button; `/api/stores/*` exposes connection fields and a test-connection endpoint.
- **Sealing-at-rest for store passwords** (#279): new `FernetBox` adapter (`infra/secrets/fernet_box.py`) sealing store credentials before persistence; `STORE_SECRET_KEY` env var required as soon as any store row holds a sealed value (boot fails otherwise — see `main.py:_check_store_secret_key`).
- **Master surface flags** (#257): `STUDIO_MODE_ENABLED` and `RAG_PIPELINE_ENABLED` env vars gate the legacy Studio mode and the reasoning pipeline respectively (default off in production; e2e suite opts in via `STUDIO_MODE_ENABLED=true` for `@critical` tests).
- **Karate UI e2e suite** (#256, #266): regression coverage for Doc tab chunk mode and rechunk flow, scaffold under `e2e/`.

### Changed

- **Push-chunks wire vocabulary**: `POST /api/documents/{id}/chunks/push` response field `jobId` renamed to `pushId`; corresponding i18n keys `chunks.pushedJob`, `chunks.stale.jobDispatched`, `docs.jobDispatched` renamed to `chunks.pushDispatched`, `chunks.stale.pushDispatched`, `docs.pushDispatched` and rephrased from "Job lance/dispatched" to "Push enregistre/recorded" — aligns the wire on the `ChunkPush` domain aggregate (#audit-02).
- **Backend DDD audit** (#269): the no-UX-shaped-routes rule is now documented in `document-parser/CLAUDE.md` and codified in `docs/design/269-backend-ddd-audit.md`. Every `/api/*` route classified as either a single domain op or a named atomicity exception.
- **Workspace navigation polish** (`0c98645`): per-tab CTAs, hierarchical doc tree, ingest-targets popover.
- **Backend uploads non-blocking** (#audit-12): `DocumentService.upload` and `ServeConverter.convert` offload their sync disk I/O + poppler subprocess to worker threads (`asyncio.to_thread`), mirroring the 0.5.0 pattern applied to `/preview`.
- **Architecture test makes pytestarch optional at collect-time** (#audit-09): `tests/test_architecture.py` now uses `pytest.importorskip` so the file collects cleanly even without test deps installed; CI installs `requirements-test.txt` and runs the rules normally.

### Fixed

- **Re-chunk preserves chunker `doc_items`** (#266): bbox ↔ chunk linking no longer breaks after a rechunk; structure tree reloads on active-analysis change.
- **Document-store-links upsert on push** (#225): per-store state was never updated — `chunk_pushes` now FK-resolves store slug → id first.
- **Ingest view refresh after push** (#225): stale count aligned with the push that just landed.
- **Neo4j Document node merged in `chunk_writer`** (#225): silent-fail after a graph wipe.
- **Ingestion availability decoupled from OpenSearch** (#199): Neo4j-only ingest no longer requires OpenSearch to be reachable.
- **Cross-doc bbox leak in analyses list** (`fa2c7d7`): list endpoint filters by `documentId`.
- **Frontend feature-flag race** (`5df009a`, `825e7d7`): flags load before mount; router guard awaits the load; idempotent.
- **Docker dev proxy** (`c43aced`, `f56ead5`): Vite dev frontend correctly targets the backend.
- **Push-chunks duplicate dropped** (#256, `b4ad874`): `pushDocumentToStore` removed; rechunk return shape aligned.
- **Backend test collection unblocked** (#audit-09): dead `test_local_converter.py` deleted (the SUT `_encode_picture_b64` was removed); was hidden behind `.gitignore` rather than fixed.
- **CI auto-close hardened** (#audit-10): commits payload moved into the `env:` block of the workflow to avoid shell interpolation of commit messages with quotes/backticks.
- **Frontend package version bumped to 0.6.1** (#audit-11): was stuck at 0.5.0.
- **Remote-mode bbox overlay restored** (#audit-remote-bbox): `ServeConverter` was silently dropping `self_ref` on every element parsed from the Docling Serve response, leaving the Linked-view canvas overlay empty for every document converted through Docling Serve. Local-mode parity was already correct (`LocalConverter` carries it); the remote path now does too.

### Security

- **CVE-2026-7598 (libssh2)**: ignored — not reachable from any code path in the image and no Debian backport available (`858c3a9`).
- **`STORE_SECRET_KEY` plumbed end-to-end** (#audit-08): `.env.example`, `docker-compose.yml`, `docker-compose.dev.yml` now document the variable with the key-generation one-liner and ship it with no default — boot fails if sealed rows exist without a key. Closes the "operator seals with an ephemeral key" foot-gun.

### BREAKING CHANGES

- **`POST /api/documents/{id}/chunks/push` response field**: `jobId` → `pushId`. Frontend consumers must update.
- **Surface flags default off in production**: `STUDIO_MODE_ENABLED` and `RAG_PIPELINE_ENABLED` were implicitly on before 0.6.1. Operators relying on the legacy `/studio` page or the RAG pipeline must explicitly set them to `true`.
- **`STORE_SECRET_KEY` required for sealed stores**: any 0.6.0 deployment that already created store rows with sealed passwords will fail the boot on 0.6.1 until `STORE_SECRET_KEY` is provided. Generate a Fernet key (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) and pin it in the environment before upgrading. Rotating the key invalidates every existing sealed value.
- **i18n keys renamed** (`chunks.pushedJob`, `chunks.stale.jobDispatched`, `docs.jobDispatched` → `chunks.pushDispatched`, `chunks.stale.pushDispatched`, `docs.pushDispatched`) and their placeholder `{jobId}` → `{pushId}`. Any external translation override file must be updated.

## [0.6.0] - 2026-05-19

### Added

- **Doc-centric data model + routing** (#202, #203, #204, #205, #206, #207, #208, #209, #210, #211, #216): `Document` lifecycle state machine, per-`(document, store)` ingestion state, deterministic chunkset hash for auto-stale detection, chunks promoted to first-class entities with an audit trail. URL scheme migrated from analysis-centric (`/analysis/:id`) to document-centric (`/docs/:id/...`); reworked sidebar nav (Home / Docs / Stores / Runs / Settings); breadcrumb; feature-flag mode gating with deep-link redirect.
- **Document Library** (#211): `/docs` page with filters, bulk actions, multi-file import, `StatusBadge`.
- **Doc workspace tabs**: `DocInspectTab` (#240, #241) for Markdown / Elements / Images from the Docling analysis; `DocAskTab` (#242) for the reasoning trace integrated into the workspace.
- **Stores CRUD UI + API** (#243, #244, #245, #251): `StoresListPage`, `StoreDetailPage`, `StoreForm`, `QueryPage`. Backend gets `/api/stores` router + `StoreService` orchestrator + `SqliteStoreRepository` with full CRUD; per-kind config validation; Neo4j added as a `StoreKind`. Typed API client; backend error detail surfaced through `apiFetch`.

### Changed

- **Vocabulary rename `index` → `ingest`** (#224, #225) across UI labels, route names and i18n keys. Stale stores strip on the workspace.
- **Workspace shell refactor** (#216): `DocWorkspacePage` (`DocTreeRail`, `DocWorkspaceHeader`, editable chunks editor) replaces the legacy single-page studio for doc-centric flows.
- **Doc state reset on navigation** (`53d28c2`): bbox / analysis state leak between docs fixed.
- **SQLite schema bootstrap clean-slate** (#279, `db145ca`): drop the incremental migration machinery and rewrite `_SCHEMA` from scratch — fresh installs only from 0.6.x onward.

### Fixed

- **CI**: install `pytestarch` in `docling-compat` workflow (`c3d4b11`); nginx template moved outside `sites-enabled` to avoid raw-load (`2807cc3`).

### BREAKING CHANGES

- **URL scheme migration**: paths under `/analysis/:id` are gone; the workspace lives under `/docs/:id/...`. The legacy `/studio` page remains accessible only when `STUDIO_MODE_ENABLED=true` (and only until 0.7.0 ships its rewrite).
- **Vocabulary `index` → `ingest`**: any external tooling parsing the public UI / API surface for the `index` keyword must update.
- **No auto-migration from 0.5.x**: the SQLite schema is bootstrapped fresh from `_SCHEMA`. Upgrading from a 0.5.x database requires either (a) re-importing your documents into a fresh DB, or (b) hand-rolling the catch-up DDL — there is no migration path shipped.

## [0.5.1] - 2026-04-30

### Fixed

- Nginx upload body cap raised from 5 MB to 200 MB (`NGINX_MAX_BODY_SIZE`, default `200M`); uploads larger than 5 MB no longer returned 413 before reaching the backend.

## [0.5.0] - 2026-04-28

### Added

- Reasoning-trace viewer: SQLite-backed graph built from `document_json`, iteration-by-iteration overlay on the document outline (StructureViewer + GraphView), bidirectional PDF ↔ graph focus
- Live reasoning runner via [docling-agent](https://github.com/docling-project/docling-agent) (Ollama backend): `POST /api/documents/:id/reasoning` returns answer + iteration trace + convergence flag (gated by `REASONING_ENABLED`, off by default)
- `LLMProvider` port abstraction with `OllamaProvider` adapter — opens the door to alternate LLM backends once docling-agent supports them
- Neo4j graph storage pipeline: `TreeWriter` + `ChunkWriter` adapters, schema bootstrap, graph fetch endpoint, `Maintain` step with cytoscape-based graph visualization
- Architecture decision record (ADR-001): graph visualization library choice and 200-page endpoint cap
- Remote chunking: enabled in Docling Serve mode (previously local-only)
- Hexagonal architecture tests powered by `pytestarch` (CI-enforced)
- Centralized magic numbers for page dimensions, limits, and timeouts
- Paste image size/type limits (env vars `MAX_PASTE_IMAGE_SIZE_MB`, `PASTE_ALLOWED_IMAGE_TYPES`); surfaced in `/api/health`

### Changed

- **Breaking — `RAG_*` env vars renamed to `REASONING_*`**: `RAG_ENABLED` → `REASONING_ENABLED`, `RAG_MODEL_ID` → `REASONING_MODEL_ID`. Health response field `ragAvailable` → `reasoningAvailable`. New `LLM_PROVIDER_TYPE` env var (default `ollama`) materializes the LLM-provider abstraction.
- **Breaking — reasoning endpoint renamed `/rag` → `/reasoning`**: `POST /api/documents/:id/rag` is now `POST /api/documents/:id/reasoning`. Aligns with frontend `reasoning` feature naming.
- `api/reasoning.py` refactored to depend on `ReasoningRunnerPort`; concrete `docling-agent` integration moved to `infra/docling_agent_reasoning.py` (clean architecture)
- Frontend `reasoning` feature flag now reads `reasoningAvailable` from `/api/health`; sidebar entry hides when the backend is not wired (instead of failing with 503 on click)
- Documented that `docker-compose.yml` ships dev-only defaults (Neo4j `changeme` password, OpenSearch `DISABLE_SECURITY_PLUGIN=true`); operators must harden their own production deployments
- Backend logs a loud warning at boot if Neo4j is wired (`NEO4J_URI` set) with the default `changeme` password, so prod operators can't silently inherit it
- `DocumentConverter` port exposes `supports_page_batching: bool` so the analysis service no longer relies on `isinstance(converter, ServeConverter)` (LSP fix)
- `VectorStore` port gains a `ping()` method; `IngestionService.ping()` now goes through the port instead of reaching into `_vector_store._client` (encapsulation)
- API path parameters renamed `{job_id}` → `{analysis_id}` across `api/analyses.py` and `api/ingestion.py` to align the OpenAPI surface with the user-facing terminology (URL paths unchanged)
- Centralised `localStorage` keys (`docling-theme`, `docling-locale`) into `frontend/src/shared/storage/keys.ts` (`STORAGE_KEYS`)
- Removed the dead `apiUrl` ref from the settings store and its orphan `settings.apiUrl` i18n entries
- Document-status string `"uploaded"` extracted to `DOCUMENT_STATUS_UPLOADED` in `api/schemas.py`
- PDF preview endpoint (`GET /api/documents/{id}/preview`) now offloads the synchronous file read + rasterisation to a worker thread (`asyncio.to_thread`), unblocking the FastAPI event loop

### Fixed

- Graph: collapse Docling `InlineGroup` and `Picture` children to avoid empty leaf nodes (#197)
- Neo4j: rewrite `fetch_graph` using `CALL` subqueries for proper relationship traversal
- CI: install `pytestarch` in backend tests job (#177)
- CI: ignore CVE-2026-40393 (Mesa) with expiry — Debian has no backport (#190)
- Reasoning: re-scroll PDF when re-clicking the active iteration
- `infra/docling_tree.py:101` migrated `isinstance(bbox, (list, tuple))` to PEP 604 union (Ruff UP038)
- Cross-feature integration test moved out of `features/history/` into `src/__tests__/integration/` so feature folders stay self-contained
- Tightened terminal `assert X is not None` checks in domain/repo/service tests to compare the value (e.g. `isinstance(.., datetime)` after `mark_running()`/`mark_completed()`)

## [0.4.0] - 2026-04-13

### Added

- Inline chunk text editing: double-click or edit button to modify chunk text, with save/cancel and "modified" badge
- Docker Compose dev stack (`docker-compose.dev.yml`) with OpenSearch, Dashboards, hot-reload backend and Vite frontend
- Soft-delete chunks: delete button with confirmation dialog, chunks hidden from UI but preserved in data
- Vector index metadata schema: `IndexedChunk` domain model, OpenSearch mapping builder, configurable embedding dimension
- `VectorStore` port (Protocol): `ensure_index`, `index_chunks`, `search_similar`, `get_chunks`, `delete_document`
- OpenSearch adapter (`OpenSearchStore`): kNN vector search, full-text search, bulk indexing, document CRUD
- Embedding microservice (`embedding-service/`): sentence-transformers REST API with batch processing and Dockerfile
- `EmbeddingService` port and `EmbeddingClient` HTTP adapter for remote embedding generation
- Orchestrated ingestion pipeline: Docling → chunking → embedding → OpenSearch indexing (idempotent)
- Ingestion REST API: `POST /api/ingestion/{jobId}`, `DELETE /api/ingestion/{docId}`, `GET /api/ingestion/status`
- Production docker-compose with OpenSearch and embedding service
- E2E Karate test for full ingestion workflow (PDF → chunks in OpenSearch)
- My Documents screen: search, filter (all/indexed/not indexed), sort (name/date), ingestion status badges
- Ingest button in Studio: one-click ingestion from completed analysis with progress feedback

### Fixed

### Changed

## [0.3.1] - 2026-04-09

### Added

- Batch conversion progress: segmented progress bar with ring indicator and per-batch visual feedback
- Inline mini progress bar in the top banner during analysis
- Informational notice in Prepare mode when chunking is unavailable (batch mode)
- `BATCH_PAGE_SIZE` environment variable forwarded in Docker Compose

### Fixed

- Batch progress reset to null on completion (progress_current/progress_total overwritten by stale in-memory job object)
- Regression test for batch progress preservation in `_run_analysis_inner` flow
- E2E assertion on final progress values in batch-progress feature

## [0.3.0] - 2026-04-07

### Added

- Chunking support: domain objects, persistence, API endpoints, and frontend Prepare mode
- Chunk-to-bbox hover highlighting in Prepare mode
- Page filtering and collapsible config in Prepare mode
- Feature flipping mechanism
- Reusable pagination composable and PaginationBar component
- Version display in sidebar, settings page, and health endpoint

### Fixed

- Feature flag health check blocked by CORS
- Zombie jobs and unprotected JSON parse
- Upload error not displayed in DocumentUpload component
- Serve API contract: send `to_formats` as repeated form fields
- Audit findings: security, robustness, dead code, domain-infra violation

### Changed

- Refactored backend to hexagonal architecture for converter extensibility
- Added ServeConverter adapter for remote Docling Serve integration
- Moved `@vitest/mocker` from dependencies to devDependencies

## [0.2.0] - 2025-05-14

### Added

- Multi-arch Docker image release pipeline (GitHub Actions)
- Docker image published to `ghcr.io/scub-france/Docling-Studio`

## [0.1.0] - 2025-01-01

### Added

- Initial release of Docling Studio
- PDF upload and document management
- Configurable Docling pipeline (OCR, tables, code, formulas, images)
- Bounding box visualization with color-coded overlays
- Per-page results synchronized with PDF viewer
- Markdown and HTML export
- Analysis history with re-visit capability
- Dark/Light theme support
- French and English localization
- Docker and Docker Compose deployment
- CI/CD with GitHub Actions (tests + multi-arch Docker build)
- Health check endpoint (`/health`)
- SQLite-backed persistence
