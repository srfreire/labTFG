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
// `parentId`, `metadata`). The reducers are identity passthroughs — agrex's
// own renderer + timeline consume the trace directly.

export const labReducers: Record<string, EventReducer> = {
  node_add(store, ev) {
    const node = ev.node as AgrexNode | undefined;
    if (node) store.addNode(node);
  },
  edge_add(store, ev) {
    const edge = ev.edge as AgrexEdge | undefined;
    if (edge) store.addEdge(edge);
  },
  graph_clear(store) {
    store.clear();
  },
  state_sync(store, ev) {
    const nodes = (ev.nodes as AgrexNode[] | undefined) ?? [];
    const edges = (ev.edges as AgrexEdge[] | undefined) ?? [];
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
  return text
    .split("\n")
    .filter((ln) => ln.trim())
    .map((ln) => JSON.parse(ln) as AgrexEvent);
}
