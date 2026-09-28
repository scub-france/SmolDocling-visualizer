/**
 * Pure helpers for the selection of the docs library (#354).
 *
 * Only listed documents stay selected, so the count and **Analyze** always
 * match the rows the user sees. Extracted from `DocsLibraryPage.vue` to be
 * unit-tested without a DOM; every helper returns a new set.
 */

export type SelectionState = 'none' | 'some' | 'all'

/** How much of the listed documents the selection covers. */
export function selectionState(
  selected: ReadonlySet<string>,
  listed: readonly string[],
): SelectionState {
  const count = listed.filter((id) => selected.has(id)).length
  if (count === 0) return 'none'
  return count === listed.length ? 'all' : 'some'
}

/** Select every listed document, or none once they all are. */
export function toggleListed(
  selected: ReadonlySet<string>,
  listed: readonly string[],
): Set<string> {
  return selectionState(selected, listed) === 'all' ? new Set() : new Set(listed)
}

export function toggleOne(selected: ReadonlySet<string>, id: string): Set<string> {
  const next = new Set(selected)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  return next
}

/** Drop what the filter or a deletion took off the list. */
export function keepListed(selected: ReadonlySet<string>, listed: readonly string[]): Set<string> {
  return new Set(listed.filter((id) => selected.has(id)))
}
