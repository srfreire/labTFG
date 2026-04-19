import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useReplay } from "./useReplay";

const sampleEvents = [
  { ts: 1000, type: "run_start", run_id: "r1" },
  { ts: 1100, type: "stage_change", stage: "research", status: "running" },
  { ts: 1200, type: "node_add", node: { id: "a", kind: "agent", label: "x", status: "running", meta: {} } },
  { ts: 1300, type: "agent_status", agent: "researcher", status: "idle" },
  { ts: 1400, type: "stage_change", stage: "formalize", status: "running" },
];

describe("useReplay", () => {
  beforeEach(() => {
    (globalThis as any).fetch = vi.fn(async (_url: string) => ({
      ok: true,
      text: async () => sampleEvents.map((e) => JSON.stringify(e)).join("\n"),
    })) as any;
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads events and starts at cursor=events.length in replay mode", async () => {
    const { result } = renderHook(() => useReplay());
    await act(async () => {
      await result.current.load("r1");
    });
    expect(result.current.events).toHaveLength(5);
    expect(result.current.cursor).toBe(5);
    expect(result.current.mode).toBe("replay");
  });

  it("seeks to a cursor clamped to bounds", async () => {
    const { result } = renderHook(() => useReplay());
    await act(async () => { await result.current.load("r1"); });
    act(() => result.current.seek(-10));
    expect(result.current.cursor).toBe(0);
    act(() => result.current.seek(999));
    expect(result.current.cursor).toBe(5);
    act(() => result.current.seek(2));
    expect(result.current.cursor).toBe(2);
  });

  it("stepForward advances to the next visible-event boundary", async () => {
    const { result } = renderHook(() => useReplay());
    await act(async () => { await result.current.load("r1"); });
    act(() => result.current.seek(0));
    // Visible events: stage_change (idx 1), node_add (idx 2), stage_change (idx 4)
    // Boundaries: [2, 3, 5]. agent_status at idx 3 is skipped.
    act(() => result.current.stepForward());
    expect(result.current.cursor).toBe(2);
    act(() => result.current.stepForward());
    expect(result.current.cursor).toBe(3);
    act(() => result.current.stepForward());
    expect(result.current.cursor).toBe(5);
  });

  it("stepBack retreats to the previous visible-event boundary", async () => {
    const { result } = renderHook(() => useReplay());
    await act(async () => { await result.current.load("r1"); });
    // cursor starts at 5; boundaries [2, 3, 5].
    act(() => result.current.stepBack());
    expect(result.current.cursor).toBe(3);
    act(() => result.current.stepBack());
    expect(result.current.cursor).toBe(2);
    act(() => result.current.stepBack());
    expect(result.current.cursor).toBe(0);
  });

  it("play at end auto-rewinds to 0", async () => {
    const { result } = renderHook(() => useReplay());
    await act(async () => { await result.current.load("r1"); });
    expect(result.current.cursor).toBe(5);
    act(() => result.current.play());
    expect(result.current.cursor).toBe(0);
    expect(result.current.playing).toBe(true);
  });

  it("appendLive is ignored in replay mode", async () => {
    const { result } = renderHook(() => useReplay());
    await act(async () => { await result.current.load("r1"); });
    const before = result.current.events.length;
    act(() =>
      result.current.appendLive({ ts: 9999, type: "node_add", node: { id: "stray" } } as any),
    );
    expect(result.current.events.length).toBe(before);
  });

  it("run_start in live mode resets prior events", async () => {
    const { result } = renderHook(() => useReplay());
    act(() => result.current.setMode("live"));
    act(() =>
      result.current.appendLive({ ts: 1, type: "node_add", node: { id: "old" } } as any),
    );
    act(() =>
      result.current.appendLive({ ts: 2, type: "run_start", run_id: "new" } as any),
    );
    expect(result.current.events).toHaveLength(1);
    expect((result.current.events[0] as any).type).toBe("run_start");
  });
});

describe("useReplay playback", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    (globalThis as any).fetch = vi.fn(async () => ({
      ok: true,
      text: async () => [
        { ts: 0,   type: "run_start" },
        { ts: 100, type: "node_add", node: {} },
        { ts: 250, type: "node_add", node: {} },
      ].map((e) => JSON.stringify(e)).join("\n"),
    })) as any;
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("advances the cursor at real inter-event timings when playing", async () => {
    const { result } = renderHook(() => useReplay());
    await act(async () => { await result.current.load("r1"); });
    act(() => result.current.seek(0));
    act(() => result.current.play());

    await act(async () => { vi.advanceTimersByTime(100); });
    expect(result.current.cursor).toBe(1);

    await act(async () => { vi.advanceTimersByTime(150); });
    expect(result.current.cursor).toBe(2);

    await act(async () => { vi.advanceTimersByTime(1000); });
    expect(result.current.cursor).toBe(3);
    expect(result.current.playing).toBe(false);
  });

  it("caps inter-event delay at 300ms", async () => {
    (globalThis as any).fetch = vi.fn(async () => ({
      ok: true,
      text: async () => [
        { ts: 0,    type: "run_start" },
        { ts: 5000, type: "node_add", node: {} },
      ].map((e) => JSON.stringify(e)).join("\n"),
    })) as any;

    const { result } = renderHook(() => useReplay());
    await act(async () => { await result.current.load("r1"); });
    act(() => result.current.seek(0));
    act(() => result.current.play());
    await act(async () => { vi.advanceTimersByTime(300); });
    expect(result.current.cursor).toBe(1);
  });

  it("speed=2 halves the delay", async () => {
    const { result } = renderHook(() => useReplay());
    await act(async () => { await result.current.load("r1"); });
    act(() => result.current.seek(0));
    act(() => result.current.setSpeed(2));
    act(() => result.current.play());
    await act(async () => { vi.advanceTimersByTime(50); });
    expect(result.current.cursor).toBe(1); // 100/2 = 50ms
  });
});
