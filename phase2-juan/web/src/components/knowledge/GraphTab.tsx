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
import { kgLabelColor, kgNodeTitle } from '../../constants'
import type { KGEdge, KGNode, KGSnapshot } from '../../types'
import { Placeholder } from './Placeholder'

interface GraphTabProps {
  data: KGSnapshot | null
  loading: boolean
  error: string | null
  runId: string
  onRunIdChange: (v: string) => void
  onRefresh: () => void
  onNodeClick: (nodeId: string) => void
}

// Top-down layered layout: each Cypher label sits in its own horizontal
// band. Order top→bottom mirrors the dependency direction (most general
// → most specific). Unknown labels sink to the bottom so unfamiliar
// additions to the KG don't crash the layout.
const LAYER_ORDER = ['Paradigm', 'Postulate', 'Formulation', 'Model', 'Paper'] as const
const LAYER_GAP = 170
const NODE_GAP = 220

type KGNodeData = {
  kgNode: KGNode
  highlighted: boolean
}

function KnowledgeNode({ data }: NodeProps<Node<KGNodeData>>) {
  const color = kgLabelColor(data.kgNode.label)
  const title = kgNodeTitle(data.kgNode, 8)
  return (
    <div
      className="rounded-[var(--radius-sm)] px-2 py-1 text-[10px] text-text flex flex-col items-center min-w-[80px] max-w-[168px]"
      style={{
        background: 'color-mix(in srgb, var(--color-surface) 92%, transparent)',
        border: `1px solid ${color}`,
        boxShadow: data.highlighted
          ? `0 0 12px ${color}, 0 0 0 2px ${color} inset`
          : undefined,
      }}
      title={title}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <div className="text-[8px] uppercase tracking-wider leading-none" style={{ color }}>
        {data.kgNode.label}
      </div>
      <div
        className="font-medium w-full text-center mt-0.5 leading-tight break-words overflow-hidden"
        style={{
          display: '-webkit-box',
          WebkitBoxOrient: 'vertical',
          WebkitLineClamp: 2,
        }}
      >
        {title}
      </div>
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  )
}

const nodeTypes = { kg: KnowledgeNode }

function layoutNodes(
  nodes: KGNode[],
  edges: KGEdge[],
): Record<string, { x: number; y: number }> {
  const byLabel = new Map<string, KGNode[]>()
  for (const n of nodes) {
    const arr = byLabel.get(n.label) ?? []
    arr.push(n)
    byLabel.set(n.label, arr)
  }
  // LAYER_ORDER drives top→bottom; unknown labels go to the bottom.
  const labels = [...byLabel.keys()].sort((a, b) => {
    const ia = LAYER_ORDER.indexOf(a as (typeof LAYER_ORDER)[number])
    const ib = LAYER_ORDER.indexOf(b as (typeof LAYER_ORDER)[number])
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib)
  })

  // Build a neighbour-index once so we can compute barycenters cheaply.
  const neighbours = new Map<string, Set<string>>()
  for (const e of edges) {
    if (!neighbours.has(e.source)) neighbours.set(e.source, new Set())
    if (!neighbours.has(e.target)) neighbours.set(e.target, new Set())
    neighbours.get(e.source)!.add(e.target)
    neighbours.get(e.target)!.add(e.source)
  }

  // Place each layer: alphabetical seed, then a barycenter sort against
  // the previous layer to reduce edge crossings. Cheap one-pass; gives
  // a clean tree-ish look without pulling in a layout dep.
  const positions: Record<string, { x: number; y: number }> = {}
  const placedX = new Map<string, number>()
  labels.forEach((label, layerIndex) => {
    const items = (byLabel.get(label) ?? []).slice().sort((a, b) => {
      const an = String(a.props.name ?? a.id)
      const bn = String(b.props.name ?? b.id)
      return an.localeCompare(bn)
    })
    if (layerIndex > 0) {
      const score = (n: KGNode): number => {
        const ns = neighbours.get(n.id)
        if (!ns) return Number.MAX_SAFE_INTEGER
        const xs: number[] = []
        for (const id of ns) {
          const x = placedX.get(id)
          if (x !== undefined) xs.push(x)
        }
        if (xs.length === 0) return Number.MAX_SAFE_INTEGER
        return xs.reduce((s, v) => s + v, 0) / xs.length
      }
      items.sort((a, b) => score(a) - score(b))
    }
    const totalWidth = Math.max(0, items.length - 1) * NODE_GAP
    const x0 = -totalWidth / 2
    items.forEach((n, i) => {
      const x = x0 + i * NODE_GAP
      positions[n.id] = { x, y: layerIndex * LAYER_GAP }
      placedX.set(n.id, x)
    })
  })
  return positions
}

