import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { GraphCanvas, darkTheme, type GraphCanvasRef } from "reagraph";

const blackTheme = {
  ...darkTheme,
  canvas: { ...darkTheme.canvas, background: "#000000" },
};
import type {
  AgentState,
  KGNode,
  KGRelation,
  KGSnapshot,
} from "../types";
import {
  formatKgPropertyValue,
  shouldShowKgProperty,
} from "../lib/kgDisplay";

interface Props {
  runId: string | null;
  memoryAgent: AgentState | undefined;
  /** Drives the enter animation — set false to fade the collapsed card in
   * later (matches the PastRunsList `active` flag on the landing band). */
  active?: boolean;
}

const ENTER_EASE_OUT = "cubic-bezier(0.23, 1, 0.32, 1)";
const ENTER_DELAY_MS = 350;

const NEW_NODE_FILL = "#22d3ee";
const OLD_NODE_FILL = "rgba(255,255,255,0.35)";

type ReagraphNode = {
  id: string;
  label: string;
  fill: string;
  data: { kind: string; isNew: boolean };
};
type ReagraphEdge = {
  id: string;
  source: string;
  target: string;
  label: string;
  size?: number;
};

function toReagraph(
  nodes: KGNode[],
  relations: KGRelation[],
  runId: string | null,
  currentRunNodeIds: Set<string>,
  showAll: boolean,
): { nodes: ReagraphNode[]; edges: ReagraphEdge[] } {
  // P0-004: per-run node membership comes from the API's
  // `current_run_node_ids` (sourced from the Postgres
  // node_run_observations table) instead of the old per-node `run_ids`
  // array.
  const isNewNode = (n: KGNode) =>
    runId !== null && currentRunNodeIds.has(n.id);
  const keptNodes = showAll ? nodes : nodes.filter(isNewNode);
  const keptIds = new Set(keptNodes.map((n) => n.id));
  const keptEdges = relations.filter(
    (r) => keptIds.has(r.source) && keptIds.has(r.target),
  );
  return {
    nodes: keptNodes.map((n) => {
      const isNew = isNewNode(n);
      return {
        id: n.id,
        label: n.display,
        fill: isNew ? NEW_NODE_FILL : OLD_NODE_FILL,
        data: { kind: n.label, isNew },
      };
    }),
    edges: keptEdges.map((r) => {
      const isNew = runId !== null && r.run_id === runId;
      return {
        id: r.id,
        source: r.source,
        target: r.target,
        label: r.type,
        size: isNew ? 2 : 1,
      };
    }),
  };
}

interface NeighborEdge {
  relId: string;
  relType: string;
  neighbor: KGNode;
  direction: "out" | "in";
  properties: Record<string, unknown>;
}

function neighborsFor(
  nodeId: string,
  nodes: KGNode[],
  relations: KGRelation[],
): NeighborEdge[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const out: NeighborEdge[] = [];
  for (const r of relations) {
    if (r.source === nodeId) {
      const other = byId.get(r.target);
      if (other) {
        out.push({
          relId: r.id,
          relType: r.type,
          neighbor: other,
          direction: "out",
          properties: r.properties,
        });
      }
    } else if (r.target === nodeId) {
      const other = byId.get(r.source);
      if (other) {
        out.push({
          relId: r.id,
          relType: r.type,
          neighbor: other,
          direction: "in",
          properties: r.properties,
        });
      }
    }
  }
  return out;
}

interface NodeStatsPanelProps {
  node: KGNode;
  neighbors: NeighborEdge[];
  onSelectNeighbor: (id: string) => void;
  onClose: () => void;
}

