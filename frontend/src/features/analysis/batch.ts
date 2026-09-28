/**
 * Pure helpers to follow many analyses at once (#354).
 *
 * The analysis library refreshes the statuses of its rows from the light
 * summaries while some analyses are still pending or running. Kept out of the
 * store so the rules can be unit-tested without timers or HTTP.
 */
import type { Analysis, AnalysisStatus, AnalysisSummary } from '../../shared/types'

/** Pending or running: its status can still change. */
export function isActive(status: AnalysisStatus): boolean {
  return status === 'PENDING' || status === 'RUNNING'
}

export function hasActive(analyses: readonly Pick<Analysis, 'status'>[]): boolean {
  return analyses.some((analysis) => isActive(analysis.status))
}

/**
 * The listed analyses with the statuses, progress, errors and dates of the
 * summaries merged in. The content an analysis already carries stays, and an
 * analysis the summaries do not list keeps its row as it was.
 */
export function mergeSummaries(
  analyses: readonly Analysis[],
  summaries: readonly AnalysisSummary[],
): Analysis[] {
  const byId = new Map(summaries.map((summary) => [summary.id, summary]))
  return analyses.map((analysis) => {
    const summary = byId.get(analysis.id)
    return summary ? { ...analysis, ...summary } : analysis
  })
}
