# Architecture decision records

An architecture decision record (ADR) is a short page about one decision: the context, the choice, and what follows from it. ADRs tell future contributors why the code looks the way it does.

ADRs live in `docs/architecture/adrs/`. The first one is [ADR-001](adrs/ADR-001-graph-visualization-library.md), on the graph visualization library.

## When to write one

Write an ADR when you:

- choose or replace a framework, library or tool;
- change the architecture: a new layer, pattern or boundary;
- make a trade-off that someone will question later;
- decide not to do something. These are often the most useful.

Do not write one for:

- details the code already makes obvious;
- style and formatting (see [coding standards](coding-standards.md));
- bug fixes and small refactors.

## How to write one

1. Copy [adr-template.md](adr-template.md) to `docs/architecture/adrs/ADR-NNN-short-title.md`.
2. Take the next number: ADR-001, ADR-002, and so on.
3. Fill in every section. Context (the why) and Alternatives Considered matter most.
4. Set the status to `Proposed` and open a pull request.
5. Once it is merged, set the status to `Accepted`.

## Status

An ADR starts as `Proposed` and becomes `Accepted`. Later it can become:

- `Deprecated`: the decision no longer applies, for example because the feature is gone.
- `Superseded by ADR-NNN`: a newer ADR replaces it. Link to the new one.

Never delete an ADR. Change its status instead.

## Decisions made before ADRs

These decisions came before the ADR process. They are recorded here for context.

| Decision | Why | Date |
|----------|-----|------|
| Vue 3 and Pinia for the frontend | Composition API and built-in reactivity, small bundle. Replaced plain HTML and JavaScript pages. | 2026-03-17 |
| FastAPI as the only backend | Async, light, Pydantic built in. Replaced a Spring Boot backend that only relayed calls to the Python parser. | 2026-03-17 |
| SQLite, not PostgreSQL | One file, nothing to operate | 2026-03-17 |
| Ports and adapters in the backend | Keeps the domain free of frameworks. The converter (local Docling or Docling Serve) plugs in behind a port. | 2026-03-31 |
| Feature flags read from `/api/health` | No flag service: what the backend can do drives what the frontend shows | 2026-04-02 |
| Karate, not Playwright, for end-to-end tests | Team expertise, one tool for API and UI tests, JVM ecosystem | 2026-04-08 |
