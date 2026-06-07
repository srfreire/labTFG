import { useEffect, useState } from "react";
import { Stage, StageStatus, STAGE_CONFIG, AgentState, MEMORY_AGENT_STAGES, MEMORY_STAGE_OF } from "../types";
import { THEME } from "./Graph";

interface SidebarProps {
  connected: boolean;
  stages: Record<Stage, StageStatus>;
  currentStage: Stage | null;
  isRunning?: boolean;
  onCancel?: () => void;
  onStageClick?: (stage: Stage) => void;
  agents?: AgentState[];
  onCollapsedChange?: (collapsed: boolean) => void;
}

// Pull sidebar status colors from the agrex theme so graph nodes and
// pipeline dots share one palette (running = amber, done = green, error
// = red, pending = the same faint border tint agrex uses on idle nodes).
const STATUS_COLORS: Record<StageStatus, string> = {
  pending: THEME.nodeBorder,
  running: THEME.statusRunning,
  done: THEME.statusDone,
  error: THEME.statusError,
};

const MAIN_DOT = 10;
const REVIEW_DOT = 7;
const LINE_LEFT = 40; // center X for dots and lines
const MEMORY_DOT = 6;

const MEMORY_STATUS_COLORS: Record<AgentState["status"], string> = {
  idle: THEME.nodeBorder,
  working: THEME.statusRunning,
  done: THEME.statusDone,
  failed: THEME.statusError,
};

function MemoryAgentDot({
  status,
  parentDone,
  error,
}: {
  status: AgentState["status"];
  parentDone: boolean;
  error?: string;
}) {
  const isWorking = status === "working";
  const isDone = status === "done";
  const isFailed = status === "failed";
  const show = parentDone || isWorking || isDone || isFailed;
  const lineColor = show
    ? "rgba(255,255,255,0.12)"
    : "rgba(255,255,255,0.08)";

  return (
    <>
      {/* Line above memory dot */}
      <div
        className="ml-[40px]"
        style={{
          borderLeft: `1px dashed ${lineColor}`,
          height: 8,
        }}
      />
      {/* Memory dot + label */}
      <div
        className="flex items-center gap-3.5 pr-5 shrink-0"
        style={{ paddingLeft: LINE_LEFT - MEMORY_DOT / 2 + 0.5 }}
        title={isFailed ? `Memory write failed: ${error ?? "unknown error"}` : undefined}
      >
        <div
          className={`rounded-full shrink-0${isWorking ? " animate-pulse-dot" : ""}`}
          style={{
            width: MEMORY_DOT,
            height: MEMORY_DOT,
            background: MEMORY_STATUS_COLORS[status],
            transition: "background 200ms",
            ...(isWorking
              ? { boxShadow: `0 0 6px ${MEMORY_STATUS_COLORS.working}` }
              : isFailed
                ? { boxShadow: `0 0 6px ${MEMORY_STATUS_COLORS.failed}` }
                : {}),
          }}
        />
        <span
          style={{
            fontSize: 8,
            textTransform: "uppercase",
            letterSpacing: 0.5,
            color: isFailed
              ? MEMORY_STATUS_COLORS.failed
              : isWorking
                ? "#fff"
                : isDone
                  ? "rgba(255,255,255,0.5)"
                  : "rgba(255,255,255,0.25)",
            fontWeight: isWorking || isFailed ? 600 : 400,
            transition: "color 200ms",
          }}
        >
          {isFailed ? "MEMORY · FAILED" : "MEMORY"}
        </span>
      </div>
    </>
  );
}

