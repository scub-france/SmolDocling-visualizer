# ADR-001: Graph visualization library for the Neo4j graph view

**Date**: 2026-04-17
**Status**: Proposed
**Deciders**: Pier-Jean Malandrino

## Context

v0.5.0 introduces Neo4j as a graph-native storage layer for parsed documents
(see [docs/design/neo4j-integration.md](https://github.com/scub-france/Docling-Studio/blob/main/docs/design/neo4j-integration.md)
and [#186](https://github.com/scub-france/Docling-Studio/issues/186)). We need
an in-app visualization of that graph: the `DoclingDocument` tree as rendered
in Neo4j, with nodes colored by element type (`SectionHeader`, `Paragraph`,
`Table`, `Figure`, `ListItem`, `Formula`) and edges (`PARENT_OF`, `NEXT`,
`ON_PAGE`, `HAS_CHUNK`, `DERIVED_FROM`).

The view lives in the existing Vue 3 debug panel. It is the **primary demo
artifact** for the Hackernoon hackathon (Neo4j partner), so polish matters as
much as correctness.

### Constraints

- Vue 3 + Vite frontend, no framework change
- Must render the full tree of a 200-page document (worst case ≈ a few
  thousand nodes; see graph endpoint cap in the design doc §8.4)
- Needs a **clean hierarchical layout** — documents are trees, not arbitrary
  graphs; a good tree layout is the single biggest UX lever
- Needs per-node styling (shape + color by label), click, hover, zoom, pan
- Must be installable without Java/Python-side changes
- License compatible with the repo (MIT-ish preferred)

### Non-goals for v0.5.0

- 3D rendering
- Force-directed simulation as the primary layout (we have a tree)
- Editing nodes in place (read-only view)
- Rendering millions of nodes

## Decision

Use **Cytoscape.js** via a thin Vue wrapper (`vue-cytoscape` or a bespoke
`GraphView.vue` that imports `cytoscape` directly and uses the
`dagre`/`breadthfirst` layouts).

## Consequences

### Positive

- Battle-tested library (13k+ GitHub stars, maintained since 2013, used by
  Neo4j's own "Bloom"-style visualizations in the community)
- First-class support for hierarchical layouts via `cytoscape-dagre` (hub-and-
  spoke / tree) and built-in `breadthfirst` — both map naturally to our
  `PARENT_OF` structure
- CSS-like selector syntax for styling (`node[label = "Table"] { ... }`),
  which is pleasant to evolve as we add node types
- Permissive licensing (MIT)
- Headless mode available, so it can be tested outside a DOM (Jest + jsdom
  works cleanly)
- Active ecosystem: `cytoscape-cola`, `cytoscape-klay`, `cytoscape-popper` for
  tooltips, all maintained
- Bundle size is reasonable for a demo: ~300 KB min+gz for core + dagre, well
  below our current frontend budget

### Negative

- Styling DSL is powerful but has its own syntax to learn; not plain CSS
- Large graphs (>10k nodes) benefit from canvas+WebGL libraries
  (sigma.js, reagraph) — we are explicitly not in that regime for v0.5, but
  we would need to swap if we later visualize the cross-document graph
- No Vue 3 component library that is both maintained and popular — we wrap it
  ourselves in `GraphView.vue` (the wrapper is ~50 LOC, so this is minor)

### Neutral

- Not "Neo4j-branded": we do not use Neovis.js, which is a thin Cytoscape
  wrapper around the Bolt protocol. Our graph API already returns shaped
  JSON, so the Neovis convenience is not worth the lock-in
- We take on one runtime dependency (`cytoscape` + `cytoscape-dagre`)

## Alternatives Considered

### Alternative 1: vis-network (vis.js)

- **Pros**: Very easy to get started, built-in physics, shipped by Neo4j
  Browser historically
- **Cons**: Maintenance has been rocky (original vis.js split into several
  forks; `vis-network` is the maintained branch but releases are sparse);
  hierarchical layout is OK but less configurable than dagre; styling API is
  less expressive; TypeScript types lag behind the JS API
- **Why rejected**: Hierarchical layout quality is the single most important
  criterion for a document tree, and vis-network is clearly a notch below
  Cytoscape + dagre here. Maintenance trajectory is also a concern for a
  release we want to keep shipping on

### Alternative 2: Neovis.js

- **Pros**: Built by Neo4j Labs, connects directly to a Bolt endpoint, nice
  out-of-the-box "Neo4j look"
- **Cons**: Wraps Cytoscape anyway, so everything it can do we can do with
  Cytoscape directly; expects the browser to talk Bolt, which forces us to
  expose Neo4j creds in the frontend OR to proxy Bolt through the backend
  (both worse than our current "backend returns JSON" design); limited
  customization compared to raw Cytoscape
- **Why rejected**: The auth story is a non-starter for a hackathon demo we
  want to show publicly, and we lose nothing vs. Cytoscape by going one
  layer lower

### Alternative 3: D3 (d3-hierarchy + d3-force)

- **Pros**: Maximum flexibility; beautiful, publication-grade output; full
  SVG control
- **Cons**: Much more code for the same result — layout, zoom, pan, hover,
  selection all hand-rolled; steeper learning curve for future contributors
  to the project; no built-in graph data model
- **Why rejected**: We're building a product feature, not a data-viz
  artefact. The time budget (1 day of Day 3) doesn't fit a D3 build-your-own

### Alternative 4: Reagraph / react-force-graph / sigma.js (WebGL)

- **Pros**: Scales to tens of thousands of nodes at 60 FPS; good for future
  cross-document visualization
- **Cons**: Optimized for force-directed layouts, weaker hierarchical
  support; Reagraph is React-only (requires a React island inside Vue);
  sigma.js's tree layout is immature
- **Why rejected**: Wrong regime for a single-document tree. Worth
  reconsidering if/when we visualize the full corpus graph in a later release

### Alternative 5: Mermaid

- **Pros**: Trivial to embed, already used in docs
- **Cons**: Static rendering, no interactivity, not designed for thousands of
  nodes, no per-node click/hover
- **Why rejected**: A viewer, not a visualizer. We need interactivity

## References

- [Neo4j integration design doc](https://github.com/scub-france/Docling-Studio/blob/main/docs/design/neo4j-integration.md) §8.3
- [Issue #186 — Neo4j integration](https://github.com/scub-france/Docling-Studio/issues/186)
- [Cytoscape.js](https://js.cytoscape.org/)
- [cytoscape-dagre](https://github.com/cytoscape/cytoscape.js-dagre)
- [vis-network](https://visjs.github.io/vis-network/docs/network/)
- [Neovis.js](https://github.com/neo4j-contrib/neovis.js)
