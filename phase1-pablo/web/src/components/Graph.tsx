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
    <div className="overflow-hidden leading-none shrink-0">
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
    <div className="flex items-center gap-2">
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
  currentStage?: string | null;
  dismissedOutputIds?: Set<string>;
  demo?: boolean;
}

export default function Graph({ nodes, edges, onNodeClick, reviewActive, currentStage, dismissedOutputIds, demo }: GraphProps) {
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<Node>([]);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const graphNodesRef = useRef<GraphNode[]>(nodes);
  const rfRef = useRef<ReactFlowInstance | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const posRef = useRef(new Map<string, { x: number; y: number }>());
  const childCountRef = useRef(new Map<string, number>());

  // Auto-fit: fitView on every new node until user manually pans/zooms
  const [autoFit, setAutoFit] = useState(true);

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
      setAutoFit(true);
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
            currentStage: currentStage ?? undefined,
            dismissed: dismissedOutputIds?.has(n.id) ?? false,
          },
          position: posRef.current.get(n.id)!,
        })),
    );

    // ── Flow edges (center-to-center, straight lines — layout edges are invisible) ──
    setFlowEdges(
      edges
        .filter(
          (e) => e.edge_kind !== 'layout' && posRef.current.has(e.source) && posRef.current.has(e.target),
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
            animated: true,
            style:
              kind === 'write'
                ? { stroke: 'rgba(251,191,36,0.35)', strokeWidth: 1.5 }
                : kind === 'read'
                ? { stroke: 'rgba(56,189,248,0.35)', strokeWidth: 1.5 }
                : { stroke: 'rgba(255,255,255,0.35)' },
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

    // ── Viewport: zoom out keeping root (0,0) centered (skip in demo) ──
    if (autoFit && newest && !demo) {
      const rf = rfRef.current;
      if (rf) {
        setTimeout(() => {
          const el = containerRef.current;
          const vw = el?.clientWidth || 800;
          const vh = el?.clientHeight || 600;
          let maxDist = 100;
          for (const [, pos] of posRef.current) {
            maxDist = Math.max(maxDist, Math.hypot(pos.x, pos.y));
          }
          const halfSize = Math.min(vw, vh) / 2;
          const zoom = Math.min(1, halfSize / (maxDist + 40));
          // Demo: long duration so each retarget blends smoothly into the next
          // Normal: snappy 300ms per step
          rf.setCenter(40, 40, { zoom: Math.max(0.15, zoom), duration: demo ? 2500 : 300 });
        }, 60);
      }
    }
  }, [nodes, edges, currentStage, dismissedOutputIds, autoFit, setFlowNodes, setFlowEdges]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (!onNodeClick) return;
      const orig = graphNodesRef.current.find((n) => n.id === node.id);
      if (orig) onNodeClick(orig);
    },
    [onNodeClick],
  );

  return (
    <div ref={containerRef} className="w-full h-full bg-bg relative">
      <ReactFlow
        className="main-rf"
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        panOnDrag={!demo}
        zoomOnScroll={!demo}
        zoomOnPinch={!demo}
        zoomOnDoubleClick={!demo}
        nodesDraggable={!demo}
        elementsSelectable={!demo}
        onMoveStart={demo ? undefined : (event) => {
          if (event) setAutoFit(false);
        }}
        onInit={(inst) => {
          rfRef.current = inst;
          inst.setCenter(40, 40, { zoom: 1 });
        }}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        style={{ background: '#000' }}
      />

      {/* Auto-fit toggle */}
      {!demo && <button
        onClick={() => {
          setAutoFit((v) => {
            if (!v) {
              const rf = rfRef.current;
              if (rf) {
                const el = containerRef.current;
                const vw = el?.clientWidth || 800;
                const vh = el?.clientHeight || 600;
                let maxDist = 100;
                for (const [, pos] of posRef.current) {
                  maxDist = Math.max(maxDist, Math.hypot(pos.x, pos.y));
                }
                const halfSize = Math.min(vw, vh) / 2;
                const zoom = Math.min(1, halfSize / (maxDist + 40));
                rf.setCenter(40, 40, { zoom: Math.max(0.15, zoom), duration: 300 });
              }
            }
            return !v;
          });
        }}
        title={autoFit ? 'Auto-fit ON — click to disable' : 'Auto-fit OFF — click to re-enable'}
        className="absolute bottom-5 right-5 z-10 w-8 h-8 flex items-center justify-center cursor-pointer transition-all duration-150"
        style={{
          background: autoFit ? 'rgba(74,222,128,0.12)' : 'rgba(255,255,255,0.05)',
          border: `1px solid ${autoFit ? 'rgba(74,222,128,0.4)' : 'rgba(255,255,255,0.15)'}`,
        }}
      >
        {/* Crosshair / focus icon */}
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke={autoFit ? '#4ade80' : 'rgba(255,255,255,0.4)'}
          strokeWidth="2"
          strokeLinecap="round"
        >
          <circle cx="12" cy="12" r="3" />
          <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
        </svg>
      </button>}

      {/* Review instruction */}
      {!demo && reviewActive && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 bg-[rgba(251,191,36,0.15)] border border-accent-amber/30 px-5 py-2 text-[11px] font-mono text-accent-amber-dark pointer-events-none">
          Click on the glowing output files to review and approve
        </div>
      )}

      {/* Toast notification */}
      {!demo && toast && (
        <div
          key={`${toast.kind}-${toast.label}`}
          className="animate-slide-in-right absolute bottom-5 left-5 z-10 bg-overlay-heavy border border-border py-2 px-4 text-[11px] font-mono flex items-center gap-2.5 pointer-events-none"
        >
          <span className="text-[9px] tracking-[1.5px] text-text-dim uppercase">
            {KIND_LABELS[toast.kind] ?? toast.kind}
          </span>
          <span className="text-text">{toast.label}</span>
        </div>
      )}

      {/* Legend */}
      {!demo && <div className="absolute top-3 right-3 z-10 bg-overlay border border-border-subtle p-2.5 px-3.5 flex flex-col gap-[7px] text-[10px] font-mono text-text-muted pointer-events-none">
        {/* Agents */}
        <span className="text-[8px] tracking-[1.5px] uppercase text-text-faint">Agents</span>
        <div className="flex items-center gap-2">
          <LegendFace name="Researcher" size={20} />
          <span>Researcher</span>
        </div>
        <div className="flex items-center gap-2">
          <LegendFace name="Formalizer" size={20} />
          <span>Formalizer</span>
        </div>
        <div className="flex items-center gap-2">
          <LegendFace name="Reasoner" size={20} />
          <span>Reasoner</span>
        </div>
        <div className="flex items-center gap-2">
          <LegendFace name="Builder" size={20} />
          <span>Builder</span>
        </div>

        {/* Sub-agents */}
        <div className="mt-0.5 border-t border-border-subtle pt-1.5 flex flex-col gap-[7px]">
          <span className="text-[8px] tracking-[1.5px] uppercase text-text-faint">Sub-agents</span>
          <div className="flex items-center gap-2">
            <LegendFace name="Deep Researcher" size={16} />
            <span>Deep Researcher</span>
          </div>
        </div>

        {/* Tools */}
        <div className="mt-0.5 border-t border-border-subtle pt-1.5 flex flex-col gap-[7px]">
          <span className="text-[8px] tracking-[1.5px] uppercase text-text-faint">Tools</span>
          <LegendIcon d="M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zM2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10A15.3 15.3 0 0 1 12 2z" label="Web Search" />
          <LegendIcon d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z" label="Read" />
          <LegendIcon d="M17 3a2.85 2.85 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" label="Write" />
        </div>

        {/* File Types */}
        <div className="mt-0.5 border-t border-border-subtle pt-1.5 flex flex-col gap-[7px]">
          <span className="text-[8px] tracking-[1.5px] uppercase text-text-faint">File Types</span>
          <div className="flex items-center gap-2">
            <svg width="14" height="14" viewBox="0 0 208 208" fill="rgba(255,255,255,0.7)"><path d="M10 158V50h28l28 35 28-35h28v108h-28V89L66 124 38 89v69zm175 0l-42-46h28V50h28v62h28z" /></svg>
            <span>.md</span>
          </div>
          <div className="flex items-center gap-2">
            <svg width="14" height="14" viewBox="0 0 32 32" fill="rgba(255,255,255,0.7)">
              <path fillRule="evenodd" clipRule="evenodd" d="M13.016 2C10.82 2 9.038 3.725 9.038 5.852V8.519h6.885v.74H5.978C3.781 9.259 2 10.984 2 13.111v5.778c0 2.127 1.781 3.852 3.978 3.852h2.295v-3.26c0-2.127 1.781-3.852 3.978-3.852h7.344c1.86 0 3.366-1.459 3.366-3.26V5.853C22.962 3.725 21.18 2 18.984 2h-5.968zm-.918 4.741c.76 0 1.377-.597 1.377-1.333 0-.737-.616-1.334-1.377-1.334-.76 0-1.377.597-1.377 1.334 0 .736.616 1.333 1.377 1.333z" />
              <path fillRule="evenodd" clipRule="evenodd" d="M18.983 30c2.197 0 3.978-1.725 3.978-3.852v-2.667h-6.885v-.74h9.946C28.219 22.74 30 21.016 30 18.889v-5.778C30 10.984 28.219 9.26 26.022 9.26h-2.295v3.26c0-2.127-1.781-3.851-3.978-3.851h-7.345c-1.859 0-3.366 1.46-3.366 3.26v6.518c0 2.128 1.781 3.852 3.978 3.852h5.968zm.918-4.741c-.76 0-1.377.597-1.377 1.333 0 .737.617 1.334 1.377 1.334.76 0 1.377-.597 1.377-1.334 0-.736-.616-1.333-1.377-1.333z" />
            </svg>
            <span>.py</span>
          </div>
          <div className="flex items-center gap-2">
            <svg width="14" height="14" viewBox="0 0 160 160" fill="rgba(255,255,255,0.7)">
              <path d="m79.865 119.1c35.398 48.255 70.04-13.469 69.989-50.587-0.0602-43.886-44.541-68.414-70.018-68.414-40.892 0-79.836 33.796-79.836 80.036 0 51.396 44.64 79.865 79.836 79.865-7.9645-1.1468-34.506-6.834-34.863-67.967-0.23987-41.347 13.488-57.866 34.805-50.599 0.47743 0.17707 23.514 9.2645 23.514 38.951 0 29.56-23.427 38.715-23.427 38.715z" />
              <path d="m79.823 41.401c-23.39-8.0619-52.043 11.216-52.043 49.829 0 63.048 46.721 68.77 52.384 68.77 40.892 0 79.836-33.796 79.836-80.036 0-51.396-44.64-79.865-79.836-79.865 9.7481-1.35 52.541 10.55 52.541 69.037 0 38.141-31.953 58.905-52.735 50.033-0.47743-0.17707-23.514-9.2645-23.514-38.951 0-29.56 23.367-38.818 23.367-38.818z" />
            </svg>
            <span>.json</span>
          </div>
        </div>

        {/* Shapes */}
        <div className="mt-0.5 border-t border-border-subtle pt-1.5 flex flex-col gap-[7px]">
          <span className="text-[8px] tracking-[1.5px] uppercase text-text-faint">Shapes</span>
          <div className="flex items-center gap-2">
            <div style={{ width: 12, height: 12, border: '1.5px solid rgba(255,255,255,0.5)' }} />
            <span>Agent</span>
          </div>
          <div className="flex items-center gap-2">
            <div style={{ width: 12, height: 12, borderRadius: '50%', border: '1.5px solid rgba(255,255,255,0.5)' }} />
            <span>Tool</span>
          </div>
          <div className="flex items-center gap-2">
            <svg width="14" height="14" viewBox="0 0 14 14"><polygon points="7,0 14,7 7,14 0,7" fill="none" stroke="rgba(255,255,255,0.5)" strokeWidth="1.5" /></svg>
            <span>Artifact</span>
          </div>
          <div className="flex items-center gap-2">
            <svg width="14" height="16" viewBox="0 0 48 55" className="shrink-0">
              <polygon points="24,1 47,14 47,41 24,54 1,41 1,14" fill="none" stroke="rgba(255,255,255,0.5)" strokeWidth="2.5" />
            </svg>
            <span>Stage Output</span>
          </div>
        </div>

        {/* Edges */}
        <div className="mt-0.5 border-t border-border-subtle pt-1.5 flex flex-col gap-[7px]">
          <span className="text-[8px] tracking-[1.5px] uppercase text-text-faint">Data Flow</span>
          <div className="flex items-center gap-2">
            <div style={{ width: 20, height: 0, borderTop: '2px solid rgba(251,191,36,0.5)' }} />
            <span>Write</span>
          </div>
          <div className="flex items-center gap-2">
            <div style={{ width: 20, height: 0, borderTop: '2px solid rgba(56,189,248,0.5)' }} />
            <span>Read</span>
          </div>
        </div>

        {/* Status */}
        <div className="mt-0.5 border-t border-border-subtle pt-1.5 flex flex-col gap-[7px]">
          <span className="text-[8px] tracking-[1.5px] uppercase text-text-faint">Status</span>
          <div className="flex items-center gap-2">
            <div style={{ width: 10, height: 10, borderRadius: '50%', border: '2px solid #f59e0b', boxShadow: '0 0 6px rgba(251,191,36,0.5)' }} />
            <span>Running</span>
          </div>
          <div className="flex items-center gap-2">
            <div style={{ width: 10, height: 10, borderRadius: '50%', border: '2px solid #22c55e' }} />
            <span>Done</span>
          </div>
          <div className="flex items-center gap-2">
            <div style={{ width: 10, height: 10, borderRadius: '50%', border: '2px solid #ef4444' }} />
            <span>Error</span>
          </div>
        </div>
      </div>}
    </div>
  );
}
