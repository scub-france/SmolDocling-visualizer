/**
 * Progress of a running analysis, as the doc workspace shows it (#344).
 *
 * The backend reports pages done / total only for a batched conversion
 * (`BATCH_PAGE_SIZE`, local engine), after each batch. Without it there is
 * no percentage to show, only the time elapsed — never a made-up one.
 * Pure functions, unit-tested without a DOM.
 */
import type { Analysis } from '../../shared/types'

export type AnalysisProgress =
  | { kind: 'pages'; percent: number; done: number; total: number }
  | { kind: 'elapsed'; seconds: number }

export function analysisProgress(
  analysis: Pick<Analysis, 'progressCurrent' | 'progressTotal' | 'startedAt' | 'createdAt'>,
  now: number,
): AnalysisProgress {
  const total = analysis.progressTotal ?? 0
  if (total > 0) {
    const done = Math.min(Math.max(analysis.progressCurrent ?? 0, 0), total)
    return { kind: 'pages', percent: Math.round((done / total) * 100), done, total }
  }
  const start = Date.parse(analysis.startedAt ?? analysis.createdAt)
  const seconds = Number.isNaN(start) ? 0 : Math.max(0, Math.floor((now - start) / 1000))
  return { kind: 'elapsed', seconds }
}

/** `m:ss` under an hour, `h:mm:ss` from there. */
export function formatElapsed(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = String(seconds % 60).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`
}
