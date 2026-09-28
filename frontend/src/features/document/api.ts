import type { DocChunk, Document, DocTreeNode, DocumentVersion, Page } from '../../shared/types'
import type { RechunkOptions } from '@/shared/types'
import { apiFetch } from '@/shared/api/http'

export function fetchDocuments(): Promise<Document[]> {
  return apiFetch<Document[]>('/api/documents')
}

export function fetchDocument(id: string): Promise<Document> {
  return apiFetch<Document>(`/api/documents/${id}`)
}

export async function uploadDocument(file: File): Promise<Document> {
  const formData = new FormData()
  formData.append('file', file)
  return apiFetch<Document>('/api/documents/upload', {
    method: 'POST',
    body: formData,
    skipContentType: true,
  })
}

export function deleteDocument(id: string): Promise<unknown> {
  return apiFetch(`/api/documents/${id}`, { method: 'DELETE' })
}

/** Rasterisation density of `/preview`. Also the basis the stacked preview
 * uses to reserve a page's box before its image decodes (#336). */
export const PREVIEW_DPI = 150

export function getPreviewUrl(id: string, page = 1, dpi = PREVIEW_DPI): string {
  return `/api/documents/${id}/preview?page=${page}&dpi=${dpi}`
}

/** The PDF's pages, sized but without elements, for the preview of a
 * document that may have no analysis yet (#352). */
export async function fetchDocumentPages(id: string): Promise<Page[]> {
  const sizes = await apiFetch<{ pageNumber: number; width: number; height: number }[]>(
    `/api/documents/${id}/pages`,
  )
  return sizes.map((size) => ({
    page_number: size.pageNumber,
    width: size.width,
    height: size.height,
    elements: [],
  }))
}

/** Markdown / JSON come from `analysisId` when given, else from the latest analysis. */
export function getExportUrl(
  id: string,
  format: 'pdf' | 'md' | 'json',
  analysisId?: string,
): string {
  const analysis = analysisId ? `&analysisId=${encodeURIComponent(analysisId)}` : ''
  return `/api/documents/${id}/export?format=${format}${analysis}`
}

/** Rechunk the canonical chunkset. Backend runs synchronously and returns
 * the new chunks — there is no async job to poll. */
export function rechunkDocument(id: string, options?: RechunkOptions): Promise<DocChunk[]> {
  const body = options ? { chunkingOptions: options } : {}
  return apiFetch<DocChunk[]>(`/api/documents/${id}/rechunk`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function fetchDocumentTree(id: string, analysisId?: string): Promise<DocTreeNode[]> {
  const query = analysisId ? `?analysisId=${encodeURIComponent(analysisId)}` : ''
  return apiFetch<DocTreeNode[]>(`/api/documents/${id}/tree${query}`)
}

/** Workspace History timeline (#267) — frozen pairs newest-first. */
export function fetchDocumentVersions(id: string): Promise<DocumentVersion[]> {
  return apiFetch<DocumentVersion[]>(`/api/documents/${id}/versions`)
}

/** Restore a version — overwrites the live chunkset with the snapshot. */
export function restoreDocumentVersion(docId: string, versionId: string): Promise<DocumentVersion> {
  return apiFetch<DocumentVersion>(`/api/documents/${docId}/versions/${versionId}/restore`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}
