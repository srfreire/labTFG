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

const EASE_OUT = "cubic-bezier(0.23, 1, 0.32, 1)";
const ENTER_DELAY_MS = 350;

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

  const visible = active;
  const count = runs?.length ?? 0;

  return (
    <div
      className="panel-chrome fixed right-4 bottom-4 w-[220px] h-[180px] z-30 flex flex-col overflow-hidden motion-reduce:transform-none"
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? "translateY(0)" : "translateY(8px)",
        transition: `opacity 500ms ${EASE_OUT} ${ENTER_DELAY_MS}ms, transform 500ms ${EASE_OUT} ${ENTER_DELAY_MS}ms`,
        willChange: "opacity, transform",
      }}
    >
      {/* Header — mirrors the KG card */}
      <div className="px-3 py-2 border-b border-border-subtle flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <div
            className="w-2 h-2 rounded-full shrink-0"
            style={{ background: "rgba(255,255,255,0.15)" }}
          />
          <span className="text-[10px] uppercase tracking-[1.5px] text-text-muted">
            Past runs
          </span>
        </div>
        <span className="text-[10px] text-text-faint">{count}</span>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-y-auto p-1">
        {runs === null ? (
          <div className="flex items-center justify-center h-full text-[11px] text-text-faint italic">
            Loading…
          </div>
        ) : runs.length === 0 ? (
          <div className="flex items-center justify-center h-full text-[11px] text-text-faint italic px-4 text-center">
            No past runs yet
          </div>
        ) : (
          runs.map((r) => (
            <button
              key={r.run_id}
              onClick={() => onSelect(r.run_id)}
              className="w-full text-left px-2 py-2 rounded-lg hover:bg-surface-hover border-none bg-transparent cursor-pointer motion-reduce:transform-none active:scale-[0.98]"
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
          ))
        )}
      </div>
    </div>
  );
}
