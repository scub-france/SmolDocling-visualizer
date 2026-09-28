import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAnalysisStore } from './store'

vi.mock('./api', () => ({
  fetchAnalyses: vi.fn(),
  fetchAnalysis: vi.fn(),
  fetchAnalysisSummaries: vi.fn(),
  createAnalysis: vi.fn(),
  deleteAnalysis: vi.fn(),
}))

import * as api from './api'

describe('useAnalysisStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts with empty state', () => {
    const store = useAnalysisStore()
    expect(store.analyses).toEqual([])
    expect(store.currentAnalysis).toBeNull()
    expect(store.running).toBe(false)
  })

  it('currentPages parses pagesJson from current analysis', () => {
    const store = useAnalysisStore()
    store.currentAnalysis = {
      pagesJson: JSON.stringify([{ pageNumber: 1, width: 612, height: 792 }]),
    }
    expect(store.currentPages).toEqual([{ pageNumber: 1, width: 612, height: 792 }])
  })

  it('currentPages returns [] when no current analysis', () => {
    const store = useAnalysisStore()
    expect(store.currentPages).toEqual([])
  })

  it('currentPages returns [] on invalid JSON', () => {
    const store = useAnalysisStore()
    store.currentAnalysis = { pagesJson: 'not json' }
    expect(store.currentPages).toEqual([])
  })

  it('load() fetches analyses', async () => {
    const data = [{ id: '1', status: 'COMPLETED' }]
    api.fetchAnalyses.mockResolvedValue(data)

    const store = useAnalysisStore()
    await store.load()

    expect(store.analyses).toEqual(data)
  })

  it('run() creates analysis, sets current, and starts polling', async () => {
    const job = { id: 'j1', status: 'PENDING', documentId: 'd1' }
    api.createAnalysis.mockResolvedValue(job)
    api.fetchAnalysis.mockResolvedValue({ ...job, status: 'COMPLETED' })

    const store = useAnalysisStore()
    const result = await store.run('d1')

    expect(result).toEqual(job)
    expect(store.currentAnalysis).toEqual(job)
    expect(store.analyses[0]).toEqual(job)
    expect(store.running).toBe(true)
    expect(api.createAnalysis).toHaveBeenCalledWith('d1', null, null)

    // Advance timer to trigger polling
    await vi.advanceTimersByTimeAsync(2000)

    expect(api.fetchAnalysis).toHaveBeenCalledWith('j1')
    expect(store.running).toBe(false) // COMPLETED stops polling

    store.stopPolling()
  })

  it('run() forwards pipeline options to API', async () => {
    const job = { id: 'j2', status: 'PENDING', documentId: 'd1' }
    api.createAnalysis.mockResolvedValue(job)
    api.fetchAnalysis.mockResolvedValue({ ...job, status: 'COMPLETED' })

    const store = useAnalysisStore()
    const options = { do_ocr: false, table_mode: 'fast' }
    await store.run('d1', options)

    expect(api.createAnalysis).toHaveBeenCalledWith('d1', options, null)

    store.stopPolling()
  })

  it('run() resets running on error', async () => {
    api.createAnalysis.mockRejectedValue(new Error('fail'))
    vi.spyOn(console, 'error').mockImplementation(() => {})

    const store = useAnalysisStore()
    await expect(store.run('d1')).rejects.toThrow('fail')

    expect(store.running).toBe(false)
  })

  it('select() fetches and sets current analysis', async () => {
    const job = { id: '42', status: 'COMPLETED' }
    api.fetchAnalysis.mockResolvedValue(job)

    const store = useAnalysisStore()
    await store.select('42')

    expect(store.currentAnalysis).toEqual(job)
  })

  it('remove() deletes and removes from list', async () => {
    api.deleteAnalysis.mockResolvedValue(null)

    const store = useAnalysisStore()
    store.analyses = [{ id: '1' }, { id: '2' }]
    store.currentAnalysis = { id: '1' }

    await store.remove('1')

    expect(store.analyses).toEqual([{ id: '2' }])
    expect(store.currentAnalysis).toBeNull()
  })

  it('remove() keeps currentAnalysis if different id', async () => {
    api.deleteAnalysis.mockResolvedValue(null)

    const store = useAnalysisStore()
    store.analyses = [{ id: '1' }, { id: '2' }]
    store.currentAnalysis = { id: '2' }

    await store.remove('1')

    expect(store.currentAnalysis).toEqual({ id: '2' })
  })

  it('polling stops on FAILED status', async () => {
    const job = { id: 'j1', status: 'PENDING', documentId: 'd1' }
    api.createAnalysis.mockResolvedValue(job)
    api.fetchAnalysis.mockResolvedValue({ ...job, status: 'FAILED', errorMessage: 'oops' })

    const store = useAnalysisStore()
    await store.run('d1')

    await vi.advanceTimersByTimeAsync(2000)

    expect(store.running).toBe(false)
    expect(store.currentAnalysis.status).toBe('FAILED')
  })

  it('polling retries on transient errors and stops after MAX_POLL_RETRIES', async () => {
    const job = { id: 'j1', status: 'PENDING', documentId: 'd1' }
    api.createAnalysis.mockResolvedValue(job)
    api.fetchAnalysis.mockRejectedValue(new Error('network'))
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})

    const store = useAnalysisStore()
    await store.run('d1')

    // First two errors: still polling
    await vi.advanceTimersByTimeAsync(2000)
    expect(store.running).toBe(true)
    await vi.advanceTimersByTimeAsync(2000)
    expect(store.running).toBe(true)

    // Third error: stops polling
    await vi.advanceTimersByTimeAsync(2000)
    expect(store.running).toBe(false)
  })

  it('polling resets error count on successful fetch', async () => {
    const job = { id: 'j1', status: 'PENDING', documentId: 'd1' }
    api.createAnalysis.mockResolvedValue(job)
    vi.spyOn(console, 'warn').mockImplementation(() => {})

    // Fail once, succeed, fail once — should NOT stop polling
    api.fetchAnalysis
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce({ ...job, status: 'RUNNING' })
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce({ ...job, status: 'COMPLETED' })

    const store = useAnalysisStore()
    await store.run('d1')

    await vi.advanceTimersByTimeAsync(2000) // error 1
    expect(store.running).toBe(true)
    await vi.advanceTimersByTimeAsync(2000) // success — resets counter
    expect(store.running).toBe(true)
    await vi.advanceTimersByTimeAsync(2000) // error 1 again
    expect(store.running).toBe(true)
    await vi.advanceTimersByTimeAsync(2000) // success — COMPLETED
    expect(store.running).toBe(false)
  })

  // #342 — the doc workspace reacts to how a run ends, whatever ended it.
  it('run() records a completed outcome once the analysis completes', async () => {
    const job = { id: 'j1', status: 'PENDING', documentId: 'd1' }
    api.createAnalysis.mockResolvedValue(job)
    api.fetchAnalysis.mockResolvedValue({ ...job, status: 'COMPLETED' })

    const store = useAnalysisStore()
    await store.run('d1')
    expect(store.lastOutcome).toBeNull()

    await vi.advanceTimersByTimeAsync(2000)

    expect(store.lastOutcome).toEqual({ kind: 'completed', documentId: 'd1', analysisId: 'j1' })
  })

  it('run() records the error message when the analysis fails', async () => {
    const job = { id: 'j1', status: 'PENDING', documentId: 'd1' }
    api.createAnalysis.mockResolvedValue(job)
    api.fetchAnalysis.mockResolvedValue({ ...job, status: 'FAILED', errorMessage: 'oops' })

    const store = useAnalysisStore()
    await store.run('d1')
    await vi.advanceTimersByTimeAsync(2000)

    expect(store.lastOutcome).toEqual({ kind: 'failed', documentId: 'd1', error: 'oops' })
  })

  it('run() records a failed outcome when polling gives up', async () => {
    const job = { id: 'j1', status: 'PENDING', documentId: 'd1' }
    api.createAnalysis.mockResolvedValue(job)
    api.fetchAnalysis.mockRejectedValue(new Error('network'))
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})

    const store = useAnalysisStore()
    await store.run('d1')
    await vi.advanceTimersByTimeAsync(3 * 2000)

    expect(store.lastOutcome).toEqual({ kind: 'failed', documentId: 'd1', error: 'network' })
  })

  it('run() records a failed outcome when the analysis times out', async () => {
    const job = { id: 'j1', status: 'PENDING', documentId: 'd1' }
    api.createAnalysis.mockResolvedValue(job)
    api.fetchAnalysis.mockResolvedValue({ ...job, status: 'RUNNING' })

    const store = useAnalysisStore()
    await store.run('d1')
    // The 15 minutes start at the first poll that sees it RUNNING (#349).
    await vi.advanceTimersByTimeAsync(15 * 60 * 1000 + 2000)

    expect(store.running).toBe(false)
    expect(store.lastOutcome).toEqual({
      kind: 'failed',
      documentId: 'd1',
      error: 'Analysis timed out',
    })
  })

  it('run() records a failed outcome when the analysis cannot start', async () => {
    api.createAnalysis.mockRejectedValue(new Error('fail'))
    vi.spyOn(console, 'error').mockImplementation(() => {})

    const store = useAnalysisStore()
    await expect(store.run('d1')).rejects.toThrow('fail')

    expect(store.lastOutcome).toEqual({ kind: 'failed', documentId: 'd1', error: 'fail' })
  })

  // #354 — batch analysis: start many, follow them with one light request.
  it('runBatch() starts one analysis per document and reports those that could not start', async () => {
    api.createAnalysis
      .mockResolvedValueOnce({ id: 'a1', status: 'PENDING', documentId: 'd1' })
      .mockRejectedValueOnce(new Error('Document not found'))
      .mockResolvedValueOnce({ id: 'a3', status: 'PENDING', documentId: 'd3' })

    const store = useAnalysisStore()
    const launch = await store.runBatch(['d1', 'd2', 'd3'])

    expect(api.createAnalysis.mock.calls.map((call) => call[0])).toEqual(['d1', 'd2', 'd3'])
    expect(launch.started.map((a) => a.id)).toEqual(['a1', 'a3'])
    expect(launch.failed).toEqual([{ documentId: 'd2', error: 'Document not found' }])
    expect(store.analyses.map((a) => a.id)).toEqual(['a3', 'a1'])
  })

  it('runBatch() leaves the single run of the document page alone', async () => {
    api.createAnalysis.mockResolvedValue({ id: 'a1', status: 'PENDING', documentId: 'd1' })

    const store = useAnalysisStore()
    await store.runBatch(['d1'])

    expect(store.running).toBe(false)
    expect(store.currentAnalysis).toBeNull()
    expect(store.lastOutcome).toBeNull()
  })

  it('followActive() refreshes the statuses until no analysis is active', async () => {
    const store = useAnalysisStore()
    store.analyses = [
      { id: 'a1', status: 'RUNNING', documentId: 'd1', contentMarkdown: null },
      { id: 'a2', status: 'COMPLETED', documentId: 'd2', contentMarkdown: '# Done' },
    ]
    api.fetchAnalysisSummaries
      .mockResolvedValueOnce([{ id: 'a1', status: 'RUNNING', progressCurrent: 10 }])
      .mockResolvedValueOnce([{ id: 'a1', status: 'COMPLETED' }])

    store.followActive()
    await vi.advanceTimersByTimeAsync(3000)
    expect(store.analyses[0]).toMatchObject({ status: 'RUNNING', progressCurrent: 10 })

    await vi.advanceTimersByTimeAsync(3000)
    expect(store.analyses[0].status).toBe('COMPLETED')
    expect(store.analyses[1].contentMarkdown).toBe('# Done')

    await vi.advanceTimersByTimeAsync(9000)
    expect(api.fetchAnalysisSummaries).toHaveBeenCalledTimes(2)
  })

  it('followActive() does not poll when nothing is active', async () => {
    const store = useAnalysisStore()
    store.analyses = [{ id: 'a1', status: 'COMPLETED', documentId: 'd1' }]

    store.followActive()
    await vi.advanceTimersByTimeAsync(9000)

    expect(api.fetchAnalysisSummaries).not.toHaveBeenCalled()
  })

  it('stopFollowing() stops the refresh when the library closes', async () => {
    const store = useAnalysisStore()
    store.analyses = [{ id: 'a1', status: 'PENDING', documentId: 'd1' }]
    api.fetchAnalysisSummaries.mockResolvedValue([{ id: 'a1', status: 'PENDING' }])

    store.followActive()
    await vi.advanceTimersByTimeAsync(3000)
    store.stopFollowing()
    await vi.advanceTimersByTimeAsync(9000)

    expect(api.fetchAnalysisSummaries).toHaveBeenCalledTimes(1)
  })

  it('followActive() keeps following after a failed refresh', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const store = useAnalysisStore()
    store.analyses = [{ id: 'a1', status: 'RUNNING', documentId: 'd1' }]
    api.fetchAnalysisSummaries
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce([{ id: 'a1', status: 'COMPLETED' }])

    store.followActive()
    await vi.advanceTimersByTimeAsync(6000)

    expect(store.analyses[0].status).toBe('COMPLETED')
  })
})
