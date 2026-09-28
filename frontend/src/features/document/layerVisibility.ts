/**
 * Pure helpers for the LAYERS bar's hide-all / show-all toggle (#343).
 *
 * Kept out of `LayersBar.vue` so they can be unit-tested without a DOM
 * environment. `types` is the list of types the bar shows a chip for.
 */

/** True when every type listed in the bar is hidden. */
export function allLayersHidden(types: readonly string[], hidden: ReadonlySet<string>): boolean {
  return types.length > 0 && types.every((type) => hidden.has(type))
}

/**
 * The hidden set after a click on the toggle: every listed type while at
 * least one is visible, none once they are all hidden. Showing resets the
 * per-type filter rather than restoring the one in place before the hide.
 */
export function toggleAllLayers(
  types: readonly string[],
  hidden: ReadonlySet<string>,
): Set<string> {
  return allLayersHidden(types, hidden) ? new Set() : new Set(types)
}
