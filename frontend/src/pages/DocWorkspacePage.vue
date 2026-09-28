<template>
  <div class="workspace-page">
    <!-- Loading doc -->
    <div v-if="loadingDoc" class="workspace-loading">
      <span class="spinner" />
    </div>

    <!-- Doc error -->
    <div v-else-if="docError" class="workspace-error">
      <p>{{ docError }}</p>
      <RouterLink :to="{ name: ROUTES.DOCS_LIBRARY }" class="back-link">
        ← {{ t('workspace.backToLibrary') }}
      </RouterLink>
    </div>

    <template v-else-if="doc">
      <DocWorkspaceHeader :doc="doc">
        <template #actions>
          <p
            v-if="launchError"
            class="analyze-error"
            role="alert"
            :title="launchError"
            data-e2e="workspace-analysis-error"
          >
            {{ launchError }}
          </p>
          <button
            class="analyze-btn"
            :disabled="analysisStore.running"
            data-e2e="workspace-new-analysis"
            @click="onLaunchAnalysis"
          >
            {{ analysisStore.running ? t('newAnalysis.running') : t('newAnalysis.title') }}
          </button>
        </template>
      </DocWorkspaceHeader>
      <AnalysisProgressBar v-if="runningAnalysis" :analysis="runningAnalysis" />

      <div class="viewer-content" data-e2e="document-viewer">
        <PagePreviewWithOverlay
          v-if="pages.length"
          :document-id="id"
          :pages="pages"
          :current-page="currentPage"
          :hidden-types="NO_HIDDEN_TYPES"
          :show-labels="false"
          @update:current-page="(p) => (currentPage = p)"
        />
        <p v-else-if="pagesFailed" class="viewer-state viewer-state--error">
          {{ t('workspace.previewUnavailable') }}
        </p>
        <div v-else class="viewer-state"><span class="spinner" /></div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import type { Document, Page } from '../shared/types'
import { fetchDocument, fetchDocumentPages } from '../features/document/api'
import { useAnalysisStore } from '../features/analysis/store'
import { useCrumbs } from '../shared/breadcrumb/store'
import { truncate } from '../shared/breadcrumb/text'
import type { Crumb } from '../shared/breadcrumb/types'
import { useI18n } from '../shared/i18n'
import { ROUTES } from '../shared/routing/names'
import AnalysisProgressBar from '../features/analysis/ui/AnalysisProgressBar.vue'
import DocWorkspaceHeader from '../features/document/ui/DocWorkspaceHeader.vue'
import PagePreviewWithOverlay from '../features/document/ui/PagePreviewWithOverlay.vue'
import { reactToOutcome } from './DocWorkspacePage.logic'

// #352 — the document shows in the Parse view's viewer, without boxes.
const NO_HIDDEN_TYPES: ReadonlySet<string> = new Set()

const props = defineProps<{ id: string }>()

const { t } = useI18n()
const router = useRouter()
const analysisStore = useAnalysisStore()

const doc = ref<Document | null>(null)
const loadingDoc = ref(true)
const docError = ref<string | null>(null)
const currentPage = ref(1)
const launchError = ref<string | null>(null)
const pages = ref<Page[]>([])
const pagesFailed = ref(false)

async function onLaunchAnalysis(): Promise<void> {
  if (analysisStore.running) return
  launchError.value = null
  try {
    await analysisStore.run(props.id)
  } catch {
    // Reported through `analysisStore.lastOutcome`, like every other failure.
  }
}

// #342 — when the analysis run ends, open the analysis it produced, or say
// why it failed. `reactToOutcome` ignores runs of another document.
watch(
  () => analysisStore.lastOutcome,
  (outcome) => {
    const reaction = reactToOutcome(outcome, props.id)
    if (reaction.kind === 'open') {
      router.push({ name: ROUTES.ANALYSIS_DETAIL, params: { id: reaction.analysisId } })
    } else if (reaction.kind === 'error') {
      launchError.value = reaction.reason
        ? t('newAnalysis.failedWithReason', { reason: reaction.reason })
        : t('newAnalysis.failed')
    }
  },
)

const crumbs = computed<Crumb[]>(() => [
  { kind: 'link', label: t('breadcrumb.studio'), to: { name: ROUTES.HOME } },
  {
    kind: 'link',
    label: doc.value ? truncate(doc.value.filename, 40) : truncate(props.id, 40),
    to: { name: ROUTES.DOC_WORKSPACE, params: { id: props.id } },
  },
])
useCrumbs(crumbs)

// #344 — the analysis running on this document, whose progress shows under the header.
const runningAnalysis = computed(() => {
  const analysis = analysisStore.currentAnalysis
  return analysisStore.running && analysis?.documentId === props.id ? analysis : null
})

async function loadDoc(): Promise<void> {
  loadingDoc.value = true
  docError.value = null
  doc.value = null
  const requestedId = props.id
  try {
    const fetched = await fetchDocument(requestedId)
    if (requestedId !== props.id) return
    doc.value = fetched
  } catch (e) {
    if (requestedId !== props.id) return
    docError.value = (e as Error).message || 'Failed to load document'
  } finally {
    if (requestedId === props.id) loadingDoc.value = false
  }
}

// The viewer needs each page's size to lay out its frames before any analysis.
async function loadPages(): Promise<void> {
  pages.value = []
  pagesFailed.value = false
  const requestedId = props.id
  try {
    const fetched = await fetchDocumentPages(requestedId)
    if (requestedId !== props.id) return
    pages.value = fetched
    pagesFailed.value = fetched.length === 0
  } catch {
    if (requestedId === props.id) pagesFailed.value = true
  }
}

onMounted(async () => {
  await Promise.all([loadDoc(), loadPages()])
})

watch(
  () => props.id,
  (newId, oldId) => {
    if (newId !== oldId) loadDoc()
    if (newId !== oldId) loadPages()
    if (newId !== oldId) currentPage.value = 1
    if (newId !== oldId) launchError.value = null
  },
)
</script>

<style scoped>
.workspace-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.workspace-loading,
.workspace-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: var(--text-muted);
  font-size: 13px;
}

.workspace-error {
  color: var(--error);
}

.back-link {
  font-size: 13px;
  color: var(--text-secondary);
  text-decoration: none;
}

.back-link:hover {
  color: var(--text);
}

.viewer-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 12px 16px;
}

.viewer-state {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
}

.viewer-state--error {
  color: var(--error);
}

.analyze-btn {
  padding: 7px 12px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  background: var(--accent-muted);
  color: var(--accent);
  cursor: pointer;
  font-size: 12px;
}

.analyze-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.analyze-error {
  max-width: 360px;
  margin: 0;
  overflow: hidden;
  color: var(--error);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
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
</style>
