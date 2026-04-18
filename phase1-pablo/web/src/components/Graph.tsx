import { useMemo, useCallback, useRef } from 'react';
import { Agrex, type AgrexNodeProps } from '@ppazosp/agrex';
import type { AgrexNode, AgrexEdge } from '@ppazosp/agrex';
import '@xyflow/react/dist/style.css';
import '@ppazosp/agrex/styles.css';
import { Search, Globe, Eye, Pencil, FlaskConical } from 'lucide-react';
import { type GraphNode, type GraphEdge } from '../types';
import FileTypeLogo from './nodes/FileTypeLogo';
import NodeHandles from './nodes/NodeHandles';

/* ── Custom renderers for node types agrex doesn't have ───── */

function SearchRenderer({ status, theme }: AgrexNodeProps) {
  const borderColor =
    status === 'running' ? theme.statusRunning
    : status === 'done' ? theme.statusDone
    : status === 'error' ? theme.statusError
    : theme.nodeBorder;

  return (
    <div
      className="w-[32px] h-[32px] rounded-full flex items-center justify-center"
      style={{
        border: `1px solid ${borderColor}`,
        background: theme.nodeFill,
        animation: status === 'running' ? 'agrex-running-ring 1.5s ease-in-out infinite' : undefined,
      }}
    >
      <NodeHandles />
      <Search size={14} style={{ color: theme.nodeIcon }} />
    </div>
  );
}

function OutputRenderer({ node, status, theme }: AgrexNodeProps) {
  const meta = node.metadata || {};
  const glow =
    status === 'done' &&
    !meta.dismissed &&
    typeof meta.currentStage === 'string' &&
    meta.currentStage.startsWith('review_');

  const borderColor =
    status === 'done' ? theme.statusDone
    : status === 'running' ? theme.statusRunning
    : status === 'error' ? theme.statusError
    : theme.nodeBorder;

  const S = 48;
  const H = Math.round((S * 2) / Math.sqrt(3));

  return (
    <div className="relative" style={{ width: S, height: H }}>
      <svg
        width={S} height={H} viewBox={`0 0 ${S} ${H}`}
        className="absolute top-0 left-0 overflow-visible"
        style={{
          filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.2))',
          ...(glow
            ? { animation: 'output-glow 2s ease-in-out infinite' }
            : status === 'running'
              ? { animation: 'agrex-running-drop 1.5s ease-in-out infinite' }
              : {}),
        }}
      >
        <path
          d="M 19.6,3.4 Q 24,1 28.4,3.4 L 42.6,11.3 Q 47,13.75 47,18.75 L 47,36.25 Q 47,41.25 42.6,43.7 L 28.4,51.6 Q 24,54 19.6,51.6 L 5.4,43.7 Q 1,41.25 1,36.25 L 1,18.75 Q 1,13.75 5.4,11.3 Z"
          fill={theme.nodeFill}
          stroke={borderColor}
          strokeWidth="1.5"
        />
      </svg>
      <div
        className="absolute inset-0 flex items-center justify-center"
        style={{ cursor: status === 'done' ? 'pointer' : 'default' }}
      >
        <NodeHandles />
        <FileTypeLogo label={node.label} size={22} />
      </div>
    </div>
  );
}

/* ── Statics (declared outside component to avoid re-creation) ── */

const NODE_RENDERERS = {
  search: SearchRenderer,
  output: OutputRenderer,
};

const TOOL_ICONS = {
  web_search: Globe,
  read_file: Eye,
  write_file: Pencil,
  run_tests: FlaskConical,
};

const THEME = {
  background: '#000',
  foreground: '#fff',
  nodeFill: '#0d0d0d',
  nodeBorder: 'rgba(255,255,255,0.15)',
  nodeIcon: 'rgba(255,255,255,0.7)',
  edgeSpawn: 'rgba(255,255,255,0.35)',
  edgeWrite: 'rgba(251,191,36,0.35)',
  edgeRead: 'rgba(56,189,248,0.35)',
  statusRunning: '#f59e0b',
  statusDone: '#22c55e',
  statusError: '#ef4444',
  fontFamily: 'var(--font-sans)',
  fontMono: 'var(--font-mono)',
};

/* ── Props (same interface as before — nothing else needs to change) ── */

