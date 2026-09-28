import { describe, expect, it } from 'vitest'

import { analysisProgress, formatElapsed } from './progress'

const STARTED = '2026-09-28T12:00:00+00:00'
const at = (seconds: number) => Date.parse(STARTED) + seconds * 1000

function run(overrides: Partial<Parameters<typeof analysisProgress>[0]> = {}) {
  return {
    progressCurrent: null,
    progressTotal: null,
    startedAt: STARTED,
    createdAt: '2026-09-28T11:59:58+00:00',
    ...overrides,
  }
}

describe('analysisProgress', () => {
  it('shows the pages done when the conversion runs in batches', () => {
    expect(analysisProgress(run({ progressCurrent: 10, progressTotal: 25 }), at(5))).toEqual({
      kind: 'pages',
      percent: 40,
      done: 10,
      total: 25,
    })
  })

  it('starts batched progress at 0 % before the first batch ends', () => {
    expect(analysisProgress(run({ progressCurrent: 0, progressTotal: 25 }), at(5))).toEqual({
      kind: 'pages',
      percent: 0,
      done: 0,
      total: 25,
    })
  })

  it('never goes past 100 %', () => {
    const progress = analysisProgress(run({ progressCurrent: 30, progressTotal: 25 }), at(5))
    expect(progress).toMatchObject({ percent: 100, done: 25 })
  })

  it('falls back to the time elapsed without batch progress', () => {
    expect(analysisProgress(run(), at(83))).toEqual({ kind: 'elapsed', seconds: 83 })
  })

  it('counts from the creation while the analysis waits for a slot', () => {
    expect(analysisProgress(run({ startedAt: null }), at(0))).toEqual({
      kind: 'elapsed',
      seconds: 2,
    })
  })

  it('never shows a negative time when the clocks disagree', () => {
    expect(analysisProgress(run(), at(-3))).toEqual({ kind: 'elapsed', seconds: 0 })
  })
})

describe('formatElapsed', () => {
  it('writes minutes and seconds under an hour', () => {
    expect(formatElapsed(0)).toBe('0:00')
    expect(formatElapsed(83)).toBe('1:23')
    expect(formatElapsed(3599)).toBe('59:59')
  })

  it('adds the hours from there', () => {
    expect(formatElapsed(3600)).toBe('1:00:00')
    expect(formatElapsed(3725)).toBe('1:02:05')
  })
})
