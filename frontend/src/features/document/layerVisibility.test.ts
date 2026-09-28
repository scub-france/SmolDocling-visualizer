import { describe, expect, it } from 'vitest'

import { allLayersHidden, toggleAllLayers } from './layerVisibility'

const TYPES = ['section_header', 'text', 'table']

describe('allLayersHidden', () => {
  it('is false while at least one type is visible', () => {
    expect(allLayersHidden(TYPES, new Set())).toBe(false)
    expect(allLayersHidden(TYPES, new Set(['text', 'table']))).toBe(false)
  })

  it('is true once every type is hidden, however it got there', () => {
    expect(allLayersHidden(TYPES, new Set(TYPES))).toBe(true)
  })

  it('ignores hidden types the bar does not list', () => {
    expect(allLayersHidden(TYPES, new Set(['text', 'table', 'formula']))).toBe(false)
  })

  it('is false when the bar lists no type', () => {
    expect(allLayersHidden([], new Set())).toBe(false)
  })
})

describe('toggleAllLayers', () => {
  it('hides every type when all are visible', () => {
    expect(toggleAllLayers(TYPES, new Set())).toEqual(new Set(TYPES))
  })

  it('hides every type when only some are hidden', () => {
    expect(toggleAllLayers(TYPES, new Set(['text']))).toEqual(new Set(TYPES))
  })

  it('shows every type once all are hidden, dropping the per-type filter', () => {
    expect(toggleAllLayers(TYPES, new Set(TYPES))).toEqual(new Set())
  })

  it('returns a new set rather than mutating the current one', () => {
    const hidden = new Set(['text'])
    toggleAllLayers(TYPES, hidden)
    expect(hidden).toEqual(new Set(['text']))
  })
})
