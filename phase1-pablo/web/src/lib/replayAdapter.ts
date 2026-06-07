import {
  defaultStepBoundaries,
  type AgrexEdge,
  type AgrexEvent,
  type AgrexMarker,
  type AgrexNode,
  type EventReducer,
} from "@ppazosp/agrex";
import type { Stage } from "../types";

// Events on the WS and in trace.jsonl are canonical agrex shape (`type`,
// `parentId`, `metadata`). The lab layer only hides misleading launcher nodes
// and memory implementation details, then repairs legacy parent ids where the
// path makes the true subagent clear.

const HIDDEN_TOOL_LABELS = new Set(["launch_deep_research"]);
const hiddenNodeIds = new Set<string>();
const liveDbNodeIds = new Set<string>();
const liveMemoryEdgeIds = new Set<string>();
let lastBuilderParentId: string | undefined;

type MemoryDbKind = "kg" | "vectors";

interface SanitizerState {
  lastBuilderParentId?: string;
  dbNodeIds: Set<string>;
  memoryEdgeIds: Set<string>;
}

const MEMORY_DB_NODES: Record<MemoryDbKind, AgrexNode> = {
  kg: {
    id: "db:knowledge-graph",
    type: "database",
    label: "Neo4j KG",
    status: "done",
    metadata: {
      db: "Neo4j",
      role: "Knowledge Graph",
      description: "Canonical nodes and relations extracted by memory",
    },
  },
  vectors: {
    id: "db:vector-memory",
    type: "database",
    label: "Qdrant Memories",
    status: "done",
    metadata: {
      db: "Qdrant",
      role: "Vector Memory",
      description: "Indexed memory facts used by retrieval",
    },
  },
};

function createSanitizerState(): SanitizerState {
  return {
    dbNodeIds: new Set<string>(),
    memoryEdgeIds: new Set<string>(),
  };
}

function nodeToolName(node: AgrexNode): string {
  const metadata = node.metadata as Record<string, unknown> | undefined;
  const metadataName = metadata?.tool_name;
  return typeof metadataName === "string" ? metadataName : node.label;
}

function shouldHideNode(node: AgrexNode): boolean {
  return (
    (node.type === "tool" && HIDDEN_TOOL_LABELS.has(nodeToolName(node))) ||
    isMemoryReadNode(node) ||
    memoryOutputDbKind(node) !== undefined
  );
}

function nodeMetadataPath(node: AgrexNode): string | undefined {
  const metadata = node.metadata as Record<string, unknown> | undefined;
  if (typeof metadata?.path === "string") return metadata.path;
  const args = metadata?.args;
  if (args && typeof args === "object" && "path" in args) {
    const path = (args as Record<string, unknown>).path;
    if (typeof path === "string") return path;
  }
  return undefined;
}

function builderParentFromPath(path: string): string | undefined {
  const reasonerSpec = path.match(/^reasoner\/([^/]+)\/([^/]+)\.json$/);
  if (reasonerSpec) return `builder:${reasonerSpec[1]}:${reasonerSpec[2]}`;

  const modelFile = path.match(/^builder\/([^/]+)\/(.+)_model\.py$/);
  if (modelFile) return `builder:${modelFile[1]}:${modelFile[2]}`;

  const testFile = path.match(/^builder\/([^/]+)\/test_(.+)\.py$/);
  if (testFile) return `builder:${testFile[1]}:${testFile[2]}`;

  const validationFile = path.match(/^builder\/([^/]+)\/(.+)_validation\.json$/);
  if (validationFile) return `builder:${validationFile[1]}:${validationFile[2]}`;

  return undefined;
}

function normalizeNode(
  node: AgrexNode,
  fallbackBuilderParentId?: string,
): AgrexNode {
  if (node.type !== "tool" || node.parentId !== "builder") return node;
  const path = nodeMetadataPath(node);
  const parentId = path ? builderParentFromPath(path) : undefined;
  if (parentId) return { ...node, parentId };
  if (nodeToolName(node) === "retrieve_knowledge" && fallbackBuilderParentId) {
    return { ...node, parentId: fallbackBuilderParentId };
  }
  return node;
}

function rememberBuilderParent(node: AgrexNode): string | undefined {
  const parentId = node.parentId;
  return node.type === "tool" &&
    typeof parentId === "string" &&
    parentId.startsWith("builder:")
    ? parentId
    : undefined;
}

function resetLiveSanitizerState() {
  hiddenNodeIds.clear();
  liveDbNodeIds.clear();
  liveMemoryEdgeIds.clear();
  lastBuilderParentId = undefined;
}

function resetReplaySanitizerState(state: SanitizerState) {
  state.lastBuilderParentId = undefined;
  state.dbNodeIds.clear();
  state.memoryEdgeIds.clear();
}

