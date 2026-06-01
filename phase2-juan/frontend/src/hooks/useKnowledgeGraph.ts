import type { KGSnapshot } from '../types'
import { buildQuery, useKnowledgeFetch, type KnowledgeFetchResult } from './fetchKnowledge'

interface UseKnowledgeGraphArgs {
  runId?: string
  label?: string
  scope?: 'overview'
  enabled?: boolean
}

export function useKnowledgeGraph(
  { runId, label, scope, enabled = true }: UseKnowledgeGraphArgs = {},
): KnowledgeFetchResult<KGSnapshot> {
  const url = enabled
    ? `/api/knowledge/graph${buildQuery({ run_id: runId, label, scope })}`
    : null
  return useKnowledgeFetch<KGSnapshot>(url)
}
