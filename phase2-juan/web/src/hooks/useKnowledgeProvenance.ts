import type { KGProvenance } from '../types'
import { useKnowledgeFetch, type KnowledgeFetchState } from './fetchKnowledge'

export function useKnowledgeProvenance(
  nodeId: string | null,
): KnowledgeFetchState<KGProvenance> {
  const url = nodeId ? `/api/knowledge/provenance/${encodeURIComponent(nodeId)}` : null
  const { data, loading, error } = useKnowledgeFetch<KGProvenance>(url)
  return { data, loading, error }
}
