import { describe, it, expect } from "vitest";
import { deriveGraphState } from "./deriveGraphState";
import { Stage } from "../types";

const nodeA = {
  id: "a",
  kind: "agent" as const,
  label: "researcher",
  status: "running" as const,
  meta: {},
};

describe("deriveGraphState", () => {
  it("folds node_add, stage_change, node_update", () => {
    const events = [
      { ts: 1, type: "run_start", run_id: "r1" },
      { ts: 2, type: "stage_change", stage: Stage.RESEARCH, status: "running" },
      { ts: 3, type: "node_add", node: nodeA },
      { ts: 4, type: "node_update", id: "a", status: "done" },
    ];
    const state = deriveGraphState(events);
    expect(state.currentStage).toBe(Stage.RESEARCH);
    expect(state.nodes).toHaveLength(1);
    expect(state.nodes[0].status).toBe("done");
  });

  it("is deterministic — same inputs give same output", () => {
    const events = [
      { ts: 1, type: "node_add", node: nodeA },
      { ts: 2, type: "edge_add", edge: { source: "a", target: "b" } },
    ];
    expect(deriveGraphState(events)).toEqual(deriveGraphState(events));
  });

  it("folds a partial prefix", () => {
    const events = [
      { ts: 1, type: "node_add", node: nodeA },
      { ts: 2, type: "node_update", id: "a", status: "done" },
    ];
    const partial = deriveGraphState(events.slice(0, 1));
    expect(partial.nodes[0].status).toBe("running");
  });
});
