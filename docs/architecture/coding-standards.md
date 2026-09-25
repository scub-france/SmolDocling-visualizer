# Coding standards

How we write code in Docling Studio. Linters and tests check most of these rules. Reviewers check the rest.

## Backend (Python, `document-parser/`)

### Tools

| Tool | Role | Config |
|------|------|--------|
| Ruff | Lint and format | `[tool.ruff]` in `document-parser/pyproject.toml` |
| pytest | Tests | `document-parser/pytest.ini` |
| pytestarch | Layer rules, run as a test | `document-parser/tests/test_architecture.py` |

The commands to run are in [CONTRIBUTING](https://github.com/scub-france/Docling-Studio/blob/main/CONTRIBUTING.md#before-you-push).

### Naming

| Element | Convention | Example |
|---------|------------|---------|
| Modules | `snake_case` | `analysis_repo.py` |
| Classes | `PascalCase` | `AnalysisJob`, `DocumentConverter` |
| Functions and methods | `snake_case` | `find_by_document()` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_PAGE_HEIGHT` |
| Private names | `_leading_underscore` | `_build_chunker()` |

### Style

- Keep functions to 30 lines at most. A longer one needs a reason.
- Keep files to 300 lines at most. Split a file that grows past it.
- Order imports: standard library, third-party, local. Ruff sorts them.
- Add type hints to every public function.
- Write a docstring only when the code is not obvious.

### Layers

The backend uses ports and adapters. The ports are `Protocol` classes, all in `domain/ports.py`. `infra/` and `persistence/` implement them. `bootstrap/` builds the adapters and passes them to the services.

`tests/test_architecture.py` fails when a layer imports something it must not:

| Layer | Must not import |
|-------|-----------------|
| `domain/` | `api`, `services`, `infra`, `persistence`, and the `fastapi`, `sqlalchemy`, `httpx` and `opensearchpy` libraries |
| `services/` | `api`, `infra`, `persistence`, and `fastapi` |
| `api/` | `infra`, `persistence` |
| `infra/` | `api`, `services` |
| `persistence/` | `api`, `services`, `infra` |

In practice: routes call services, and services reach adapters only through ports.

### API contract

- JSON uses camelCase. API models extend `_CamelModel` in `api/schemas.py`, which generates camelCase aliases. Python code stays snake_case.
- One exception: an analysis's `pagesJson` is a JSON string whose keys stay snake_case (`page_number`, `self_ref`), because the backend builds it with `dataclasses.asdict()`.
- Route design rules are in [Architecture](../architecture.md#api-rules).

## Frontend (TypeScript and Vue, `frontend/src/`)

### Tools

| Tool | Role | Config |
|------|------|--------|
| ESLint | Lint | `frontend/eslint.config.js` (flat config) |
| Prettier | Format | `frontend/.prettierrc` |
| vue-tsc | Type check | `frontend/tsconfig.json` |
| Vitest | Tests | `frontend/vite.config.js` (Vitest reads the Vite config) |

### Naming

| Element | Convention | Example |
|---------|------------|---------|
| Components | `PascalCase.vue` | `BboxCanvas.vue` |
| Composables | `useCamelCase.ts` | `usePagination.ts` |
| Stores | `store.ts` in the feature folder | `features/analysis/store.ts`, which exports `useAnalysisStore` |
| Types and interfaces | `PascalCase` | `Analysis`, `PageElement` |
| Constants | `UPPER_SNAKE_CASE` | `PREVIEW_DPI` |
| CSS classes | `kebab-case` | `.bbox-canvas` |
| `data-e2e` attributes | `kebab-case` | `data-e2e="upload-zone"` |

### Style

- Use the Composition API: `<script setup lang="ts">`. No Options API.
- Put one component in each file.
- Type props and emits: `defineProps<T>()`, `defineEmits<T>()`.
- A feature has one Pinia store at most, in `store.ts`. Shared state lives in stores. The only exception is `shared/appConfig.ts`.
- Put HTTP calls in the feature's `api.ts`, built on `apiFetch` from `shared/api/http.ts`. Components and stores call those functions.
- Put unit tests next to the code: `store.test.ts` beside `store.ts`. Tests that span features go in `src/__tests__/integration/`.

### Feature boundaries

Each feature lives in `src/features/<name>/`. Its `index.ts` lists what other features may use. A feature imports another feature only through `@/features/<name>`, or uses `@/shared`. It never reaches into another feature's `store`, `api` or `ui`.

ESLint enforces this with the `no-restricted-imports` rule in `frontend/eslint.config.js`. Test files are exempt.

## End-to-end tests (Karate, `e2e/`)

The full rules are in [e2e/CONVENTIONS.md](https://github.com/scub-france/Docling-Studio/blob/main/e2e/CONVENTIONS.md). The essentials:

- Select elements with `data-e2e`, never with CSS classes.
- Wait with `waitFor()` or `waitUntil()`, never with `Thread.sleep()` or `delay()`.
- Set up through the API, check through the UI, clean up through the API.
- Tag tests: `@critical`, `@ui`, `@smoke`, `@regression` or `@e2e`.
