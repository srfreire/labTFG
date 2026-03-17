import { Stage, StageStatus, STAGE_CONFIG } from "../types";

interface SidebarProps {
  connected: boolean;
  stages: Record<Stage, StageStatus>;
  currentStage: Stage | null;
  onStageClick?: (stage: Stage) => void;
}

const STATUS_COLORS: Record<StageStatus, string> = {
  pending: "rgba(255,255,255,0.2)",
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

      {/* Timeline — fills remaining height */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-evenly",
          padding: "32px 0",
          position: "relative",
        }}
      >
        {items.map(({ stage, label, indented }, i) => {
          const status = stages[stage];
          const isActive = stage === currentStage;
          const isDone = status === "done";
          const clickable = isDone && onStageClick;
          const isLast = i === items.length - 1;

          // Line color: done segments use green, others use dim
          const lineColor =
            status === "done"
              ? "rgba(74,222,128,0.3)"
              : "rgba(255,255,255,0.08)";

          return (
            <div
              key={stage}
              onClick={clickable ? () => onStageClick(stage) : undefined}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                paddingLeft: indented ? 56 : 36,
                paddingRight: 20,
                position: "relative",
                cursor: clickable ? "pointer" : "default",
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
              {/* Vertical dashed connector line BELOW this dot */}
              {!isLast && (
                <div
                  style={{
                    position: "absolute",
                    left: indented ? 59 : 39,
                    top: "50%",
                    bottom: 0,
                    width: 0,
                    height: "100%",
                    borderLeft: `1px dashed ${lineColor}`,
                    pointerEvents: "none",
                    zIndex: 0,
                  }}
                />
              )}

              {/* Dot */}
              <div
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  background: STATUS_COLORS[status],
                  flexShrink: 0,
                  position: "relative",
                  zIndex: 1,
                  ...(status === "running"
                    ? { animation: "pulse 1.5s ease-in-out infinite" }
                    : {}),
                }}
              />

              {/* Label */}
              <span
                style={{
                  fontSize: 10,
                  textTransform: "uppercase",
                  letterSpacing: 1,
                  color: isActive ? "#fff" : "rgba(255,255,255,0.5)",
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
