import { useCallback, useEffect, useState } from 'react'
import type { KGSnapshot } from '../types'

interface UseKnowledgeGraphArgs {
  runId?: string
  label?: string
  enabled?: boolean
}

interface UseKnowledgeGraphResult {
  data: KGSnapshot | null
  loading: boolean
  error: string | null
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
    const params = new URLSearchParams()
    if (runId) params.set('run_id', runId)
    if (label) params.set('label', label)
    const url = `/api/knowledge/graph${params.toString() ? `?${params}` : ''}`

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(url)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const json = (await res.json()) as KGSnapshot
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