function normalizeReplayNode(
  node: AgrexNode,
  state: SanitizerState,
): AgrexNode {
  const normalized = normalizeNode(node, state.lastBuilderParentId);
  const remembered = rememberBuilderParent(normalized);
  if (remembered) state.lastBuilderParentId = remembered;
  return normalized;
}

function normalizeLiveNode(node: AgrexNode): AgrexNode {
  const normalized = normalizeNode(node, lastBuilderParentId);
  const remembered = rememberBuilderParent(normalized);
  if (remembered) lastBuilderParentId = remembered;
  return normalized;
}

function normalizeSnapshotNode(
  node: AgrexNode,
  state: SanitizerState,
): AgrexNode {
  const normalized = normalizeNode(node, state.lastBuilderParentId);
  const remembered = rememberBuilderParent(normalized);
  if (remembered) state.lastBuilderParentId = remembered;
  return normalized;
}

function edgeTouchesHiddenNode(edge: AgrexEdge, hiddenIds: Set<string>): boolean {
  return hiddenIds.has(edge.source) || hiddenIds.has(edge.target);
}

function isMemoryReadNode(node: AgrexNode): boolean {
  return node.type === "tool" && nodeToolName(node) === "retrieve_knowledge";
}

function memoryOutputDbKind(node: AgrexNode): MemoryDbKind | undefined {
  if (node.type !== "artifact" || !node.id.startsWith("memory_output:")) {
    return undefined;
  }
  if (node.id.endsWith(":kg")) return "kg";
  if (node.id.endsWith(":facts")) return "vectors";
  return undefined;
}

function memoryReadEdges(parentId: string): AgrexEdge[] {
  return [
    {
      id: `edge:memory-read:kg:${parentId}`,
      source: MEMORY_DB_NODES.kg.id,
      target: parentId,
      type: "memory_read",
      label: "read",
    },
    {
      id: `edge:memory-read:vectors:${parentId}`,
      source: MEMORY_DB_NODES.vectors.id,
      target: parentId,
      type: "memory_read",
      label: "read",
    },
  ];
}

function memoryWriteEdge(kind: MemoryDbKind, parentId: string): AgrexEdge {
  return {
    id: `edge:memory-write:${kind}:${parentId}`,
    source: parentId,
    target: MEMORY_DB_NODES[kind].id,
    type: kind === "kg" ? "memory_write" : "memory_index",
    label: kind === "kg" ? "write" : "index",
  };
}

function memoryProjectionForNode(
  node: AgrexNode,
): { dbKinds: MemoryDbKind[]; edges: AgrexEdge[] } | undefined {
  if (isMemoryReadNode(node)) {
    if (typeof node.parentId !== "string" || node.parentId.length === 0) {
      return undefined;
    }
    return {
      dbKinds: ["kg", "vectors"],
      edges: memoryReadEdges(node.parentId),
    };
  }

  const writeKind = memoryOutputDbKind(node);
  if (!writeKind) return undefined;
  if (typeof node.parentId !== "string" || node.parentId.length === 0) {
    return undefined;
  }
  return {
    dbKinds: [writeKind],
    edges: [memoryWriteEdge(writeKind, node.parentId)],
  };
}

function ensureMemoryDbEvent(
  kind: MemoryDbKind,
  out: AgrexEvent[],
  state: SanitizerState,
  ts: number,
) {
  const node = MEMORY_DB_NODES[kind];
  if (state.dbNodeIds.has(node.id)) return;
  state.dbNodeIds.add(node.id);
  out.push({ type: "node_add", ts, node } as AgrexEvent);
}

function emitMemoryEdgeEvent(
  edge: AgrexEdge,
  out: AgrexEvent[],
  state: SanitizerState,
  ts: number,
) {
  if (state.memoryEdgeIds.has(edge.id)) return;
  state.memoryEdgeIds.add(edge.id);
  out.push({ type: "edge_add", ts, edge } as AgrexEvent);
}

function projectHiddenMemoryNodeToEvents(
  node: AgrexNode,
  out: AgrexEvent[],
  state: SanitizerState,
  ts: number,
) {
  const projection = memoryProjectionForNode(node);
  if (!projection) return;

  for (const kind of projection.dbKinds) {
    ensureMemoryDbEvent(kind, out, state, ts);
  }
  for (const edge of projection.edges) {
    emitMemoryEdgeEvent(edge, out, state, ts);
  }
}

function ensureMemoryDbSnapshotNode(
  kind: MemoryDbKind,
  out: AgrexNode[],
  state: SanitizerState,
) {
  const node = MEMORY_DB_NODES[kind];
  if (state.dbNodeIds.has(node.id)) return;
  state.dbNodeIds.add(node.id);
  out.push(node);
}

