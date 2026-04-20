import {
  defaultStepBoundaries,
  type AgrexEvent,
  type AgrexMarker,
  type EventReducer,
} from "@ppazosp/agrex";
import type { Stage } from "../types";

// labTFG's event shapes are richer than agrex's canonical set:
// - edges arrive without an `id` (source/target pair is the key)
// - `graph_clear` and `state_sync` are mutation events agrex doesn't know about
// Built-in `node_add` / `node_update` / `node_remove` / `clear` reducers from
// agrex are reused via `composeReducers` (applied automatically by
// `useAgrexReplay`), so we only override what differs.

function edgeWithId(edge: unknown): { id: string; source: string; target: string } & Record<string, unknown> {
  const e = edge as { source: string; target: string } & Record<string, unknown>;
  return { id: `${e.source}-${e.target}`, ...e };
}

export const labReducers: Record<string, EventReducer> = {
  edge_add(store, ev) {
    if (ev.edge) store.addEdge(edgeWithId(ev.edge));
  },
  graph_clear(store) {
    store.clear();
  },
  state_sync(store, ev) {
    const nodes = (ev.nodes as Record<string, unknown>[]) ?? [];
    const edges = ((ev.edges as Record<string, unknown>[]) ?? []).map(edgeWithId);
    // AgrexNode vs labTFG GraphNode: labTFG's custom Graph component renders
    // the stored objects directly, so field-name translation isn't needed.
    store.loadJSON({ nodes: nodes as never, edges });
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
 * Also rewrites `node_add` events so the spawned node carries `parent_id`
 * inline. The backend emits `node_add` first, then a separate spawn
 * `edge_add` — that order works for burst reduction (all events applied
 * atomically, labTFG's Graph builds its parent map from the full edge list)
 * but NOT for incremental reduction: at the moment `node_add` is applied,
 * the spawn edge hasn't arrived yet, so the node carries no parent and the
 * layout drops it as a root. Its position locks before the edge catches up.
 * Scanning the log once at fetch time and baking `parent_id` onto each
 * sub-node eliminates the ordering hazard for all downstream replay paths
 * (load-then-scrub, play-from-start, step-through).
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
 * Given a full event log, return a copy where each `node_add` whose target
 * later appears as the target of a `spawn` edge_add carries `parent_id` on
 * its node payload. Non-matching node_add events pass through unchanged.
 */
export function injectSpawnParents(events: AgrexEvent[]): AgrexEvent[] {
  const spawnParent = new Map<string, string>(); // target node id → source node id
  for (const ev of events) {
    if (ev.type === "edge_add") {
      const edge = ev.edge as { source?: string; target?: string; edge_kind?: string } | undefined;
      if (edge && edge.edge_kind === "spawn" && edge.source && edge.target && !spawnParent.has(edge.target)) {
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
