import { useCallback, useEffect, useState } from 'react'

export interface KnowledgeFetchState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

export interface KnowledgeFetchResult<T> extends KnowledgeFetchState<T> {
  refetch: () => void
}

export async function fetchKnowledge<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as T
}

export function buildQuery(params: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === '' || v === null) continue
    q.set(k, String(v))
  }
  const s = q.toString()
  return s ? `?${s}` : ''
}
export function useKnowledgeFetch<T>(url: string | null): KnowledgeFetchResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reqId, setReqId] = useState(0)

  const refetch = useCallback(() => setReqId(n => n + 1), [])

  useEffect(() => {
    if (url === null) {
      setData(null)
      setError(null)
      return
    }
    let stale = false

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const json = await fetchKnowledge<T>(url as string)
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
  }, [url, reqId])

  return { data, loading, error, refetch }
}
