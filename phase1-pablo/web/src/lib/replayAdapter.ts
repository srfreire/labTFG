import {
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
const MISSING_READ_ERROR_TYPES = new Set([
  "NoSuchKey",
  "FileNotFoundError",
  "NotFound",
  "404",
]);
const hiddenNodeIds = new Set<string>();
const liveDbNodeIds = new Set<string>();
const liveMemoryEdgeIds = new Set<string>();
const liveFileNodeIdsByPath = new Map<string, Set<string>>();
const livePendingReadNodesByPath = new Map<string, AgrexNode[]>();
const liveFileReadEdgeIds = new Set<string>();
let lastBuilderParentId: string | undefined;

type MemoryDbKind = "kg" | "vectors";

interface SanitizerState {
  lastBuilderParentId?: string;
  dbNodeIds: Set<string>;
  memoryEdgeIds: Set<string>;
  fileNodeIdsByPath: Map<string, Set<string>>;
  pendingReadNodesByPath: Map<string, AgrexNode[]>;
  fileReadEdgeIds: Set<string>;
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
    fileNodeIdsByPath: new Map<string, Set<string>>(),
    pendingReadNodesByPath: new Map<string, AgrexNode[]>(),
    fileReadEdgeIds: new Set<string>(),
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
    isHumanReviewToolNode(node) ||
    isReadFileNode(node) ||
    isNoisyMissingReadFileNode(node) ||
    isMemoryReadNode(node) ||
    memoryOutputDbKind(node) !== undefined
  );
}