export default function Sidebar({
  connected,
  stages,
  currentStage,
  isRunning,
  onCancel,
  onStageClick,
  agents = [],
  onCollapsedChange,
}: SidebarProps) {
  const items = STAGE_CONFIG;
  const memoryAgent = agents.find((a) => a.name === "memory_agent");
  const [collapsed, setCollapsed] = useState(false);

  // Memory tick status for work stage `s`: read directly from the dedicated
  // MEMORY_X stage's status (synthesized in `useWebSocket` from work-stage
  // transitions and review markers, same source of truth as every other dot).
  const STATUS_TO_AGENT: Record<StageStatus, AgentState["status"]> = {
    pending: "idle",
    running: "working",
    done: "done",
    error: "failed",
  };
  function memoryStatusFor(s: Stage): AgentState["status"] {
    const memStage = MEMORY_STAGE_OF[s];
    if (!memStage) return "idle";
    return STATUS_TO_AGENT[stages[memStage]];
  }

  useEffect(() => {
    onCollapsedChange?.(collapsed);
  }, [collapsed, onCollapsedChange]);

  return (
    <>
    <aside
      className="panel-chrome fixed left-4 top-4 w-[160px] z-30 flex flex-col overflow-hidden"
      style={{
        bottom: 212,
        transform: collapsed ? 'translateX(calc(-100% - 20px))' : 'translateX(0)',
        transition: 'transform 250ms cubic-bezier(0.23, 1, 0.32, 1)',
      }}
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-border-subtle shrink-0">
        <div className="text-[17px] font-semibold tracking-tight text-text">
          DecisionLab
        </div>
        <div className="flex items-center gap-1.5 mt-1">
          <span className="text-[13px] text-text-muted">Pipeline</span>
          <span
            className="w-2 h-2 rounded-full inline-block shrink-0"
            style={{ background: connected ? THEME.statusDone : THEME.statusError }}
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
          const showMemoryAfter =
            memoryAgent && MEMORY_AGENT_STAGES.has(stage);

          const dotSize = isReview ? REVIEW_DOT : MAIN_DOT;
          const lineColor = isDone
            ? "rgba(255,255,255,0.12)"
            : "rgba(255,255,255,0.08)";

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
                        ? "rgba(255,255,255,0.5)"
                        : isReview
                          ? "rgba(255,255,255,0.25)"
                          : "rgba(255,255,255,0.4)",
                    fontWeight: isActive ? 600 : 400,
                  }}
                >
                  {label}
                </span>
              </div>

              {/* Memory Agent interstitial — between work stage and its REVIEW */}
              {showMemoryAfter && (
                <MemoryAgentDot
                  status={memoryStatusFor(stage)}
                  parentDone={isDone}
                  error={memoryAgent?.error}
                />
              )}

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
            className="w-full py-2 bg-accent-red/8 border border-accent-red/25 text-accent-red text-[12px] uppercase tracking-[1px] cursor-pointer rounded-lg hover:bg-accent-red/15"
          >
            Cancel
          </button>
        </div>
      )}

    </aside>

    {/* Toggle tab */}
    <button
      onClick={() => setCollapsed((v) => !v)}
      className="fixed z-30 top-1/2 -translate-y-1/2 w-5 h-10 rounded-r-md backdrop-blur-[16px] border border-l-0 flex items-center justify-center cursor-pointer text-text-dim hover:text-text"
      style={{
        left: collapsed ? 0 : 176,
        // Inline the agrex panel-chrome colours (background + border) so
        // the toggle tab blends with the sidebar instead of using the
        // app's 0.1 border token.
        background: 'color-mix(in srgb, var(--color-bg) 80%, transparent)',
        borderColor: 'rgba(255,255,255,0.15)',
        transition: 'left 250ms cubic-bezier(0.23, 1, 0.32, 1)',
      }}
    >
      <svg width="8" height="8" viewBox="0 0 8 8" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
        style={{
          transform: collapsed ? 'rotate(0deg)' : 'rotate(180deg)',
          transition: 'transform 200ms cubic-bezier(0.23, 1, 0.32, 1)',
        }}
      >
        <path d="M2 1L6 4L2 7" />
      </svg>
    </button>
    </>
  );
}
