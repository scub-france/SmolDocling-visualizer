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
        <div class="viewer-toolbar">
          <span class="viewer-label">{{ t('docs.preview') }}</span>
          <div class="viewer-nav">
            <button class="page-btn" :disabled="currentPage <= 1" @click="currentPage--">‹</button>
            <span
              >Page {{ currentPage }}<span v-if="doc.pageCount"> / {{ doc.pageCount }}</span></span
            >
            <button
              class="page-btn"
              :disabled="!!doc.pageCount && currentPage >= doc.pageCount"
              @click="currentPage++"
            >
              ›
            </button>
          </div>
        </div>
        <div class="viewer-stage">
          <PagePreview
            :document-id="id"
            :page="currentPage"
            :page-count="doc.pageCount ?? undefined"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import type { Document } from '../shared/types'
import { fetchDocument } from '../features/document/api'
import { useAnalysisStore } from '../features/analysis/store'
import { useCrumbs } from '../shared/breadcrumb/store'
import { truncate } from '../shared/breadcrumb/text'
import type { Crumb } from '../shared/breadcrumb/types'
import { useI18n } from '../shared/i18n'
import { ROUTES } from '../shared/routing/names'
import AnalysisProgressBar from '../features/analysis/ui/AnalysisProgressBar.vue'
import DocWorkspaceHeader from '../features/document/ui/DocWorkspaceHeader.vue'
import PagePreview from '../features/document/ui/PagePreview.vue'
import { reactToOutcome } from './DocWorkspacePage.logic'

const props = defineProps<{ id: string }>()

const { t } = useI18n()
const router = useRouter()
const analysisStore = useAnalysisStore()

const doc = ref<Document | null>(null)
const loadingDoc = ref(true)
const docError = ref<string | null>(null)
const currentPage = ref(1)
const launchError = ref<string | null>(null)

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

onMounted(async () => {
  await loadDoc()
})

watch(
  () => props.id,
  (newId, oldId) => {
    if (newId !== oldId) loadDoc()
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
  overflow: auto;
  padding: 18px 24px 32px;
}

.viewer-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 900px;
  margin: 0 auto 12px;
  color: var(--text-secondary);
  font-size: 12px;
}

.viewer-label {
  color: var(--text-muted);
  font:
    500 11px 'IBM Plex Mono',
    monospace;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.viewer-nav {
  display: flex;
  align-items: center;
  gap: 10px;
}

.page-btn {
  width: 28px;
  height: 28px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-elevated);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 18px;
}

.page-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.viewer-stage {
  max-width: 900px;
  margin: 0 auto;
}

.viewer-stage :deep(.page-preview) {
  min-height: 0;
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