function addMemorySnapshotEdge(
  edge: AgrexEdge,
  out: AgrexEdge[],
  state: SanitizerState,
) {
  if (state.memoryEdgeIds.has(edge.id)) return;
  state.memoryEdgeIds.add(edge.id);
  out.push(edge);
}

function projectHiddenMemoryNodeToSnapshot(
  node: AgrexNode,
  dbNodes: AgrexNode[],
  edges: AgrexEdge[],
  state: SanitizerState,
) {
  const projection = memoryProjectionForNode(node);
  if (!projection) return;

  for (const kind of projection.dbKinds) {
    ensureMemoryDbSnapshotNode(kind, dbNodes, state);
  }
  for (const edge of projection.edges) {
    addMemorySnapshotEdge(edge, edges, state);
  }
}

function ensureLiveMemoryDbNode(
  store: Parameters<EventReducer>[0],
  kind: MemoryDbKind,
) {
  const node = MEMORY_DB_NODES[kind];
  if (liveDbNodeIds.has(node.id)) return;
  liveDbNodeIds.add(node.id);
  store.addNode(node);
}

function projectHiddenMemoryNodeLive(
  store: Parameters<EventReducer>[0],
  node: AgrexNode,
) {
  const projection = memoryProjectionForNode(node);
  if (!projection) return;

  for (const kind of projection.dbKinds) {
    ensureLiveMemoryDbNode(store, kind);
  }
  for (const edge of projection.edges) {
    if (liveMemoryEdgeIds.has(edge.id)) continue;
    liveMemoryEdgeIds.add(edge.id);
    store.addEdge(edge);
  }
}

function sanitizeSnapshot(
  nodes: AgrexNode[],
  edges: AgrexEdge[],
  hiddenIds: Set<string>,
  state: SanitizerState,
) {
  const visibleNodes: AgrexNode[] = [];
  const dbNodes: AgrexNode[] = [];
  const projectedEdges: AgrexEdge[] = [];
  for (const node of nodes) {
    const normalized = normalizeSnapshotNode(node, state);
    if (shouldHideNode(normalized)) {
      hiddenIds.add(normalized.id);
      projectHiddenMemoryNodeToSnapshot(normalized, dbNodes, projectedEdges, state);
    } else {
      visibleNodes.push(normalized);
    }
  }
  const visibleEdges = edges.filter((edge) => !edgeTouchesHiddenNode(edge, hiddenIds));
  return { nodes: [...visibleNodes, ...dbNodes], edges: [...visibleEdges, ...projectedEdges] };
}

export function sanitizeLabTraceEvents(events: AgrexEvent[]): AgrexEvent[] {
  const hiddenIds = new Set<string>();
  const replayState = createSanitizerState();
  const out: AgrexEvent[] = [];

  for (const ev of events) {
    if (ev.type === "node_add") {
      const node = ev.node as AgrexNode | undefined;
      if (!node) {
        out.push(ev);
      } else {
        const normalized = normalizeReplayNode(node, replayState);
        if (shouldHideNode(normalized)) {
          hiddenIds.add(normalized.id);
          projectHiddenMemoryNodeToEvents(normalized, out, replayState, ev.ts);
        } else {
          out.push({ ...ev, node: normalized } as AgrexEvent);
        }
      }
    } else if (
      (ev.type === "node_update" || ev.type === "node_remove") &&
      typeof ev.id === "string" &&
      hiddenIds.has(ev.id)
    ) {
      if (ev.type === "node_remove") hiddenIds.delete(ev.id);
    } else if (ev.type === "edge_add") {
      const edge = ev.edge as AgrexEdge | undefined;
      if (!edge || !edgeTouchesHiddenNode(edge, hiddenIds)) out.push(ev);
    } else if (ev.type === "state_sync") {
      hiddenIds.clear();
      resetReplaySanitizerState(replayState);
      const snapshot = sanitizeSnapshot(
        (ev.nodes as AgrexNode[] | undefined) ?? [],
        (ev.edges as AgrexEdge[] | undefined) ?? [],
        hiddenIds,
        replayState,
      );
      out.push({ ...ev, ...snapshot } as AgrexEvent);
    } else if (ev.type === "graph_clear" || ev.type === "clear") {
      hiddenIds.clear();
      resetReplaySanitizerState(replayState);
      out.push(ev);
    } else {
      out.push(ev);
    }
  }

  return out;
}

