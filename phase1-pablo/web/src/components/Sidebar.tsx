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

export default function Sidebar({
  connected,
  stages,
  currentStage,
  onStageClick,
}: SidebarProps) {
  const items = STAGE_CONFIG;
  const DOT_LEFT = 40; // px from left edge for non-indented dots
  const DOT_LEFT_INDENTED = 60;

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
          borderBottom: "1px solid rgba(255,255,255,0.18)",
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

      {/* Timeline — fills remaining height */}
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
          const isLast = i === items.length - 1;
          const dotLeft = indented ? DOT_LEFT_INDENTED : DOT_LEFT;

          // Next item's dot position (for the connector line)
          const nextIndented = !isLast && items[i + 1].indented;
          const nextDotLeft = nextIndented ? DOT_LEFT_INDENTED : DOT_LEFT;

          // Connector line color: use done color if this stage is done
          const lineColor =
            status === "done"
              ? "rgba(74,222,128,0.25)"
              : "rgba(255,255,255,0.18)";

          return (
            <div key={stage} style={{ display: "contents" }}>
              {/* Stage row */}
              <div
                onClick={
                  clickable ? () => onStageClick(stage) : undefined
                }
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  paddingLeft: dotLeft,
                  paddingRight: 20,
                  paddingTop: 4,
                  paddingBottom: 4,
                  cursor: clickable ? "pointer" : "default",
                  flexShrink: 0,
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
                {/* Dot */}
                <div
                  style={{
                    width: 10,
                    height: 10,
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

                {/* Label */}
                <span
                  style={{
                    fontSize: 10,
                    textTransform: "uppercase",
                    letterSpacing: 1,
                    color: isActive
                      ? "#fff"
                      : isDone
                        ? "rgba(74,222,128,0.7)"
                        : "rgba(255,255,255,0.4)",
                    fontWeight: isActive ? 600 : 400,
                  }}
                >
                  {label}
                </span>
              </div>

              {/* Connector line between this dot and the next */}
              {!isLast && (
                <div
                  style={{
                    flex: 1,
                    minHeight: 12,
                    position: "relative",
                  }}
                >
                  {/* SVG line connecting current dot center to next dot center */}
                  <svg
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      height: "100%",
                      overflow: "visible",
                      pointerEvents: "none",
                    }}
                  >
                    <line
                      x1={dotLeft + 5}
                      y1={0}
                      x2={nextDotLeft + 5}
                      y2="100%"
                      stroke={lineColor}
                      strokeWidth={1}
                      strokeDasharray="4 4"
                    />
                  </svg>
                </div>
              )}
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
