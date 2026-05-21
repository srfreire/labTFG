import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useWebSocket } from "./useWebSocket";
import { Stage, type ServerMessage } from "../types";

/* ------------------------------------------------------------------ */
/*  Mock WebSocket                                                     */
/* ------------------------------------------------------------------ */
// Replace the global so the hook's `new WebSocket(url)` resolves to this
// class. We track every constructed instance so tests can drive `onopen` /
// `onmessage` deterministically without real network or timers.

class MockSocket {
  static OPEN = 1;
  static CONNECTING = 0;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: MockSocket[] = [];

  readyState: number = MockSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  send = vi.fn<(data: string) => void>();
  close = vi.fn(() => {
    this.readyState = MockSocket.CLOSED;
  });

  constructor(public url: string) {
    MockSocket.instances.push(this);
  }

  emitOpen() {
    this.readyState = MockSocket.OPEN;
    this.onopen?.();
  }

  emitMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

beforeEach(() => {
  MockSocket.instances = [];
  vi.stubGlobal("WebSocket", MockSocket);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function setup() {
  const onMessage = vi.fn();
  const utils = renderHook(() => useWebSocket(onMessage));
  const ws = MockSocket.instances.at(-1);
  if (!ws) throw new Error("Hook did not construct a WebSocket");
  act(() => ws.emitOpen());

  function send(msg: ServerMessage) {
    act(() => ws!.emitMessage(msg));
  }

  return { ...utils, ws, onMessage, send };
}

/* ------------------------------------------------------------------ */
/*  case "stage"                                                       */
/* ------------------------------------------------------------------ */

describe("useWebSocket reducer — case 'stage'", () => {
  it("marks the new stage running and lights its memory stage up front", () => {
    const { result, send } = setup();

    send({ type: "stage", ts: 0, label: Stage.RESEARCH });

    expect(result.current.stages[Stage.RESEARCH]).toBe("running");
    expect(result.current.stages[Stage.MEMORY_RESEARCH]).toBe("running");
    expect(result.current.currentStage).toBe(Stage.RESEARCH);
  });

  it("marks the previous work stage done when a new one begins", () => {
    const { result, send } = setup();

    send({ type: "stage", ts: 0, label: Stage.RESEARCH });
    send({ type: "stage", ts: 1, label: Stage.FORMALIZE });

    expect(result.current.stages[Stage.RESEARCH]).toBe("done");
    expect(result.current.stages[Stage.FORMALIZE]).toBe("running");
    expect(result.current.currentStage).toBe(Stage.FORMALIZE);
  });

  it("sweeps lingering review_ stages to done on stage transition", () => {
    const { result, send } = setup();

    send({ type: "stage", ts: 0, label: Stage.RESEARCH });
    send({ type: "marker", ts: 1, kind: "review_research" });
    expect(result.current.stages[Stage.REVIEW_RESEARCH]).toBe("running");

    send({ type: "stage", ts: 2, label: Stage.FORMALIZE });

    expect(result.current.stages[Stage.REVIEW_RESEARCH]).toBe("done");
  });

  it("sweeps lingering memory_ stages to done if no review marker closed them", () => {
    const { result, send } = setup();

    send({ type: "stage", ts: 0, label: Stage.RESEARCH });
    expect(result.current.stages[Stage.MEMORY_RESEARCH]).toBe("running");

    send({ type: "stage", ts: 1, label: Stage.FORMALIZE });

    expect(result.current.stages[Stage.MEMORY_RESEARCH]).toBe("done");
  });

  it("closes GET_ENV_SPEC when entering REASON", () => {
    const { result, send } = setup();

    send({ type: "stage", ts: 0, label: Stage.FORMALIZE });
    send({ type: "review_request", stage: Stage.GET_ENV_SPEC, data: {} });
    expect(result.current.stages[Stage.GET_ENV_SPEC]).toBe("running");

    send({ type: "stage", ts: 1, label: Stage.REASON });

    expect(result.current.stages[Stage.GET_ENV_SPEC]).toBe("done");
    expect(result.current.stages[Stage.REASON]).toBe("running");
  });

  it("resets a stale review_ flag to pending when a stage re-runs", () => {
    const { result, send } = setup();

    send({ type: "stage", ts: 0, label: Stage.RESEARCH });
    send({ type: "marker", ts: 1, kind: "review_research" });

    // Loop back into RESEARCH (e.g. user rejected the review).
    send({ type: "stage", ts: 2, label: Stage.RESEARCH });

    expect(result.current.stages[Stage.REVIEW_RESEARCH]).toBe("pending");
    expect(result.current.stages[Stage.RESEARCH]).toBe("running");
  });
});

/* ------------------------------------------------------------------ */
/*  case "marker"                                                      */
/* ------------------------------------------------------------------ */

describe("useWebSocket reducer — case 'marker'", () => {
  it("review_<stage> marks the review running and closes the matching memory", () => {
    const { result, send } = setup();

    send({ type: "stage", ts: 0, label: Stage.RESEARCH });
    expect(result.current.stages[Stage.MEMORY_RESEARCH]).toBe("running");

    send({ type: "marker", ts: 1, kind: "review_research" });

    expect(result.current.stages[Stage.REVIEW_RESEARCH]).toBe("running");
    expect(result.current.stages[Stage.MEMORY_RESEARCH]).toBe("done");
    expect(result.current.currentStage).toBe(Stage.REVIEW_RESEARCH);
  });

  it("non-review_ marker kinds leave reducer state unchanged", () => {
    const { result, send } = setup();

    send({ type: "stage", ts: 0, label: Stage.RESEARCH });
    const stagesBefore = result.current.stages;
    const currentBefore = result.current.currentStage;

    send({ type: "marker", ts: 1, kind: "annotation" });

    // Reducer returns the same state object; React's useReducer bails out and
    // identity is preserved.
    expect(result.current.stages).toBe(stagesBefore);
    expect(result.current.currentStage).toBe(currentBefore);
  });
});

/* ------------------------------------------------------------------ */
/*  case "review_request"                                              */
/* ------------------------------------------------------------------ */

describe("useWebSocket reducer — case 'review_request'", () => {
  it("GET_ENV_SPEC marks the stage running and updates currentStage", () => {
    const { result, send } = setup();

    send({ type: "stage", ts: 0, label: Stage.FORMALIZE });
    send({ type: "review_request", stage: Stage.GET_ENV_SPEC, data: {} });

    expect(result.current.stages[Stage.GET_ENV_SPEC]).toBe("running");
    expect(result.current.currentStage).toBe(Stage.GET_ENV_SPEC);
    expect(result.current.reviewRequest).toEqual({
      stage: Stage.GET_ENV_SPEC,
      data: {},
    });
  });

  it("non-env-spec stages set reviewRequest without overriding currentStage", () => {
    const { result, send } = setup();

    send({ type: "stage", ts: 0, label: Stage.RESEARCH });
    send({ type: "marker", ts: 1, kind: "review_research" });
    const currentBefore = result.current.currentStage;

    send({
      type: "review_request",
      stage: Stage.REVIEW_RESEARCH,
      data: { paradigms: [] },
    });

    expect(result.current.currentStage).toBe(currentBefore);
    expect(result.current.reviewRequest).toEqual({
      stage: Stage.REVIEW_RESEARCH,
      data: { paradigms: [] },
    });
  });
});

/* ------------------------------------------------------------------ */
/*  case "pipeline_done"                                               */
/* ------------------------------------------------------------------ */

describe("useWebSocket reducer — case 'pipeline_done'", () => {
  it("sweeps every running stage to done and clears currentStage", () => {
    const { result, send } = setup();

    act(() => result.current.startPipeline("test problem"));
    send({ type: "stage", ts: 0, label: Stage.BUILD });
    expect(result.current.isRunning).toBe(true);
    expect(result.current.stages[Stage.BUILD]).toBe("running");

    send({ type: "pipeline_done" });

    for (const status of Object.values(result.current.stages)) {
      expect(status).not.toBe("running");
    }
    expect(result.current.currentStage).toBeNull();
    expect(result.current.isRunning).toBe(false);
  });
});

/* ------------------------------------------------------------------ */
/*  Graph deltas — reducer no-op, callback fires                       */
/* ------------------------------------------------------------------ */

describe("useWebSocket — graph delta passthrough", () => {
  it("node_add does not mutate reducer state but invokes onServerMessage", () => {
    const { result, send, onMessage } = setup();
    send({ type: "stage", ts: 0, label: Stage.RESEARCH });
    const stagesBefore = result.current.stages;

    send({
      type: "node_add",
      node: {
        id: "a",
        kind: "agent",
        label: "Researcher",
        status: "running",
        meta: {},
      },
    });

    expect(result.current.stages).toBe(stagesBefore);
    expect(onMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: "node_add" }),
    );
  });

  it("edge_add does not mutate reducer state but invokes onServerMessage", () => {
    const { result, send, onMessage } = setup();
    const stagesBefore = result.current.stages;

    send({
      type: "edge_add",
      edge: { source: "a", target: "b" },
    });

    expect(result.current.stages).toBe(stagesBefore);
    expect(onMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: "edge_add" }),
    );
  });

