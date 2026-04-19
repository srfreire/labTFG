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
}

export default function PastRunsList({ onSelect }: Props) {
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

  return (
    <div className="absolute left-6 bottom-5 w-[260px] max-h-[180px] overflow-y-auto bg-surface/80 backdrop-blur-xl border border-border rounded-xl shadow-xl shadow-black/20 p-2 z-20">
      <div className="text-[10px] uppercase tracking-[1.5px] text-text-faint px-2 py-1">
        Past runs
      </div>
      {runs.map((r) => (
        <button
          key={r.run_id}
          onClick={() => onSelect(r.run_id)}
          className="w-full text-left px-2 py-2 rounded-lg hover:bg-surface-hover border-none bg-transparent cursor-pointer"
        >
          <div className="text-[12px] text-text truncate">{r.problem}</div>
          <div className="flex items-center gap-2 mt-1">
            <span className={statusPillClass(r.status)}>{r.status}</span>
            {r.artifact_count !== null && (
              <span className="text-[10px] text-text-muted">
                {r.artifact_count} model{r.artifact_count === 1 ? "" : "s"}
              </span>
            )}
            <span className="text-[10px] text-text-dim ml-auto">
              {formatDate(r.started_at)}
            </span>
          </div>
        </button>
      ))}
    </div>
  );
}
