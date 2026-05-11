import { useKnowledgeProvenance } from '../../hooks/useKnowledgeProvenance'
import { kgLabelColor } from '../../constants'
import type { KGNode } from '../../types'

interface ProvenanceTabProps {
  nodeId: string | null
}

export function ProvenanceTab({ nodeId }: ProvenanceTabProps) {
  const { data, loading, error } = useKnowledgeProvenance(nodeId)

  if (!nodeId) {
    return (
      <Placeholder
        title="No node selected"
        body="Selecciona un nodo en el Graph tab para ver su cadena de procedencia."
      />
    )
  }

  if (error) {
    return (
      <Placeholder
        title="Provenance unavailable"
        body="¿Está el backend levantado y Neo4j accesible?"
      />
    )
  }

  if (!data) {
    return <div className="p-4 text-[11px] text-text-faint">{loading ? 'Loading…' : '—'}</div>
  }

  return (
    <div className="flex flex-col gap-2 p-4 overflow-auto h-full">
      <NodeRow node={data.node} primary />
      {data.trail.length === 0 ? (
        <div className="text-[11px] text-text-faint italic">
          Este nodo no tiene una cadena de procedencia hasta un Paper.
        </div>
      ) : (
        data.trail.map((step, i) => (
          <div key={`${step.edge.id}-${i}`} className="flex flex-col gap-2">
            <div className="text-[10px] text-text-faint pl-3 flex items-center gap-2">
              <span className="text-text-dim">↓</span>
              <span className="uppercase tracking-wider">{step.edge.type}</span>
            </div>
            <NodeRow node={step.node} />
          </div>
        ))
      )}
    </div>
  )
}

function NodeRow({ node, primary = false }: { node: KGNode; primary?: boolean }) {
  const color = kgLabelColor(node.label)
  const title = pickTitle(node)
  const year = pickProp(node, 'year')
  return (
    <div
      className="rounded-[var(--radius-sm)] px-3 py-2"
      style={{
        background: 'var(--color-surface)',
        border: `1px solid ${color}`,
        boxShadow: primary ? `0 0 8px ${color}` : undefined,
      }}
    >
      <div className="text-[9px] uppercase tracking-wider mb-1" style={{ color }}>
        {node.label}
      </div>
      <div className="text-[12px] text-text font-medium">{title}</div>
      {year && <div className="text-[10px] text-text-muted">{year}</div>}
    </div>
  )
}

function pickTitle(node: KGNode): string {
  for (const key of ['name', 'title', 'id', 'doi']) {
    const v = node.props[key]
    if (typeof v === 'string' && v) return v
  }
  return node.id.slice(0, 12)
}

function pickProp(node: KGNode, key: string): string | null {
  const v = node.props[key]
  if (typeof v === 'string' || typeof v === 'number') return String(v)
  return null
}

function Placeholder({ title, body }: { title: string; body: string }) {
  return (
    <div className="h-full flex items-center justify-center flex-col gap-1 text-center px-6">
      <div className="text-[13px] font-medium text-text">{title}</div>
      <div className="text-[11px] text-text-muted">{body}</div>
    </div>
  )
}
