export interface KnowledgeFetchState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

/**
 * Fetch a knowledge-API endpoint, mapping non-OK responses (including 503)
 * to an `error` string the panel can display as a placeholder.
 */
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
