import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  fetchDocuments,
  fetchDocument,
  uploadDocument,
  deleteDocument,
  getPreviewUrl,
  getExportUrl,
  rechunkDocument,
  fetchDocumentTree,
  fetchDocumentPages,
} from './api'

vi.mock('../../shared/api/http', () => ({
  apiFetch: vi.fn(),
}))

import { apiFetch } from '../../shared/api/http'

describe('document API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetchDocuments calls GET /api/documents', async () => {
    const docs = [{ id: '1', filename: 'a.pdf' }]
    apiFetch.mockResolvedValue(docs)

    const result = await fetchDocuments()

    expect(apiFetch).toHaveBeenCalledWith('/api/documents')
    expect(result).toEqual(docs)
  })

  it('fetchDocument calls GET /api/documents/:id', async () => {
    const doc = { id: '42', filename: 'test.pdf' }
    apiFetch.mockResolvedValue(doc)

    const result = await fetchDocument('42')

    expect(apiFetch).toHaveBeenCalledWith('/api/documents/42')
    expect(result).toEqual(doc)
  })

  it('fetchDocumentPages maps the page sizes to pages without elements (#352)', async () => {
    apiFetch.mockResolvedValue([
      { pageNumber: 1, width: 612, height: 792 },
      { pageNumber: 2, width: 842, height: 595 },
    ])

    const result = await fetchDocumentPages('42')

    expect(apiFetch).toHaveBeenCalledWith('/api/documents/42/pages')
    expect(result).toEqual([
      { page_number: 1, width: 612, height: 792, elements: [] },
      { page_number: 2, width: 842, height: 595, elements: [] },
    ])
  })

  it('uploadDocument sends file via FormData with skipContentType', async () => {
    const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
    const response = { id: '1', filename: 'test.pdf' }
    apiFetch.mockResolvedValue(response)

    const result = await uploadDocument(file)

    expect(apiFetch).toHaveBeenCalledWith('/api/documents/upload', {
      method: 'POST',
      body: expect.any(FormData),
      skipContentType: true,
    })
    expect(result).toEqual(response)
  })

  it('deleteDocument calls DELETE /api/documents/:id', async () => {
    apiFetch.mockResolvedValue(null)

    await deleteDocument('42')

    expect(apiFetch).toHaveBeenCalledWith('/api/documents/42', { method: 'DELETE' })
  })

  it('getPreviewUrl builds correct URL with defaults', () => {
    expect(getPreviewUrl('abc')).toBe('/api/documents/abc/preview?page=1&dpi=150')
  })

  it('getPreviewUrl accepts custom page and dpi', () => {
    expect(getPreviewUrl('abc', 3, 300)).toBe('/api/documents/abc/preview?page=3&dpi=300')
  })

  it('getExportUrl exports the latest analysis by default', () => {
    expect(getExportUrl('abc', 'md')).toBe('/api/documents/abc/export?format=md')
  })

  it('getExportUrl scopes the export to an analysis when provided', () => {
    expect(getExportUrl('abc', 'json', 'analysis 1')).toBe(
      '/api/documents/abc/export?format=json&analysisId=analysis%201',
    )
  })

  it('rechunkDocument calls POST /api/documents/:id/rechunk and returns chunks', async () => {
    const chunks = [{ id: 'c1' }, { id: 'c2' }]
    apiFetch.mockResolvedValue(chunks)

    const result = await rechunkDocument('42')

    expect(apiFetch).toHaveBeenCalledWith('/api/documents/42/rechunk', {
      method: 'POST',
      body: JSON.stringify({}),
    })
    expect(result).toEqual(chunks)
  })

  it('fetchDocumentTree calls GET /api/documents/:id/tree', async () => {
    const tree = [{ ref: '#/body', type: 'body', label: 'Body', children: [] }]
    apiFetch.mockResolvedValue(tree)

    const result = await fetchDocumentTree('42')

    expect(apiFetch).toHaveBeenCalledWith('/api/documents/42/tree')
    expect(result).toEqual(tree)
  })

  it('fetchDocumentTree scopes the tree to an analysis when provided', async () => {
    apiFetch.mockResolvedValue([])

    await fetchDocumentTree('42', 'analysis 1')

    expect(apiFetch).toHaveBeenCalledWith('/api/documents/42/tree?analysisId=analysis%201')
  })
})
