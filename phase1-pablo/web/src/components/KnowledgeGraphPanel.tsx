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

interface Props {
  runId: string | null;
  memoryAgent: AgentState | undefined;
}

const NEW_NODE_FILL = "#22d3ee";
const OLD_NODE_FILL = "rgba(255,255,255,0.35)";
const NEW_EDGE_FILL = "#22d3ee";
const OLD_EDGE_FILL = "rgba(255,255,255,0.15)";

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
  showAll: boolean,
): { nodes: ReagraphNode[]; edges: ReagraphEdge[] } {
  const isNewNode = (n: KGNode) =>
    runId !== null && n.run_ids.includes(runId);
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

export default function KnowledgeGraphPanel({
  runId,
  memoryAgent,
}: Props) {
  const [snapshot, setSnapshot] = useState<KGSnapshot | null>(null);
  const [expanded, setExpanded] = useState(false);
  const collapsedRef = useRef<GraphCanvasRef | null>(null);
  const expandedRef = useRef<GraphCanvasRef | null>(null);

  const fetchSnapshot = useCallback(async () => {
    try {
      const res = await fetch("/api/kg/snapshot");
      if (!res.ok) return;
      const data: KGSnapshot = await res.json();
      setSnapshot(data);
    } catch {
      /* KG may be unavailable — silently stay empty */
    }
  }, []);

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

  const delta = useMemo(
    () =>
      toReagraph(
        snapshot?.nodes ?? [],
        snapshot?.relations ?? [],
        runId,
        false,
      ),
    [snapshot, runId],
  );

  const full = useMemo(
    () =>
      toReagraph(
        snapshot?.nodes ?? [],
        snapshot?.relations ?? [],
        runId,
        true,
      ),
    [snapshot, runId],
  );

  const isWorking = memoryStatus === "working";
  const deltaCount = delta.nodes.length;
  const totalCount = full.nodes.length;

  return (
    <>
      {/* Collapsed panel — sits directly below the Sidebar, matching its width */}
      <div
        onClick={() => setExpanded(true)}
        className="fixed left-4 bottom-4 w-[160px] h-[180px] z-30 rounded-2xl bg-surface/80 backdrop-blur-xl border border-border shadow-xl shadow-black/20 flex flex-col overflow-hidden cursor-pointer hover:border-border-strong transition-[border-color] duration-200"
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
            +{deltaCount}
          </span>
        </div>

        {/* Graph body — delta only */}
        <div className="flex-1 relative min-h-0">
          {deltaCount === 0 ? (
            <div className="absolute inset-0 flex items-center justify-center text-[11px] text-text-faint px-4 text-center">
              {runId
                ? "No new nodes yet"
                : "Run a pipeline to populate"}
            </div>
          ) : (
            <div className="absolute inset-0">
              <GraphCanvas
                ref={collapsedRef}
                nodes={delta.nodes}
                edges={delta.edges}
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

            {/* Body */}
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
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
