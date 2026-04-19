import type { AgrexEvent, AgrexMarker, EventReducer } from "@ppazosp/agrex";
import type { Stage } from "../types";

// labTFG's event shapes are richer than agrex's canonical set:
// - edges arrive without an `id` (source/target pair is the key)
// - `graph_clear` and `state_sync` are mutation events agrex doesn't know about
// - nodes carry `parent_id` / `kind`, not `parentId` / `type`
// These reducers bridge the two so the agrex store mirrors the live graph.

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

// Step boundaries: advance one visible graph delta per step. The agrex default
// only counts mutation events; this version also includes `stage_change` and
// `graph_clear` so scrubbing a decision-lab run lines up with pipeline phases.
const VISIBLE_TYPES = new Set([
  "node_add",
  "node_update",
  "edge_add",
  "stage_change",
  "graph_clear",
  "state_sync",
]);

export function labStepBoundaries(events: AgrexEvent[]): number[] {
  const out: number[] = [];
  for (let i = 0; i < events.length; i++) {
    if (VISIBLE_TYPES.has(events[i].type)) out.push(i + 1);
  }
  return out;
}

/**
 * Fetches and parses an NDJSON run log from the backend.
 * Replaces the transport code that used to live in useReplay.
 */
export async function fetchRunEvents(runId: string): Promise<AgrexEvent[]> {
  const resp = await fetch(`/api/runs/${runId}/events`);
  if (!resp.ok) throw new Error(`Failed to load run ${runId}`);
  const text = await resp.text();
  return text
    .split("\n")
    .filter((ln) => ln.trim())
    .map((ln) => JSON.parse(ln) as AgrexEvent);
}