function isHumanReviewToolNode(node: AgrexNode): boolean {
  if (node.type !== "tool") return false;
  return node.id.startsWith("human_review:") || nodeToolName(node).startsWith("review_");
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

function nodeStorageKey(node: AgrexNode): string | undefined {
  const metadata = node.metadata as Record<string, unknown> | undefined;
  if (typeof metadata?.s3_key === "string") return metadata.s3_key;
  if (typeof metadata?.key === "string") return metadata.key;
  return undefined;
}

function normalizeReadablePath(path: string): string {
  return path.replace(/^\.?\//, "").replace(/\/+/g, "/");
}

function filePathAliases(node: AgrexNode): string[] {
  if (node.type !== "file") return [];

  const aliases = new Set<string>();
  const metadataPath = nodeMetadataPath(node);
  const storageKey = nodeStorageKey(node);

  if (metadataPath) aliases.add(normalizeReadablePath(metadataPath));
  if (storageKey) {
    const normalized = normalizeReadablePath(storageKey);
    aliases.add(normalized);
    for (const prefix of ["research", "models"]) {
      const match = normalized.match(new RegExp(`^${prefix}/[^/]+/(.+)$`));
      if (match) aliases.add(normalizeReadablePath(match[1]));
    }
  }

  return [...aliases];
}

function isReadFileNode(node: AgrexNode): boolean {
  return node.type === "tool" && nodeToolName(node) === "read_file";
}

function metadataErrorType(metadata: Record<string, unknown> | undefined): string {
  const direct = metadata?.error_type;
  if (typeof direct === "string") return direct;
  const error = metadata?.error;
  if (error && typeof error === "object" && "name" in error) {
    const name = (error as Record<string, unknown>).name;
    if (typeof name === "string") return name;
  }
  return "";
}

function isMissingReadErrorMetadata(
  metadata: Record<string, unknown> | undefined,
): boolean {
  return MISSING_READ_ERROR_TYPES.has(metadataErrorType(metadata));
}

function isNoisyMissingReadFileNode(node: AgrexNode): boolean {
  const metadata = node.metadata as Record<string, unknown> | undefined;
  return (
    isReadFileNode(node) &&
    node.status === "error" &&
    isMissingReadErrorMetadata(metadata)
  );
}

function sanitizeErrorMetadata(
  metadata: Record<string, unknown> | undefined,
): Record<string, unknown> | undefined {
  if (!metadata) return metadata;
  const error = metadata.error;
  if (!error || typeof error !== "object") return metadata;
  const raw = error as Record<string, unknown>;
  const nextError: Record<string, unknown> = {};
  if (typeof raw.name === "string") nextError.name = raw.name;
  if (typeof raw.message === "string") nextError.message = raw.message;
  return { ...metadata, error: nextError };
}

function sanitizeNodeUpdateEvent(ev: AgrexEvent): AgrexEvent {
  const metadata = sanitizeErrorMetadata(
    ev.metadata as Record<string, unknown> | undefined,
  );
  return metadata === ev.metadata ? ev : ({ ...ev, metadata } as AgrexEvent);
}

function collectNoisyHiddenNodeIds(events: AgrexEvent[]): Set<string> {
  const nodeById = new Map<string, AgrexNode>();
  const out = new Set<string>();
  for (const ev of events) {
    if (ev.type === "node_add") {
      const node = ev.node as AgrexNode | undefined;
      if (node) {
        nodeById.set(node.id, node);
        if (isHumanReviewToolNode(node)) out.add(node.id);
      }
      continue;
    }

    if (ev.type !== "node_update" || ev.status !== "error") continue;
    const id = typeof ev.id === "string" ? ev.id : "";
    const node = nodeById.get(id);
    if (!node || !isReadFileNode(node)) continue;
    if (
      isMissingReadErrorMetadata(
        ev.metadata as Record<string, unknown> | undefined,
      )
    ) {
      out.add(id);
    }
  }
  return out;
}

function registerFileNode(node: AgrexNode, state: SanitizerState) {
  for (const alias of filePathAliases(node)) {
    const ids = state.fileNodeIdsByPath.get(alias) ?? new Set<string>();
    ids.add(node.id);
    state.fileNodeIdsByPath.set(alias, ids);
  }
}

function rememberPendingReadNode(node: AgrexNode, state: SanitizerState) {
  const path = nodeMetadataPath(node);
  if (!path) return;
  const normalized = normalizeReadablePath(path);
  const pending = state.pendingReadNodesByPath.get(normalized) ?? [];
  if (!pending.some((readNode) => readNode.id === node.id)) {
    pending.push(node);
  }
  state.pendingReadNodesByPath.set(normalized, pending);
}

function readConsumerId(node: AgrexNode): string | undefined {
  return typeof node.parentId === "string" && node.parentId.length > 0
    ? node.parentId
    : undefined;
}

function fileReadEdge(fileId: string, readNode: AgrexNode): AgrexEdge | undefined {
  const target = readConsumerId(readNode);
  if (!target) return undefined;
  return {
    id: `edge:file-read:${fileId}:${target}`,
    source: fileId,
    target,
    type: "reads",
    label: "reads",
  };
}

function readEdgesForNode(node: AgrexNode, state: SanitizerState): AgrexEdge[] {
  if (!isReadFileNode(node)) return [];
  const path = nodeMetadataPath(node);
  if (!path) return [];
  const fileIds = state.fileNodeIdsByPath.get(normalizeReadablePath(path));
  if (!fileIds || fileIds.size === 0) return [];
  return [...fileIds].flatMap((fileId) => {
    const edge = fileReadEdge(fileId, node);
    return edge ? [edge] : [];
  });
}

function pendingReadEdgesForFileNode(
  node: AgrexNode,
  state: SanitizerState,
): AgrexEdge[] {
  const seenReadNodeIds = new Set<string>();
  const edges: AgrexEdge[] = [];
  for (const alias of filePathAliases(node)) {
    const pending = state.pendingReadNodesByPath.get(alias) ?? [];
    for (const readNode of pending) {
      if (seenReadNodeIds.has(readNode.id)) continue;
      seenReadNodeIds.add(readNode.id);
      const edge = fileReadEdge(node.id, readNode);
      if (edge) edges.push(edge);
    }
    state.pendingReadNodesByPath.delete(alias);
  }
  return edges;
}

function emitFileReadEdgeEvent(
  edge: AgrexEdge,
  out: AgrexEvent[],
  state: SanitizerState,
  ts: number,
) {
  if (state.fileReadEdgeIds.has(edge.id)) return;
  state.fileReadEdgeIds.add(edge.id);
  out.push({ type: "edge_add", ts, edge } as AgrexEvent);
}

function projectVisibleFileReadNodeToEvents(
  node: AgrexNode,
  out: AgrexEvent[],
  state: SanitizerState,
  ts: number,
) {
  if (node.type === "file") {
    registerFileNode(node, state);
    for (const edge of pendingReadEdgesForFileNode(node, state)) {
      emitFileReadEdgeEvent(edge, out, state, ts);
    }
    return;
  }

  if (!isReadFileNode(node)) return;
  const edges = readEdgesForNode(node, state);
  if (edges.length === 0) {
    rememberPendingReadNode(node, state);
    return;
  }
  for (const edge of edges) {
    emitFileReadEdgeEvent(edge, out, state, ts);
  }
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
  liveFileNodeIdsByPath.clear();
  livePendingReadNodesByPath.clear();
  liveFileReadEdgeIds.clear();
  lastBuilderParentId = undefined;
}

function resetReplaySanitizerState(state: SanitizerState) {
  state.lastBuilderParentId = undefined;
  state.dbNodeIds.clear();
  state.memoryEdgeIds.clear();
  state.fileNodeIdsByPath.clear();
  state.pendingReadNodesByPath.clear();
  state.fileReadEdgeIds.clear();
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

function memoryRetrieveEdges(parentId: string): AgrexEdge[] {
  return [
    {
      id: `edge:memory-retrieve:kg:${parentId}`,
      source: MEMORY_DB_NODES.kg.id,
      target: parentId,
      type: "memory_retrieve",
      label: "retrieves",
      collapseOwnerId: MEMORY_DB_NODES.kg.id,
    },
    {
      id: `edge:memory-retrieve:vectors:${parentId}`,
      source: MEMORY_DB_NODES.vectors.id,
      target: parentId,
      type: "memory_retrieve",
      label: "retrieves",
      collapseOwnerId: MEMORY_DB_NODES.vectors.id,
    },
  ];
}

function memoryStoreEdge(kind: MemoryDbKind, parentId: string): AgrexEdge {
  return {
    id: `edge:memory-store:${kind}:${parentId}`,
    source: parentId,
    target: MEMORY_DB_NODES[kind].id,
    type: "memory_store",
    label: "stores",
    collapseOwnerId: MEMORY_DB_NODES[kind].id,
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
      edges: memoryRetrieveEdges(node.parentId),
    };
  }

  const storeKind = memoryOutputDbKind(node);
  if (!storeKind) return undefined;
  if (typeof node.parentId !== "string" || node.parentId.length === 0) {
    return undefined;
  }
  return {
    dbKinds: [storeKind],
    edges: [memoryStoreEdge(storeKind, node.parentId)],
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

function addFileReadSnapshotEdge(
  edge: AgrexEdge,
  out: AgrexEdge[],
  state: SanitizerState,
) {
  if (state.fileReadEdgeIds.has(edge.id)) return;
  state.fileReadEdgeIds.add(edge.id);
  out.push(edge);
}

function projectVisibleFileReadNodeToSnapshot(
  node: AgrexNode,
  edges: AgrexEdge[],
  state: SanitizerState,
) {
  for (const edge of readEdgesForNode(node, state)) {
    addFileReadSnapshotEdge(edge, edges, state);
  }
}

function removePendingReadNode(
  nodeId: string,
  pendingByPath: Map<string, AgrexNode[]>,
) {
  for (const [path, pending] of pendingByPath.entries()) {
    const next = pending.filter((node) => node.id !== nodeId);
    if (next.length === 0) {
      pendingByPath.delete(path);
    } else if (next.length !== pending.length) {
      pendingByPath.set(path, next);
    }
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

function addLiveFileAlias(alias: string, nodeId: string) {
  const ids = liveFileNodeIdsByPath.get(alias) ?? new Set<string>();
  ids.add(nodeId);
  liveFileNodeIdsByPath.set(alias, ids);
}

function addLiveFileReadEdge(
  store: Parameters<EventReducer>[0],
  edge: AgrexEdge,
) {
  if (liveFileReadEdgeIds.has(edge.id)) return;
  liveFileReadEdgeIds.add(edge.id);
  store.addEdge(edge);
}

function rememberLivePendingReadNode(node: AgrexNode) {
  const path = nodeMetadataPath(node);
  if (!path) return;
  const normalized = normalizeReadablePath(path);
  const pending = livePendingReadNodesByPath.get(normalized) ?? [];
  if (!pending.some((readNode) => readNode.id === node.id)) {
    pending.push(node);
  }
  livePendingReadNodesByPath.set(normalized, pending);
}

function projectVisibleFileReadNodeLive(
  store: Parameters<EventReducer>[0],
  node: AgrexNode,
) {
  if (node.type === "file") {
    const aliases = filePathAliases(node);
    for (const alias of aliases) addLiveFileAlias(alias, node.id);

    const seenReadNodeIds = new Set<string>();
    for (const alias of aliases) {
      const pending = livePendingReadNodesByPath.get(alias) ?? [];
      for (const readNode of pending) {
        if (seenReadNodeIds.has(readNode.id)) continue;
        seenReadNodeIds.add(readNode.id);
        const edge = fileReadEdge(node.id, readNode);
        if (edge) addLiveFileReadEdge(store, edge);
      }
      livePendingReadNodesByPath.delete(alias);
    }
    return;
  }

  if (!isReadFileNode(node)) return;
  const path = nodeMetadataPath(node);
  if (!path) return;
  const fileIds = liveFileNodeIdsByPath.get(normalizeReadablePath(path));
  if (!fileIds || fileIds.size === 0) {
    rememberLivePendingReadNode(node);
    return;
  }
  for (const fileId of fileIds) {
    const edge = fileReadEdge(fileId, node);
    if (edge) addLiveFileReadEdge(store, edge);
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
  const hiddenReadNodes: AgrexNode[] = [];
  for (const node of nodes) {
    const normalized = normalizeSnapshotNode(node, state);
    if (shouldHideNode(normalized)) {
      hiddenIds.add(normalized.id);
      projectHiddenMemoryNodeToSnapshot(normalized, dbNodes, projectedEdges, state);
      if (isReadFileNode(normalized) && !isNoisyMissingReadFileNode(normalized)) {
        hiddenReadNodes.push(normalized);
      }
    } else {
      visibleNodes.push(normalized);
    }
  }
  for (const node of visibleNodes) {
    registerFileNode(node, state);
  }
  for (const node of hiddenReadNodes) {
    projectVisibleFileReadNodeToSnapshot(node, projectedEdges, state);
  }
  for (const node of visibleNodes) {
    projectVisibleFileReadNodeToSnapshot(node, projectedEdges, state);
  }
  const visibleEdges = edges.filter((edge) => !edgeTouchesHiddenNode(edge, hiddenIds));
  return { nodes: [...visibleNodes, ...dbNodes], edges: [...visibleEdges, ...projectedEdges] };
}

function recoveredDeepResearcherNode(id: string): AgrexNode | undefined {
  const match = id.match(/^deep_researcher:(.+)$/);
  if (!match) return undefined;
  const paradigm = match[1];
  return {
    id,
    type: "sub_agent",
    label: `DeepResearcher: ${paradigm}`,
    parentId: "researcher",
    status: "running",
    metadata: { paradigm, recovered: true },
  };
}

export function sanitizeLabTraceEvents(events: AgrexEvent[]): AgrexEvent[] {
  const noisyHiddenIds = collectNoisyHiddenNodeIds(events);
  const hiddenIds = new Set(noisyHiddenIds);
  const replayState = createSanitizerState();
  const out: AgrexEvent[] = [];
  const visibleNodeIds = new Set<string>();
  const recoveredNodeIds = new Set<string>();

  const ensureRecoveredDeepResearcher = (id: string, ts: number) => {
    if (visibleNodeIds.has(id)) return;
    const node = recoveredDeepResearcherNode(id);
    if (!node) return;
    visibleNodeIds.add(id);
    recoveredNodeIds.add(id);
    out.push({ type: "node_add", ts, node } as AgrexEvent);
  };

  for (const ev of events) {
    if (ev.type === "node_add") {
      const node = ev.node as AgrexNode | undefined;
      if (!node) {
        out.push(ev);
      } else {
        const normalized = normalizeReplayNode(node, replayState);
        if (typeof normalized.parentId === "string") {
          ensureRecoveredDeepResearcher(normalized.parentId, ev.ts);
        }
        if (hiddenIds.has(normalized.id) || shouldHideNode(normalized)) {
          hiddenIds.add(normalized.id);
          projectHiddenMemoryNodeToEvents(normalized, out, replayState, ev.ts);
          if (!noisyHiddenIds.has(normalized.id)) {
            projectVisibleFileReadNodeToEvents(normalized, out, replayState, ev.ts);
          }
        } else if (visibleNodeIds.has(normalized.id)) {
          if (recoveredNodeIds.has(normalized.id)) {
            out.push({
              type: "node_update",
              ts: ev.ts,
              id: normalized.id,
              status: normalized.status,
              label: normalized.label,
              metadata: normalized.metadata,
            } as AgrexEvent);
            recoveredNodeIds.delete(normalized.id);
          }
        } else {
          visibleNodeIds.add(normalized.id);
          out.push({ ...ev, node: normalized } as AgrexEvent);
          projectVisibleFileReadNodeToEvents(normalized, out, replayState, ev.ts);
        }
      }
    } else if (
      (ev.type === "node_update" || ev.type === "node_remove") &&
      typeof ev.id === "string" &&
      hiddenIds.has(ev.id)
    ) {
      if (ev.type === "node_remove") hiddenIds.delete(ev.id);
    } else if (ev.type === "node_update") {
      if (typeof ev.id === "string") {
        ensureRecoveredDeepResearcher(ev.id, ev.ts);
      }
      out.push(sanitizeNodeUpdateEvent(ev));
    } else if (ev.type === "edge_add") {
      const edge = ev.edge as AgrexEdge | undefined;
      if (!edge || !edgeTouchesHiddenNode(edge, hiddenIds)) out.push(ev);
    } else if (ev.type === "node_remove") {
      if (typeof ev.id === "string") {
        visibleNodeIds.delete(ev.id);
        recoveredNodeIds.delete(ev.id);
      }
      out.push(ev);
    } else if (ev.type === "state_sync") {
      hiddenIds.clear();
      resetReplaySanitizerState(replayState);
      visibleNodeIds.clear();
      recoveredNodeIds.clear();
      const snapshot = sanitizeSnapshot(
        (ev.nodes as AgrexNode[] | undefined) ?? [],
        (ev.edges as AgrexEdge[] | undefined) ?? [],
        hiddenIds,
        replayState,
      );
      for (const node of snapshot.nodes) visibleNodeIds.add(node.id);
      out.push({ ...ev, ...snapshot } as AgrexEvent);
    } else if (ev.type === "graph_clear" || ev.type === "clear") {
      hiddenIds.clear();
      resetReplaySanitizerState(replayState);
      visibleNodeIds.clear();
      recoveredNodeIds.clear();
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
      projectVisibleFileReadNodeLive(store, normalized);
      return;
    }
    store.addNode(normalized);
    projectVisibleFileReadNodeLive(store, normalized);
  },
  node_update(store, ev) {
    const id = ev.id;
    if (typeof id !== "string") return;
    if (
      ev.status === "error" &&
      isMissingReadErrorMetadata(ev.metadata as Record<string, unknown> | undefined)
    ) {
      hiddenNodeIds.add(id);
      removePendingReadNode(id, livePendingReadNodesByPath);
      store.removeNode(id);
      return;
    }
    if (hiddenNodeIds.has(id)) return;
    const updates: Partial<Pick<AgrexNode, "status" | "label" | "metadata">> = {};
    if ("status" in ev) updates.status = ev.status as AgrexNode["status"];
    if ("label" in ev) updates.label = ev.label as string;
    if ("metadata" in ev) {
      updates.metadata = sanitizeErrorMetadata(
        ev.metadata as Record<string, unknown> | undefined,
      ) as AgrexNode["metadata"];
    }
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
      if (node.type === "file") {
        for (const alias of filePathAliases(node)) {
          addLiveFileAlias(alias, node.id);
        }
      }
    }
    for (const edge of edges) {
      if (edge.type?.startsWith("memory_")) liveMemoryEdgeIds.add(edge.id);
      if (edge.type === "reads") liveFileReadEdgeIds.add(edge.id);
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

// Step boundaries: advance one visible graph delta per step. Metadata-only
// node updates carry token and cost telemetry, but do not change the graph
// rendered on screen, so they must not create empty replay steps.
const GRAPH_BOUNDARY_TYPES = new Set([
  "node_add",
  "node_remove",
  "edge_add",
  "edge_remove",
  "clear",
]);
const EXTRA_BOUNDARY_TYPES = new Set(["graph_clear", "state_sync"]);

export function labStepBoundaries(events: AgrexEvent[]): number[] {
  const boundaries = new Set<number>();
  for (let i = 0; i < events.length; i++) {
    const event = events[i];
    const visibleNodeUpdate =
      event.type === "node_update" &&
      ("status" in event || "label" in event);
    if (
      GRAPH_BOUNDARY_TYPES.has(event.type) ||
      EXTRA_BOUNDARY_TYPES.has(event.type) ||
      visibleNodeUpdate
    ) {
      boundaries.add(i + 1);
    }
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
