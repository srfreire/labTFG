import type { KGMemoryPage } from '../types'
import { buildQuery, useKnowledgeFetch, type KnowledgeFetchState } from './fetchKnowledge'

interface UseKnowledgeMemoriesArgs {
  namespace?: string
  runId?: string
  since?: string
  page: number
  pageSize: number
  enabled?: boolean
}

export function useKnowledgeMemories(
  { namespace, runId, since, page, pageSize, enabled = true }: UseKnowledgeMemoriesArgs,
): KnowledgeFetchState<KGMemoryPage> {
  const url = enabled
    ? `/api/knowledge/memories${buildQuery({
        namespace,
        run_id: runId,
        since,
        page,
        page_size: pageSize,
      })}`
    : null
  const { data, loading, error } = useKnowledgeFetch<KGMemoryPage>(url)
  return { data, loading, error }
}
