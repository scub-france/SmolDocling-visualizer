<template>
  <div class="analysis-progress" data-e2e="analysis-progress">
    <div
      v-if="progress.kind === 'pages'"
      class="progress-track"
      role="progressbar"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-valuenow="progress.percent"
      :aria-label="label"
    >
      <div class="progress-fill" :style="{ width: `${progress.percent}%` }" />
    </div>
    <span v-else class="progress-spinner" aria-hidden="true" />
    <span class="progress-label">{{ label }}</span>
  </div>
</template>

<script setup lang="ts">
/**
 * Progress strip of a running analysis (#344): pages done when the backend
 * converts in batches, the time elapsed otherwise.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { Analysis } from '../../../shared/types'
import { useI18n } from '../../../shared/i18n'
import { analysisProgress, formatElapsed } from '../progress'

const props = defineProps<{ analysis: Analysis }>()

const { t } = useI18n()
const now = ref(Date.now())
let clock: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  clock = setInterval(() => (now.value = Date.now()), 1000)
})
onUnmounted(() => {
  if (clock) clearInterval(clock)
})

const progress = computed(() => analysisProgress(props.analysis, now.value))
const label = computed(() => {
  const p = progress.value
  return p.kind === 'pages'
    ? t('analyses.progressPages', { percent: p.percent, done: p.done, total: p.total })
    : t('analyses.progressElapsed', { elapsed: formatElapsed(p.seconds) })
})
</script>

<style scoped>
.analysis-progress {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
  color: var(--text-secondary);
  font-size: 12px;
}

.progress-track {
  flex: 0 0 160px;
  height: 4px;
  overflow: hidden;
  border-radius: 2px;
  background: var(--border);
}

.progress-fill {
  height: 100%;
  background: var(--accent);
  transition: width 0.4s ease;
}

.progress-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid var(--border-light);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.progress-label {
  font-family: 'IBM Plex Mono', monospace;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
