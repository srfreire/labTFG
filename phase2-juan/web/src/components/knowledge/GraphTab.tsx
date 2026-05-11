import { useMemo, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  forceCenter,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from 'd3-force'
import { kgLabelColor } from '../../constants'
import type { KGEdge, KGNode, KGSnapshot } from '../../types'

interface GraphTabProps {
  data: KGSnapshot | null
  loading: boolean
  error: string | null
  runId: string
  onRunIdChange: (v: string) => void
  onRefresh: () => void
}

const LAYOUT_WIDTH = 700
const LAYOUT_HEIGHT = 500

interface SimNode extends SimulationNodeDatum {
  id: string
  kgNode: KGNode
}

type KGNodeData = {
  kgNode: KGNode
  highlighted: boolean
}

function KnowledgeNode({ data }: NodeProps<Node<KGNodeData>>) {
  const color = kgLabelColor(data.kgNode.label)
  const title = pickTitle(data.kgNode)
  return (
    <div
      className="rounded-[var(--radius-sm)] px-2 py-1 text-[10px] text-text flex flex-col items-center min-w-[80px] max-w-[140px]"
      style={{
        background: 'var(--color-surface)',
        border: `1px solid ${color}`,
        boxShadow: data.highlighted
          ? `0 0 12px ${color}, 0 0 0 2px ${color} inset`
          : undefined,
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <div className="text-[8px] uppercase tracking-wider" style={{ color }}>
        {data.kgNode.label}
      </div>
      <div className="font-medium truncate w-full text-center">{title}</div>
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  )
}

const nodeTypes = { kg: KnowledgeNode }

function pickTitle(node: KGNode): string {
  const props = node.props || {}
  for (const key of ['name', 'title', 'id', 'doi']) {
    const v = props[key]
    if (typeof v === 'string' && v) return v
  }
  return node.id.slice(0, 8)
}

function layoutNodes(
  nodes: KGNode[],
  edges: KGEdge[],
): Record<string, { x: number; y: number }> {
  const simNodes: SimNode[] = nodes.map(n => ({ id: n.id, kgNode: n }))
  const simLinks: SimulationLinkDatum<SimNode>[] = edges
    .filter(e => nodes.some(n => n.id === e.source) && nodes.some(n => n.id === e.target))
    .map(e => ({ source: e.source, target: e.target }))

  const sim = forceSimulation(simNodes)
    .force('link', forceLink<SimNode, SimulationLinkDatum<SimNode>>(simLinks).id(d => d.id).distance(120))
    .force('charge', forceManyBody().strength(-300))
    .force('center', forceCenter(LAYOUT_WIDTH / 2, LAYOUT_HEIGHT / 2))
    .stop()

  for (let i = 0; i < 300; i++) sim.tick()

  const positions: Record<string, { x: number; y: number }> = {}
  for (const n of simNodes) {
    positions[n.id] = { x: n.x ?? 0, y: n.y ?? 0 }
  }
  return positions
}

export function GraphTab({ data, loading, error, runId, onRunIdChange, onRefresh }: GraphTabProps) {
  const [localRunId, setLocalRunId] = useState(runId)

  const { flowNodes, flowEdges } = useMemo(() => {
    if (!data) return { flowNodes: [] as Node<KGNodeData>[], flowEdges: [] as Edge[] }
    const positions = layoutNodes(data.nodes, data.edges)
    const highlightSet = new Set(data.current_run_node_ids)
    const flowNodes: Node<KGNodeData>[] = data.nodes.map(n => ({
      id: n.id,
      type: 'kg',
      position: positions[n.id] ?? { x: 0, y: 0 },
      data: { kgNode: n, highlighted: highlightSet.has(n.id) },
    }))
    const flowEdges: Edge[] = data.edges.map(e => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.type,
      style: { stroke: 'var(--color-border)', strokeWidth: 1 },
      labelStyle: { fontSize: 8, fill: 'var(--color-text-faint)' },
    }))
    return { flowNodes, flowEdges }
  }, [data])

  return (
    <div className="flex flex-col h-full min-h-0">
      <form
        className="flex items-center gap-2 px-3 py-2 border-b border-border-subtle shrink-0"
        onSubmit={e => {
          e.preventDefault()
          onRunIdChange(localRunId.trim())
        }}
      >
        <input
          type="text"
          placeholder="run_id (UUID) — highlight"
          value={localRunId}
          onChange={e => setLocalRunId(e.target.value)}
          className="flex-1 bg-transparent border border-border-subtle rounded-[var(--radius-sm)] px-2 py-1 text-[11px] text-text focus:outline-none focus:border-text-faint"
        />
        <button
          type="submit"
          className="text-[10px] uppercase tracking-wider px-2 py-1 rounded-[var(--radius-sm)] border border-border-subtle text-text-muted hover:text-text"
        >
          Apply
        </button>
        <button
          type="button"
          onClick={onRefresh}
          className="text-[10px] uppercase tracking-wider px-2 py-1 rounded-[var(--radius-sm)] border border-border-subtle text-text-muted hover:text-text"
        >
          Refresh
        </button>
      </form>

      <div className="flex-1 min-h-0 relative">
        {loading && (
          <div className="absolute top-2 right-2 text-[10px] text-text-faint z-10">Loading…</div>
        )}
        {error && (
          <Placeholder
            title="Knowledge Graph unavailable"
            body="¿Está el backend corriendo? (`uvicorn simlab.api:app`)"
          />
        )}
        {!error && data && data.nodes.length === 0 && (
          <Placeholder
            title="No knowledge stored yet"
            body="Lanza un experimento para empezar a poblar el grafo."
          />
        )}
        {!error && data && data.nodes.length > 0 && (
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            nodeTypes={nodeTypes}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background color="var(--color-border-subtle)" gap={20} />
            <Controls showInteractive={false} />
          </ReactFlow>
        )}
      </div>
    </div>
  )
}

function Placeholder({ title, body }: { title: string; body: string }) {
  return (
    <div className="absolute inset-0 flex items-center justify-center flex-col gap-1 text-center px-6 pointer-events-none">
      <div className="text-[13px] font-medium text-text">{title}</div>
      <div className="text-[11px] text-text-muted">{body}</div>
    </div>
  )
}
