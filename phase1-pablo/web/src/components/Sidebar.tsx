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
          <span
            style={{
              fontSize: 11,
              color: "rgba(255,255,255,0.5)",
            }}
          >
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

      {/* Stage list — fills remaining height as a timeline */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "24px 20px",
          gap: 4,
        }}
      >
        {STAGE_CONFIG.map(({ stage, label, indented }) => {
          const status = stages[stage];
          const isActive = stage === currentStage;
          const isDone = status === "done";
          const clickable = isDone && onStageClick;

          return (
            <div
              key={stage}
              onClick={clickable ? () => onStageClick(stage) : undefined}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "8px 10px",
                marginLeft: indented ? 20 : 0,
                cursor: clickable ? "pointer" : "default",
                color: isActive ? "#fff" : "rgba(255,255,255,0.5)",
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
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: STATUS_COLORS[status],
                  flexShrink: 0,
                  ...(status === "running"
                    ? { animation: "pulse 1.5s ease-in-out infinite" }
                    : {}),
                }}
              />
              <span
                style={{
                  fontSize: 10,
                  textTransform: "uppercase",
                  letterSpacing: 1,
                }}
              >
                {label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Pulse animation keyframes */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </aside>
  );
}
