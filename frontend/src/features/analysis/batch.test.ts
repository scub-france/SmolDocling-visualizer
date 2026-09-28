import { describe, expect, it } from 'vitest'

import type { Analysis, AnalysisSummary } from '../../shared/types'
import { hasActive, isActive, mergeSummaries } from './batch'

function analysis(overrides: Partial<Analysis> = {}): Analysis {
  return {
    id: 'a1',
    documentId: 'd1',
    documentFilename: 'doc.pdf',
    status: 'PENDING',
    contentMarkdown: null,
    contentHtml: null,
    pagesJson: null,
    chunksJson: null,
    hasDocumentJson: false,
    errorMessage: null,
    progressCurrent: null,
    progressTotal: null,
    startedAt: null,
    completedAt: null,
    createdAt: '2026-09-28T12:00:00+00:00',
    ...overrides,
  }
}

function summary(overrides: Partial<AnalysisSummary> = {}): AnalysisSummary {
  const { id, documentId, documentFilename, status, errorMessage, progressCurrent } = analysis()
  return {
    id,
    documentId,
    documentFilename,
    status,
    errorMessage,
    progressCurrent,
    progressTotal: null,
    startedAt: null,
    completedAt: null,
    createdAt: '2026-09-28T12:00:00+00:00',
    ...overrides,
  }
}

describe('isActive', () => {
  it('holds while the status can still change', () => {
    expect(isActive('PENDING')).toBe(true)
    expect(isActive('RUNNING')).toBe(true)
    expect(isActive('COMPLETED')).toBe(false)
    expect(isActive('FAILED')).toBe(false)
  })
})

describe('hasActive', () => {
  it('is true while one analysis is pending or running', () => {
    expect(hasActive([{ status: 'COMPLETED' }, { status: 'RUNNING' }])).toBe(true)
  })

  it('is false once every analysis has ended', () => {
    expect(hasActive([{ status: 'COMPLETED' }, { status: 'FAILED' }])).toBe(false)
    expect(hasActive([])).toBe(false)
  })
})

describe('mergeSummaries', () => {
  it('brings the status, progress and dates of the summaries in', () => {
    const merged = mergeSummaries(
      [analysis({ id: 'a1' })],
      [
        summary({
          id: 'a1',
          status: 'RUNNING',
          progressCurrent: 10,
          progressTotal: 25,
          startedAt: '2026-09-28T12:00:05+00:00',
        }),
      ],
    )

    expect(merged[0]).toMatchObject({
      status: 'RUNNING',
      progressCurrent: 10,
      progressTotal: 25,
      startedAt: '2026-09-28T12:00:05+00:00',
    })
  })

  it('keeps the content the analysis already carries', () => {
    const merged = mergeSummaries(
      [analysis({ id: 'a1', status: 'COMPLETED', contentMarkdown: '# Doc' })],
      [summary({ id: 'a1', status: 'COMPLETED' })],
    )

    expect(merged[0].contentMarkdown).toBe('# Doc')
  })

  it('leaves an analysis the summaries do not list as it was', () => {
    const kept = analysis({ id: 'gone', status: 'RUNNING' })

    expect(mergeSummaries([kept], [summary({ id: 'other' })])).toEqual([kept])
  })

  it('reports why an analysis failed', () => {
    const merged = mergeSummaries(
      [analysis({ id: 'a1', status: 'RUNNING' })],
      [summary({ id: 'a1', status: 'FAILED', errorMessage: 'Out of memory' })],
    )

    expect(merged[0]).toMatchObject({ status: 'FAILED', errorMessage: 'Out of memory' })
  })
})
