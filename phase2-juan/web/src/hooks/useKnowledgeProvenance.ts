import { useEffect, useState } from 'react'
import type { KGProvenance } from '../types'
import { fetchKnowledge, type KnowledgeFetchState } from './fetchKnowledge'

export function useKnowledgeProvenance(
  nodeId: string | null,
): KnowledgeFetchState<KGProvenance> {
  const [data, setData] = useState<KGProvenance | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!nodeId) {
      setData(null)
      setError(null)
      return
    }
    let stale = false
    const url = `/api/knowledge/provenance/${encodeURIComponent(nodeId)}`

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const json = await fetchKnowledge<KGProvenance>(url)
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
  }, [nodeId])

  return { data, loading, error }
}
