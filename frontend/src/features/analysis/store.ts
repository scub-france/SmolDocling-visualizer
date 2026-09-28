import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Analysis, Chunk, ChunkingOptions, Page, PipelineOptions } from '../../shared/types'
import * as api from './api'
import { hasActive, mergeSummaries } from './batch'

/**
 * How the run started by `run()` ended (#342). A run fails when the analysis
 * reaches `FAILED`, but also when it cannot start, when polling gives up after
 * repeated errors, or when it times out — `error` then holds the reason.
 */
export type AnalysisOutcome =
  | { kind: 'completed'; documentId: string; analysisId: string }
  | { kind: 'failed'; documentId: string; error: string | null }

/** What `runBatch()` managed to start (#354). */
export interface BatchLaunch {
  started: Analysis[]
  failed: { documentId: string; error: string }[]
}

export const useAnalysisStore = defineStore('analysis', () => {
  const analyses = ref<Analysis[]>([])
  const currentAnalysis = ref<Analysis | null>(null)
  const running = ref(false)
  const lastOutcome = ref<AnalysisOutcome | null>(null)
  const error = ref<string | null>(null)
  const loading = ref(false)
  const pollingInterval = ref<ReturnType<typeof setInterval> | null>(null)
  const pollingTimeout = ref<ReturnType<typeof setTimeout> | null>(null)
  const MAX_POLLING_DURATION = 15 * 60 * 1000 // 15 minutes — aligned with backend timeout
  const MAX_POLL_RETRIES = 3
  const following = ref<ReturnType<typeof setInterval> | null>(null)
  const FOLLOW_INTERVAL = 3000

  const currentPages = computed<Page[]>(() => {
    if (!currentAnalysis.value?.pagesJson) return []
    try {
      return JSON.parse(currentAnalysis.value.pagesJson) as Page[]
    } catch {
      return []
    }
  })

  function clearError(): void {
    error.value = null
  }

  async function load(): Promise<void> {
    if (loading.value) return
    loading.value = true
    try {
      error.value = null
      analyses.value = await api.fetchAnalyses()
    } catch (e) {
      error.value = (e as Error).message || 'Failed to load analyses'
      console.error('Failed to load analyses', e)
    } finally {
      loading.value = false
    }
  }

  const currentChunks = computed<Chunk[]>(() => {
    if (!currentAnalysis.value?.chunksJson) return []
    try {
      return JSON.parse(currentAnalysis.value.chunksJson) as Chunk[]
    } catch {
      return []
    }
  })

  async function run(
    documentId: string,
    pipelineOptions: PipelineOptions | null = null,
    chunkingOptions: ChunkingOptions | null = null,
  ): Promise<Analysis> {
    running.value = true
    error.value = null
    try {
      const analysis = await api.createAnalysis(documentId, pipelineOptions, chunkingOptions)
      currentAnalysis.value = analysis
      analyses.value.unshift(analysis)
      startPolling(analysis.id, documentId)
      return analysis
    } catch (e) {
      error.value = (e as Error).message || 'Failed to start analysis'
      console.error('Failed to start analysis', e)
      finishRun({ kind: 'failed', documentId, error: error.value })
      throw e
    }
  }

  /** Stop tracking the current run and record how it ended. */
  function finishRun(outcome: AnalysisOutcome): void {
    stopPolling()
    running.value = false
    lastOutcome.value = outcome
  }

  function startPolling(id: string, documentId: string): void {
    stopPolling()
    let consecutiveErrors = 0
    pollingInterval.value = setInterval(async () => {
      try {
        const updated = await api.fetchAnalysis(id)
        consecutiveErrors = 0
        currentAnalysis.value = updated
        const idx = analyses.value.findIndex((a) => a.id === id)
        if (idx !== -1) analyses.value[idx] = updated
        // #349 — a queued analysis waits for its turn, however long: the
        // limit only counts once it runs, as the backend's own budget does.
        if (updated.status === 'RUNNING' && !pollingTimeout.value) armTimeout(documentId)
        if (updated.status === 'COMPLETED') {
          finishRun({ kind: 'completed', documentId, analysisId: id })
        } else if (updated.status === 'FAILED') {
          finishRun({ kind: 'failed', documentId, error: updated.errorMessage })
        }
      } catch (e) {
        consecutiveErrors++
        console.warn(`Polling error (${consecutiveErrors}/${MAX_POLL_RETRIES})`, e)
        if (consecutiveErrors >= MAX_POLL_RETRIES) {
          error.value = (e as Error).message || 'Polling error'
          console.error('Polling abandoned after retries', e)
          finishRun({ kind: 'failed', documentId, error: error.value })
        }
      }
    }, 2000)
  }

  function armTimeout(documentId: string): void {
    pollingTimeout.value = setTimeout(() => {
      if (pollingInterval.value) {
        error.value = 'Analysis timed out'
        finishRun({ kind: 'failed', documentId, error: error.value })
      }
    }, MAX_POLLING_DURATION)
  }

  function stopPolling(): void {
    if (pollingInterval.value) {
      clearInterval(pollingInterval.value)
      pollingInterval.value = null
    }
    if (pollingTimeout.value) {
      clearTimeout(pollingTimeout.value)
      pollingTimeout.value = null
    }
  }

  /**
   * Start one analysis per document with the default options, one request
   * after the other (#354). The single run of `run()` is left alone: its
   * `running` flag, `currentAnalysis` and `lastOutcome` do not move.
   */
  async function runBatch(documentIds: string[]): Promise<BatchLaunch> {
    const launch: BatchLaunch = { started: [], failed: [] }
    for (const documentId of documentIds) {
      try {
        const analysis = await api.createAnalysis(documentId)
        analyses.value.unshift(analysis)
        launch.started.push(analysis)
      } catch (e) {
        const reason = (e as Error).message || 'Failed to start analysis'
        launch.failed.push({ documentId, error: reason })
      }
    }
    return launch
  }

  /**
   * Refresh the statuses of the listed analyses every 3 s while some are
   * pending or running, and stop once none is left (#354). One summaries
   * request per tick, however many analyses run: polling each of them would
   * hit the rate limit, and the full list carries all their content.
   */
  function followActive(): void {
    if (following.value || !hasActive(analyses.value)) return
    following.value = setInterval(async () => {
      try {
        analyses.value = mergeSummaries(analyses.value, await api.fetchAnalysisSummaries())
      } catch (e) {
        console.warn('Could not refresh the analysis statuses', e)
        return
      }
      if (!hasActive(analyses.value)) stopFollowing()
    }, FOLLOW_INTERVAL)
  }

  function stopFollowing(): void {
    if (following.value) {
      clearInterval(following.value)
      following.value = null
    }
  }

  function updateChunks(chunks: Chunk[]): void {
    if (currentAnalysis.value) {
      currentAnalysis.value = {
        ...currentAnalysis.value,
        chunksJson: JSON.stringify(chunks),
      }
    }
  }

  async function select(id: string): Promise<void> {
    try {
      currentAnalysis.value = await api.fetchAnalysis(id)
    } catch (e) {
      error.value = (e as Error).message || 'Failed to load analysis'
      console.error('Failed to load analysis', e)
    }
  }

  async function remove(id: string): Promise<void> {
    try {
      await api.deleteAnalysis(id)
      analyses.value = analyses.value.filter((a) => a.id !== id)
      if (currentAnalysis.value?.id === id) currentAnalysis.value = null
    } catch (e) {
      error.value = (e as Error).message || 'Failed to delete analysis'
      console.error('Failed to delete analysis', e)
    }
  }

  return {
    analyses,
    currentAnalysis,
    currentPages,
    currentChunks,
    running,
    lastOutcome,
    error,
    loading,
    clearError,
    load,
    run,
    runBatch,
    followActive,
    stopFollowing,
    select,
    updateChunks,
    remove,
    stopPolling,
  }
})
