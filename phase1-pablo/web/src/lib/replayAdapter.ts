import {
  defaultStepBoundaries,
  type AgrexEdge,
  type AgrexEvent,
  type AgrexMarker,
  type AgrexNode,
  type EventReducer,
} from "@ppazosp/agrex";
import type { Stage } from "../types";

// The backend emits its own GraphNode / GraphEdge shape (`kind`, `parent_id`,
// `meta`). Agrex renders from AgrexNode shape (`type`, `parentId`,
// `metadata`) and derives parent-child edges from `parentId`. Translating in
// the reducers keeps `replay.instance` in Agrex's canonical shape, so we can
// hand the whole `replay` to `<Agrex>` and let it render + embed the timeline
// with no app-side transformation layer.

interface BackendNode {
  id: string;
  kind: string;
  label: string;
  parent_id?: string;
  status?: AgrexNode["status"];
  meta?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

interface BackendEdge {
  source: string;
  target: string;
  edge_kind?: "spawn" | "read" | "write" | "layout";
}

export function toAgrexNode(n: BackendNode): AgrexNode {
  // Agrex resolves tool icons via `toolIcons[node.label]`. labTFG's tool
  // nodes carry a filename/query as their descriptive label, so we promote
  // `meta.toolType` to the Agrex label and keep the original in metadata
  // under `displayLabel` for renderers/tooltips.
  const toolType = n.kind === "tool" ? (n.meta as Record<string, unknown> | undefined)?.toolType : undefined;
  const label = typeof toolType === "string" ? toolType : n.label;
  return {
    id: n.id,
    type: n.kind,
    label,
    parentId: n.parent_id,
    status: n.status,
    metadata: {
      ...(n.meta ?? {}),
      ...(n.metadata ?? {}),
      displayLabel: n.label,
    },
  };
}

export function toAgrexEdge(e: BackendEdge): AgrexEdge | null {
  // Spawn edges are implicit — Agrex derives parent→child relations from
  // `parentId`. `layout` edges are invisible positioning hints in labTFG and
  // not something Agrex understands. Drop both.
  if (!e.edge_kind || e.edge_kind === "spawn" || e.edge_kind === "layout") return null;
  return {
    id: `${e.source}-${e.target}`,
    source: e.source,
    target: e.target,
    type: e.edge_kind,
  };
}

export const labReducers: Record<string, EventReducer> = {
  node_add(store, ev) {
    const node = ev.node as BackendNode | undefined;
    if (node) store.addNode(toAgrexNode(node));
  },
  edge_add(store, ev) {
    const edge = ev.edge as BackendEdge | undefined;
    const mapped = edge ? toAgrexEdge(edge) : null;
    if (mapped) store.addEdge(mapped);
  },
  graph_clear(store) {
    store.clear();
  },
  state_sync(store, ev) {
    const nodes = ((ev.nodes as BackendNode[] | undefined) ?? []).map(toAgrexNode);
    const edges = ((ev.edges as BackendEdge[] | undefined) ?? [])
      .map(toAgrexEdge)
      .filter((e): e is AgrexEdge => e !== null);
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
  approved: boolean | null;
}

/**
 * Extract stage + review markers from the event log.
 *
 * Review markers are pinned at the cursor of the matching `review_request`
 * (not the decision) so the timeline highlights where the reviewer was
 * prompted, even if the run was cancelled before a decision landed.
 */
export function extractLabMarkers(events: AgrexEvent[]): AgrexMarker[] {
  const out: AgrexMarker[] = [];
  const pendingReview: { index: number; stage: Stage }[] = [];

  for (let i = 0; i < events.length; i++) {
    const ev = events[i];
    if (ev.type === "stage_change" && ev.status === "running") {
      const m: StageMarker = {
        cursor: i,
        kind: "stage",
        label: String(ev.stage),
        stage: ev.stage as Stage,
      };
      out.push(m);
    } else if (ev.type === "review_request") {
      pendingReview.push({ index: i, stage: ev.stage as Stage });
    } else if (ev.type === "review_decision") {
      const match = pendingReview.pop();
      const approved = isAllApproved(ev.approved);
      const stage = (match?.stage ?? ev.stage) as Stage;
      const m: ReviewMarker = {
        cursor: match ? match.index : i,
        kind: "review",
        label: `Review: ${stage} (${approved === true ? "approved" : approved === false ? "rejected" : "incomplete"})`,
        color: "#fbbf24",
        stage,
        approved,
      };
      out.push(m);
    }
  }
  for (const { index, stage } of pendingReview) {
    const m: ReviewMarker = {
      cursor: index,
      kind: "review",
      label: `Review: ${stage} (incomplete)`,
      color: "#fbbf24",
      stage,
      approved: null,
    };
    out.push(m);
  }
  out.sort((a, b) => a.cursor - b.cursor);
  return out;
}

function isAllApproved(approved: unknown): boolean | null {
  if (!approved || typeof approved !== "object") return null;
  const vals = Object.values(approved as Record<string, unknown>);
  if (vals.length === 0) return null;
  if (vals.every((v) => v === true)) return true;
  if (vals.every((v) => v === false)) return false;
  return null;
}

// Step boundaries: advance one visible graph delta per step. Start from the
// agrex defaults (node/edge mutations + `clear`) and add labTFG-specific
// events so scrubbing a decision-lab run lines up with pipeline phases.
const EXTRA_BOUNDARY_TYPES = new Set(["stage_change", "graph_clear", "state_sync"]);

export function labStepBoundaries(events: AgrexEvent[]): number[] {
  const boundaries = new Set<number>(defaultStepBoundaries(events));
  for (let i = 0; i < events.length; i++) {
    if (EXTRA_BOUNDARY_TYPES.has(events[i].type)) boundaries.add(i + 1);
  }
  return [...boundaries].sort((a, b) => a - b);
}

/**
 * Fetches and parses an NDJSON run log from the backend.
 *
 * Also rewrites legacy `node_add` events so the spawned node carries
 * `parent_id` inline — older persisted runs relied on a following spawn
 * `edge_add` to establish the parent relationship, which worked for burst
 * reduction but broke incremental replay (the node_add applied first, then
 * the layout locked its position as a root before the edge arrived). New
 * runs from the current backend already emit `parent_id` inline, so this
 * pass is a no-op for them.
 */
export async function fetchRunEvents(runId: string): Promise<AgrexEvent[]> {
  const resp = await fetch(`/api/runs/${runId}/events`);
  if (!resp.ok) throw new Error(`Failed to load run ${runId}`);
  const text = await resp.text();
  const events = text
    .split("\n")
    .filter((ln) => ln.trim())
    .map((ln) => JSON.parse(ln) as AgrexEvent);
  return injectSpawnParents(events);
}

/**
 * Legacy-log compatibility: given a full event log, return a copy where
 * each `node_add` whose target later appears as the target of a spawn
 * `edge_add` carries `parent_id` on its node payload. No-op for logs where
 * the backend already emits `parent_id` inline.
 */
export function injectSpawnParents(events: AgrexEvent[]): AgrexEvent[] {
  const spawnParent = new Map<string, string>(); // target node id → source node id
  for (const ev of events) {
    if (ev.type === "edge_add") {
      const edge = ev.edge as { source?: string; target?: string; edge_kind?: string } | undefined;
      if (
        edge &&
        (edge.edge_kind === "spawn" || edge.edge_kind === undefined) &&
        edge.source &&
        edge.target &&
        !spawnParent.has(edge.target)
      ) {
        spawnParent.set(edge.target, edge.source);
      }
    }
  }
  if (spawnParent.size === 0) return events;
  return events.map((ev) => {
    if (ev.type !== "node_add") return ev;
    const node = ev.node as { id?: string; parent_id?: string } | undefined;
    if (!node?.id || node.parent_id) return ev;
    const pid = spawnParent.get(node.id);
    if (!pid) return ev;
    return { ...ev, node: { ...node, parent_id: pid } };
  });
}
