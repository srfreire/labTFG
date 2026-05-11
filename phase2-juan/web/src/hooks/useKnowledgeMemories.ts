import { useEffect, useState } from 'react'
import type { KGMemoryPage } from '../types'
import { buildQuery, fetchKnowledge, type KnowledgeFetchState } from './fetchKnowledge'

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
  const [data, setData] = useState<KGMemoryPage | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!enabled) return
    let stale = false
    const url = `/api/knowledge/memories${buildQuery({
      namespace,
      run_id: runId,
      since,
      page,
      page_size: pageSize,
    })}`

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const json = await fetchKnowledge<KGMemoryPage>(url)
        if (!stale) setData(json)
      } catch (err) {
        if (!stale) setError((err as Error).message ?? 'fetch failed')
      } finally {
        if (!stale) setLoading(false)
      }
    }
    load()

    return () => {
      stale = true
    }
  }, [namespace, runId, since, page, pageSize, enabled])

  return { data, loading, error }
}
