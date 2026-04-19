import { useCallback, useMemo, useRef, useState } from "react";
import type { RecordedEvent, ReplayMode } from "../types";
import { extractMarkers, type StageMarker, type ReviewMarker } from "../lib/markers";

// Step-navigation boundaries: cursor positions that end an agent action.
// An agent action ends when an agent transitions to "idle". The final
// position is always included so stepping from the last action lands at
// the end of the stream.
function stepBoundaries(events: readonly Record<string, any>[]): number[] {
  const out: number[] = [];
  for (let i = 0; i < events.length; i++) {
    const ev = events[i];
    if (ev.type === "agent_status" && ev.status === "idle") {
      out.push(i + 1);
    }
  }
  if (events.length > 0 && (out.length === 0 || out[out.length - 1] !== events.length)) {
    out.push(events.length);
  }
  return out;
}

export interface UseReplay {
  events: RecordedEvent[];
  cursor: number;
  playing: boolean;
  speed: 1 | 2 | 4;
  mode: ReplayMode;
  stageMarkers: StageMarker[];
  reviewMarkers: ReviewMarker[];
  load(runId: string): Promise<void>;
  seek(cursor: number): void;
  stepForward(): void;
  stepBack(): void;
  prevStage(): void;
  nextStage(): void;
  goLive(): void;
  setSpeed(s: 1 | 2 | 4): void;
  play(): void;
  pause(): void;
  appendLive(event: RecordedEvent): void;
  setMode(m: ReplayMode): void;
}

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

export function useReplay(): UseReplay {
  const [events, setEvents] = useState<RecordedEvent[]>([]);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<1 | 2 | 4>(1);
  const [mode, setMode] = useState<ReplayMode>("idle");
  const playTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { stageMarkers, reviewMarkers } = useMemo(() => extractMarkers(events), [events]);
  const boundaries = useMemo(() => stepBoundaries(events), [events]);

  const eventsRef = useRef(events);
  eventsRef.current = events;
  const boundariesRef = useRef(boundaries);
  boundariesRef.current = boundaries;
  const stageMarkersRef = useRef(stageMarkers);
  stageMarkersRef.current = stageMarkers;

  const stopTimer = useCallback(() => {
    if (playTimerRef.current) {
      clearTimeout(playTimerRef.current);
      playTimerRef.current = null;
    }
    setPlaying(false);
  }, []);

  const load = useCallback(async (runId: string) => {
    stopTimer();
    const resp = await fetch(`/api/runs/${runId}/events`);
    if (!resp.ok) throw new Error(`Failed to load run ${runId}`);
    const text = await resp.text();
    const parsed: RecordedEvent[] = text
      .split("\n")
      .filter((ln) => ln.trim())
      .map((ln) => JSON.parse(ln));
    setEvents(parsed);
    setCursor(parsed.length);
    setMode("replay");
  }, [stopTimer]);

  const seek = useCallback((c: number) => {
    stopTimer();
    setCursor(() => clamp(c, 0, eventsRef.current.length));
  }, [stopTimer]);

  const stepForward = useCallback(() => {
    stopTimer();
    setCursor((prev) => {
      const next = boundariesRef.current.find((b) => b > prev);
      return next ?? eventsRef.current.length;
    });
  }, [stopTimer]);

  const stepBack = useCallback(() => {
    stopTimer();
    setCursor((prev) => {
      const prevBoundaries = boundariesRef.current.filter((b) => b < prev);
      return prevBoundaries.length ? prevBoundaries[prevBoundaries.length - 1] : 0;
    });
  }, [stopTimer]);

  const prevStage = useCallback(() => {
    stopTimer();
    setCursor((prev) => {
      const earlier = stageMarkersRef.current.filter((m) => m.cursor < prev);
      return earlier.length ? earlier[earlier.length - 1].cursor : 0;
    });
  }, [stopTimer]);

  const nextStage = useCallback(() => {
    stopTimer();
    setCursor((prev) => {
      const later = stageMarkersRef.current.find((m) => m.cursor > prev);
      return later ? later.cursor : eventsRef.current.length;
    });
  }, [stopTimer]);

  const goLive = useCallback(() => {
    stopTimer();
    setCursor(eventsRef.current.length);
  }, [stopTimer]);

  const play = useCallback(() => setPlaying(true), []);
  const pause = useCallback(() => stopTimer(), [stopTimer]);

  const appendLive = useCallback((event: RecordedEvent) => {
    setEvents((prev) => [...prev, event]);
  }, []);

  return {
    events,
    cursor,
    playing,
    speed,
    mode,
    stageMarkers,
    reviewMarkers,
    load,
    seek,
    stepForward,
    stepBack,
    prevStage,
    nextStage,
    goLive,
    setSpeed,
    play,
    pause,
    appendLive,
    setMode,
  };
}
