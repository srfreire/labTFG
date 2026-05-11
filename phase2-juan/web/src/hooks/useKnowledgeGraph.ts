import type { KGSnapshot } from '../types'
import { buildQuery, useKnowledgeFetch, type KnowledgeFetchResult } from './fetchKnowledge'

interface UseKnowledgeGraphArgs {
  runId?: string
  label?: string
  enabled?: boolean
}

export function useKnowledgeGraph(
  { runId, label, enabled = true }: UseKnowledgeGraphArgs = {},
): KnowledgeFetchResult<KGSnapshot> {
  const url = enabled
    ? `/api/knowledge/graph${buildQuery({ run_id: runId, label })}`
    : null
  return useKnowledgeFetch<KGSnapshot>(url)
}
