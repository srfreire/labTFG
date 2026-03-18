import {
  useState,
  useCallback,
  useRef,
  useMemo,
  useEffect,
  type KeyboardEvent,
} from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { Play } from "lucide-react";
import Sidebar from "./components/Sidebar";
import Graph from "./components/Graph";
import DemoGraph from "./components/DemoGraph";
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
            <div className="text-[11px] mb-2 text-text-muted">
              <span className="text-[9px] uppercase tracking-[1px] block mb-1 text-text-faint">
                Query
              </span>
              {String(meta.query)}
            </div>
          )}
          {Array.isArray(meta.results) && meta.results.length > 0 && (
            <div>
              <span className="text-[9px] uppercase tracking-[1px] block mb-1 text-text-faint">
                Results
              </span>
              {meta.results.map((r, i) => (
                <div
                  key={i}
                  className="text-[11px] py-1 text-text-muted border-b border-border-faint"
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
      <div className="text-[11px] text-text-dim">No details available.</div>
    );
  }

  return (
    <div className="animate-scale-in fixed bottom-5 right-5 w-[380px] max-h-[320px] bg-surface border border-border z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <span className="text-[9px] uppercase tracking-[1px] text-text-faint">
            {node.kind}
          </span>
          <span className="text-[12px] text-white font-medium">
            {node.label}
          </span>
        </div>
        <button
          className="text-[10px] cursor-pointer text-text-faint bg-transparent border-none"
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
      className="fixed inset-0 z-[100] flex items-center justify-center bg-overlay backdrop-blur-[6px]"
      onClick={onClose}
    >
      <div
        className="animate-scale-in flex flex-col overflow-hidden transition-[border-color] duration-200 w-[min(820px,92vw)] max-h-[88vh] bg-[#0a0a0a]"
        onClick={(e) => e.stopPropagation()}
        style={{
          border: `1px solid ${
            approval === true
              ? "rgba(34,197,94,0.3)"
              : approval === false
                ? "rgba(239,68,68,0.3)"
                : "rgba(255,255,255,0.1)"
          }`,
        }}
      >
        {/* ── Header ── */}
        <div className="px-5 py-3.5 border-b border-border-subtle flex items-center justify-between">
          <div>
            <div className="flex items-center gap-[10px]">
              <span className="text-[9px] tracking-[1.5px] text-text-faint uppercase">
                Output
              </span>
              {approval === true && (
                <span className="text-[8px] px-1.5 py-0.5 bg-[rgba(34,197,94,0.12)] border border-accent-green/30 text-accent-green uppercase tracking-[1px]">
                  Approved
                </span>
              )}
              {approval === false && (
                <span className="text-[8px] px-1.5 py-0.5 bg-[rgba(239,68,68,0.12)] border border-accent-red/30 text-accent-red uppercase tracking-[1px]">
                  Rejected
                </span>
              )}
            </div>
            <div className="text-[13px] text-text mt-1">{node.label}</div>
          </div>

          <div className="flex items-center gap-4">
            <span className="text-[11px] text-text-faint">
              {index + 1} / {outputs.length}
            </span>
            <button
              onClick={onClose}
              className="bg-transparent border-none text-text-dim text-[18px] cursor-pointer font-mono"
            >
              ✕
            </button>
          </div>
        </div>

        {/* ── Content ── */}
        <div className="flex-1 overflow-auto px-6 py-5">
          {ext === "md" ? (
            <MarkdownRenderer content={content} />
          ) : (
            <CodeBlock code={content} language={ext || undefined} />
          )}
        </div>

        {/* ── Footer ── */}
        <div className="px-5 py-3 border-t border-border-subtle flex items-center justify-between">
          {/* Navigation */}
          <div className="flex gap-1.5">
            <button
              disabled={!hasPrev}
              onClick={() => onIndexChange(index - 1)}
              className="text-[10px] uppercase tracking-[1px] cursor-pointer px-3.5 py-2 bg-transparent border border-border disabled:cursor-default disabled:text-text-ghost text-text-muted"
            >
              ← Prev
            </button>
            <button
              disabled={!hasNext}
              onClick={() => onIndexChange(index + 1)}
              className="text-[10px] uppercase tracking-[1px] cursor-pointer px-3.5 py-2 bg-transparent border border-border disabled:cursor-default disabled:text-text-ghost text-text-muted"
            >
              Next →
            </button>
          </div>

          {/* Approve / Disapprove */}
          <div className="flex gap-2">
            <button
              onClick={() => onDisapprove(node.id)}
              className="text-[10px] uppercase tracking-[1px] cursor-pointer px-5 py-2 text-accent-red"
              style={{
                background:
                  approval === false
                    ? "rgba(239,68,68,0.15)"
                    : "transparent",
                border: `1px solid ${
                  approval === false
                    ? "rgba(239,68,68,0.5)"
                    : "rgba(239,68,68,0.2)"
                }`,
              }}
            >
              Disapprove
            </button>
            <button
              onClick={() => onApprove(node.id)}
              className="text-[10px] uppercase tracking-[1px] cursor-pointer px-5 py-2 text-accent-green"
              style={{
                background:
                  approval === true
                    ? "rgba(34,197,94,0.15)"
                    : "transparent",
                border: `1px solid ${
                  approval === true
                    ? "rgba(34,197,94,0.5)"
                    : "rgba(34,197,94,0.2)"
                }`,
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
  const inputRef = useRef<HTMLTextAreaElement>(null);

  /* ── Output review state ── */
  const [showOutputModal, setShowOutputModal] = useState(false);
  const [outputIndex, setOutputIndex] = useState(0);
  const [outputApprovals, setOutputApprovals] = useState<
    Record<string, boolean>
  >({});
  const [routerPrompt, setRouterPrompt] = useState("");
  const [dismissedOutputs, setDismissedOutputs] = useState<Set<string>>(
    new Set(),
  );

  const reviewActive = reviewRequest !== null;

  /* Collect done output nodes */
  const stageOutputs = useMemo(
    () => nodes.filter((n) => n.kind === "output" && n.status === "done"),
    [nodes],
  );

  /* Reset review state when review changes */
  useEffect(() => {
    setDismissedOutputs(new Set());
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
        setDismissedOutputs((prev) => new Set([...prev, node.id]));
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
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        handleRun();
      }
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
  const [demoComplete, setDemoComplete] = useState(false);
  const handleDemoComplete = useCallback(() => setDemoComplete(true), []);

  /* Review progress */
  const reviewedCount = stageOutputs.filter(
    (n) => n.id in outputApprovals,
  ).length;

  const isEnvSpec = reviewRequest?.stage === Stage.GET_ENV_SPEC;

  return (
    <div className="flex h-screen w-screen">
      {/* Sidebar — hidden on idle */}
      {!showIdle && (
        <Sidebar
          connected={connected}
          stages={stages}
          currentStage={currentStage}
          isRunning={isRunning}
          onCancel={cancelPipeline}
        />
      )}

      {/* Main panel */}
      <div className={`${showIdle ? "" : "ml-[200px]"} flex-1 flex flex-col relative h-screen overflow-hidden`}>
        {/* Error bar */}
        {error && (
          <div
            onClick={clearError}
            className="bg-accent-red/10 border border-accent-red/30 text-accent-red text-[11px] px-4 py-2 cursor-pointer shrink-0"
          >
            {error}
          </div>
        )}

        {/* Content area */}
        <div className="flex-1 flex overflow-hidden">
          {showIdle ? (
            <div className="flex-1 relative overflow-hidden">
              {/* Demo graph — always fills 100% */}
              <div className="absolute inset-0">
                <DemoGraph onComplete={handleDemoComplete} />
              </div>

              {/* Landing overlay — fades in over graph after demo */}
              <div
                className="absolute bottom-0 left-0 right-0 z-10 pointer-events-none transition-opacity duration-700"
                style={{
                  opacity: demoComplete ? 1 : 0,
                  transitionTimingFunction: "cubic-bezier(0.23, 1, 0.32, 1)",
                }}
              >
                {/* Content */}
                <div className="bg-bg border-t border-border pointer-events-auto">
                  {/* Title */}
                  <div className="text-center p-4">
                    <h1
                      className="text-[22px] font-bold uppercase tracking-[6px] text-text transition-all duration-500 delay-200"
                      style={{
                        opacity: demoComplete ? 1 : 0,
                        transform: demoComplete
                          ? "translateY(0)"
                          : "translateY(12px)",
                        transitionTimingFunction:
                          "cubic-bezier(0.23, 1, 0.32, 1)",
                      }}
                    >
                      DecisionLab
                    </h1>
                    <p
                      className="text-[11px] uppercase tracking-[2px] text-text-faint mt-2 transition-all duration-500 delay-300"
                      style={{
                        opacity: demoComplete ? 1 : 0,
                        transform: demoComplete
                          ? "translateY(0)"
                          : "translateY(8px)",
                        transitionTimingFunction:
                          "cubic-bezier(0.23, 1, 0.32, 1)",
                      }}
                    >
                      Describe a decision problem
                    </p>
                  </div>

                  {/* Input */}
                  <div
                    className="px-6 pb-5 transition-all duration-500 delay-[400ms]"
                    style={{
                      opacity: demoComplete ? 1 : 0,
                      transform: demoComplete
                        ? "translateY(0)"
                        : "translateY(10px)",
                      transitionTimingFunction:
                        "cubic-bezier(0.23, 1, 0.32, 1)",
                    }}
                  >
                    <div className="max-w-3xl mx-auto flex gap-3 items-stretch">
                      <textarea
                        ref={inputRef}
                        value={problemInput}
                        onChange={(e) => setProblemInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="e.g. survival decision-making"
                        autoFocus
                        rows={3}
                        className="flex-1 bg-transparent border border-text-ghost text-text text-[13px] font-mono py-3 px-4 outline-none resize-none"
                      />
                      <button
                        onClick={handleRun}
                        disabled={!problemInput.trim()}
                        className="shrink-0 w-16 flex items-center justify-center border transition-colors bg-transparent border-accent-green/30 text-accent-green cursor-pointer hover:border-accent-green/60 hover:bg-accent-green/5 disabled:border-text-ghost disabled:text-text-ghost disabled:cursor-default disabled:hover:bg-transparent"
                      >
                        <Play size={20} fill="currentColor" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <>
              {/* Graph */}
              <div className="flex-1 min-w-0 h-full">
                <Graph
                  nodes={nodes}
                  edges={edges}
                  onNodeClick={handleNodeClick}
                  reviewActive={reviewActive}
                  currentStage={currentStage}
                  dismissedOutputIds={dismissedOutputs}
                />
              </div>

              {/* ── Stage completion bar ── */}
              {reviewActive && (
                <div className="animate-slide-up absolute bottom-0 left-0 right-0 z-50 bg-surface-frosted border-t border-accent-green/15 backdrop-blur-[10px] px-6 py-4">
                  {isEnvSpec ? (
                    /* ENV SPEC — upload mode */
                    <div>
                      <span className="text-[9px] uppercase tracking-[1.5px] text-accent-amber">
                        Environment Specification Required
                      </span>
                      <div className="text-[11px] text-text-muted mt-1 mb-3">
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
                      <div className="flex items-center justify-between mb-3">
                        <div>
                          <span className="text-[9px] uppercase tracking-[1.5px] text-accent-green">
                            Stage Complete
                          </span>
                          <div className="text-[11px] text-text-muted mt-1">
                            Review generated outputs before continuing.
                            {stageOutputs.length > 0 && (
                              <span className="ml-[10px] text-text-faint">
                                {reviewedCount}/{stageOutputs.length} reviewed
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex gap-2.5">
                          {stageOutputs.length > 0 && (
                            <button
                              onClick={() => {
                                setOutputIndex(0);
                                setShowOutputModal(true);
                              }}
                              className="text-[10px] uppercase tracking-[1px] cursor-pointer px-5 py-2 bg-[rgba(34,197,94,0.08)] border border-accent-green/25 text-accent-green"
                            >
                              View Outputs ({stageOutputs.length})
                            </button>
                          )}
                          <button
                            onClick={handleContinue}
                            className="text-[10px] uppercase tracking-[1px] cursor-pointer px-6 py-2 bg-surface-hover border border-[rgba(255,255,255,0.2)] text-text"
                          >
                            Continue →
                          </button>
                        </div>
                      </div>

                      {/* Router prompt */}
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={routerPrompt}
                          onChange={(e) => setRouterPrompt(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleSendRouterPrompt();
                          }}
                          placeholder="Send instructions to the router..."
                          className="flex-1 bg-transparent border border-border-subtle text-text text-[11px] font-mono py-2 px-3 outline-none"
                        />
                        <button
                          onClick={handleSendRouterPrompt}
                          disabled={!routerPrompt.trim()}
                          className="text-[10px] uppercase tracking-[1px] px-4 py-2 border border-border bg-transparent cursor-pointer disabled:cursor-default disabled:text-text-ghost text-text"
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
