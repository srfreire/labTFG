import {
  useState,
  useCallback,
  useRef,
  useMemo,
  useEffect,
  type KeyboardEvent,
} from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import Sidebar from "./components/Sidebar";
import Graph from "./components/Graph";
import { EnvSpecUpload } from "./components/reviews";
import MarkdownRenderer from "./components/shared/MarkdownRenderer";
import CodeBlock from "./components/shared/CodeBlock";
import { Stage, type GraphNode } from "./types";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function getFileExt(name: string): string {
  const i = name.lastIndexOf(".");
  return i > 0 ? name.slice(i + 1).toLowerCase() : "";
}

const BTN: React.CSSProperties = {
  fontSize: 10,
  fontFamily: "inherit",
  textTransform: "uppercase",
  letterSpacing: 1,
  cursor: "pointer",
  borderRadius: 0,
};

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
    case "output":
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
/*  Output Review Modal                                                */
/* ------------------------------------------------------------------ */

function OutputReviewModal({
  outputs,
  index,
  approvals,
  onIndexChange,
  onApprove,
  onDisapprove,
  onClose,
}: {
  outputs: GraphNode[];
  index: number;
  approvals: Record<string, boolean>;
  onIndexChange: (i: number) => void;
  onApprove: (id: string) => void;
  onDisapprove: (id: string) => void;
  onClose: () => void;
}) {
  if (outputs.length === 0) return null;

  const node = outputs[index];
  const content = String(node.meta?.content || "No content available.");
  const path = String(node.meta?.path || node.label || "");
  const ext = getFileExt(path);
  const approval: boolean | undefined =
    node.id in approvals ? approvals[node.id] : undefined;

  const hasPrev = index > 0;
  const hasNext = index < outputs.length - 1;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.85)",
        backdropFilter: "blur(6px)",
      }}
      onClick={onClose}
    >
      <div
        className="animate-scale-in"
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#0a0a0a",
          border: `1px solid ${
            approval === true
              ? "rgba(34,197,94,0.3)"
              : approval === false
                ? "rgba(239,68,68,0.3)"
                : "rgba(255,255,255,0.1)"
          }`,
          width: "min(820px, 92vw)",
          maxHeight: "88vh",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          transition: "border-color 0.2s",
        }}
      >
        {/* ── Header ── */}
        <div
          style={{
            padding: "14px 20px",
            borderBottom: "1px solid rgba(255,255,255,0.08)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div>
            <div
              style={{ display: "flex", alignItems: "center", gap: 10 }}
            >
              <span
                style={{
                  fontSize: 9,
                  letterSpacing: "1.5px",
                  color: "rgba(255,255,255,0.3)",
                  textTransform: "uppercase",
                }}
              >
                Output
              </span>
              {approval === true && (
                <span
                  style={{
                    fontSize: 8,
                    padding: "2px 6px",
                    background: "rgba(34,197,94,0.12)",
                    border: "1px solid rgba(34,197,94,0.3)",
                    color: "#22c55e",
                    textTransform: "uppercase",
                    letterSpacing: 1,
                  }}
                >
                  Approved
                </span>
              )}
              {approval === false && (
                <span
                  style={{
                    fontSize: 8,
                    padding: "2px 6px",
                    background: "rgba(239,68,68,0.12)",
                    border: "1px solid rgba(239,68,68,0.3)",
                    color: "#ef4444",
                    textTransform: "uppercase",
                    letterSpacing: 1,
                  }}
                >
                  Rejected
                </span>
              )}
            </div>
            <div style={{ fontSize: 13, color: "#fff", marginTop: 4 }}>
              {node.label}
            </div>
          </div>

          <div
            style={{ display: "flex", alignItems: "center", gap: 16 }}
          >
            <span
              style={{ fontSize: 11, color: "rgba(255,255,255,0.35)" }}
            >
              {index + 1} / {outputs.length}
            </span>
            <button
              onClick={onClose}
              style={{
                background: "none",
                border: "none",
                color: "rgba(255,255,255,0.4)",
                fontSize: 18,
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              ✕
            </button>
          </div>
        </div>

        {/* ── Content ── */}
        <div
          style={{
            flex: 1,
            overflow: "auto",
            padding: "20px 24px",
          }}
        >
          {ext === "md" ? (
            <MarkdownRenderer content={content} />
          ) : (
            <CodeBlock code={content} language={ext || undefined} />
          )}
        </div>

        {/* ── Footer ── */}
        <div
          style={{
            padding: "12px 20px",
            borderTop: "1px solid rgba(255,255,255,0.08)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          {/* Navigation */}
          <div style={{ display: "flex", gap: 6 }}>
            <button
              disabled={!hasPrev}
              onClick={() => onIndexChange(index - 1)}
              style={{
                ...BTN,
                padding: "8px 14px",
                background: "none",
                border: "1px solid rgba(255,255,255,0.1)",
                color: hasPrev
                  ? "rgba(255,255,255,0.6)"
                  : "rgba(255,255,255,0.15)",
                cursor: hasPrev ? "pointer" : "default",
              }}
            >
              ← Prev
            </button>
            <button
              disabled={!hasNext}
              onClick={() => onIndexChange(index + 1)}
              style={{
                ...BTN,
                padding: "8px 14px",
                background: "none",
                border: "1px solid rgba(255,255,255,0.1)",
                color: hasNext
                  ? "rgba(255,255,255,0.6)"
                  : "rgba(255,255,255,0.15)",
                cursor: hasNext ? "pointer" : "default",
              }}
            >
              Next →
            </button>
          </div>

          {/* Approve / Disapprove */}
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={() => onDisapprove(node.id)}
              style={{
                ...BTN,
                padding: "8px 20px",
                background:
                  approval === false
                    ? "rgba(239,68,68,0.15)"
                    : "transparent",
                border: `1px solid ${
                  approval === false
                    ? "rgba(239,68,68,0.5)"
                    : "rgba(239,68,68,0.2)"
                }`,
                color: "#ef4444",
              }}
            >
              Disapprove
            </button>
            <button
              onClick={() => onApprove(node.id)}
              style={{
                ...BTN,
                padding: "8px 20px",
                background:
                  approval === true
                    ? "rgba(34,197,94,0.15)"
                    : "transparent",
                border: `1px solid ${
                  approval === true
                    ? "rgba(34,197,94,0.5)"
                    : "rgba(34,197,94,0.2)"
                }`,
                color: "#22c55e",
              }}
            >
              Approve
            </button>
          </div>
        </div>
      </div>
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
    sendRouterPrompt,
    cancelPipeline,
    clearError,
  } = useWebSocket();

  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [problemInput, setProblemInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  /* ── Output review state ── */
  const [showOutputModal, setShowOutputModal] = useState(false);
  const [outputIndex, setOutputIndex] = useState(0);
  const [outputApprovals, setOutputApprovals] = useState<
    Record<string, boolean>
  >({});
  const [routerPrompt, setRouterPrompt] = useState("");

  const reviewActive = reviewRequest !== null;

  /* Collect done output nodes */
  const stageOutputs = useMemo(
    () => nodes.filter((n) => n.kind === "output" && n.status === "done"),
    [nodes],
  );

  /* Reset review state when review clears */
  useEffect(() => {
    if (!reviewActive) {
      setShowOutputModal(false);
      setOutputIndex(0);
      setOutputApprovals({});
      setRouterPrompt("");
    }
  }, [reviewActive]);

  /* Clamp index */
  useEffect(() => {
    if (outputIndex >= stageOutputs.length && stageOutputs.length > 0) {
      setOutputIndex(stageOutputs.length - 1);
    }
  }, [outputIndex, stageOutputs.length]);

  /* ── Node click ── */
  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      if (reviewActive && node.kind === "output" && node.status === "done") {
        const idx = stageOutputs.findIndex((n) => n.id === node.id);
        if (idx >= 0) {
          setOutputIndex(idx);
          setShowOutputModal(true);
        }
        return;
      }
      setSelectedNode((prev) => (prev?.id === node.id ? null : node));
    },
    [reviewActive, stageOutputs],
  );

  /* ── Pipeline start ── */
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

  /* ── Output approval ── */
  const handleApproveOutput = useCallback(
    (nodeId: string) => {
      setOutputApprovals((prev) => ({ ...prev, [nodeId]: true }));
      // Auto-advance to next
      setOutputIndex((i) => (i < stageOutputs.length - 1 ? i + 1 : i));
    },
    [stageOutputs.length],
  );

  const handleDisapproveOutput = useCallback((nodeId: string) => {
    setOutputApprovals((prev) => ({ ...prev, [nodeId]: false }));
  }, []);

  /* ── Continue / submit review ── */
  const handleContinue = useCallback(() => {
    if (!reviewRequest) return;

    const items =
      reviewRequest.data.paradigms ||
      reviewRequest.data.specs ||
      reviewRequest.data.models ||
      [];

    const anyRejected = stageOutputs.some(
      (n) => outputApprovals[n.id] === false,
    );

    sendReviewResponse(reviewRequest.stage, {
      approved: Object.fromEntries(
        items.map((p: any) => [
          p.slug || p.id || p.spec_id,
          !anyRejected,
        ]),
      ),
    });

    setShowOutputModal(false);
    setSelectedNode(null);
  }, [reviewRequest, stageOutputs, outputApprovals, sendReviewResponse]);

  /* ── Router prompt ── */
  const handleSendRouterPrompt = useCallback(() => {
    const trimmed = routerPrompt.trim();
    if (!trimmed) return;
    sendRouterPrompt(trimmed);
    setRouterPrompt("");
  }, [routerPrompt, sendRouterPrompt]);

  const hasGraph = nodes.length > 0;
  const showIdle = !hasGraph && !isRunning;

  /* Review progress */
  const reviewedCount = stageOutputs.filter(
    (n) => n.id in outputApprovals,
  ).length;

  const isEnvSpec = reviewRequest?.stage === Stage.GET_ENV_SPEC;

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
          marginLeft: 200,
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
                  reviewActive={reviewActive}
                />
              </div>

              {/* ── Stage completion bar ── */}
              {reviewActive && (
                <div
                  className="animate-slide-up"
                  style={{
                    position: "absolute",
                    bottom: 0,
                    left: 0,
                    right: 0,
                    zIndex: 50,
                    background: "rgba(9,9,9,0.96)",
                    borderTop: "1px solid rgba(34,197,94,0.15)",
                    backdropFilter: "blur(10px)",
                    padding: "16px 24px",
                  }}
                >
                  {isEnvSpec ? (
                    /* ENV SPEC — upload mode */
                    <div>
                      <span
                        style={{
                          fontSize: 9,
                          textTransform: "uppercase",
                          letterSpacing: "1.5px",
                          color: "#fbbf24",
                        }}
                      >
                        Environment Specification Required
                      </span>
                      <div
                        style={{
                          fontSize: 11,
                          color: "rgba(255,255,255,0.6)",
                          marginTop: 4,
                          marginBottom: 12,
                        }}
                      >
                        Upload or paste the environment specification JSON.
                      </div>
                      <EnvSpecUpload
                        onSubmit={(data) =>
                          sendReviewResponse(Stage.GET_ENV_SPEC, data)
                        }
                      />
                    </div>
                  ) : (
                    /* Normal output review mode */
                    <>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          marginBottom: 12,
                        }}
                      >
                        <div>
                          <span
                            style={{
                              fontSize: 9,
                              textTransform: "uppercase",
                              letterSpacing: "1.5px",
                              color: "#22c55e",
                            }}
                          >
                            Stage Complete
                          </span>
                          <div
                            style={{
                              fontSize: 11,
                              color: "rgba(255,255,255,0.6)",
                              marginTop: 4,
                            }}
                          >
                            Review generated outputs before continuing.
                            {stageOutputs.length > 0 && (
                              <span
                                style={{
                                  marginLeft: 10,
                                  color: "rgba(255,255,255,0.3)",
                                }}
                              >
                                {reviewedCount}/{stageOutputs.length} reviewed
                              </span>
                            )}
                          </div>
                        </div>
                        <div style={{ display: "flex", gap: 10 }}>
                          {stageOutputs.length > 0 && (
                            <button
                              onClick={() => {
                                setOutputIndex(0);
                                setShowOutputModal(true);
                              }}
                              style={{
                                ...BTN,
                                padding: "8px 20px",
                                background: "rgba(34,197,94,0.08)",
                                border: "1px solid rgba(34,197,94,0.25)",
                                color: "#22c55e",
                              }}
                            >
                              View Outputs ({stageOutputs.length})
                            </button>
                          )}
                          <button
                            onClick={handleContinue}
                            style={{
                              ...BTN,
                              padding: "8px 24px",
                              background: "rgba(255,255,255,0.05)",
                              border: "1px solid rgba(255,255,255,0.2)",
                              color: "#fff",
                            }}
                          >
                            Continue →
                          </button>
                        </div>
                      </div>

                      {/* Router prompt */}
                      <div style={{ display: "flex", gap: 8 }}>
                        <input
                          type="text"
                          value={routerPrompt}
                          onChange={(e) => setRouterPrompt(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleSendRouterPrompt();
                          }}
                          placeholder="Send instructions to the router..."
                          style={{
                            flex: 1,
                            background: "transparent",
                            border: "1px solid rgba(255,255,255,0.08)",
                            color: "#fff",
                            fontSize: 11,
                            fontFamily: "inherit",
                            padding: "8px 12px",
                            outline: "none",
                            borderRadius: 0,
                          }}
                        />
                        <button
                          onClick={handleSendRouterPrompt}
                          disabled={!routerPrompt.trim()}
                          style={{
                            ...BTN,
                            padding: "8px 16px",
                            border: "1px solid rgba(255,255,255,0.12)",
                            background: "transparent",
                            color: routerPrompt.trim()
                              ? "#fff"
                              : "rgba(255,255,255,0.25)",
                            cursor: routerPrompt.trim()
                              ? "pointer"
                              : "default",
                          }}
                        >
                          Send
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* ── Output review modal ── */}
              {showOutputModal && stageOutputs.length > 0 && (
                <OutputReviewModal
                  outputs={stageOutputs}
                  index={outputIndex}
                  approvals={outputApprovals}
                  onIndexChange={setOutputIndex}
                  onApprove={handleApproveOutput}
                  onDisapprove={handleDisapproveOutput}
                  onClose={() => setShowOutputModal(false)}
                />
              )}

              {/* Cancel button — floating top-right on graph */}
              {isRunning && (
                <button
                  onClick={cancelPipeline}
                  style={{
                    position: "absolute",
                    top: 12,
                    right: 12,
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

        {/* Node detail panel — hidden during output review */}
        {selectedNode && !showOutputModal && (
          <NodeDetail
            node={selectedNode}
            onClose={() => setSelectedNode(null)}
          />
        )}
      </div>
    </div>
  );
}
