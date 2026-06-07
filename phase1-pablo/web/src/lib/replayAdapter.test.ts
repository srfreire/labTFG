import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { AgrexEvent } from "@ppazosp/agrex";
import {
  extractLabMarkers,
  fetchRunTrace,
  labReducers,
  labStepBoundaries,
  sanitizeLabTraceEvents,
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

describe("sanitizeLabTraceEvents", () => {
  it("removes launch_deep_research tool nodes and their updates", () => {
    const events = [
      ev("node_add", {
        node: { id: "launch-1", type: "tool", label: "launch_deep_research" },
      }),
      ev("node_update", { id: "launch-1", status: "done" }),
      ev("node_add", { node: { id: "deep-1", type: "sub_agent", label: "Deep" } }),
    ];

    expect(sanitizeLabTraceEvents(events)).toEqual([
      ev("node_add", { node: { id: "deep-1", type: "sub_agent", label: "Deep" } }),
    ]);
  });

  it("reparents builder tools when a path identifies the formulation", () => {
    const events = [
      ev("node_add", {
        node: {
          id: "tool-1",
          type: "tool",
          label: "run_tests",
          parentId: "builder",
          metadata: { path: "builder/homeostatic/test_pi_controller.py" },
        },
      }),
    ];

    expect(sanitizeLabTraceEvents(events)[0]).toMatchObject({
      node: { parentId: "builder:homeostatic:pi_controller" },
    });
  });

  it("projects legacy builder retrieve_knowledge nodes into DB retrieve edges", () => {
    const events = [
      ev("node_add", {
        node: {
          id: "tool-1",
          type: "tool",
          label: "read_file",
          parentId: "builder",
          metadata: { path: "reasoner/homeostatic/pi_controller.json" },
        },
      }),
      ev("node_add", {
        node: {
          id: "tool-2",
          type: "tool",
          label: "retrieve_knowledge",
          parentId: "builder",
          metadata: { query: "DecisionModel implementation pattern" },
        },
      }),
    ];

    const sanitized = sanitizeLabTraceEvents(events);
    const nodes = sanitized
      .filter((event) => event.type === "node_add")
      .map((event) => event.node);
    const edges = sanitized
      .filter((event) => event.type === "edge_add")
      .map((event) => event.edge);

    expect(nodes).toEqual([
      expect.objectContaining({ id: "tool-1" }),
      expect.objectContaining({ id: "db:knowledge-graph", type: "database" }),
      expect.objectContaining({ id: "db:vector-memory", type: "database" }),
    ]);
    expect(nodes).not.toContainEqual(expect.objectContaining({ id: "tool-2" }));
    expect(edges).toEqual([
      expect.objectContaining({
        id: "edge:memory-retrieve:kg:builder:homeostatic:pi_controller",
        source: "db:knowledge-graph",
        target: "builder:homeostatic:pi_controller",
        type: "memory_retrieve",
      }),
      expect.objectContaining({
        id: "edge:memory-retrieve:vectors:builder:homeostatic:pi_controller",
        source: "db:vector-memory",
        target: "builder:homeostatic:pi_controller",
        type: "memory_retrieve",
      }),
    ]);
  });

  it("projects memory output artifacts into DB store edges", () => {
    const events = [
      ev("node_add", {
        node: { id: "memory_agent:research", type: "sub_agent", label: "Memory" },
      }),
      ev("node_add", {
        node: {
          id: "memory_output:research:kg",
          type: "artifact",
          label: "KG writes: research",
          parentId: "memory_agent:research",
        },
      }),
      ev("edge_add", {
        edge: {
          id: "old-memory-edge",
          source: "memory_agent:research",
          target: "memory_output:research:kg",
        },
      }),
      ev("node_add", {
        node: {
          id: "memory_output:research:facts",
          type: "artifact",
          label: "Memories: research",
          parentId: "memory_agent:research",
        },
      }),
    ];

    const sanitized = sanitizeLabTraceEvents(events);
    const nodeIds = sanitized
      .filter((event) => event.type === "node_add")
      .map((event) => (event.node as { id: string }).id);
    const edges = sanitized
      .filter((event) => event.type === "edge_add")
      .map((event) => event.edge);

    expect(nodeIds).toEqual([
      "memory_agent:research",
      "db:knowledge-graph",
      "db:vector-memory",
    ]);
    expect(edges).toEqual([
      expect.objectContaining({
        id: "edge:memory-store:kg:memory_agent:research",
        source: "memory_agent:research",
        target: "db:knowledge-graph",
        type: "memory_store",
      }),
      expect.objectContaining({
        id: "edge:memory-store:vectors:memory_agent:research",
        source: "memory_agent:research",
        target: "db:vector-memory",
        type: "memory_store",
      }),
    ]);
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

  beforeEach(() => {
    labReducers.graph_clear(makeStore(), ev("graph_clear"));
  });

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

  it("node_add hides launch_deep_research tool nodes", () => {
    const store = makeStore();
    const node = {
      id: "launch-1",
      type: "tool" as const,
      label: "launch_deep_research",
    };

    labReducers.node_add(store, ev("node_add", { node }));
    labReducers.node_update(store, ev("node_update", { id: "launch-1", status: "done" }));

    expect(store.addNode).not.toHaveBeenCalled();
    expect(store.updateNode).not.toHaveBeenCalled();
  });

  it("node_add reparents builder tools when path identifies the formulation", () => {
    const store = makeStore();
    const node = {
      id: "tool-1",
      type: "tool" as const,
      label: "read_file",
      parentId: "builder",
      metadata: { path: "reasoner/homeostatic/pi_controller.json" },
    };

    labReducers.node_add(store, ev("node_add", { node }));

    expect(store.addNode).toHaveBeenCalledWith({
      ...node,
      parentId: "builder:homeostatic:pi_controller",
    });
  });

  it("node_add projects legacy builder retrieve_knowledge into DB retrieve edges", () => {
    const store = makeStore();
    labReducers.node_add(
      store,
      ev("node_add", {
        node: {
          id: "tool-1",
          type: "tool",
          label: "read_file",
          parentId: "builder",
          metadata: { path: "reasoner/homeostatic/pi_controller.json" },
        },
      }),
    );

    const node = {
      id: "tool-2",
      type: "tool" as const,
      label: "retrieve_knowledge",
      parentId: "builder",
      metadata: { query: "DecisionModel implementation pattern" },
    };
    labReducers.node_add(store, ev("node_add", { node }));

    expect(store.addNode).not.toHaveBeenCalledWith(
      expect.objectContaining({ id: "tool-2" }),
    );
    expect(store.addNode).toHaveBeenCalledWith(
      expect.objectContaining({ id: "db:knowledge-graph", type: "database" }),
    );
    expect(store.addNode).toHaveBeenCalledWith(
      expect.objectContaining({ id: "db:vector-memory", type: "database" }),
    );
    expect(store.addEdge).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "edge:memory-retrieve:kg:builder:homeostatic:pi_controller",
        source: "db:knowledge-graph",
        target: "builder:homeostatic:pi_controller",
      }),
    );
    expect(store.addEdge).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "edge:memory-retrieve:vectors:builder:homeostatic:pi_controller",
        source: "db:vector-memory",
        target: "builder:homeostatic:pi_controller",
      }),
    );
  });

  it("node_add projects memory output artifacts into DB store edges", () => {
    const store = makeStore();
    const node = {
      id: "memory_output:research:kg",
      type: "artifact" as const,
      label: "KG writes: research",
      parentId: "memory_agent:research",
    };

    labReducers.node_add(store, ev("node_add", { node }));
    labReducers.node_update(store, ev("node_update", { id: node.id, status: "done" }));

    expect(store.addNode).toHaveBeenCalledWith(
      expect.objectContaining({ id: "db:knowledge-graph", type: "database" }),
    );
    expect(store.addNode).not.toHaveBeenCalledWith(node);
    expect(store.addEdge).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "edge:memory-store:kg:memory_agent:research",
        source: "memory_agent:research",
        target: "db:knowledge-graph",
        type: "memory_store",
      }),
    );
    expect(store.updateNode).not.toHaveBeenCalled();
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

  it("state_sync filters hidden launcher nodes and touching edges", () => {
    const store = makeStore();
    const nodes = [
      { id: "launch-1", type: "tool" as const, label: "launch_deep_research" },
      { id: "agent-1", type: "agent" as const, label: "Researcher" },
    ];
    const edges = [{ id: "e", source: "agent-1", target: "launch-1" }];

    labReducers.state_sync(store, ev("state_sync", { nodes, edges }));

    expect(store.loadJSON).toHaveBeenCalledWith({
      nodes: [{ id: "agent-1", type: "agent", label: "Researcher" }],
      edges: [],
    });
  });

  it("state_sync projects hidden memory nodes into DB edges", () => {
    const store = makeStore();
    const nodes = [
      { id: "agent-1", type: "agent" as const, label: "Researcher" },
      {
        id: "tool-1",
        type: "tool" as const,
        label: "retrieve_knowledge",
        parentId: "agent-1",
      },
      {
        id: "memory_output:research:facts",
        type: "artifact" as const,
        label: "Memories: research",
        parentId: "memory_agent:research",
      },
    ];
    const edges = [{ id: "e", source: "agent-1", target: "tool-1" }];

    labReducers.state_sync(store, ev("state_sync", { nodes, edges }));

    expect(store.loadJSON).toHaveBeenCalledWith({
      nodes: [
        { id: "agent-1", type: "agent", label: "Researcher" },
        expect.objectContaining({ id: "db:knowledge-graph", type: "database" }),
        expect.objectContaining({ id: "db:vector-memory", type: "database" }),
      ],
      edges: [
        expect.objectContaining({
          id: "edge:memory-retrieve:kg:agent-1",
          source: "db:knowledge-graph",
          target: "agent-1",
          type: "memory_retrieve",
        }),
        expect.objectContaining({
          id: "edge:memory-retrieve:vectors:agent-1",
          source: "db:vector-memory",
          target: "agent-1",
          type: "memory_retrieve",
        }),
        expect.objectContaining({
          id: "edge:memory-store:vectors:memory_agent:research",
          source: "memory_agent:research",
          target: "db:vector-memory",
          type: "memory_store",
        }),
      ],
    });
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
