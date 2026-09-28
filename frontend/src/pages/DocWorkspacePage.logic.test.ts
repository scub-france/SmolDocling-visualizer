/**
 * Tests for the doc workspace's reaction to the end of an analysis (#342).
 *
 * Pure-function tests only — the frontend doesn't ship a DOM test
 * environment, so `DocWorkspacePage.vue` is not mountable. The decision
 * lives in `DocWorkspacePage.logic.ts` and is covered here.
 */
import { describe, expect, it } from 'vitest'

import { reactToOutcome } from './DocWorkspacePage.logic'

describe('reactToOutcome', () => {
  it('opens the analysis when it completes on the document on screen', () => {
    const outcome = { kind: 'completed', documentId: 'doc-a', analysisId: 'an-1' } as const
    expect(reactToOutcome(outcome, 'doc-a')).toEqual({ kind: 'open', analysisId: 'an-1' })
  })

  it('stays put when the user switched to another document', () => {
    const outcome = { kind: 'completed', documentId: 'doc-a', analysisId: 'an-1' } as const
    expect(reactToOutcome(outcome, 'doc-b')).toEqual({ kind: 'none' })
  })

  it('reports the reason when the analysis fails on the document on screen', () => {
    const outcome = { kind: 'failed', documentId: 'doc-a', error: 'Out of memory' } as const
    expect(reactToOutcome(outcome, 'doc-a')).toEqual({ kind: 'error', reason: 'Out of memory' })
  })

  it('reports a failure without a reason as such', () => {
    const outcome = { kind: 'failed', documentId: 'doc-a', error: null } as const
    expect(reactToOutcome(outcome, 'doc-a')).toEqual({ kind: 'error', reason: null })
  })

  it('does not report a failure on another document', () => {
    const outcome = { kind: 'failed', documentId: 'doc-a', error: 'Out of memory' } as const
    expect(reactToOutcome(outcome, 'doc-b')).toEqual({ kind: 'none' })
  })

  it('does nothing before any analysis has ended', () => {
    expect(reactToOutcome(null, 'doc-a')).toEqual({ kind: 'none' })
  })
})
