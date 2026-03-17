import { Stage, StageStatus, STAGE_CONFIG } from "../types";

interface SidebarProps {
  connected: boolean;
  stages: Record<Stage, StageStatus>;
  currentStage: Stage | null;
  onStageClick?: (stage: Stage) => void;
}

const STATUS_COLORS: Record<StageStatus, string> = {
  pending: "rgba(255,255,255,0.12)",
  running: "#fbbf24",
  done: "#4ade80",
  error: "#ef4444",
};

// All dots centered at this X offset (center of dot)
const DOT_CENTER_X = 40;
const MAIN_DOT = 10;
const REVIEW_DOT = 7;

export default function Sidebar({
  connected,
  stages,
  currentStage,
  onStageClick,
}: SidebarProps) {
  const items = STAGE_CONFIG;

  return (
    <aside
      style={{
        position: "fixed",
        left: 0,
        top: 0,
        width: 280,
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
          padding: "24px 0",
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
          const dotLeft = DOT_CENTER_X - dotSize / 2;

          const lineColor =
            isDone ? "rgba(74,222,128,0.2)" : "rgba(255,255,255,0.15)";

          return (
            <div
              key={stage}
              onClick={clickable ? () => onStageClick(stage) : undefined}
              style={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                position: "relative",
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
              {/* Line from top edge to dot center (connects from previous) */}
              {!isFirst && (
                <div
                  style={{
                    position: "absolute",
                    left: DOT_CENTER_X,
                    top: 0,
                    height: "50%",
                    width: 0,
                    borderLeft: `1px dashed ${lineColor}`,
                    pointerEvents: "none",
                    zIndex: 0,
                  }}
                />
              )}

              {/* Line from dot center to bottom edge (connects to next) */}
              {!isLast && (
                <div
                  style={{
                    position: "absolute",
                    left: DOT_CENTER_X,
                    top: "50%",
                    height: "50%",
                    width: 0,
                    borderLeft: `1px dashed ${lineColor}`,
                    pointerEvents: "none",
                    zIndex: 0,
                  }}
                />
              )}

              {/* Dot — solid halo masks the line behind */}
              <div
                style={{
                  position: "absolute",
                  left: dotLeft,
                  width: dotSize,
                  height: dotSize,
                  borderRadius: "50%",
                  background: STATUS_COLORS[status],
                  zIndex: 1,
                  boxShadow:
                    status === "running"
                      ? `0 0 0 4px #090909, 0 0 10px ${STATUS_COLORS[status]}`
                      : "0 0 0 4px #090909",
                  ...(status === "running"
                    ? { animation: "pulse 1.5s ease-in-out infinite" }
                    : {}),
                }}
              />

              {/* Label */}
              <span
                style={{
                  marginLeft: DOT_CENTER_X + MAIN_DOT / 2 + 14,
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
                  zIndex: 1,
                }}
              >
                {label}
              </span>
            </div>
          );
        })}
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </aside>
  );
}
