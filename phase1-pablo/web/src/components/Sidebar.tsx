import { useState, useRef, type KeyboardEvent } from "react";
import { Stage, StageStatus, STAGE_CONFIG } from "../types";

interface SidebarProps {
  connected: boolean;
  stages: Record<Stage, StageStatus>;
  currentStage: Stage | null;
  isRunning: boolean;
  onRun: (problem: string) => void;
  onCancel: () => void;
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
  isRunning,
  onRun,
  onCancel,
  onStageClick,
}: SidebarProps) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleRun = () => {
    const trimmed = input.trim();
    if (!trimmed) return;
    onRun(trimmed);
    setInput("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") handleRun();
  };

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

      {/* Stage list */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "12px 20px",
          borderBottom: "1px solid rgba(255,255,255,0.08)",
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
                gap: 8,
                padding: "6px 8px",
                marginLeft: indented ? 16 : 0,
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
                (e.currentTarget as HTMLElement).style.background = "transparent";
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

      {/* Bottom controls */}
      <div style={{ padding: "12px 20px" }}>
        {!isRunning ? (
          <>
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Describe a decision problem..."
              style={{
                width: "100%",
                background: "transparent",
                border: "1px solid rgba(255,255,255,0.15)",
                color: "#fff",
                fontSize: 11,
                fontFamily: "inherit",
                padding: "8px 10px",
                outline: "none",
                borderRadius: 0,
                boxSizing: "border-box",
              }}
            />
            <button
              onClick={handleRun}
              disabled={!input.trim()}
              style={{
                width: "100%",
                marginTop: 8,
                padding: "8px 10px",
                background: "transparent",
                border: "1px solid rgba(255,255,255,0.3)",
                color: !input.trim() ? "rgba(255,255,255,0.3)" : "#fff",
                fontSize: 11,
                fontFamily: "inherit",
                textTransform: "uppercase",
                letterSpacing: 1,
                cursor: !input.trim() ? "default" : "pointer",
                borderRadius: 0,
                transition: "background 0.15s",
              }}
              onMouseEnter={(e) => {
                if (input.trim())
                  (e.currentTarget as HTMLElement).style.background =
                    "rgba(255,255,255,0.05)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.background = "transparent";
              }}
            >
              Run
            </button>
          </>
        ) : (
          <button
            onClick={onCancel}
            style={{
              width: "100%",
              padding: "8px 10px",
              background: "transparent",
              border: "1px solid rgba(239,68,68,0.5)",
              color: "#ef4444",
              fontSize: 11,
              fontFamily: "inherit",
              textTransform: "uppercase",
              letterSpacing: 1,
              cursor: "pointer",
              borderRadius: 0,
            }}
          >
            Cancel
          </button>
        )}
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
