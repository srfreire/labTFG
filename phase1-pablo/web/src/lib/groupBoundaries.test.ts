import { describe, it, expect } from "vitest";
import { groupBoundaries } from "./groupBoundaries";

describe("groupBoundaries", () => {
  it("splits on agent_status idle and on stage_change", () => {
    const events = [
      { ts: 1, type: "agent_status", agent: "researcher", status: "working" },
      { ts: 2, type: "node_add", node: {} },
      { ts: 3, type: "agent_status", agent: "researcher", status: "idle" },
      { ts: 4, type: "stage_change", stage: "formalize", status: "running" },
      { ts: 5, type: "node_add", node: {} },
    ];
    expect(groupBoundaries(events)).toEqual([3, 4, 5]);
  });

  it("handles an empty stream", () => {
    expect(groupBoundaries([])).toEqual([]);
  });

  it("emits a final boundary at events.length", () => {
    const events = [{ ts: 1, type: "node_add", node: {} }];
    expect(groupBoundaries(events)).toEqual([1]);
  });
});
