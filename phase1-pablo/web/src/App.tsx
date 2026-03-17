import { useState, useCallback, useRef, type KeyboardEvent } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import Sidebar from "./components/Sidebar";
import Graph from "./components/Graph";
import {
  ReviewResearch,
  ReviewFormalize,
  EnvSpecUpload,
  ReviewReason,
  ReviewBuild,
} from "./components/reviews";
import MarkdownRenderer from "./components/shared/MarkdownRenderer";
import CodeBlock from "./components/shared/CodeBlock";
import { Stage, type GraphNode } from "./types";

/* ------------------------------------------------------------------ */
/*  Node detail panel                                                  */
/* ------------------------------------------------------------------ */

function NodeDetail({
  node,
  onClose,
}: {
  node: GraphNode;
  onClose: () => void;
}) {
  const meta = node.meta;

  let content: React.ReactNode = null;

  switch (node.kind) {
    case "agent":
    case "sub_agent":
      if (meta.output) {
        content = <MarkdownRenderer content={String(meta.output)} />;
      }
      break;
    case "file":
      if (meta.content) {
        content = (
          <CodeBlock
            code={String(meta.content)}
            language={
              typeof meta.path === "string"
                ? meta.path.split(".").pop()
                : undefined
            }
          />
        );
      }
      break;
    case "search":
      content = (
        <>
          {meta.query && (
            <div
              className="text-[11px] mb-2"
              style={{ color: "rgba(255,255,255,0.6)" }}
            >
              <span
                className="text-[9px] uppercase tracking-[1px] block mb-1"
                style={{ color: "rgba(255,255,255,0.3)" }}
              >
                Query
              </span>
              {String(meta.query)}
            </div>
          )}
          {Array.isArray(meta.results) && meta.results.length > 0 && (
            <div>
              <span
                className="text-[9px] uppercase tracking-[1px] block mb-1"
                style={{ color: "rgba(255,255,255,0.3)" }}
              >
                Results
              </span>
              {meta.results.map((r, i) => (
                <div
                  key={i}
                  className="text-[11px] py-1"
                  style={{
                    color: "rgba(255,255,255,0.6)",
                    borderBottom: "1px solid rgba(255,255,255,0.06)",
                  }}
                >
                  {String(r)}
                </div>
              ))}
            </div>
          )}
        </>
      );
      break;
    case "tool":
      if (meta.args) {
        content = (
          <CodeBlock
            code={JSON.stringify(meta.args, null, 2)}
            language="json"
          />
        );
      }
      break;
  }

  if (!content) {
    content = (
      <div className="text-[11px]" style={{ color: "rgba(255,255,255,0.4)" }}>
        No details available.
      </div>
    );
  }

  return (
    <div
      className="animate-scale-in"
      style={{
        position: "fixed",
        bottom: 20,
        right: 20,
        width: 380,
        maxHeight: 320,
        background: "#090909",
        border: "1px solid rgba(255,255,255,0.1)",
        zIndex: 50,
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.08)" }}
      >
        <div className="flex items-center gap-2">
          <span
            className="text-[9px] uppercase tracking-[1px]"
            style={{ color: "rgba(255,255,255,0.3)" }}
          >
            {node.kind}
          </span>
          <span className="text-[12px] text-white font-medium">
            {node.label}
          </span>
        </div>
        <button
          className="text-[10px] cursor-pointer"
          style={{
            color: "rgba(255,255,255,0.3)",
            background: "none",
            border: "none",
          }}
          onClick={onClose}
        >
          [x]
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-3">{content}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Review drawer                                                      */
/* ------------------------------------------------------------------ */

function ReviewDrawer({
  stage,
  data,
  onSubmit,
}: {
  stage: Stage;
  data: any;
  onSubmit: (stage: Stage, data: any) => void;
}) {
  const handleSubmit = useCallback(
    (responseData: any) => {
      onSubmit(stage, responseData);
    },
    [stage, onSubmit],
  );

  let reviewComponent: React.ReactNode = null;

  switch (stage) {
    case Stage.REVIEW_RESEARCH:
      reviewComponent = <ReviewResearch data={data} onSubmit={handleSubmit} />;
      break;
    case Stage.REVIEW_FORMALIZE:
      reviewComponent = <ReviewFormalize data={data} onSubmit={handleSubmit} />;
      break;
    case Stage.GET_ENV_SPEC:
      reviewComponent = <EnvSpecUpload onSubmit={handleSubmit} />;
      break;
    case Stage.REVIEW_REASON:
      reviewComponent = <ReviewReason data={data} onSubmit={handleSubmit} />;
      break;
    case Stage.REVIEW_BUILD:
      reviewComponent = <ReviewBuild data={data} onSubmit={handleSubmit} />;
      break;
    default:
      return null;
  }

  return (
    <div
      className="animate-slide-in-right"
      style={{
        width: "50%",
        height: "100%",
        background: "#090909",
        borderLeft: "1px solid rgba(255,255,255,0.1)",
        flexShrink: 0,
        overflow: "hidden",
      }}
    >
      {reviewComponent}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  App                                                                */
/* ------------------------------------------------------------------ */

export default function App() {
  const {
    connected,
    nodes,
    edges,
    stages,
    currentStage,
    reviewRequest,
    isRunning,
    error,
    startPipeline,
    sendReviewResponse,
    cancelPipeline,
    clearError,
  } = useWebSocket();

  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [problemInput, setProblemInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelectedNode((prev) => (prev?.id === node.id ? null : node));
  }, []);

  const handleRun = useCallback(() => {
    const trimmed = problemInput.trim();
    if (!trimmed) return;
    startPipeline(trimmed);
    setProblemInput("");
  }, [problemInput, startPipeline]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") handleRun();
    },
    [handleRun],
  );

  const hasGraph = nodes.length > 0;
  const reviewActive = reviewRequest !== null;
  const showIdle = !hasGraph && !isRunning;

  return (
    <div style={{ display: "flex", height: "100vh", width: "100vw" }}>
      {/* Sidebar — pipeline only */}
      <Sidebar
        connected={connected}
        stages={stages}
        currentStage={currentStage}
      />

      {/* Main panel */}
      <div
        style={{
          marginLeft: 280,
          flex: 1,
          display: "flex",
          flexDirection: "column",
          position: "relative",
          height: "100vh",
          overflow: "hidden",
        }}
      >
        {/* Error bar */}
        {error && (
          <div
            onClick={clearError}
            style={{
              background: "rgba(239,68,68,0.1)",
              border: "1px solid rgba(239,68,68,0.3)",
              color: "#ef4444",
              fontSize: 11,
              padding: "8px 16px",
              cursor: "pointer",
              flexShrink: 0,
            }}
          >
            {error}
          </div>
        )}

        {/* Content area */}
        <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
          {showIdle ? (
            /* Idle — problem input centered */
            <div
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 16,
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  textTransform: "uppercase",
                  letterSpacing: 2,
                  color: "rgba(255,255,255,0.3)",
                  marginBottom: 8,
                }}
              >
                Describe a decision problem
              </div>
              <input
                ref={inputRef}
                type="text"
                value={problemInput}
                onChange={(e) => setProblemInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="e.g. survival decision-making"
                autoFocus
                style={{
                  width: 420,
                  maxWidth: "80%",
                  background: "transparent",
                  border: "1px solid rgba(255,255,255,0.15)",
                  color: "#fff",
                  fontSize: 13,
                  fontFamily: "inherit",
                  padding: "12px 16px",
                  outline: "none",
                  borderRadius: 0,
                  textAlign: "center",
                }}
              />
              <button
                onClick={handleRun}
                disabled={!problemInput.trim()}
                style={{
                  padding: "10px 32px",
                  background: "transparent",
                  border: "1px solid rgba(255,255,255,0.3)",
                  color: !problemInput.trim()
                    ? "rgba(255,255,255,0.3)"
                    : "#fff",
                  fontSize: 11,
                  fontFamily: "inherit",
                  textTransform: "uppercase",
                  letterSpacing: 1,
                  cursor: !problemInput.trim() ? "default" : "pointer",
                  borderRadius: 0,
                }}
              >
                Run
              </button>
            </div>
          ) : (
            <>
              {/* Graph */}
              <div style={{ flex: 1, minWidth: 0, height: "100%" }}>
                <Graph
                  nodes={nodes}
                  edges={edges}
                  onNodeClick={handleNodeClick}
                />
              </div>

              {/* Review drawer */}
              {reviewActive && (
                <ReviewDrawer
                  stage={reviewRequest.stage}
                  data={reviewRequest.data}
                  onSubmit={sendReviewResponse}
                />
              )}

              {/* Cancel button — floating top-right on graph */}
              {isRunning && (
                <button
                  onClick={cancelPipeline}
                  style={{
                    position: "absolute",
                    top: 12,
                    right: reviewActive ? "calc(50% + 12px)" : 12,
                    padding: "6px 16px",
                    background: "rgba(0,0,0,0.7)",
                    border: "1px solid rgba(239,68,68,0.4)",
                    color: "#ef4444",
                    fontSize: 10,
                    fontFamily: "inherit",
                    textTransform: "uppercase",
                    letterSpacing: 1,
                    cursor: "pointer",
                    borderRadius: 0,
                    zIndex: 40,
                  }}
                >
                  Cancel
                </button>
              )}
            </>
          )}
        </div>

        {/* Node detail panel */}
        {selectedNode && (
          <NodeDetail
            node={selectedNode}
            onClose={() => setSelectedNode(null)}
          />
        )}
      </div>
    </div>
  );
}
