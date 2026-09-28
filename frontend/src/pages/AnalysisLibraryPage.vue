<template>
  <section class="analyses-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">{{ t('nav.analyses') }}</p>
        <h1>{{ t('analyses.title') }}</h1>
      </div>
      <button type="button" class="refresh-btn" :disabled="store.loading" @click="load">
        {{ store.loading ? '...' : '↻' }}
      </button>
    </header>

    <div v-if="store.loading && !store.analyses.length" class="state">
      {{ t('analyses.loading') }}
    </div>
    <div v-else-if="store.error && !store.analyses.length" class="state state--error">
      {{ t('analyses.failed') }}
    </div>
    <template v-else>
      <label class="filter-field">
        <span>{{ t('analyses.filterDocument') }}</span>
        <input
          v-model="documentFilter"
          type="search"
          :placeholder="t('analyses.filterPlaceholder')"
        />
      </label>

      <div v-if="!store.analyses.length" class="state">{{ t('analyses.empty') }}</div>
      <div v-else-if="!filteredAnalyses.length" class="state">{{ t('analyses.noMatches') }}</div>
      <div v-else class="table-wrapper">
        <table class="analysis-table">
          <thead>
            <tr>
              <th>{{ t('analyses.datetime') }}</th>
              <th>{{ t('analyses.document') }}</th>
              <th>{{ t('analyses.analysisId') }}</th>
              <th>{{ t('analyses.status') }}</th>
              <th class="actions-column">
                <span class="sr-only">{{ t('analyses.open') }}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="analysis in filteredAnalyses"
              :key="analysis.id"
              data-e2e="analysis-row"
              :data-document-id="analysis.documentId"
            >
              <td class="date-cell">
                <time :datetime="analysis.createdAt">{{ formatDate(analysis.createdAt) }}</time>
              </td>
              <td>
                <span class="truncated" :title="analysis.documentFilename || analysis.documentId">
                  {{ shorten(analysis.documentFilename || analysis.documentId, 30) }}
                </span>
              </td>
              <td>
                <span class="analysis-id" :title="analysis.id">{{ shorten(analysis.id, 10) }}</span>
              </td>
              <td>
                <span
                  class="status"
                  :class="`status--${analysis.status.toLowerCase()}`"
                  data-e2e="analysis-status"
                  :data-status="analysis.status"
                  :title="analysis.errorMessage ?? undefined"
                >
                  {{ statusLabel(analysis) }}
                </span>
              </td>
              <td class="actions-column" @click.stop>
                <div class="row-actions">
                  <RouterLink
                    :to="{ name: ROUTES.ANALYSIS_DETAIL, params: { id: analysis.id } }"
                    class="icon-button"
                    :title="t('analyses.open')"
                    :aria-label="t('analyses.open')"
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
                      <circle cx="12" cy="12" r="2.5" />
                    </svg>
                  </RouterLink>
                  <button
                    class="icon-button"
                    type="button"
                    :title="t('analyses.delete')"
                    :aria-label="t('analyses.delete')"
                    @click="deleteAnalysis(analysis.id)"
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7l1-3h4l1 3" />
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { analysisProgress } from '../features/analysis/progress'
import { useAnalysisStore } from '../features/analysis/store'
import { useI18n } from '../shared/i18n'
import { ROUTES } from '../shared/routing/names'
import type { Analysis } from '../shared/types'

const store = useAnalysisStore()
const { t } = useI18n()
const documentFilter = ref('')

const filteredAnalyses = computed(() => {
  const query = documentFilter.value.trim().toLocaleLowerCase()
  const analyses = query
    ? store.analyses.filter((analysis) =>
        (analysis.documentFilename || analysis.documentId).toLocaleLowerCase().includes(query),
      )
    : [...store.analyses]

  return analyses.sort((a, b) => {
    const documentOrder = getDate(b.createdAt) - getDate(a.createdAt)
    if (a.documentId !== b.documentId && documentOrder !== 0) return documentOrder
    return getDate(b.createdAt) - getDate(a.createdAt)
  })
})

async function load(): Promise<void> {
  await store.load()
  // #354 — pending and running analyses refresh until they end.
  store.followActive()
}

// A batched analysis reports its pages done: show the share next to RUNNING.
function statusLabel(analysis: Analysis): string {
  if (analysis.status !== 'RUNNING') return analysis.status
  const progress = analysisProgress(analysis, Date.now())
  if (progress.kind !== 'pages') return analysis.status
  return `${analysis.status} · ${t('analyses.statusPercent', { percent: progress.percent })}`
}

async function deleteAnalysis(id: string): Promise<void> {
  if (!window.confirm(t('analyses.deleteConfirm'))) return
  await store.remove(id)
}

function getDate(value: string): number {
  return Date.parse(value) || 0
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value),
  )
}

function shorten(value: string, length: number): string {
  return value.length > length ? `${value.slice(0, length)}...` : value
}

onMounted(load)
onBeforeUnmount(() => store.stopFollowing())
</script>

<style scoped>
.analyses-page {
  height: 100%;
  overflow-y: auto;
  padding: 32px clamp(20px, 5vw, 72px);
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}
.eyebrow {
  color: var(--accent);
  font:
    500 11px 'IBM Plex Mono',
    monospace;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
h1 {
  margin-top: 4px;
  font-size: 28px;
}
.refresh-btn {
  width: 36px;
  height: 36px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 20px;
}
.filter-field {
  display: grid;
  gap: 7px;
  max-width: 420px;
  margin-bottom: 20px;
  color: var(--text-muted);
  font:
    500 11px 'IBM Plex Mono',
    monospace;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.filter-field input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text);
  font: 14px inherit;
  text-transform: none;
  letter-spacing: normal;
  outline: none;
}
.filter-field input:focus {
  border-color: var(--accent);
}
.table-wrapper {
  overflow-x: auto;
  padding: 0;
}
.analysis-table {
  width: 100%;
  min-width: 680px;
  border-collapse: collapse;
  font-size: 13px;
}
.analysis-table thead {
  position: sticky;
  top: 0;
  background: var(--bg);
  z-index: 1;
}
.analysis-table th {
  padding: 10px 12px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border);
}
.analysis-table td {
  padding: 12px;
  border-bottom: 1px solid var(--border);
  color: var(--text-secondary);
}
.analysis-table tbody tr:hover {
  background: var(--bg-hover);
}
.date-cell {
  white-space: nowrap;
}
.truncated,
.analysis-id {
  display: inline-block;
  max-width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}
.truncated {
  color: var(--text);
}
.analysis-id {
  max-width: 110px;
  color: var(--text-muted);
  font:
    11px 'IBM Plex Mono',
    monospace;
}
.status {
  font:
    500 11px 'IBM Plex Mono',
    monospace;
}
.status--completed {
  color: var(--success);
}
.status--failed {
  color: var(--error);
}
.status--running,
.status--pending {
  color: var(--warning);
}
.actions-column {
  width: 96px;
  text-align: center !important;
}
.row-actions {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.icon-button {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}
.icon-button:hover {
  color: var(--accent);
}
.icon-button svg {
  width: 19px;
  height: 19px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.state {
  padding: 56px 0;
  color: var(--text-secondary);
}
.state--error {
  color: var(--error);
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
@media (max-width: 720px) {
  .analyses-page {
    padding: 24px 16px;
  }
  .analysis-table th,
  .analysis-table td {
    padding: 12px 10px;
  }
}
</style>
