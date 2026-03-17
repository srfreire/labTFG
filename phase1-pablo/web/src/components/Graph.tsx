import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ReactFlow,
  type Node,
  type Edge,
  type NodeTypes,
  type ReactFlowInstance,
  useNodesState,
  useEdgesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Facehash } from 'facehash';
import { AgentNode, SubAgentNode, ToolNode, FileNode, SearchNode, OutputNode } from './nodes';
import { colorForName } from './nodes/faceColors';
import { type GraphNode, type GraphEdge, AGENT_COLORS } from '../types';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const nodeTypes: NodeTypes = {
  agent: AgentNode,
  sub_agent: SubAgentNode,
  tool: ToolNode,
  file: FileNode,
  search: SearchNode,
  output: OutputNode,
};

const NODE_SIZES: Record<string, { width: number; height: number }> = {
  agent: { width: 80, height: 80 },
  sub_agent: { width: 56, height: 56 },
  tool: { width: 36, height: 36 },
  file: { width: 56, height: 64 },
  search: { width: 32, height: 32 },
  output: { width: 48, height: 48 },
};

const KIND_LABELS: Record<string, string> = {
  agent: 'AGENT',
  sub_agent: 'SUB-AGENT',
  tool: 'TOOL',
  file: 'FILE',
  search: 'SEARCH',
  output: 'OUTPUT',
};

/* ------------------------------------------------------------------ */
/*  Outward radial placement                                           */
/* ------------------------------------------------------------------ */

const GOLDEN_ANGLE = 2.399963229728653;
const BASE_R = 140;
const MIN_DIST = 100;

function placeNode(
  parentPos: { x: number; y: number } | undefined,
  placed: Map<string, { x: number; y: number }>,
  childIndex: number,
): { x: number; y: number } {
  if (!parentPos) return { x: 0, y: 0 };

  const parentDist = Math.hypot(parentPos.x, parentPos.y);

  for (let ring = 1; ring <= 10; ring++) {
    const r = BASE_R * ring;
    const slots = Math.max(6, Math.floor((2 * Math.PI * r) / MIN_DIST));
    for (let s = 0; s < slots; s++) {
      const angle = childIndex * GOLDEN_ANGLE + (s * 2 * Math.PI) / slots;
      const x = parentPos.x + r * Math.cos(angle);
      const y = parentPos.y + r * Math.sin(angle);

      // Must be further from root than parent — graph always expands
      if (Math.hypot(x, y) <= parentDist + 20) continue;

      let free = true;
      for (const [, pos] of placed) {
        if (Math.hypot(pos.x - x, pos.y - y) < MIN_DIST) {
          free = false;
          break;
        }
      }
      if (free) return { x, y };
    }
  }

  // Fallback: extend outward along root→parent direction
  const angle = Math.atan2(parentPos.y || 1, parentPos.x || 1);
  return {
    x: parentPos.x + BASE_R * Math.cos(angle),
    y: parentPos.y + BASE_R * Math.sin(angle),
  };
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

function LegendFace({ name, size = 20 }: { name: string; size?: number }) {
  return (
    <div style={{ overflow: 'hidden', lineHeight: 0, flexShrink: 0 }}>
      <Facehash
        name={name}
        size={size}
        colors={[colorForName(name)]}
        variant="solid"
        intensity3d="none"
        interactive={false}
        showInitial={false}
        style={{ display: 'block' }}
      />
    </div>
  );
}

function LegendIcon({ d, label }: { d: string; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.7)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d={d} />
      </svg>
      <span>{label}</span>
    </div>
  );
}

interface GraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick?: (node: GraphNode) => void;
  reviewActive?: boolean;
}