function NodeStatsPanel({
  node,
  neighbors,
  onSelectNeighbor,
  onClose,
}: NodeStatsPanelProps) {
  const props = node.properties ?? {};
  const mainEntries = Object.entries(props).filter(
    ([key, value]) => shouldShowKgProperty(key, value),
  );
  const createdAt = props.created_at as string | undefined;
  const updatedAt = props.updated_at as string | undefined;
  const runCount = node.run_count;

  const outgoing = neighbors.filter((n) => n.direction === "out");
  const incoming = neighbors.filter((n) => n.direction === "in");

  return (
    <div className="w-[340px] border-l border-border-subtle bg-[#0a0a0a] flex flex-col shrink-0">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border-subtle flex items-start justify-between gap-3 shrink-0">
        <div className="min-w-0">
          <span className="text-[10px] tracking-[1.5px] uppercase text-text-faint">
            {node.label}
          </span>
          <div className="text-[14px] text-text mt-0.5 truncate">
            {node.display}
          </div>
        </div>
        <button
          onClick={onClose}
          className="w-6 h-6 flex items-center justify-center rounded-full bg-transparent border-none text-text-dim text-[15px] cursor-pointer hover:bg-surface-hover shrink-0"
          aria-label="Close details"
        >
          ✕
        </button>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4 text-[12px]">
        {/* Properties */}
        <section>
          <div className="text-[10px] uppercase tracking-[1.5px] text-text-faint mb-2">
            Properties
          </div>
          {mainEntries.length === 0 ? (
            <div className="text-text-faint italic">No properties</div>
          ) : (
            <dl className="space-y-2">
              {mainEntries.map(([k, v]) => (
                <div key={k}>
                  <dt className="text-text-muted text-[10px] uppercase tracking-[1px]">
                    {k}
                  </dt>
                  <dd className="text-text break-words whitespace-pre-wrap">
                    {formatKgPropertyValue(v)}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </section>

        {/* Outgoing edges */}
        {outgoing.length > 0 && (
          <section>
            <div className="text-[10px] uppercase tracking-[1.5px] text-text-faint mb-2">
              Outgoing · {outgoing.length}
            </div>
            <ul className="space-y-1.5">
              {outgoing.map((e) => (
                <li key={e.relId}>
                  <button
                    onClick={() => onSelectNeighbor(e.neighbor.id)}
                    className="w-full text-left px-2 py-1.5 rounded bg-surface/40 border border-border-subtle hover:border-border-strong transition-[border-color] duration-150 cursor-pointer"
                  >
                    <div className="text-[10px] text-text-faint">
                      <span className="text-cyan-300">{e.relType}</span>
                      <span className="mx-1">→</span>
                      <span>{e.neighbor.label}</span>
                    </div>
                    <div className="text-text text-[12px] truncate">
                      {e.neighbor.display}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Incoming edges */}
        {incoming.length > 0 && (
          <section>
            <div className="text-[10px] uppercase tracking-[1.5px] text-text-faint mb-2">
              Incoming · {incoming.length}
            </div>
            <ul className="space-y-1.5">
              {incoming.map((e) => (
                <li key={e.relId}>
                  <button
                    onClick={() => onSelectNeighbor(e.neighbor.id)}
                    className="w-full text-left px-2 py-1.5 rounded bg-surface/40 border border-border-subtle hover:border-border-strong transition-[border-color] duration-150 cursor-pointer"
                  >
                    <div className="text-[10px] text-text-faint">
                      <span>{e.neighbor.label}</span>
                      <span className="mx-1">→</span>
                      <span className="text-cyan-300">{e.relType}</span>
                    </div>
                    <div className="text-text text-[12px] truncate">
                      {e.neighbor.display}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Provenance footer */}
        {(createdAt || updatedAt || runCount > 0) && (
          <section className="pt-3 border-t border-border-subtle space-y-1 text-[10px] text-text-faint">
            {createdAt && (
              <div>
                <span className="uppercase tracking-[1px] mr-2">Created</span>
                {createdAt}
              </div>
            )}
            {updatedAt && (
              <div>
                <span className="uppercase tracking-[1px] mr-2">Updated</span>
                {updatedAt}
              </div>
            )}
            {runCount > 0 && (
              <div>
                <span className="uppercase tracking-[1px] mr-2">Runs</span>
                {runCount}
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}

export default function KnowledgeGraphPanel({
  runId,
  memoryAgent,
  active = true,
}: Props) {
  const [snapshot, setSnapshot] = useState<KGSnapshot | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const collapsedRef = useRef<GraphCanvasRef | null>(null);
  const expandedRef = useRef<GraphCanvasRef | null>(null);

  const fetchSnapshot = useCallback(async () => {
    try {
      // Pass the active run_id so the backend can resolve
      // current_run_node_ids from node_run_observations (P0-004).
      const url = runId
        ? `/api/kg/snapshot?run_id=${encodeURIComponent(runId)}`
        : "/api/kg/snapshot";
      const res = await fetch(url);
      if (!res.ok) return;
      const data: KGSnapshot = await res.json();
      setSnapshot(data);
    } catch {
      /* KG may be unavailable — silently stay empty */
    }
  }, [runId]);

  /* Initial fetch */
  useEffect(() => {
    fetchSnapshot();
  }, [fetchSnapshot]);

  /* Refetch each time memory agent transitions working -> done */
  const prevStatusRef = useRef<AgentState["status"] | undefined>(undefined);
  const memoryStatus = memoryAgent?.status;
  useEffect(() => {
    if (prevStatusRef.current === "working" && memoryStatus === "done") {
      fetchSnapshot();
    }
    prevStatusRef.current = memoryStatus;
  }, [memoryStatus, fetchSnapshot]);

  /* Clear selection when the modal closes */
  useEffect(() => {
    if (!expanded) {
      setSelectedId(null);
      setHoveredId(null);
    }
  }, [expanded]);

  const currentRunNodeIds = useMemo(
    () => new Set(snapshot?.current_run_node_ids ?? []),
    [snapshot],
  );

  const delta = useMemo(
    () =>
      toReagraph(
        snapshot?.nodes ?? [],
        snapshot?.relations ?? [],
        runId,
        currentRunNodeIds,
        false,
      ),
    [snapshot, runId, currentRunNodeIds],
  );

  const full = useMemo(
    () =>
      toReagraph(
        snapshot?.nodes ?? [],
        snapshot?.relations ?? [],
        runId,
        currentRunNodeIds,
        true,
      ),
    [snapshot, runId, currentRunNodeIds],
  );

  const isWorking = memoryStatus === "working";
  const deltaCount = delta.nodes.length;
  const totalCount = full.nodes.length;

  // On the idle landing page (no current run) show the whole graph in the
  // collapsed card; during a run, keep the delta-only view.
  const collapsedView = runId === null ? full : delta;
  const collapsedCount = collapsedView.nodes.length;

  /* Selected node + its neighborhood — used for the right-side panel. */
  const selectedNode = useMemo(() => {
    if (!selectedId) return null;
    return snapshot?.nodes.find((n) => n.id === selectedId) ?? null;
  }, [selectedId, snapshot]);

  const selectedNeighbors = useMemo<NeighborEdge[]>(() => {
    if (!selectedId || !snapshot) return [];
    return neighborsFor(selectedId, snapshot.nodes, snapshot.relations);
  }, [selectedId, snapshot]);

  /* Highlight the focused node (selected takes precedence over hovered) and
     its 1-hop neighborhood — so picking a node visually de-emphasises the
     rest of the graph. */
  const focusId = selectedId ?? hoveredId;
  const { selections, actives } = useMemo(() => {
    if (!focusId || !snapshot) return { selections: [], actives: [] };
    const neighborIds = neighborsFor(
      focusId,
      snapshot.nodes,
      snapshot.relations,
    ).map((n) => n.neighbor.id);
    const neighborRelIds = snapshot.relations
      .filter((r) => r.source === focusId || r.target === focusId)
      .map((r) => r.id);
    return {
      selections: [focusId],
      actives: [...neighborIds, ...neighborRelIds],
    };
  }, [focusId, snapshot]);

  return (
    <>
      {/* Collapsed panel — sits directly below the Sidebar, matching its width */}
      <div
        onClick={() => setExpanded(true)}
        className="panel-chrome fixed left-4 bottom-4 w-[220px] h-[180px] z-30 flex flex-col overflow-hidden cursor-pointer transition-[border-color] duration-200 motion-reduce:transform-none"
        style={{
          opacity: active ? 1 : 0,
          transform: active ? "translateY(0)" : "translateY(8px)",
          transition: `opacity 500ms ${ENTER_EASE_OUT} ${ENTER_DELAY_MS}ms, transform 500ms ${ENTER_EASE_OUT} ${ENTER_DELAY_MS}ms, border-color 200ms`,
          willChange: "opacity, transform",
        }}
      >
        {/* Header */}
        <div className="px-3 py-2 border-b border-border-subtle flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full shrink-0${isWorking ? " animate-pulse-dot" : ""}`}
              style={{
                background: isWorking
                  ? "#fbbf24"
                  : memoryStatus === "done"
                    ? "#4ade80"
                    : "rgba(255,255,255,0.15)",
                boxShadow: isWorking ? "0 0 6px #fbbf24" : undefined,
              }}
            />
            <span className="text-[10px] uppercase tracking-[1.5px] text-text-muted">
              Knowledge
            </span>
          </div>
          <span className="text-[10px] text-text-faint">
            {runId === null ? collapsedCount : `+${deltaCount}`}
          </span>
        </div>

        {/* Graph body — full graph on idle, delta during a run */}
        <div className="flex-1 relative min-h-0">
          {collapsedCount === 0 ? (
            <div className="absolute inset-0 flex items-center justify-center text-[11px] text-text-faint px-4 text-center">
              {runId
                ? "No new nodes yet"
                : "Knowledge graph is empty"}
            </div>
          ) : (
            <div className="absolute inset-0">
              <GraphCanvas
                ref={collapsedRef}
                nodes={collapsedView.nodes}
                edges={collapsedView.edges}
                theme={blackTheme}
                labelType="none"
                layoutType="forceDirected2d"
                animated={false}
                draggable={false}
              />
            </div>
          )}
        </div>
      </div>

      {/* Expanded modal */}
      {expanded && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-overlay backdrop-blur-[6px]"
          onClick={() => setExpanded(false)}
        >
          <div
            className="flex flex-col overflow-hidden w-[min(1100px,92vw)] h-[min(720px,88vh)] bg-[#0a0a0a] rounded-2xl shadow-2xl shadow-black/40 border border-border"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="px-5 py-3.5 border-b border-border-subtle flex items-center justify-between shrink-0">
              <div className="flex items-center gap-3">
                <div
                  className={`w-2 h-2 rounded-full${isWorking ? " animate-pulse-dot" : ""}`}
                  style={{
                    background: isWorking
                      ? "#fbbf24"
                      : "rgba(255,255,255,0.2)",
                    boxShadow: isWorking ? "0 0 6px #fbbf24" : undefined,
                  }}
                />
                <div>
                  <span className="text-[11px] tracking-[1.5px] text-text-faint uppercase block">
                    Knowledge Graph
                  </span>
                  <div className="text-[15px] text-text mt-0.5">
                    {totalCount} nodes
                    <span className="ml-3 text-text-muted">
                      {deltaCount} new this run
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2 text-[11px] text-text-muted">
                  <span
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ background: NEW_NODE_FILL }}
                  />
                  Current run
                  <span
                    className="w-2.5 h-2.5 rounded-full ml-3"
                    style={{ background: OLD_NODE_FILL }}
                  />
                  Existing
                </div>
                <button
                  onClick={() => setExpanded(false)}
                  className="w-7 h-7 flex items-center justify-center rounded-full bg-transparent border-none text-text-dim text-[18px] cursor-pointer hover:bg-surface-hover"
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Body — graph + optional right stats panel */}
            <div className="flex-1 flex min-h-0">
              <div className="flex-1 relative min-h-0">
                {totalCount === 0 ? (
                  <div className="absolute inset-0 flex items-center justify-center text-[13px] text-text-faint">
                    Knowledge graph is empty
                  </div>
                ) : (
                  <div className="absolute inset-0">
                    <GraphCanvas
                      ref={expandedRef}
                      nodes={full.nodes}
                      edges={full.edges}
                      theme={blackTheme}
                      labelType="nodes"
                      edgeLabelPosition="natural"
                      layoutType="forceDirected2d"
                      selections={selections}
                      actives={actives}
                      onNodeClick={(node) =>
                        setSelectedId((prev) =>
                          prev === node.id ? null : node.id,
                        )
                      }
                      onNodePointerOver={(node) => setHoveredId(node.id)}
                      onNodePointerOut={() => setHoveredId(null)}
                      onCanvasClick={() => setSelectedId(null)}
                    />
                  </div>
                )}
              </div>

              {selectedNode && (
                <NodeStatsPanel
                  node={selectedNode}
                  neighbors={selectedNeighbors}
                  onSelectNeighbor={setSelectedId}
                  onClose={() => setSelectedId(null)}
                />
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
