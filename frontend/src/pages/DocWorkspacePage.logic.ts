/**
 * Pure helpers for the doc workspace (#342).
 *
 * Extracted from `DocWorkspacePage.vue` so the decision taken when an
 * analysis ends can be unit-tested without a DOM environment (the frontend
 * doesn't ship `@vue/test-utils` / `happy-dom` today). Keep them
 * dependency-free (no Vue, no router, no i18n).
 */
import type { AnalysisOutcome } from '../features/analysis'

export type OutcomeReaction =
  | { kind: 'open'; analysisId: string }
  | { kind: 'error'; reason: string | null }
  | { kind: 'none' }

/**
 * What the workspace of `docId` does when an analysis run ends: open the
 * analysis it produced, or report why it failed.
 *
 * Only the workspace of the analysed document reacts. The page is reused
 * across `/docs/:id`, so a user who switched documents while the analysis
 * ran stays where they are.
 */
export function reactToOutcome(outcome: AnalysisOutcome | null, docId: string): OutcomeReaction {
  if (!outcome || outcome.documentId !== docId) return { kind: 'none' }
  if (outcome.kind === 'completed') return { kind: 'open', analysisId: outcome.analysisId }
  return { kind: 'error', reason: outcome.error }
}