export default function Graph({ nodes, edges, onNodeClick, reviewActive }: GraphProps) {
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<Node>([]);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const graphNodesRef = useRef<GraphNode[]>(nodes);
  const rfRef = useRef<ReactFlowInstance | null>(null);

  const posRef = useRef(new Map<string, { x: number; y: number }>());
  const childCountRef = useRef(new Map<string, number>());
  const firstFitDone = useRef(false);

  // Toast state
  const [toast, setToast] = useState<{ kind: string; label: string } | null>(
    null,
  );
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    graphNodesRef.current = nodes;
  }, [nodes]);

  useEffect(() => {
    // ── Reset ──
    if (nodes.length === 0) {
      posRef.current.clear();
      childCountRef.current.clear();
      firstFitDone.current = false;
      setFlowNodes([]);
      setFlowEdges([]);
      return;
    }

    // ── Parent lookup (read edges excluded — they don't determine layout) ──
    const parentOf = new Map<string, string>();
    for (const e of edges) {
      if (e.edge_kind === 'read') continue;
      if (!parentOf.has(e.target)) parentOf.set(e.target, e.source);
    }

    // ── Place new nodes ──
    let newest: GraphNode | null = null;
    for (const nd of nodes) {
      if (posRef.current.has(nd.id)) continue;

      const pid = parentOf.get(nd.id);
      if (pid && !posRef.current.has(pid) && posRef.current.size > 0) continue;
      if (!pid && posRef.current.size > 0) continue;

      const parentPos = pid ? posRef.current.get(pid) : undefined;
      const ci = pid ? (childCountRef.current.get(pid) ?? 0) : 0;
      if (pid) childCountRef.current.set(pid, ci + 1);

      posRef.current.set(nd.id, placeNode(parentPos, posRef.current, ci));
      newest = nd;
    }

    // ── Flow nodes ──
    setFlowNodes(
      nodes
        .filter((n) => posRef.current.has(n.id))
        .map((n) => ({
          id: n.id,
          type: n.kind,
          data: {
            label: n.label,
            status: n.status,
            color: AGENT_COLORS[n.label.toLowerCase()] || '#fff',
            ...n.meta,
          },
          position: posRef.current.get(n.id)!,
        })),
    );

    // ── Flow edges (center-to-center, straight lines) ──
    setFlowEdges(
      edges
        .filter(
          (e) => posRef.current.has(e.source) && posRef.current.has(e.target),
        )
        .map((e) => {
          const kind = e.edge_kind ?? 'spawn';
          return {
            id: `${e.source}-${e.target}`,
            source: e.source,
            target: e.target,
            sourceHandle: 'center-out',
            targetHandle: 'center-in',
            type: 'straight' as const,
            animated: kind !== 'write',
            style:
              kind === 'write'
                ? { stroke: 'rgba(251,191,36,0.35)', strokeWidth: 1.5 }
                : kind === 'read'
                ? { stroke: 'rgba(56,189,248,0.35)', strokeWidth: 1.5 }
                : { stroke: 'rgba(255,255,255,0.15)' },
          };
        }),
    );

    // ── Toast ──
    if (newest) {
      if (toastTimer.current) clearTimeout(toastTimer.current);
      setToast({
        kind: newest.kind,
        label: newest.label,
      });
      toastTimer.current = setTimeout(() => setToast(null), 2500);
    }

    // ── Viewport ──
    const rf = rfRef.current;
    if (rf && newest) {
      const p = posRef.current.get(newest.id);
      if (p) {
        if (!firstFitDone.current) {
          setTimeout(() => rf.fitView({ duration: 300, padding: 0.5 }), 60);
          firstFitDone.current = true;
        } else {
          const sz = NODE_SIZES[newest.kind] ?? NODE_SIZES.agent;
          rf.setCenter(p.x + sz.width / 2, p.y + sz.height / 2, {
            duration: 700,
          });
        }
      }
    }
  }, [nodes, edges, setFlowNodes, setFlowEdges]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (!onNodeClick) return;
      const orig = graphNodesRef.current.find((n) => n.id === node.id);
      if (orig) onNodeClick(orig);
    },
    [onNodeClick],
  );

  return (
    <div style={{ width: '100%', height: '100%', background: '#000', position: 'relative' }}>
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onInit={(inst) => {
          rfRef.current = inst;
        }}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        style={{ background: '#000' }}
      />

      {/* Review instruction */}
      {reviewActive && (
        <div
          style={{
            position: 'absolute',
            top: 12,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 10,
            background: 'rgba(251,191,36,0.15)',
            border: '1px solid rgba(251,191,36,0.3)',
            padding: '8px 20px',
            fontSize: 11,
            fontFamily: "'IBM Plex Mono', monospace",
            color: '#f59e0b',
            pointerEvents: 'none',
          }}
        >
          Click on the glowing output files to review and approve
        </div>
      )}

      {/* Toast notification */}
      {toast && (
        <div
          key={`${toast.kind}-${toast.label}`}
          className="animate-slide-in-right"
          style={{
            position: 'absolute',
            bottom: 20,
            left: 20,
            zIndex: 10,
            background: 'rgba(0,0,0,0.92)',
            border: '1px solid rgba(255,255,255,0.12)',
            padding: '8px 16px',
            fontSize: 11,
            fontFamily: "'IBM Plex Mono', monospace",
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            pointerEvents: 'none',
          }}
        >
          <span
            style={{
              fontSize: 9,
              letterSpacing: '1.5px',
              color: 'rgba(255,255,255,0.4)',
              textTransform: 'uppercase',
            }}
          >
            {KIND_LABELS[toast.kind] ?? toast.kind}
          </span>
          <span style={{ color: '#fff' }}>{toast.label}</span>
        </div>
      )}

      {/* Legend */}
      <div
        style={{
          position: 'absolute',
          top: 12,
          right: 12,
          zIndex: 10,
          background: 'rgba(0,0,0,0.85)',
          border: '1px solid rgba(255,255,255,0.08)',
          padding: '10px 14px',
          display: 'flex',
          flexDirection: 'column',
          gap: 7,
          fontSize: 10,
          fontFamily: "'IBM Plex Mono', monospace",
          color: 'rgba(255,255,255,0.5)',
          pointerEvents: 'none',
        }}
      >
        {/* Agents */}
        <span style={{ fontSize: 8, letterSpacing: '1.5px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.3)' }}>Agents</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <LegendFace name="Researcher" size={20} />
          <span>Researcher</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <LegendFace name="Formalizer" size={20} />
          <span>Formalizer</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <LegendFace name="Reasoner" size={20} />
          <span>Reasoner</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <LegendFace name="Builder" size={20} />
          <span>Builder</span>
        </div>

        {/* Sub-agents */}
        <div style={{ marginTop: 2, borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 6, display: 'flex', flexDirection: 'column', gap: 7 }}>
          <span style={{ fontSize: 8, letterSpacing: '1.5px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.3)' }}>Sub-agents</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <LegendFace name="Deep Researcher" size={16} />
            <span>Deep Researcher</span>
          </div>
        </div>

        {/* Tools & Artifacts */}
        <div style={{ marginTop: 2, borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 6, display: 'flex', flexDirection: 'column', gap: 7 }}>
          <span style={{ fontSize: 8, letterSpacing: '1.5px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.3)' }}>Tools & Artifacts</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.7)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" /><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" /></svg>
            <span>Web Search</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.7)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" /></svg>
            <span>Tool</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.7)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><text x="12" y="18" textAnchor="middle" fill="rgba(255,255,255,0.7)" stroke="none" fontSize="7" fontFamily="monospace" fontWeight="bold">md</text></svg>
            <span>md</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <svg width="14" height="14" viewBox="0 0 32 32" fill="rgba(255,255,255,0.7)">
              <path fillRule="evenodd" clipRule="evenodd" d="M13.016 2C10.82 2 9.038 3.725 9.038 5.852V8.519h6.885v.74H5.978C3.781 9.259 2 10.984 2 13.111v5.778c0 2.127 1.781 3.852 3.978 3.852h2.295v-3.26c0-2.127 1.781-3.852 3.978-3.852h7.344c1.86 0 3.366-1.459 3.366-3.26V5.853C22.962 3.725 21.18 2 18.984 2h-5.968zm-.918 4.741c.76 0 1.377-.597 1.377-1.333 0-.737-.616-1.334-1.377-1.334-.76 0-1.377.597-1.377 1.334 0 .736.616 1.333 1.377 1.333z" />
              <path fillRule="evenodd" clipRule="evenodd" d="M18.983 30c2.197 0 3.978-1.725 3.978-3.852v-2.667h-6.885v-.74h9.946C28.219 22.74 30 21.016 30 18.889v-5.778C30 10.984 28.219 9.26 26.022 9.26h-2.295v3.26c0 2.127-1.781 3.851-3.978 3.851h-7.345c-1.859 0-3.366 1.46-3.366 3.26v6.518c0 2.128 1.781 3.852 3.978 3.852h5.968zm.918-4.741c-.76 0-1.377.597-1.377 1.333 0 .737.617 1.334 1.377 1.334.76 0 1.377-.597 1.377-1.334 0-.736-.616-1.333-1.377-1.333z" />
            </svg>
            <span>.py</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.7)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><text x="12" y="18" textAnchor="middle" fill="rgba(255,255,255,0.7)" stroke="none" fontSize="8" fontFamily="monospace" fontWeight="bold">{`{}`}</text></svg>
            <span>.json</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <svg width="16" height="18" viewBox="0 0 48 55" style={{ flexShrink: 0 }}>
              <polygon points="24,1 47,14 47,41 24,54 1,41 1,14" fill="#090909" stroke="#22c55e" strokeWidth="2" />
            </svg>
            <span>Stage Output</span>
          </div>
        </div>

        {/* Edges */}
        <div style={{ marginTop: 2, borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 6, display: 'flex', flexDirection: 'column', gap: 7 }}>
          <span style={{ fontSize: 8, letterSpacing: '1.5px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.3)' }}>Data Flow</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 20, height: 0, borderTop: '2px solid rgba(251,191,36,0.5)' }} />
            <span>Write</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 20, height: 0, borderTop: '2px solid rgba(56,189,248,0.5)' }} />
            <span>Read</span>
          </div>
        </div>

        {/* Status */}
        <div style={{ marginTop: 2, borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 6, display: 'flex', flexDirection: 'column', gap: 7 }}>
          <span style={{ fontSize: 8, letterSpacing: '1.5px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.3)' }}>Status</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', border: '2px solid #f59e0b', boxShadow: '0 0 6px rgba(251,191,36,0.5)' }} />
            <span>Running</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', border: '2px solid #22c55e' }} />
            <span>Done</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', border: '2px solid #ef4444' }} />
            <span>Error</span>
          </div>
        </div>
      </div>
    </div>
  );
}
