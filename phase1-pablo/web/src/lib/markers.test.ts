import { describe, it, expect } from "vitest";
import { extractMarkers } from "./markers";
import { Stage } from "../types";

describe("extractMarkers", () => {
  it("captures each running stage_change as a marker", () => {
    const events = [
      { ts: 1, type: "run_start" },
      { ts: 2, type: "stage_change", stage: Stage.RESEARCH, status: "running" },
      { ts: 3, type: "node_add", node: {} },
      { ts: 4, type: "stage_change", stage: Stage.REVIEW_RESEARCH, status: "running" },
      { ts: 5, type: "stage_change", stage: Stage.FORMALIZE, status: "running" },
    ];
    const { stageMarkers } = extractMarkers(events);
    expect(stageMarkers.map((m) => m.cursor)).toEqual([1, 3, 4]);
    expect(stageMarkers.map((m) => m.stage)).toEqual([
      Stage.RESEARCH,
      Stage.REVIEW_RESEARCH,
      Stage.FORMALIZE,
    ]);
  });

  it("pairs review_request with review_decision when present", () => {
    const events = [
      { ts: 1, type: "review_request", stage: Stage.REVIEW_RESEARCH },
      { ts: 2, type: "review_decision", stage: Stage.REVIEW_RESEARCH, approved: { a: true } },
      { ts: 3, type: "review_request", stage: Stage.REVIEW_FORMALIZE },
    ];
    const { reviewMarkers } = extractMarkers(events);
    expect(reviewMarkers).toEqual([
      { cursor: 0, stage: Stage.REVIEW_RESEARCH, approved: true },
      { cursor: 2, stage: Stage.REVIEW_FORMALIZE, approved: null },
    ]);
  });
});
