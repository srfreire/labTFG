import { useEffect, useState } from "react";
import type { PastRun } from "../types";

function statusPillClass(status: PastRun["status"]): string {
  const base =
    "text-[9px] uppercase tracking-[1px] px-2 py-0.5 rounded-full border";
  if (status === "done") return `${base} border-border text-text-muted`;
  if (status === "failed") return `${base} border-border text-accent-red`;
  return `${base} border-border text-text-dim`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

interface Props {
  onSelect: (runId: string) => void;
  /** Drives the enter animation — set true once the idle demo is ready. */
  active?: boolean;
}

// Match the easing curve used by the landing title/subtitle/input stagger
// (ui-craft --ease-out). Keep enter distance small (8px) so the list slides
// in without competing for attention with the primary input CTA.
const EASE_OUT = "cubic-bezier(0.23, 1, 0.32, 1)";
const CONTAINER_DELAY_MS = 350;
const ROW_STAGGER_MS = 60;

export default function PastRunsList({ onSelect, active = true }: Props) {
  const [runs, setRuns] = useState<PastRun[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch("/api/runs");
        if (!r.ok) throw new Error("failed");
        const data: PastRun[] = await r.json();
        if (!cancelled) setRuns(data);
      } catch {
        if (!cancelled) setRuns([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (runs === null || runs.length === 0) return null;

  const visible = active;

  return (
    <div
      className="absolute left-6 bottom-5 w-[260px] max-h-[180px] overflow-y-auto bg-surface/80 backdrop-blur-xl border border-border rounded-xl shadow-xl shadow-black/20 p-2 z-20 motion-reduce:transform-none"
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? "translateY(0)" : "translateY(8px)",
        transition: `opacity 500ms ${EASE_OUT} ${CONTAINER_DELAY_MS}ms, transform 500ms ${EASE_OUT} ${CONTAINER_DELAY_MS}ms`,
        willChange: "opacity, transform",
      }}
    >
      <div className="text-[10px] uppercase tracking-[1.5px] text-text-faint px-2 py-1">
        Past runs
      </div>
      {runs.map((r, i) => (
        <button
          key={r.run_id}
          onClick={() => onSelect(r.run_id)}
          className="w-full text-left px-2 py-2 rounded-lg hover:bg-surface-hover border-none bg-transparent cursor-pointer motion-reduce:transform-none active:scale-[0.98]"
          style={{
            opacity: visible ? 1 : 0,
            transform: visible ? "translateY(0)" : "translateY(6px)",
            transition: `opacity 260ms ${EASE_OUT} ${CONTAINER_DELAY_MS + 120 + i * ROW_STAGGER_MS}ms, transform 260ms ${EASE_OUT} ${CONTAINER_DELAY_MS + 120 + i * ROW_STAGGER_MS}ms`,
          }}
        >
          <div className="text-[12px] text-text truncate">{r.problem}</div>
          <div className="flex items-center gap-2 mt-1">
            <span className={statusPillClass(r.status)}>{r.status}</span>
            {r.artifact_count !== null && (
              <span className="text-[10px] text-text-muted">
                {r.artifact_count} model{r.artifact_count === 1 ? "" : "s"}
              </span>
            )}
            <span className="text-[10px] text-text-dim ml-auto tabular-nums">
              {formatDate(r.started_at)}
            </span>
          </div>
        </button>
      ))}
    </div>
  );
}
