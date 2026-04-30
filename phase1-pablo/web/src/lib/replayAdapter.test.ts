import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { AgrexEvent } from "@ppazosp/agrex";
import {
  extractLabMarkers,
  fetchRunTrace,
  labReducers,
  labStepBoundaries,
} from "./replayAdapter";
import { Stage } from "../types";

// Build an AgrexEvent fixture without the verbosity of stamping `ts` everywhere.
function ev(
  type: string,
  extra: Record<string, unknown> = {},
  ts = 0,
): AgrexEvent {
  return { type, ts, ...extra } as AgrexEvent;
}

describe("extractLabMarkers", () => {
  it("emits a stage marker per stage event with the event's index as cursor", () => {
    const events = [
      ev("stage", { label: Stage.RESEARCH }),
      ev("node_add", { node: { id: "a", type: "agent", label: "Researcher" } }),
      ev("stage", { label: Stage.FORMALIZE }),
    ];

    expect(extractLabMarkers(events)).toEqual([
      {
        cursor: 0,
        kind: "stage",
        label: Stage.RESEARCH,
        stage: Stage.RESEARCH,
      },
      {
        cursor: 2,
        kind: "stage",
        label: Stage.FORMALIZE,
        stage: Stage.FORMALIZE,
      },
    ]);
  });

  it("falls back to an empty label string when stage event has no label", () => {
    const events = [ev("stage")];
    expect(extractLabMarkers(events)[0]).toMatchObject({
      kind: "stage",
      label: "",
    });
  });

  it("turns review_<stage> markers into yellow review markers with the stripped stage", () => {
    const events = [ev("marker", { kind: "review_research" })];

    const markers = extractLabMarkers(events);
    expect(markers).toHaveLength(1);
    expect(markers[0]).toEqual({
      cursor: 0,
      kind: "review",
      label: "Review: research",
      color: "#fbbf24",
      stage: "research",
    });
  });

  it("uses the marker event's color when one is provided", () => {
    const events = [ev("marker", { kind: "review_build", color: "#ff00ff" })];
    expect(extractLabMarkers(events)[0]).toMatchObject({ color: "#ff00ff" });
  });

  it("ignores marker events whose kind is missing or non-review_", () => {
    const events = [
      ev("marker", { kind: "annotation" }),
      ev("marker", { kind: "" }),
      ev("marker"),
    ];
    expect(extractLabMarkers(events)).toEqual([]);
  });

  it("ignores events that are neither stage nor marker", () => {
    const events = [
      ev("node_add"),
      ev("edge_add"),
      ev("graph_clear"),
      ev("state_sync"),
    ];
    expect(extractLabMarkers(events)).toEqual([]);
  });
});

describe("labStepBoundaries", () => {
  it("emits a boundary after each stage / graph_clear / state_sync event", () => {
    const events = [
      ev("stage", { label: Stage.RESEARCH }),
      ev("graph_clear"),
      ev("state_sync", { nodes: [], edges: [] }),
    ];
    expect(labStepBoundaries(events)).toEqual([1, 2, 3]);
  });

  it("includes default agrex boundaries for graph deltas", () => {
    const events = [
      ev("node_add", { node: { id: "a", type: "agent", label: "x" } }),
      ev("edge_add", { edge: { id: "e", source: "a", target: "b" } }),
    ];
    const boundaries = labStepBoundaries(events);
    expect(boundaries).toContain(1);
    expect(boundaries).toContain(2);
  });

  it("returns sorted, deduplicated boundary indices", () => {
    const events = [
      ev("node_add", { node: { id: "a", type: "agent", label: "x" } }),
      ev("stage", { label: Stage.RESEARCH }),
      ev("graph_clear"),
    ];
    const boundaries = labStepBoundaries(events);
    const expected = [...new Set(boundaries)].sort((a, b) => a - b);
    expect(boundaries).toEqual(expected);
  });
});

describe("labReducers", () => {
  function makeStore() {
    return {
      addNode: vi.fn(),
      addNodes: vi.fn(),
      updateNode: vi.fn(),
      removeNode: vi.fn(),
      addEdge: vi.fn(),
      addEdges: vi.fn(),
      removeEdge: vi.fn(),
      clear: vi.fn(),
      loadJSON: vi.fn(),
    };
  }

  it("node_add forwards the canonical node to store.addNode", () => {
    const store = makeStore();
    const node = { id: "a", type: "agent" as const, label: "Researcher" };

    labReducers.node_add(store, ev("node_add", { node }));

    expect(store.addNode).toHaveBeenCalledTimes(1);
    expect(store.addNode).toHaveBeenCalledWith(node);
  });

  it("node_add with no node payload is a no-op", () => {
    const store = makeStore();
    labReducers.node_add(store, ev("node_add"));
    expect(store.addNode).not.toHaveBeenCalled();
  });

  it("edge_add forwards the canonical edge to store.addEdge", () => {
    const store = makeStore();
    const edge = { id: "e1", source: "a", target: "b" };

    labReducers.edge_add(store, ev("edge_add", { edge }));

    expect(store.addEdge).toHaveBeenCalledTimes(1);
    expect(store.addEdge).toHaveBeenCalledWith(edge);
  });

  it("edge_add with no edge payload is a no-op", () => {
    const store = makeStore();
    labReducers.edge_add(store, ev("edge_add"));
    expect(store.addEdge).not.toHaveBeenCalled();
  });

  it("graph_clear empties the store", () => {
    const store = makeStore();
    labReducers.graph_clear(store, ev("graph_clear"));
    expect(store.clear).toHaveBeenCalledTimes(1);
  });

  it("state_sync hydrates the store with snapshot nodes and edges", () => {
    const store = makeStore();
    const nodes = [{ id: "a", type: "agent" as const, label: "x" }];
    const edges = [{ id: "e", source: "a", target: "b" }];

    labReducers.state_sync(store, ev("state_sync", { nodes, edges }));

    expect(store.loadJSON).toHaveBeenCalledWith({ nodes, edges });
  });

  it("state_sync defaults missing fields to empty arrays", () => {
    const store = makeStore();
    labReducers.state_sync(store, ev("state_sync"));
    expect(store.loadJSON).toHaveBeenCalledWith({ nodes: [], edges: [] });
  });
});

describe("fetchRunTrace", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requests the canonical trace URL", async () => {
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response("", { status: 200 }),
    );
    await fetchRunTrace("abc-123");
    expect(globalThis.fetch).toHaveBeenCalledWith("/api/runs/abc-123/trace");
  });

  it("parses each NDJSON line into an AgrexEvent", async () => {
    const body =
      [
        '{"type":"stage","ts":1,"label":"research"}',
        '{"type":"node_add","ts":2}',
      ].join("\n") + "\n";
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(body, { status: 200 }),
    );

    const events = await fetchRunTrace("run-1");

    expect(events).toEqual([
      { type: "stage", ts: 1, label: "research" },
      { type: "node_add", ts: 2 },
    ]);
  });

  it("ignores blank and whitespace-only lines", async () => {
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response('{"type":"stage","ts":1}\n\n   \n', { status: 200 }),
    );
    const events = await fetchRunTrace("run-2");
    expect(events).toHaveLength(1);
  });

  it("throws when the response is not OK", async () => {
    (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response("nope", { status: 404 }),
    );
    await expect(fetchRunTrace("missing")).rejects.toThrow(
      /Failed to load trace/,
    );
  });
});