export function GraphTab({ data, loading, error, runId, onRunIdChange, onRefresh, onNodeClick }: GraphTabProps) {
  const [localRunId, setLocalRunId] = useState(runId)
  const [query, setQuery] = useState('')

  const graph = useMemo(() => {
    if (!data) {
      return {
        flowNodes: [] as Node<KGNodeData>[],
        flowEdges: [] as Edge[],
        visibleNodes: [] as KGNode[],
        visibleEdges: [] as KGEdge[],
        labelCounts: {} as Record<string, number>,
      }
    }
    const normalizedQuery = query.trim().toLowerCase()
    const visibleNodes = data.nodes.filter(n => {
      if (normalizedQuery) {
        const haystack = `${n.label} ${kgNodeTitle(n, 24)} ${Object.values(n.props).join(' ')}`.toLowerCase()
        if (!haystack.includes(normalizedQuery)) return false
      }
      return true
    })
    const visibleIds = new Set(visibleNodes.map(n => n.id))
    const visibleEdges = data.edges.filter(e => visibleIds.has(e.source) && visibleIds.has(e.target))
    const positions = layoutNodes(visibleNodes, visibleEdges)
    const highlightSet = new Set(data.current_run_node_ids)
    const labelCounts = visibleNodes.reduce<Record<string, number>>((acc, node) => {
      acc[node.label] = (acc[node.label] ?? 0) + 1
      return acc
    }, {})
    const flowNodes: Node<KGNodeData>[] = visibleNodes.map(n => ({
      id: n.id,
      type: 'kg',
      position: positions[n.id] ?? { x: 0, y: 0 },
      data: { kgNode: n, highlighted: highlightSet.has(n.id) },
    }))
    const flowEdges: Edge[] = visibleEdges.map(e => ({
      id: e.id,
      source: e.source,
      target: e.target,
      style: { stroke: 'rgba(255,255,255,0.22)', strokeWidth: 1 },
    }))
    return { flowNodes, flowEdges, visibleNodes, visibleEdges, labelCounts }
  }, [data, query])

  const totalNodes = data?.nodes.length ?? 0
  const totalEdges = data?.edges.length ?? 0

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="border-b border-border-subtle shrink-0">
        <div className="flex items-center gap-2 px-3 pt-2">
          <span className="text-[10px] uppercase tracking-wider text-text-faint">Scientific overview</span>
          <button
            type="button"
            onClick={onRefresh}
            className="ml-auto text-[10px] uppercase tracking-wider px-2 py-1 rounded-[var(--radius-sm)] border border-border-subtle text-text-muted hover:text-text"
          >
            Refresh
          </button>
        </div>
        <form
          className="grid grid-cols-[1fr_auto_auto] items-center gap-2 px-3 py-2"
          onSubmit={e => {
            e.preventDefault()
            onRunIdChange(localRunId.trim())
          }}
        >
          <input
            type="search"
            placeholder="Search label, node, equation..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="bg-transparent border border-border-subtle rounded-[var(--radius-sm)] px-2 py-1 text-[11px] text-text focus:outline-none focus:border-text-faint"
          />
          <input
            type="text"
            placeholder="run_id"
            value={localRunId}
            onChange={e => setLocalRunId(e.target.value)}
            className="w-[86px] bg-transparent border border-border-subtle rounded-[var(--radius-sm)] px-2 py-1 text-[11px] text-text focus:outline-none focus:border-text-faint"
          />
          <button
            type="submit"
            className="text-[10px] uppercase tracking-wider px-2 py-1 rounded-[var(--radius-sm)] border border-border-subtle text-text-muted hover:text-text"
          >
            Apply
          </button>
        </form>
        <div className="px-3 pb-2 flex items-center gap-2 text-[10px] text-text-faint overflow-hidden">
          <span className="shrink-0">
            {graph.visibleNodes.length}/{totalNodes} nodes · {graph.visibleEdges.length}/{totalEdges} edges
          </span>
          <div className="flex gap-1 overflow-hidden">
            {Object.entries(graph.labelCounts).slice(0, 5).map(([label, count]) => (
              <span key={label} className="px-1.5 py-0.5 rounded-[var(--radius-sm)] border border-border-subtle truncate">
                {label} {count}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-0 relative">
        {loading && (
          <div className="absolute top-2 right-2 text-[10px] text-text-faint z-10">Loading…</div>
        )}
        {error && (
          <Placeholder
            variant="absolute"
            title="Knowledge Graph unavailable"
            body="¿Está el backend corriendo? (`uvicorn simlab.api:app`)"
          />
        )}
        {!error && data && data.nodes.length === 0 && (
          <Placeholder
            variant="absolute"
            title="No knowledge stored yet"
            body="Lanza un experimento para empezar a poblar el grafo."
          />
        )}
        {!error && data && data.nodes.length > 0 && graph.visibleNodes.length === 0 && (
          <Placeholder
            variant="absolute"
            title="No nodes match this view"
            body="Limpia la búsqueda o revisa el filtro de run_id."
          />
        )}
        {!error && data && graph.visibleNodes.length > 0 && (
          <ReactFlow
            nodes={graph.flowNodes}
            edges={graph.flowEdges}
            nodeTypes={nodeTypes}
            colorMode="dark"
            fitView
            fitViewOptions={{ padding: 0.18 }}
            minZoom={0.1}
            maxZoom={3}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable
            onlyRenderVisibleElements
            proOptions={{ hideAttribution: true }}
            onNodeClick={(_e, node) => onNodeClick(node.id)}
          >
            <Background color="var(--color-border-subtle)" gap={20} />
            <Controls showInteractive={false} />
          </ReactFlow>
        )}
      </div>
    </div>
  )
}
