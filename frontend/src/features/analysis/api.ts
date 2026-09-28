import type {
  Analysis,
  AnalysisSummary,
  Chunk,
  ChunkingOptions,
  PipelineOptions,
} from '../../shared/types'
import { apiFetch } from '@/shared/api/http'

export function createAnalysis(
  documentId: string,
  pipelineOptions: PipelineOptions | null = null,
  chunkingOptions: ChunkingOptions | null = null,
): Promise<Analysis> {
  const body: Record<string, unknown> = { documentId }
  if (pipelineOptions) {
    body.pipelineOptions = pipelineOptions
  }
  if (chunkingOptions) {
    body.chunkingOptions = chunkingOptions
  }
  return apiFetch<Analysis>('/api/analyses', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function rechunkAnalysis(jobId: string, chunkingOptions: ChunkingOptions): Promise<Chunk[]> {
  return apiFetch<Chunk[]>(`/api/analyses/${jobId}/rechunk`, {
    method: 'POST',
    body: JSON.stringify({ chunkingOptions }),
  })
}

export function fetchAnalyses(): Promise<Analysis[]> {
  return apiFetch<Analysis[]>('/api/analyses')
}

/** Every analysis without its content: light enough to poll (#354). */
export function fetchAnalysisSummaries(): Promise<AnalysisSummary[]> {
  return apiFetch<AnalysisSummary[]>('/api/analyses/summaries')
}

export function fetchAnalysis(id: string): Promise<Analysis> {
  return apiFetch<Analysis>(`/api/analyses/${id}`)
}

export function deleteAnalysis(id: string): Promise<unknown> {
  return apiFetch(`/api/analyses/${id}`, { method: 'DELETE' })
}

export function fetchDocumentAnalyses(docId: string): Promise<Analysis[]> {
  return apiFetch<Analysis[]>(`/api/analyses?documentId=${encodeURIComponent(docId)}`)
}
