<template>
  <div class="library-page">
    <!-- Flash: redirected here because all workspace modes are disabled (#210) -->
    <div v-if="showFlashAllModesDisabled" class="flash flash--warning" role="alert">
      {{ t('flags.allModesDisabled') }}
    </div>

    <!-- Page header -->
    <div class="library-header">
      <h1 class="library-title">{{ t('docs.title') }}</h1>
      <RouterLink :to="{ name: ROUTES.DOCS_NEW }" class="btn-primary">
        {{ t('docs.import') }}
      </RouterLink>
    </div>

    <!-- Filter bar (#212) -->
    <div class="content-wrapper">
      <label v-if="docStore.documents.length" class="filter-field">
        <span>{{ t('docs.filterSearch') }}</span>
        <input v-model="searchInput" type="search" :placeholder="t('docs.filterSearch')" />
      </label>

      <!-- Loading skeleton -->
      <div v-if="docStore.loading" class="loading-state">
        <div class="spinner" />
      </div>

      <!-- Table (#211) -->
      <template v-else-if="docStore.documents.length">
        <!-- Batch analysis (#354) -->
        <div v-if="selected.size" class="bulk-bar" data-e2e="docs-bulk-bar">
          <span class="bulk-count">{{ t('docs.selectedCount', { n: selected.size }) }}</span>
          <button
            type="button"
            class="btn-primary"
            :disabled="launching"
            data-e2e="docs-analyze-selected"
            @click="analyzeSelected"
          >
            {{ launching ? t('docs.analyzeStarting') : t('docs.analyzeSelected') }}
          </button>
          <button
            type="button"
            class="btn-secondary"
            :disabled="launching"
            data-e2e="docs-clear-selection"
            @click="clearSelection"
          >
            {{ t('docs.clearSelection') }}
          </button>
        </div>
        <div
          v-if="launchFailures.length"
          class="flash flash--error"
          role="alert"
          data-e2e="docs-batch-failures"
        >
          <p>{{ t('docs.batchFailed') }}</p>
          <ul>
            <li v-for="failure in launchFailures" :key="failure.documentId">
              {{ filenameOf(failure.documentId) }}: {{ failure.error }}
            </li>
          </ul>
        </div>

        <div class="table-wrapper">
          <table class="doc-table" data-e2e="docs-table">
            <thead>
              <tr>
                <th class="col-select">
                  <input
                    type="checkbox"
                    class="select-box"
                    :checked="selection === 'all'"
                    :indeterminate="selection === 'some'"
                    :aria-label="t('docs.selectAll')"
                    data-e2e="docs-select-all"
                    @change="onToggleListed"
                  />
                </th>
                <th>{{ t('docs.colName') }}</th>
                <th class="col-updated">{{ t('docs.colUpdated') }}</th>
                <th class="col-download">
                  <span class="sr-only">{{ t('docs.download') }}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="doc in filteredDocs"
                :key="doc.id"
                class="doc-row"
                data-e2e="doc-row"
                :data-doc-id="doc.id"
                @click="openDoc(doc.id)"
              >
                <td class="col-select" @click.stop>
                  <input
                    type="checkbox"
                    class="select-box"
                    :checked="selected.has(doc.id)"
                    :aria-label="t('docs.selectRow', { name: doc.filename })"
                    data-e2e="doc-select"
                    @change="onToggleOne(doc.id)"
                  />
                </td>
                <td class="col-name">
                  <svg class="doc-icon" viewBox="0 0 20 20" fill="currentColor">
                    <path
                      fill-rule="evenodd"
                      d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
                      clip-rule="evenodd"
                    />
                  </svg>
                  <span class="doc-filename" :title="doc.filename">{{ doc.filename }}</span>
                </td>
                <td class="col-updated">
                  <span class="updated-time">{{ formatUpdated(doc) }}</span>
                </td>
                <td class="col-download" @click.stop>
                  <div class="row-actions">
                    <button
                      class="icon-button"
                      type="button"
                      :title="t('docs.openVisualization')"
                      :aria-label="t('docs.openVisualization')"
                      @click="openDoc(doc.id)"
                    >
                      <svg viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
                        <circle cx="12" cy="12" r="2.5" />
                      </svg>
                    </button>
                    <DownloadDropdown :doc-id="doc.id" icon-only pdf-only />
                    <button
                      class="icon-button"
                      type="button"
                      :title="t('docs.delete')"
                      :aria-label="t('docs.delete')"
                      @click="deleteDoc(doc.id, doc.filename)"
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

          <!-- Filtered empty state -->
          <div v-if="!filteredDocs.length" class="empty-state empty-state--filtered">
            <p class="empty-title">{{ t('docs.emptyFiltered') }}</p>
            <button class="btn-secondary" @click="clearFilters">{{ t('docs.filterClear') }}</button>
          </div>
        </div>
      </template>
    </div>

    <!-- Empty corpus state -->
    <div
      v-if="!docStore.loading && !docStore.documents.length"
      class="empty-state"
      data-e2e="docs-empty"
    >
      <svg
        class="empty-icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1"
      >
        <path
          d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
        />
      </svg>
      <p class="empty-title">{{ t('docs.emptyTitle') }}</p>
      <p class="empty-subtitle">{{ t('docs.emptySubtitle') }}</p>
      <RouterLink :to="{ name: ROUTES.DOCS_NEW }" class="btn-primary">
        {{ t('docs.emptyAction') }}
      </RouterLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { useDocumentStore } from '../features/document/store'
import DownloadDropdown from '../features/document/ui/DownloadDropdown.vue'
import { fetchDocumentAnalyses } from '../features/analysis/api'
import { useAnalysisStore } from '../features/analysis/store'
import type { BatchLaunch } from '../features/analysis/store'
import { keepListed, selectionState, toggleListed, toggleOne } from './DocsLibraryPage.logic'
import { useI18n } from '../shared/i18n'
import { ROUTES } from '../shared/routing/names'
import type { Document } from '../shared/types'
import { formatRelativeTime } from '../shared/format'
import { appLocale } from '../shared/appConfig'

const docStore = useDocumentStore()
const analysisStore = useAnalysisStore()
const route = useRoute()
const router = useRouter()
const { t } = useI18n()

// ---------------------------------------------------------------------------
// Flash for "no-mode-enabled" redirect (#210)
// ---------------------------------------------------------------------------
const showFlashAllModesDisabled = computed(() => route.query.reason === 'no-mode-enabled')

// ---------------------------------------------------------------------------
// Filters — init from URL query params (#212)
// ---------------------------------------------------------------------------
const searchInput = ref<string>(typeof route.query.q === 'string' ? route.query.q : '')
const debouncedSearch = ref<string>(searchInput.value)

let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(searchInput, (val) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    debouncedSearch.value = val
    syncUrl()
  }, 300)
})

function syncUrl(): void {
  const query: Record<string, string> = {}
  if (debouncedSearch.value) query.q = debouncedSearch.value
  router.replace({ query })
}

function clearFilters(): void {
  searchInput.value = ''
  debouncedSearch.value = ''
  router.replace({ query: {} })
}

// ---------------------------------------------------------------------------
// Filtered documents
// ---------------------------------------------------------------------------
const filteredDocs = computed(() => {
  const q = debouncedSearch.value.toLowerCase()
  return docStore.documents.filter((doc) => {
    if (q && !doc.filename.toLowerCase().includes(q)) return false
    return true
  })
})

// ---------------------------------------------------------------------------
// Selection and batch analysis (#354)
// ---------------------------------------------------------------------------
const selected = ref<Set<string>>(new Set())
const launching = ref(false)
const launchFailures = ref<BatchLaunch['failed']>([])

const listedIds = computed(() => filteredDocs.value.map((doc) => doc.id))
const selection = computed(() => selectionState(selected.value, listedIds.value))

// Only listed documents stay selected, so the count and Analyze match the rows shown.
watch(listedIds, (ids) => {
  selected.value = keepListed(selected.value, ids)
})

function onToggleListed(): void {
  selected.value = toggleListed(selected.value, listedIds.value)
}

function onToggleOne(id: string): void {
  selected.value = toggleOne(selected.value, id)
}

function clearSelection(): void {
  selected.value = new Set()
  launchFailures.value = []
}

function filenameOf(id: string): string {
  return docStore.documents.find((doc) => doc.id === id)?.filename ?? id
}

// Start one analysis per selected document, then follow them in the Analysis
// library. When some cannot start, stay here: those documents stay selected.
async function analyzeSelected(): Promise<void> {
  launching.value = true
  launchFailures.value = []
  try {
    const ids = listedIds.value.filter((id) => selected.value.has(id))
    const launch = await analysisStore.runBatch(ids)
    selected.value = new Set(launch.failed.map((failure) => failure.documentId))
    if (launch.failed.length) {
      launchFailures.value = launch.failed
      return
    }
    router.push({ name: ROUTES.ANALYSIS_LIBRARY })
  } finally {
    launching.value = false
  }
}

// ---------------------------------------------------------------------------
// Table helpers
// ---------------------------------------------------------------------------
function formatUpdated(doc: Document): string {
  return formatRelativeTime(doc.createdAt, appLocale.value)
}

function openDoc(id: string): void {
  router.push({ name: ROUTES.DOC_WORKSPACE, params: { id } })
}

async function deleteDoc(id: string, filename: string): Promise<void> {
  let analysisCount = 0
  try {
    analysisCount = (await fetchDocumentAnalyses(id)).length
  } catch (error) {
    console.error('Failed to load analyses before document deletion', error)
    window.alert(t('docs.deleteAnalysisLookupFailed'))
    return
  }

  if (!window.confirm(t('docs.deleteConfirm', { n: 1, name: filename, analyses: analysisCount })))
    return
  await docStore.remove(id)
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
onMounted(() => {
  docStore.load()
})
</script>

<style scoped>
.library-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  position: relative;
}

.library-header {
  padding: 32px clamp(20px, 5vw, 72px) 24px;
}
.library-title {
  font-size: 28px;
}

/* Header */
.library-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.library-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text);
}

