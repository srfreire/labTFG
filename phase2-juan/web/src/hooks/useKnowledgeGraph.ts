import { useCallback, useEffect, useState } from 'react'
import type { KGSnapshot } from '../types'
import { buildQuery, fetchKnowledge, type KnowledgeFetchState } from './fetchKnowledge'

interface UseKnowledgeGraphArgs {
  runId?: string
  label?: string
  enabled?: boolean
}

interface UseKnowledgeGraphResult extends KnowledgeFetchState<KGSnapshot> {
  refetch: () => void
}

export function useKnowledgeGraph(
  { runId, label, enabled = true }: UseKnowledgeGraphArgs = {},
): UseKnowledgeGraphResult {
  const [data, setData] = useState<KGSnapshot | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reqId, setReqId] = useState(0)

  const refetch = useCallback(() => setReqId(n => n + 1), [])

  useEffect(() => {
    if (!enabled) return
    let stale = false
    const url = `/api/knowledge/graph${buildQuery({ run_id: runId, label })}`

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const json = await fetchKnowledge<KGSnapshot>(url)
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
  }, [runId, label, enabled, reqId])

  return { data, loading, error, refetch }
}
