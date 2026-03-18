import { Stage, StageStatus, STAGE_CONFIG } from "../types";
interface SidebarProps {
  connected: boolean;
  stages: Record<Stage, StageStatus>;
  currentStage: Stage | null;
  isRunning?: boolean;
  onCancel?: () => void;
  onStageClick?: (stage: Stage) => void;
}

const STATUS_COLORS: Record<StageStatus, string> = {
  pending: "rgba(255,255,255,0.15)",
  running: "#fbbf24",
  done: "#4ade80",
  error: "#ef4444",
};

const MAIN_DOT = 10;
const REVIEW_DOT = 7;
const LINE_LEFT = 40; // center X for dots and lines

export default function Sidebar({
  connected,
  stages,
  currentStage,
  isRunning,
  onCancel,
  onStageClick,
}: SidebarProps) {
  const items = STAGE_CONFIG;

  return (
    <aside className="fixed left-4 top-4 bottom-4 w-[160px] rounded-2xl bg-surface border border-border shadow-xl shadow-black/20 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-border-subtle shrink-0">
        <div className="text-[15px] font-semibold tracking-tight text-text">
          DecisionLab
        </div>
        <div className="flex items-center gap-1.5 mt-1">
          <span className="text-[11px] text-text-muted">Pipeline</span>
          <span
            className="w-2 h-2 rounded-full inline-block shrink-0"
            style={{ background: connected ? "#4ade80" : "#ef4444" }}
          />
        </div>
      </div>

      {/* Timeline */}
      <div className="flex-1 flex flex-col">
        {items.map(({ stage, label, indented }, i) => {
          const status = stages[stage];
          const isActive = stage === currentStage;
          const isDone = status === "done";
          const clickable = isDone && onStageClick;
          const isReview = indented;
          const isFirst = i === 0;
          const isLast = i === items.length - 1;

          const dotSize = isReview ? REVIEW_DOT : MAIN_DOT;
          const lineColor = isDone
            ? "rgba(74,222,128,0.25)"
            : "rgba(255,255,255,0.15)";

          return (
            <div
              key={stage}
              className="flex-1 flex flex-col items-stretch"
            >
              {/* Line segment ABOVE dot — fills space from previous dot */}
              <div
                className="flex-1 ml-[40px]"
                style={{
                  borderLeft: isFirst ? "none" : `1px dashed ${lineColor}`,
                }}
              />

              {/* Dot + Label row */}
              <div
                onClick={clickable ? () => onStageClick(stage) : undefined}
                className={[
                  "flex items-center gap-3.5 pr-5 shrink-0 transition-colors duration-150",
                  clickable ? "cursor-pointer hover:bg-surface-hover" : "cursor-default",
                ].join(" ")}
                style={{
                  paddingLeft: LINE_LEFT - dotSize / 2 + 0.5,
                }}
              >
                <div
                  className={`rounded-full shrink-0${status === "running" ? " animate-pulse-dot" : ""}`}
                  style={{
                    width: dotSize,
                    height: dotSize,
                    background: STATUS_COLORS[status],
                    ...(status === "running"
                      ? {
                          boxShadow: `0 0 8px ${STATUS_COLORS[status]}`,
                        }
                      : {}),
                  }}
                />
                <span
                  style={{
                    fontSize: isReview ? 9 : 10,
                    textTransform: "uppercase",
                    letterSpacing: isReview ? 0.5 : 1,
                    color: isActive
                      ? "#fff"
                      : isDone
                        ? "rgba(74,222,128,0.7)"
                        : isReview
                          ? "rgba(255,255,255,0.25)"
                          : "rgba(255,255,255,0.4)",
                    fontWeight: isActive ? 600 : 400,
                  }}
                >
                  {label}
                </span>
              </div>

              {/* Line segment BELOW dot — fills space to next dot */}
              <div
                className="flex-1 ml-[40px]"
                style={{
                  borderLeft: isLast ? "none" : `1px dashed ${lineColor}`,
                }}
              />
            </div>
          );
        })}
      </div>

      {/* Cancel button */}
      {isRunning && onCancel && (
        <div className="px-6 py-3 border-t border-border-subtle shrink-0">
          <button
            onClick={onCancel}
            className="w-full py-2 bg-transparent border border-accent-red/30 text-accent-red text-[10px] uppercase tracking-[1px] cursor-pointer rounded-lg hover:bg-accent-red/10"
          >
            Cancel
          </button>
        </div>
      )}

    </aside>
  );
}