export const labReducers: Record<string, EventReducer> = {
  node_add(store, ev) {
    const node = ev.node as AgrexNode | undefined;
    if (!node) return;
    const normalized = normalizeLiveNode(node);
    if (shouldHideNode(normalized)) {
      hiddenNodeIds.add(normalized.id);
      projectHiddenMemoryNodeLive(store, normalized);
      return;
    }
    store.addNode(normalized);
  },
  node_update(store, ev) {
    const id = ev.id;
    if (typeof id !== "string" || hiddenNodeIds.has(id)) return;
    const updates: Partial<Pick<AgrexNode, "status" | "label" | "metadata">> = {};
    if ("status" in ev) updates.status = ev.status as AgrexNode["status"];
    if ("label" in ev) updates.label = ev.label as string;
    if ("metadata" in ev) updates.metadata = ev.metadata as AgrexNode["metadata"];
    store.updateNode(id, updates);
  },
  node_remove(store, ev) {
    const id = ev.id;
    if (typeof id !== "string") return;
    if (hiddenNodeIds.has(id)) {
      hiddenNodeIds.delete(id);
      return;
    }
    store.removeNode(id);
  },
  edge_add(store, ev) {
    const edge = ev.edge as AgrexEdge | undefined;
    if (edge && !edgeTouchesHiddenNode(edge, hiddenNodeIds)) store.addEdge(edge);
  },
  clear(store) {
    resetLiveSanitizerState();
    store.clear();
  },
  graph_clear(store) {
    resetLiveSanitizerState();
    store.clear();
  },
  state_sync(store, ev) {
    resetLiveSanitizerState();
    const liveState = createSanitizerState();
    const { nodes, edges } = sanitizeSnapshot(
      (ev.nodes as AgrexNode[] | undefined) ?? [],
      (ev.edges as AgrexEdge[] | undefined) ?? [],
      hiddenNodeIds,
      liveState,
    );
    lastBuilderParentId = liveState.lastBuilderParentId;
    for (const node of nodes) {
      if (node.type === "database") liveDbNodeIds.add(node.id);
    }
    for (const edge of edges) {
      if (edge.type?.startsWith("memory_")) liveMemoryEdgeIds.add(edge.id);
    }
    store.loadJSON({ nodes, edges });
  },
};

export interface StageMarker extends AgrexMarker {
  kind: "stage";
  stage: Stage;
}

export interface ReviewMarker extends AgrexMarker {
  kind: "review";
  stage: Stage;
}

const REVIEW_MARKER_PREFIX = "review_";

/**
 * Extract stage + review markers from the agrex trace.
 *
 * - `stage` events become stage markers on the timeline (cursor at the index
 *   of the stage event itself).
 * - `marker` events whose `kind` starts with `review_` become yellow review
 *   markers (cursor at the prompt index).
 */
export function extractLabMarkers(events: AgrexEvent[]): AgrexMarker[] {
  const out: AgrexMarker[] = [];
  for (let i = 0; i < events.length; i++) {
    const ev = events[i];
    if (ev.type === "stage") {
      const label = String(ev.label ?? "");
      const m: StageMarker = {
        cursor: i,
        kind: "stage",
        label,
        stage: label as Stage,
      };
      out.push(m);
    } else if (
      ev.type === "marker" &&
      typeof ev.kind === "string" &&
      ev.kind.startsWith(REVIEW_MARKER_PREFIX)
    ) {
      const stage = ev.kind.slice(REVIEW_MARKER_PREFIX.length) as Stage;
      const m: ReviewMarker = {
        cursor: i,
        kind: "review",
        label: `Review: ${stage}`,
        color: typeof ev.color === "string" ? ev.color : "#fbbf24",
        stage,
      };
      out.push(m);
    }
  }
  return out;
}

// Step boundaries: advance one visible graph delta per step. Start from the
// agrex defaults and add `stage` events so scrubbing aligns with pipeline
// phases.
const EXTRA_BOUNDARY_TYPES = new Set(["stage", "graph_clear", "state_sync"]);

export function labStepBoundaries(events: AgrexEvent[]): number[] {
  const boundaries = new Set<number>(defaultStepBoundaries(events));
  for (let i = 0; i < events.length; i++) {
    if (EXTRA_BOUNDARY_TYPES.has(events[i].type)) boundaries.add(i + 1);
  }
  return [...boundaries].sort((a, b) => a - b);
}

/**
 * Fetch and parse the agrex trace.jsonl for a run.
 */
export async function fetchRunTrace(runId: string): Promise<AgrexEvent[]> {
  const resp = await fetch(`/api/runs/${runId}/trace`);
  if (!resp.ok) throw new Error(`Failed to load trace for run ${runId}`);
  const text = await resp.text();
  const events = text
    .split("\n")
    .filter((ln) => ln.trim())
    .map((ln) => JSON.parse(ln) as AgrexEvent);
  return sanitizeLabTraceEvents(events);
}
