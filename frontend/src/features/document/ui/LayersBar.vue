<template>
  <div class="layers-bar" data-e2e="layers-bar">
    <span class="layers-label">LAYERS</span>
    <button
      type="button"
      class="layers-toggle"
      :title="allHidden ? t('layers.showBoxesHint') : t('layers.hideBoxesHint')"
      data-e2e="layers-toggle-all"
      @click="onToggleAll"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
        <circle cx="12" cy="12" r="2.5" />
        <path v-if="!allHidden" d="M4 4l16 16" />
      </svg>
      {{ allHidden ? t('layers.showBoxes') : t('layers.hideBoxes') }}
    </button>
    <div class="layers-chips">
      <button
        v-for="entry in chipEntries"
        :key="entry.type"
        class="layer-chip"
        :class="{ dimmed: hiddenTypes.has(entry.type) }"
        :aria-pressed="!hiddenTypes.has(entry.type)"
        :data-e2e="`layer-chip-${entry.type}`"
        @click="toggle(entry.type)"
      >
        <span class="chip-dot" :style="{ background: entry.color }" />
        <span class="chip-type">{{ entry.type }}</span>
        <span class="chip-count">{{ entry.count }}</span>
      </button>
    </div>
    <div class="layers-action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * LAYERS chip row (#264).
 *
 * Externally controlled via v-model on `hiddenTypes`.
 * Renders chips in `LAYER_ORDER`, then appends any extra types found on
 * the page (in insertion order) so the bar never silently swallows a new
 * element kind. An optional `action` slot is right-aligned for the
 * tab-level primary CTA. A toggle left of the chips hides or shows every
 * type in one click (#343).
 */
import { computed } from 'vue'
import type { PageElement } from '../../../shared/types'
import { colorFor, LAYER_ORDER } from '@/shared/elementColors'
import { useI18n } from '@/shared/i18n'
import { allLayersHidden, toggleAllLayers } from '../layerVisibility'

const props = defineProps<{
  elements: readonly PageElement[]
  hiddenTypes: ReadonlySet<string>
}>()

const emit = defineEmits<{
  'update:hiddenTypes': [next: Set<string>]
}>()

const { t } = useI18n()

const chipEntries = computed(() => {
  const counts = new Map<string, number>()
  for (const type of LAYER_ORDER) counts.set(type, 0)
  for (const el of props.elements) {
    counts.set(el.type, (counts.get(el.type) ?? 0) + 1)
  }
  return Array.from(counts.entries()).map(([type, count]) => ({
    type,
    count,
    color: colorFor(type),
  }))
})

function toggle(type: string): void {
  const next = new Set(props.hiddenTypes)
  if (next.has(type)) next.delete(type)
  else next.add(type)
  emit('update:hiddenTypes', next)
}

// Derived from `hiddenTypes`, so hiding every chip by hand flips it too.
const chipTypes = computed(() => chipEntries.value.map((entry) => entry.type))
const allHidden = computed(() => allLayersHidden(chipTypes.value, props.hiddenTypes))

function onToggleAll(): void {
  emit('update:hiddenTypes', toggleAllLayers(chipTypes.value, props.hiddenTypes))
}
</script>

<style scoped>
.layers-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 20px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}

.layers-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 0.08em;
  font-family: 'IBM Plex Mono', monospace;
}

.layers-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px;
  background: none;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--text-secondary);
  cursor: pointer;
  font-family: 'IBM Plex Mono', monospace;
}

.layers-toggle:hover {
  background: var(--bg-hover);
  color: var(--text);
}

.layers-toggle svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.layers-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.layer-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 16px;
  font-size: 11px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: opacity var(--transition);
  font-family: 'IBM Plex Mono', monospace;
}

.layer-chip:hover {
  background: var(--bg-hover);
}

.layer-chip.dimmed {
  opacity: 0.35;
}

.chip-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.chip-count {
  color: var(--text-muted);
  font-size: 10px;
}

.layers-action {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
}
</style>
