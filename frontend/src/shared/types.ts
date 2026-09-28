/**
 * Canonical document lifecycle state — mirrors the backend enum
 * `DocumentLifecycleState` (see `domain/value_objects.py`).
 *
 * - `Uploaded` raw file persisted, no parse yet
 * - `Parsed`   conversion produced a document tree
 * - `Chunked`  chunker produced a draft chunkset
 * - `Ingested` chunkset has been embedded into at least one store
 * - `Stale`    chunkset edited after a successful push (per-store concept)
 * - `Failed`   a pipeline step failed; recoverable by retry
 */
export type DocumentLifecycleState =
  | 'Uploaded'
  | 'Parsed'
  | 'Chunked'
  | 'Ingested'
  | 'Stale'
  | 'Failed'

/** Per-store ingestion state for a document (#224). */
export interface DocStoreLink {
  store: string
  state: DocumentLifecycleState
  pushedAt: string | null
}

export interface Document {
  id: string
  filename: string
  contentType: string | null
  fileSize: number | null
  pageCount: number | null
  createdAt: string
  /** Canonical lifecycle state. Drives the status badge in `/docs`. */
  lifecycleState: DocumentLifecycleState
  /** ISO timestamp of the last lifecycle transition (UTC). */
  lifecycleStateAt: string | null
  /** Stores this document has been pushed to (added in E1 #203). */
  stores?: string[]
  /** Per-store state detail (#224). Present when backend returns storeLinks. */
  storeLinks?: DocStoreLink[]
}

export interface PipelineOptions {
  do_ocr?: boolean
  do_table_structure?: boolean
  table_mode?: 'accurate' | 'fast'
  do_code_enrichment?: boolean
  do_formula_enrichment?: boolean
  do_picture_classification?: boolean
  do_picture_description?: boolean
  generate_picture_images?: boolean
  generate_page_images?: boolean
  images_scale?: number
}

export type AnalysisStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'

export interface Analysis {
  id: string
  documentId: string
  documentFilename: string | null
  status: AnalysisStatus
  contentMarkdown: string | null
  contentHtml: string | null
  pagesJson: string | null
  chunksJson: string | null
  hasDocumentJson: boolean
  errorMessage: string | null
  progressCurrent: number | null
  progressTotal: number | null
  startedAt: string | null
  completedAt: string | null
  createdAt: string
}

/** An analysis without its content, as `GET /api/analyses/summaries` lists it (#354). */
export type AnalysisSummary = Pick<
  Analysis,
  | 'id'
  | 'documentId'
  | 'documentFilename'
  | 'status'
  | 'errorMessage'
  | 'progressCurrent'
  | 'progressTotal'
  | 'startedAt'
  | 'completedAt'
  | 'createdAt'
>

export interface ChunkingOptions {
  chunker_type?: 'hybrid' | 'hierarchical'
  max_tokens?: number
  merge_peers?: boolean
  repeat_table_header?: boolean
}

/**
 * Camel-case chunking options for the rechunk endpoint (#268). The
 * backend `ChunkingOptionsRequest` accepts both snake_case and camelCase
 * via `AliasChoices`; the rest of the API contract is camelCase, so the
 * new Linked/Chunk view sticks to camelCase too.
 */
export interface RechunkOptions {
  chunkerType?: 'hybrid' | 'hierarchical'
  maxTokens?: number
  mergePeers?: boolean
  repeatTableHeader?: boolean
}

export interface ChunkBbox {
  page: number
  bbox: [number, number, number, number]
}

export interface Chunk {
  text: string
  headings: string[]
  sourcePage: number | null
  tokenCount: number
  bboxes: ChunkBbox[]
  modified?: boolean
  deleted?: boolean
}

export interface PageElement {
  type: string
  bbox: [number, number, number, number]
  content: string
  level: number
  /** Docling `self_ref` — "#/texts/12", "#/tables/3", etc. Empty string for
   * items that don't have one (rare). Lets callers correlate a bbox with
   * the matching graph node without fuzzy bbox matching. */
  self_ref?: string
}

// Backend serializes with snake_case (dataclasses.asdict)
export interface Page {
  page_number: number
  width: number
  height: number
  elements: PageElement[]
}

export type ElementType =
  | 'title'
  | 'section_header'
  | 'text'
  | 'table'
  | 'picture'
  | 'list'
  | 'formula'
  | 'code'
  | 'caption'
  | 'floating'

export interface Scale {
  sx: number
  sy: number
}

export interface Rect {
  x: number
  y: number
  w: number
  h: number
}

export type Locale = 'fr' | 'en'
export type Theme = 'dark' | 'light'

// ---------------------------------------------------------------------------
// E4/E5 — Doc workspace tree + chunks (#216–#222)
// ---------------------------------------------------------------------------

/** Node in the parsed document tree returned by GET /api/documents/:id/tree */
export interface DocTreeNode {
  ref: string
  type: string
  label: string
  children: DocTreeNode[]
}

/** Source element referenced by a chunk (Docling self_ref + label). */
export interface ChunkDocItem {
  selfRef: string
  label: string
}

/** Doc-centric chunk (distinct from legacy analysis Chunk).
 *
 * `bboxes` and `docItems` were added in #264 so the Linked view can map
 * a chunk to the bboxes / elements it covers on the page preview.
 */
export interface DocChunk {
  id: string
  docId: string
  sequence: number
  text: string
  headings: string[]
  sourcePage: number | null
  tokenCount: number | null
  bboxes: ChunkBbox[]
  docItems: ChunkDocItem[]
  createdAt: string
  updatedAt: string
}

export type ChunkDiffStatus = 'added' | 'modified' | 'removed' | 'unchanged'

export interface ChunkDiff {
  chunkId: string
  status: ChunkDiffStatus
  textDiff?: string
}

export interface PushSummary {
  embeds: number
  tokens: number
}

/**
 * Frozen pair (#267) — `+ New analysis` and `+ Generate chunks` each
 * append one of these to the document's History timeline. The drawer
 * surfaces them; restore replaces the live chunkset with the version's
 * snapshot.
 */
export type DocumentVersionKind = 'analysis' | 'chunks'

export interface DocumentVersion {
  id: string
  documentId: string
  kind: DocumentVersionKind
  analysisId: string | null
  chunksSnapshotSize: number
  summary: string
  createdAt: string
}
