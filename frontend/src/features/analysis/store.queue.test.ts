/**
 * The document page follows a queued analysis as long as it waits (#349).
 *
 * The backend may keep an analysis PENDING while the engine converts others.
 * The 15-minute limit of the page only starts once the analysis is RUNNING,
 * as the backend's own budget does.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAnalysisStore } from './store'

vi.mock('./api', () => ({
  fetchAnalyses: vi.fn(),
  fetchAnalysis: vi.fn(),
  createAnalysis: vi.fn(),
  deleteAnalysis: vi.fn(),
}))

import * as api from './api'

const MINUTE = 60 * 1000

describe('a queued analysis', () => {
  let status: string

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useFakeTimers()
    status = 'PENDING'
    api.createAnalysis.mockResolvedValue({ id: 'j1', status: 'PENDING', documentId: 'd1' })
    api.fetchAnalysis.mockImplementation(async () => ({ id: 'j1', status, documentId: 'd1' }))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('is followed for as long as it waits for its turn', async () => {
    const store = useAnalysisStore()
    await store.run('d1')

    await vi.advanceTimersByTimeAsync(30 * MINUTE)

    expect(store.running).toBe(true)
    expect(store.lastOutcome).toBeNull()
    store.stopPolling()
  })

  it('gets 15 minutes once it runs', async () => {
    const store = useAnalysisStore()
    await store.run('d1')
    await vi.advanceTimersByTimeAsync(20 * MINUTE)

    status = 'RUNNING'
    await vi.advanceTimersByTimeAsync(15 * MINUTE)
    expect(store.running).toBe(true)

    await vi.advanceTimersByTimeAsync(2000)
    expect(store.running).toBe(false)
    expect(store.lastOutcome).toEqual({
      kind: 'failed',
      documentId: 'd1',
      error: 'Analysis timed out',
    })
  })
})
