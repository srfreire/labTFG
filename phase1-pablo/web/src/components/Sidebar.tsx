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
const LINE_LEFT = 64; // center X for dots and lines

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
    <aside
      style={{
        position: "fixed",
        left: 0,
        top: 0,
        width: 200,
        height: "100vh",
        background: "#090909",
        borderRight: "1px solid rgba(255,255,255,0.1)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "16px 20px",
          borderBottom: "1px solid rgba(255,255,255,0.08)",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            fontSize: 14,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: 2,
            color: "#fff",
          }}
        >
          DecisionLab
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            marginTop: 4,
          }}
        >
          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.5)" }}>
            Pipeline
          </span>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: connected ? "#4ade80" : "#ef4444",
              display: "inline-block",
              flexShrink: 0,
            }}
          />
        </div>
      </div>

      {/* Timeline */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          padding: "0 0",
        }}
      >
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
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                alignItems: "stretch",
              }}
            >
              {/* Line segment ABOVE dot — fills space from previous dot */}
              <div
                style={{
                  flex: 1,
                  marginLeft: LINE_LEFT,
                  borderLeft: isFirst
                    ? "none"
                    : `1px dashed ${lineColor}`,
                }}
              />

              {/* Dot + Label row */}
              <div
                onClick={
                  clickable ? () => onStageClick(stage) : undefined
                }
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 14,
                  paddingLeft: LINE_LEFT - dotSize / 2 + 0.5,
                  paddingRight: 20,
                  flexShrink: 0,
                  cursor: clickable ? "pointer" : "default",
                  transition: "background 0.15s",
                }}
                onMouseEnter={(e) => {
                  if (clickable)
                    (e.currentTarget as HTMLElement).style.background =
                      "rgba(255,255,255,0.03)";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.background =
                    "transparent";
                }}
              >
                <div
                  style={{
                    width: dotSize,
                    height: dotSize,
                    borderRadius: "50%",
                    background: STATUS_COLORS[status],
                    flexShrink: 0,
                    ...(status === "running"
                      ? {
                          animation: "pulse 1.5s ease-in-out infinite",
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
                style={{
                  flex: 1,
                  marginLeft: LINE_LEFT,
                  borderLeft: isLast
                    ? "none"
                    : `1px dashed ${lineColor}`,
                }}
              />
            </div>
          );
        })}
      </div>

      {/* Cancel button */}
      {isRunning && onCancel && (
        <div
          style={{
            padding: "16px 24px",
            borderTop: "1px solid rgba(255,255,255,0.08)",
            flexShrink: 0,
          }}
        >
          <button
            onClick={onCancel}
            style={{
              width: "100%",
              padding: "8px 0",
              background: "transparent",
              border: "1px solid rgba(239,68,68,0.3)",
              color: "#ef4444",
              fontSize: 10,
              fontFamily: "inherit",
              textTransform: "uppercase",
              letterSpacing: 1,
              cursor: "pointer",
              borderRadius: 0,
            }}
          >
            Cancel
          </button>
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </aside>
  );
}
