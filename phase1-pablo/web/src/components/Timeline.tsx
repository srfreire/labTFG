import { useEffect, useMemo, useState } from "react";
import {
  SkipBack,
  SkipForward,
  Play,
  Pause,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Radio,
  X,
} from "lucide-react";
import type { UseReplay } from "../hooks/useReplay";

const LS_KEY = "decisionlab.timeline.collapsed";

function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

interface Props {
  replay: UseReplay;
  onExit?: () => void;
  reviewActive: boolean;
}

export default function Timeline({ replay, onExit, reviewActive }: Props) {
  const {
    events, cursor, playing, speed, mode,
    stageMarkers, reviewMarkers,
    play, pause, seek, stepForward, stepBack,
    prevStage, nextStage, goLive, setSpeed,
  } = replay;

  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(LS_KEY) === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    if (reviewActive) setCollapsed(true);
  }, [reviewActive]);

  useEffect(() => {
    try {
      localStorage.setItem(LS_KEY, collapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [collapsed]);

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

  if (collapsed) {
    return (
      <div className="absolute left-1/2 bottom-4 -translate-x-1/2 z-30 flex items-center gap-2 bg-surface/80 backdrop-blur-xl border border-border rounded-full shadow-xl shadow-black/30 px-3 py-2">
        <button
          className="w-7 h-7 flex items-center justify-center rounded-full bg-transparent border-none text-text cursor-pointer hover:bg-surface-hover"
          onClick={playing ? pause : play}
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? <Pause size={14} /> : <Play size={14} fill="currentColor" />}
        </button>
        <span className="text-[11px] text-text-muted font-mono">
          {formatElapsed(elapsed)}
        </span>
        <button
          className="w-7 h-7 flex items-center justify-center rounded-full bg-transparent border-none text-text-faint cursor-pointer hover:bg-surface-hover"
          onClick={() => setCollapsed(false)}
          aria-label="Expand timeline"
        >
          <ChevronUp size={14} />
        </button>
      </div>
    );
  }

  return (
    <div className="absolute left-1/2 bottom-4 -translate-x-1/2 z-30 w-[720px] bg-surface/80 backdrop-blur-xl border border-border rounded-2xl shadow-xl shadow-black/30 px-4 py-3">
      <div className="flex items-center gap-2">
        <button className="tl-btn" onClick={prevStage} aria-label="Previous stage">
          <SkipBack size={14} />
        </button>
        <button className="tl-btn" onClick={stepBack} aria-label="Step back">
          <ChevronLeft size={14} />
        </button>
        <button
          className="tl-btn tl-btn-primary"
          onClick={playing ? pause : play}
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? <Pause size={14} /> : <Play size={14} fill="currentColor" />}
        </button>
        <button className="tl-btn" onClick={stepForward} aria-label="Step forward">
          <ChevronRight size={14} />
        </button>
        <button className="tl-btn" onClick={nextStage} aria-label="Next stage">
          <SkipForward size={14} />
        </button>

        <div className="flex-1 relative h-4 mx-2">
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
              title={`Review: ${m.stage} (${m.approved === true ? "approved" : m.approved === false ? "rejected" : "incomplete"})`}
              className="absolute top-1/2 -translate-y-1/2 w-1.5 h-3 rounded-sm bg-amber-400/80"
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
              className={`px-1.5 py-0.5 rounded ${speed === s ? "bg-surface-hover text-text" : ""}`}
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

        <button
          className="tl-btn"
          onClick={() => setCollapsed(true)}
          aria-label="Collapse timeline"
        >
          <ChevronDown size={14} />
        </button>

        {mode === "replay" && onExit && (
          <button className="tl-btn" onClick={onExit} aria-label="Exit replay">
            <X size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
