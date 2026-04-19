import { useEffect, useMemo, useState } from "react";
import { Play, Pause, Radio, X, SkipBack, SkipForward, ChevronLeft, ChevronRight } from "lucide-react";
import type { UseReplay } from "../hooks/useReplay";

const LS_KEY = "decisionlab.timeline.collapsed";
const PANEL_WIDTH = 820;
const PANEL_HEIGHT = 58;

function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

interface Props {
  replay: UseReplay;
  onExit?: () => void;
  onCollapsedChange?: (collapsed: boolean) => void;
}

export default function Timeline({ replay, onExit, onCollapsedChange }: Props) {
  const {
    events,
    cursor,
    playing,
    speed,
    mode,
    stageMarkers,
    reviewMarkers,
    play,
    pause,
    seek,
    goLive,
    setSpeed,
    stepForward,
    stepBack,
    prevStage,
    nextStage,
  } = replay;

  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(LS_KEY) === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(LS_KEY, collapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
    onCollapsedChange?.(collapsed);
  }, [collapsed, onCollapsedChange]);

  const total = events.length;
  const elapsed = useMemo(() => {
    if (total === 0) return 0;
    const first = Number(events[0].ts);
    const idx = Math.max(0, Math.min(cursor, total) - 1);
    return Number(events[idx].ts) - first;
  }, [cursor, total, events]);
  const duration = useMemo(() => {
    if (total < 2) return 0;
    return Number(events[total - 1].ts) - Number(events[0].ts);
  }, [events, total]);

  if (mode === "idle") return null;

  return (
    <>
      <div
        className="absolute left-1/2 bottom-4 z-30 bg-surface/80 backdrop-blur-xl border border-border rounded-2xl shadow-xl shadow-black/30 px-4 py-3"
        style={{
          width: PANEL_WIDTH,
          transform: collapsed
            ? `translate(-50%, calc(100% + ${PANEL_HEIGHT}px))`
            : "translate(-50%, 0)",
          transition: "transform 250ms cubic-bezier(0.23, 1, 0.32, 1)",
        }}
      >
        <div className="flex items-center gap-3">
          <button
            className="tl-btn"
            onClick={prevStage}
            aria-label="Previous stage"
            title="Previous stage"
          >
            <SkipBack size={14} />
          </button>
          <button
            className="tl-btn"
            onClick={stepBack}
            aria-label="Step back"
            title="Step back (one event)"
          >
            <ChevronLeft size={14} />
          </button>
          <button
            className="tl-btn tl-btn-primary"
            onClick={playing ? pause : play}
            aria-label={playing ? "Pause" : "Play"}
          >
            {playing ? <Pause size={14} /> : <Play size={14} fill="currentColor" />}
          </button>
          <button
            className="tl-btn"
            onClick={stepForward}
            aria-label="Step forward"
            title="Step forward (one event)"
          >
            <ChevronRight size={14} />
          </button>
          <button
            className="tl-btn"
            onClick={nextStage}
            aria-label="Next stage"
            title="Next stage"
          >
            <SkipForward size={14} />
          </button>

          <div className="flex-1 relative h-4 mx-1">
            <div className="absolute inset-0 top-1/2 -translate-y-1/2 h-[2px] bg-border" />
            <div
              className="absolute top-1/2 -translate-y-1/2 h-[2px] bg-text-muted"
              style={{ width: total ? `${(cursor / total) * 100}%` : "0%" }}
            />
            {stageMarkers.map((m, i) => (
              <div
                key={`sm-${i}`}
                title={m.stage}
                className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-text-muted cursor-pointer"
                style={{ left: `calc(${(m.cursor / total) * 100}% - 4px)` }}
                onClick={() => seek(m.cursor)}
              />
            ))}
            {reviewMarkers.map((m, i) => (
              <div
                key={`rm-${i}`}
                title={`Review: ${m.stage} (${
                  m.approved === true
                    ? "approved"
                    : m.approved === false
                      ? "rejected"
                      : "incomplete"
                })`}
                className="absolute top-1/2 -translate-y-1/2 w-1.5 h-3 rounded-sm bg-amber-400/80 pointer-events-none"
                style={{ left: `calc(${(m.cursor / total) * 100}% - 3px)` }}
              />
            ))}
            <input
              aria-label="Scrub"
              type="range"
              min={0}
              max={total}
              value={cursor}
              onChange={(e) => seek(parseInt(e.target.value))}
              className="absolute inset-0 w-full opacity-0 cursor-pointer"
            />
            <div
              className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rotate-45 bg-white pointer-events-none"
              style={{ left: `calc(${(cursor / total) * 100}% - 6px)` }}
            />
          </div>

          <div className="flex gap-0.5 text-[11px] text-text-muted">
            {[1, 2, 4].map((s) => (
              <button
                key={s}
                onClick={() => setSpeed(s as 1 | 2 | 4)}
                className={`px-1.5 py-0.5 rounded ${
                  speed === s ? "bg-surface-hover text-text" : ""
                }`}
              >
                {s}×
              </button>
            ))}
          </div>

          <span className="text-[11px] text-text-muted font-mono">
            {formatElapsed(elapsed)} / {formatElapsed(duration)}
          </span>

          <button
            className="tl-btn"
            onClick={goLive}
            aria-label={mode === "live" ? "Return to live" : "Jump to end"}
            title={mode === "live" ? "Return to live" : "Jump to end"}
          >
            <Radio size={14} />
          </button>

          {mode === "replay" && onExit && (
            <button className="tl-btn" onClick={onExit} aria-label="Exit replay">
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Toggle tab — mirrors Sidebar's chevron pattern */}
      <button
        onClick={() => setCollapsed((v) => !v)}
        className="fixed z-30 left-1/2 -translate-x-1/2 w-10 h-5 rounded-t-md bg-surface/80 backdrop-blur-xl border border-b-0 border-border flex items-center justify-center cursor-pointer text-text-dim hover:text-text"
        style={{
          bottom: collapsed ? 0 : PANEL_HEIGHT + 16,
          transition: "bottom 250ms cubic-bezier(0.23, 1, 0.32, 1)",
        }}
        aria-label={collapsed ? "Expand timeline" : "Collapse timeline"}
      >
        <svg
          width="8"
          height="8"
          viewBox="0 0 8 8"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          style={{
            transform: collapsed ? "rotate(-90deg)" : "rotate(90deg)",
            transition: "transform 200ms cubic-bezier(0.23, 1, 0.32, 1)",
          }}
        >
          <path d="M2 1L6 4L2 7" />
        </svg>
      </button>
    </>
  );
}
