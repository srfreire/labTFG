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

const DOT_X = 36; // px from left for the vertical line

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
          position: "relative",
          display: "flex",
          flexDirection: "column",
          padding: "24px 0",
        }}
      >
        {/* Continuous vertical dashed line behind dots */}
        <div
          style={{
            position: "absolute",
            left: DOT_X + 4,
            top: 24,
            bottom: 24,
            width: 0,
            borderLeft: "1px dashed rgba(255,255,255,0.15)",
            pointerEvents: "none",
          }}
        />

        {items.map(({ stage, label, indented }) => {
          const status = stages[stage];
          const isActive = stage === currentStage;
          const isDone = status === "done";
          const clickable = isDone && onStageClick;
          const isReview = indented;

          const dotSize = isReview ? 7 : 10;

          return (
            <div
              key={stage}
              onClick={clickable ? () => onStageClick(stage) : undefined}
              style={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                gap: 14,
                paddingLeft: DOT_X,
                paddingRight: 20,
                cursor: clickable ? "pointer" : "default",
                transition: "background 0.15s",
                position: "relative",
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
              {/* Dot — centered on the vertical line */}
              <div
                style={{
                  width: dotSize,
                  height: dotSize,
                  borderRadius: "50%",
                  background: STATUS_COLORS[status],
                  flexShrink: 0,
                  position: "relative",
                  zIndex: 1,
                  // Center dot on the line: line is at DOT_X+4,
                  // dot needs its center at DOT_X+4
                  marginLeft: (9 - dotSize) / 2,
                  ...(status === "running"
                    ? {
                        animation: "pulse 1.5s ease-in-out infinite",
                        boxShadow: `0 0 8px ${STATUS_COLORS[status]}`,
                      }
                    : {}),
                }}
              />

              {/* Label */}
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
                  position: "relative",
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