/* Flash */
.flash {
  margin: 12px 24px 0;
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  flex-shrink: 0;
}

.flash--warning {
  color: #92400e;
  background: #fef3c7;
  border: 1px solid #fde68a;
}

/* Batch analysis (#354) */
.content-wrapper .flash {
  margin: 0 0 12px;
}
.flash--error {
  color: var(--error);
  border: 1px solid var(--error);
}
.flash--error ul {
  margin: 6px 0 0;
  padding-left: 18px;
}
.bulk-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 8px 12px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  background: var(--accent-muted);
}
.bulk-count {
  margin-right: auto;
  color: var(--text);
  font-size: 13px;
}
.col-select {
  width: 36px;
}
.select-box {
  cursor: pointer;
  accent-color: var(--accent);
}

.filter-field {
  display: grid;
  gap: 7px;
  max-width: 420px;
  margin: 0 0 20px;
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
.content-wrapper {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px clamp(20px, 5vw, 72px) 24px;
}

/* Loading */
.loading-state {
  display: flex;
  justify-content: center;
  padding: 60px;
}

.spinner {
  width: 28px;
  height: 28px;
  border: 2px solid var(--border-light);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Table */
.table-wrapper {
  overflow-x: auto;
}

.doc-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.doc-table thead {
  position: sticky;
  top: 0;
  background: var(--bg);
  z-index: 1;
}

.doc-table th {
  padding: 10px 12px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border);
}

.col-updated {
  width: 130px;
  white-space: nowrap;
}

.col-download {
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

.doc-row {
  cursor: pointer;
  transition: background var(--transition);
  border-bottom: 1px solid var(--border);
}

.doc-row:hover {
  background: var(--bg-hover);
}

.doc-table td {
  padding: 12px 12px;
  vertical-align: middle;
}

.col-name {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.doc-icon {
  width: 14px;
  height: 14px;
  color: var(--accent);
  flex-shrink: 0;
}

.doc-filename {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
  color: var(--text);
}

.updated-time {
  color: var(--text-muted);
  font-size: 12px;
  font-family: 'IBM Plex Mono', monospace;
}

/* Empty states */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 80px 24px;
  text-align: center;
}

.empty-icon {
  width: 48px;
  height: 48px;
  color: var(--text-muted);
}

.empty-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
}

.empty-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
}

.empty-state--filtered {
  padding: 40px 24px;
}

/* Buttons */
.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  font-size: 13px;
  font-weight: 500;
  color: white;
  background: var(--accent);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  text-decoration: none;
  transition: background var(--transition);
}

.btn-primary:hover {
  background: var(--accent-hover);
}

.btn-primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 7px 14px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition);
}

.btn-secondary:hover {
  background: var(--bg-hover);
  color: var(--text);
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
</style>