  it("graph_clear does not mutate reducer state but invokes onServerMessage", () => {
    const { result, send, onMessage } = setup();
    const stagesBefore = result.current.stages;

    send({ type: "graph_clear", from_stage: Stage.RESEARCH });

    expect(result.current.stages).toBe(stagesBefore);
    expect(onMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: "graph_clear" }),
    );
  });
});

/* ------------------------------------------------------------------ */
/*  cancelPipeline — sweep stages so the sidebar doesn't lie           */
/* ------------------------------------------------------------------ */

describe("useWebSocket — cancelPipeline", () => {
  it("sweeps any running stage to done", () => {
    const { result, send } = setup();

    send({ type: "stage", ts: 0, label: Stage.RESEARCH });
    expect(result.current.stages[Stage.RESEARCH]).toBe("running");
    expect(result.current.stages[Stage.MEMORY_RESEARCH]).toBe("running");

    act(() => result.current.cancelPipeline());

    expect(result.current.stages[Stage.RESEARCH]).toBe("done");
    expect(result.current.stages[Stage.MEMORY_RESEARCH]).toBe("done");
    expect(result.current.currentStage).toBeNull();
    expect(result.current.isRunning).toBe(false);
  });

  it("leaves pending stages untouched", () => {
    const { result, send } = setup();

    send({ type: "stage", ts: 0, label: Stage.RESEARCH });
    expect(result.current.stages[Stage.FORMALIZE]).toBe("pending");

    act(() => result.current.cancelPipeline());

    expect(result.current.stages[Stage.FORMALIZE]).toBe("pending");
    expect(result.current.stages[Stage.BUILD]).toBe("pending");
  });
});

/* ------------------------------------------------------------------ */
/*  send() while not OPEN — surface an error instead of silent warn    */
/* ------------------------------------------------------------------ */

describe("useWebSocket — send while not connected", () => {
  it("sets state.error when send fires before the socket opens", () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() => useWebSocket(onMessage));
    // Deliberately do NOT emit open — the mock stays in CONNECTING.
    expect(result.current.connected).toBe(false);
    expect(result.current.error).toBeNull();

    act(() => result.current.startPipeline("test problem"));

    expect(result.current.error).toBeTruthy();
    expect(result.current.error?.toLowerCase()).toContain("connect");
  });

  it("does not mark the pipeline running when start could not be sent", () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() => useWebSocket(onMessage));

    act(() => result.current.startPipeline("test problem"));

    expect(result.current.isRunning).toBe(false);
    expect(result.current.currentStage).toBeNull();
  });
});