interface GraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick?: (node: GraphNode) => void;
  reviewActive?: boolean;
  currentStage?: string | null;
  dismissedOutputIds?: Set<string>;
  demo?: boolean;
  sidebarCollapsed?: boolean;
}

/* ── Component ── */

export default function Graph({
  nodes,
  edges,
  onNodeClick,
  currentStage,
  dismissedOutputIds,
  demo,
  sidebarCollapsed,
}: GraphProps) {
  const nodeMapRef = useRef(new Map<string, GraphNode>());
  const prevAgrexNodesRef = useRef(new Map<string, AgrexNode>());
  const prevAgrexEdgesRef = useRef(new Map<string, AgrexEdge>());

  const { agrexNodes, agrexEdges } = useMemo(() => {
    // Derive parentId from spawn edges for nodes without parent_id
    const parentMap = new Map<string, string>();
    for (const e of edges) {
      if (!e.edge_kind || e.edge_kind === 'spawn') {
        if (!parentMap.has(e.target)) parentMap.set(e.target, e.source);
      }
    }

    const map = new Map<string, GraphNode>();
    const prevNodes = prevAgrexNodesRef.current;
    const nextNodes = new Map<string, AgrexNode>();

    const agrexNodes: AgrexNode[] = nodes.map((n) => {
      map.set(n.id, n);
      const parentId = n.parent_id || parentMap.get(n.id);
      const dismissed = dismissedOutputIds?.has(n.id) ?? false;
      const prev = prevNodes.get(n.id);
      const prevMeta = prev?.metadata as Record<string, unknown> | undefined;

      // Reuse the previous AgrexNode reference if nothing observable changed
      if (
        prev &&
        prev.type === n.kind &&
        prev.label === n.label &&
        prev.parentId === parentId &&
        prev.status === n.status &&
        prevMeta?.__raw === n.meta &&
        prevMeta?.currentStage === (currentStage ?? undefined) &&
        prevMeta?.dismissed === dismissed
      ) {
        nextNodes.set(n.id, prev);
        return prev;
      }

      const node: AgrexNode = {
        id: n.id,
        type: n.kind,
        label: n.label,
        parentId,
        status: n.status,
        metadata: {
          ...n.meta,
          __raw: n.meta,
          currentStage: currentStage ?? undefined,
          dismissed,
        },
      };
      nextNodes.set(n.id, node);
      return node;
    });
    nodeMapRef.current = map;
    prevAgrexNodesRef.current = nextNodes;

    // Only non-spawn, non-layout edges (spawn edges auto-derived from parentId)
    const prevEdges = prevAgrexEdgesRef.current;
    const nextEdges = new Map<string, AgrexEdge>();
    const agrexEdges: AgrexEdge[] = edges
      .filter((e) => e.edge_kind === 'read' || e.edge_kind === 'write')
      .map((e) => {
        const id = `${e.source}-${e.target}`;
        const prev = prevEdges.get(id);
        if (prev && prev.source === e.source && prev.target === e.target && prev.type === e.edge_kind) {
          nextEdges.set(id, prev);
          return prev;
        }
        const edge: AgrexEdge = { id, source: e.source, target: e.target, type: e.edge_kind! };
        nextEdges.set(id, edge);
        return edge;
      });
    prevAgrexEdgesRef.current = nextEdges;

    return { agrexNodes, agrexEdges };
  }, [nodes, edges, currentStage, dismissedOutputIds]);

  const handleNodeClick = useCallback(
    (agrexNode: AgrexNode) => {
      if (!onNodeClick) return;
      const original = nodeMapRef.current.get(agrexNode.id);
      if (original) onNodeClick(original);
    },
    [onNodeClick],
  );

  return (
    <Agrex
      nodes={agrexNodes}
      edges={agrexEdges}
      onNodeClick={onNodeClick ? handleNodeClick : undefined}
      nodeRenderers={NODE_RENDERERS}
      toolIcons={TOOL_ICONS}
      theme={THEME}
      className="w-full h-full"
      showControls={!demo}
      showLegend={!demo}
      showToasts={!demo}
      toastPlacement="top-left"
      toastInsets={{ left: sidebarCollapsed ? 16 : 192 }}
      showDetailPanel={false}
      fitOnUpdate={!demo}
      animateEdges
      keyboardShortcuts={!demo}
    />
  );
}
