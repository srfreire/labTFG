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
import KnowledgeGraphPanel from "./components/KnowledgeGraphPanel";
import {
  EnvSpecUpload,
  ReviewBuild,
  ReviewFormalize,
  ReviewReason,
  ReviewResearch,
} from "./components/reviews";
import MarkdownRenderer from "./components/shared/MarkdownRenderer";
import CodeBlock from "./components/shared/CodeBlock";
import { Stage } from "./types";
import PastRunsList from "./components/PastRunsList";
import { useAgrexReplay, type AgrexEvent, type AgrexNode } from "@ppazosp/agrex";
import {
  extractLabMarkers,
  fetchRunTrace,
  labReducers,
  labStepBoundaries,
} from "./lib/replayAdapter";

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

function nodeMetadata(node: AgrexNode): Record<string, unknown> {
  return (node.metadata ?? {}) as Record<string, unknown>;
}

function nodeDisplayLabel(node: AgrexNode): string {
  const meta = nodeMetadata(node);
  return typeof meta.displayLabel === "string" ? meta.displayLabel : node.label;
}

function numberMeta(meta: Record<string, unknown>, key: string): number | undefined {
  const value = meta[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds >= 10 ? 1 : 2)} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}m ${String(rest).padStart(2, "0")}s`;
}

function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}k`;
  return String(tokens);
}

function formatCost(cost: number): string {
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

function stringifyDetail(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function DetailMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-[82px] rounded-lg border border-border-subtle bg-white/[0.03] px-2.5 py-2">
      <div className="text-[10px] uppercase tracking-[1px] text-text-faint">
        {label}
      </div>
      <div className="mt-1 text-[13px] text-text tabular-nums">{value}</div>
    </div>
  );
}

function DetailCode({
  title,
  value,
  language = "json",
}: {
  title: string;
  value: unknown;
  language?: string;
}) {
  if (value === undefined || value === null || value === "") return null;
  return (
    <div className="mb-3">
      <div className="text-[10px] uppercase tracking-[1px] text-text-faint mb-1.5">
        {title}
      </div>
      <CodeBlock code={stringifyDetail(value)} language={language} />
    </div>
  );
}

const DETAIL_METADATA_HIDDEN = new Set([
  "args",
  "input",
  "output",
  "content",
  "error",
  "startedAt",
  "endedAt",
  "tokens",
  "cost",
  "duration_ms",
]);

function NodeDetail({
  node,
  onClose,
}: {
  node: AgrexNode;
  onClose: () => void;
}) {
  const meta = nodeMetadata(node);
  const kind = node.type;
  const displayLabel = nodeDisplayLabel(node);
  const startedAt = numberMeta(meta, "startedAt");
  const endedAt = numberMeta(meta, "endedAt");
  const durationMs =
    numberMeta(meta, "duration_ms") ??
    (startedAt !== undefined && endedAt !== undefined
      ? Math.max(0, endedAt - startedAt)
      : undefined);
  const tokens = numberMeta(meta, "tokens");
  const cost = numberMeta(meta, "cost");
  const llmCalls = numberMeta(meta, "llm_calls");
  const resultChars = numberMeta(meta, "result_chars");
  const errorValue = meta.error;
  const extraMetadata = Object.entries(meta).filter(
    ([key]) => !DETAIL_METADATA_HIDDEN.has(key),
  );

  let content: React.ReactNode = null;

  switch (kind) {
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
            <div className="text-[13px] mb-2 text-text-muted">
              <span className="text-[11px] uppercase tracking-[1px] block mb-1 text-text-faint">
                Query
              </span>
              {String(meta.query)}
            </div>
          )}
          {Array.isArray(meta.results) && meta.results.length > 0 && (
            <div>
              <span className="text-[11px] uppercase tracking-[1px] block mb-1 text-text-faint">
                Results
              </span>
              {meta.results.map((r, i) => (
                <div
                  key={i}
                  className="text-[13px] py-1 text-text-muted border-b border-border-faint"
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
      if (meta.args !== undefined || meta.output !== undefined) {
        content = (
          <>
            <DetailCode title="Args" value={meta.args} />
            <DetailCode title="Output" value={meta.output} language="text" />
          </>
        );
      }
      break;
  }

  if (!content && extraMetadata.length === 0 && !errorValue) {
    content = (
      <div className="text-[13px] text-text-dim">No details available.</div>
    );
  }

  return (
    <div className="animate-scale-in fixed bottom-5 right-5 w-[380px] max-h-[320px] bg-surface border border-border z-50 flex flex-col rounded-2xl shadow-2xl shadow-black/30 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <span className="text-[11px] uppercase tracking-[1px] text-text-faint">
            {kind}
          </span>
          <span className="text-[14px] text-white font-medium">
            {displayLabel}
          </span>
        </div>
        <button
          className="w-6 h-6 flex items-center justify-center rounded-full cursor-pointer text-text-faint bg-transparent border-none hover:bg-surface-hover text-[14px]"
          onClick={onClose}
        >
          ✕
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-3">
        {(durationMs !== undefined ||
          tokens !== undefined ||
          cost !== undefined ||
          llmCalls !== undefined ||
          resultChars !== undefined) && (
          <div className="grid grid-cols-2 gap-2 mb-3">
            {durationMs !== undefined && (
              <DetailMetric label="Time" value={formatDuration(durationMs)} />
            )}
            {tokens !== undefined && (
              <DetailMetric label="Tokens" value={formatTokens(tokens)} />
            )}
            {cost !== undefined && (
              <DetailMetric label="Cost" value={formatCost(cost)} />
            )}
            {llmCalls !== undefined && (
              <DetailMetric label="LLM calls" value={String(llmCalls)} />
            )}
            {resultChars !== undefined && (
              <DetailMetric label="Result" value={`${resultChars} chars`} />
            )}
          </div>
        )}

        {errorValue !== undefined && (
          <div className="mb-3 rounded-lg border border-red-500/30 bg-red-500/10 p-2.5">
            <div className="text-[10px] uppercase tracking-[1px] text-red-200/80 mb-1.5">
              Error
            </div>
            <pre className="m-0 whitespace-pre-wrap break-words text-[12px] leading-5 text-red-50/90 font-mono">
              {stringifyDetail(errorValue)}
            </pre>
          </div>
        )}

        {content}

        {extraMetadata.length > 0 && (
          <div className="mt-3">
            <div className="text-[10px] uppercase tracking-[1px] text-text-faint mb-1.5">
              Metadata
            </div>
            <div className="space-y-1.5 text-[12px]">
              {extraMetadata.map(([key, value]) => (
                <div
                  key={key}
                  className="grid grid-cols-[112px_minmax(0,1fr)] gap-2"
                >
                  <span className="text-text-faint">{key}</span>
                  <span className="min-w-0 break-words text-text-muted">
                    {typeof value === "string" ? value : stringifyDetail(value)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
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
  mode,
  onIndexChange,
  onApprove,
  onDisapprove,
  onClose,
}: {
  outputs: AgrexNode[];
  index: number;
  approvals: Record<string, boolean>;
  mode: "single" | "sequence";
  onIndexChange: (i: number) => void;
  onApprove: (id: string) => void;
  onDisapprove: (id: string) => void;
  onClose: () => void;
}) {
  if (outputs.length === 0) return null;

  const node = outputs[index];
  const meta = nodeMetadata(node);
  const content = String(meta.content || "No content available.");
  const path = String(meta.path || nodeDisplayLabel(node) || "");
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
        className="animate-scale-in flex flex-col overflow-hidden transition-[border-color] duration-200 w-[min(820px,92vw)] max-h-[88vh] bg-[#0a0a0a] rounded-2xl shadow-2xl shadow-black/40"
        onClick={(e) => e.stopPropagation()}
        style={{
          border: `1px solid ${
            approval === true
              ? "rgba(255,255,255,0.2)"
              : approval === false
                ? "rgba(255,255,255,0.2)"
                : "rgba(255,255,255,0.1)"
          }`,
        }}
      >
        {/* ── Header ── */}
        <div className="px-5 py-3.5 border-b border-border-subtle flex items-center justify-between">
          <div>
            <div className="flex items-center gap-[10px]">
              <span className="text-[11px] tracking-[1.5px] text-text-faint uppercase">
                Output
              </span>
              {approval === true && (
                <span className="text-[10px] px-2 py-0.5 bg-[rgba(255,255,255,0.08)] border border-border text-text-muted uppercase tracking-[1px] rounded-full">
                  Approved
                </span>
              )}
              {approval === false && (
                <span className="text-[10px] px-2 py-0.5 bg-[rgba(255,255,255,0.05)] border border-border text-text-dim uppercase tracking-[1px] rounded-full">
                  Rejected
                </span>
              )}
            </div>
            <div className="text-[15px] text-text mt-1">{nodeDisplayLabel(node)}</div>
          </div>

          <div className="flex items-center gap-4">
            {mode === "sequence" && (
              <span className="text-[13px] text-text-faint">
                {index + 1} / {outputs.length}
              </span>
            )}
            <button
              onClick={onClose}
              className="w-7 h-7 flex items-center justify-center rounded-full bg-transparent border-none text-text-dim text-[18px] cursor-pointer hover:bg-surface-hover"
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
          {/* Navigation — only in sequence mode */}
          {mode === "sequence" ? (
            <div className="flex gap-1.5">
              <button
                disabled={!hasPrev}
                onClick={() => onIndexChange(index - 1)}
                className="text-[12px] uppercase tracking-[1px] cursor-pointer px-3.5 py-2 bg-transparent border border-border rounded-lg disabled:cursor-default disabled:text-text-ghost text-text-muted"
              >
                ← Prev
              </button>
              <button
                disabled={!hasNext}
                onClick={() => onIndexChange(index + 1)}
                className="text-[12px] uppercase tracking-[1px] cursor-pointer px-3.5 py-2 bg-transparent border border-border rounded-lg disabled:cursor-default disabled:text-text-ghost text-text-muted"
              >
                Next →
              </button>
            </div>
          ) : (
            <div />
          )}

          {/* Approve / Disapprove */}
          <div className="flex gap-2">
            <button
              onClick={() => onDisapprove(node.id)}
              className="text-[12px] uppercase tracking-[1px] cursor-pointer px-5 py-2 text-accent-red rounded-lg"
              style={{
                background:
                  approval === false
                    ? "rgba(239,68,68,0.12)"
                    : "rgba(239,68,68,0.06)",
                border: `1px solid ${
                  approval === false
                    ? "rgba(239,68,68,0.4)"
                    : "rgba(239,68,68,0.2)"
                }`,
              }}
            >
              Disapprove
            </button>
            <button
              onClick={() => onApprove(node.id)}
              className="text-[12px] uppercase tracking-[1px] cursor-pointer px-5 py-2 bg-white text-black rounded-lg font-medium"
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
  const replay = useAgrexReplay({
    reducers: labReducers,
    markerExtractor: extractLabMarkers,
    stepBoundaries: labStepBoundaries,
  });

  // Gate replay event ingestion on having seen `run_start` in this session.
  // The mock server re-emits stale `review_request` / `state_sync` on
  // reconnect from unfinished previous-run state — without this guard, those
  // messages would bump `replay.events.length` on a fresh page load and
  // kick us out of the idle/landing state into a phantom run.
  const liveRunActiveRef = useRef(false);

  const {
    connected,
    stages,
    currentStage,
    reviewRequest,
    isRunning,
    error,
    agents,
    runId,
    startPipeline,
    sendReviewResponse,
    cancelPipeline,
    clearError,
  } = useWebSocket((msg) => {
    if (msg.type === "run_start") {
      // Fresh run: clear the replay buffer and open the live gate. Order
      // matters: reset → setMode('live') → appendLive, because `appendLive`
      // is a no-op in 'replay' mode.
      replay.reset();
      replay.setMode("live");
      liveRunActiveRef.current = true;
    }
    if (!liveRunActiveRef.current) return;
    replay.appendLive({ ts: Date.now(), ...msg } as AgrexEvent);
    if (msg.type === "pipeline_done") {
      replay.setMode("live-finished");
      liveRunActiveRef.current = false;
    }
  });

  const memoryAgent = agents.find((a) => a.name === "memory_agent");

  const handleSelectPastRun = useCallback(
    async (runIdSel: string) => {
      if (isRunning) return;
      await replay.load(fetchRunTrace(runIdSel));
    },
    [isRunning, replay],
  );
  const exitReplay = useCallback(() => {
    replay.reset();
    liveRunActiveRef.current = false;
  }, [replay]);

  const [selectedNode, setSelectedNode] = useState<AgrexNode | null>(null);
  const [problemInput, setProblemInput] = useState("");
  // `undefined` = run the full pipeline (default). Otherwise the work stage
  // after which the pipeline terminates (kept review enabled).
  const [untilStage, setUntilStage] = useState<Stage | undefined>(undefined);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  /* ── Output review state ── */
  const [showOutputModal, setShowOutputModal] = useState(false);
  const [outputIndex, setOutputIndex] = useState(0);
  const [modalMode, setModalMode] = useState<"single" | "sequence">("single");
  const [outputApprovals, setOutputApprovals] = useState<
    Record<string, boolean>
  >({});
  const [dismissedOutputs, setDismissedOutputs] = useState<Set<string>>(
    new Set(),
  );

  const reviewActive = reviewRequest !== null;
  const [reviewHintDismissed, setReviewHintDismissed] = useState(false);

  /* Collect done output nodes for the stage currently under review. Source
   * of truth is `replay.instance.nodes` — AgrexNode[] driven by the reducer,
   * consistent whether the run is live, scrubbed, or a loaded past run. */
  const replayNodes = replay.instance.nodes;
  const stageOutputs = useMemo(() => {
    const allDone = replayNodes.filter(
      (n) => n.type === "output" && n.status === "done",
    );
    if (!reviewRequest) return allDone;
    const target = reviewRequest.stage.replace(/^review_/, "");
    return allDone.filter(
      (n) => (n.metadata as Record<string, unknown> | undefined)?.stage === target,
    );
  }, [replayNodes, reviewRequest]);

  /* Reset review state when review stage changes */
  const reviewStage = reviewRequest?.stage ?? null;
  useEffect(() => {
    setDismissedOutputs(new Set());
    setReviewHintDismissed(false);
    setOutputApprovals({});
    setOutputIndex(0);
    setShowOutputModal(false);
  }, [reviewStage]);

  /* Clamp index */
  useEffect(() => {
    if (outputIndex >= stageOutputs.length && stageOutputs.length > 0) {
      setOutputIndex(stageOutputs.length - 1);
    }
  }, [outputIndex, stageOutputs.length]);

  /* ── Node click ── */
  const handleNodeClick = useCallback(
    (node: AgrexNode) => {
      if (reviewActive && node.type === "output" && node.status === "done") {
        setDismissedOutputs((prev) => new Set([...prev, node.id]));
        const idx = stageOutputs.findIndex((n) => n.id === node.id);
        if (idx >= 0) {
          setOutputIndex(idx);
          setModalMode("single");
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
    startPipeline(trimmed, untilStage);
    setProblemInput("");
  }, [problemInput, startPipeline, untilStage]);

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
  const advanceOrClose = useCallback(() => {
    if (modalMode === "single") {
      setShowOutputModal(false);
      return;
    }
    setOutputIndex((i) => {
      if (i < stageOutputs.length - 1) return i + 1;
      setShowOutputModal(false);
      return i;
    });
  }, [modalMode, stageOutputs.length]);

  const handleApproveOutput = useCallback(
    (nodeId: string) => {
      setOutputApprovals((prev) => ({ ...prev, [nodeId]: true }));
      advanceOrClose();
    },
    [advanceOrClose],
  );

  const handleDisapproveOutput = useCallback(
    (nodeId: string) => {
      setOutputApprovals((prev) => ({ ...prev, [nodeId]: false }));
      advanceOrClose();
    },
    [advanceOrClose],
  );

  // Agrex renders directly from `replay.instance` when we hand it `replay`;
  // no separate "display" array. For idle-detection we just check whether
  // the replay has any events yet.
  const hasGraph =
    replay.events.length > 0 ||
    replay.mode === "replay" ||
    replay.mode === "live-finished";
  const showIdle = !hasGraph && !isRunning && replay.mode === "idle";
  const [demoComplete, setDemoComplete] = useState(false);
  const handleDemoComplete = useCallback(() => setDemoComplete(true), []);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [timelineCollapsed, setTimelineCollapsed] = useState(false);

  /* Review progress */
  const reviewedCount = stageOutputs.filter(
    (n) => n.id in outputApprovals,
  ).length;

  const isEnvSpec = reviewRequest?.stage === Stage.GET_ENV_SPEC;

  const reviewPanel = useMemo(() => {
    if (!reviewRequest || isEnvSpec) return null;

    const submit = (data: unknown) => {
      sendReviewResponse(reviewRequest.stage, data);
      setShowOutputModal(false);
      setSelectedNode(null);
    };

    switch (reviewRequest.stage) {
      case Stage.REVIEW_RESEARCH:
        return (
          <ReviewResearch
            data={reviewRequest.data}
            onSubmit={(data) => submit(data)}
          />
        );
      case Stage.REVIEW_FORMALIZE:
        return (
          <ReviewFormalize
            data={reviewRequest.data}
            onSubmit={(data) => submit(data)}
          />
        );
      case Stage.REVIEW_REASON:
        return (
          <ReviewReason
            data={reviewRequest.data}
            onSubmit={(data) => submit(data)}
          />
        );
      case Stage.REVIEW_BUILD:
        return (
          <ReviewBuild
            data={reviewRequest.data}
            onSubmit={(data) => submit(data)}
          />
        );
      default:
        return null;
    }
  }, [isEnvSpec, reviewRequest, sendReviewResponse]);

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
          agents={agents}
          onCollapsedChange={setSidebarCollapsed}
        />
      )}

      {/* Main panel */}
      <div className="flex-1 flex flex-col relative h-screen overflow-hidden">
        {/* Error bar */}
        {error && (
          <div
            onClick={clearError}
            className="bg-[rgba(255,255,255,0.04)] border border-border text-text-muted text-[13px] mx-4 mt-3 px-4 py-2 cursor-pointer shrink-0 rounded-lg"
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

              <PastRunsList onSelect={handleSelectPastRun} active={demoComplete} />

              <KnowledgeGraphPanel
                runId={null}
                memoryAgent={undefined}
                active={demoComplete}
              />

              {/* Landing overlay — fades in over graph after demo */}
              <div
                className="absolute bottom-0 left-0 right-0 z-10 pointer-events-none transition-opacity duration-700"
                style={{
                  opacity: demoComplete ? 1 : 0,
                  transitionTimingFunction: "cubic-bezier(0.23, 1, 0.32, 1)",
                }}
              >
                {/* Content */}
                <div className="border-t border-border pointer-events-auto" style={{ background: 'var(--color-bg)' }}>
                  {/* Title */}
                  <div className="text-center p-4">
                    <h1
                      className="text-[30px] font-bold tracking-tight text-text transition-all duration-500 delay-200"
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
                      className="text-[16px] text-text-muted mt-2 transition-all duration-500 delay-300"
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

                  {/* Input — fills the gap between the two corner cards;
                       textarea is the only thing that resizes with the window. */}
                  <div
                    className="pb-5 pl-[252px] pr-[252px] transition-all duration-500 delay-[400ms]"
                    style={{
                      opacity: demoComplete ? 1 : 0,
                      transform: demoComplete
                        ? "translateY(0)"
                        : "translateY(10px)",
                      transitionTimingFunction:
                        "cubic-bezier(0.23, 1, 0.32, 1)",
                    }}
                  >
                    {/* Run-until selector */}
                    <div className="flex items-center gap-1.5 mb-2.5 text-[10px] uppercase tracking-[1.5px]">
                      <span className="text-text-faint mr-1">Run until</span>
                      {(
                        [
                          { value: Stage.RESEARCH, label: "Research" },
                          { value: Stage.FORMALIZE, label: "Formalize" },
                          { value: Stage.REASON, label: "Reason" },
                          { value: undefined, label: "Full" },
                        ] as Array<{ value: Stage | undefined; label: string }>
                      ).map(({ value, label }) => {
                        const active = untilStage === value;
                        return (
                          <button
                            key={label}
                            type="button"
                            onClick={() => setUntilStage(value)}
                            className={[
                              "px-2.5 py-1 rounded-md border cursor-pointer transition-colors",
                              active
                                ? "bg-white text-black border-white"
                                : "bg-transparent text-text-muted border-border hover:border-border-strong hover:text-text",
                            ].join(" ")}
                          >
                            {label}
                          </button>
                        );
                      })}
                    </div>

                    <div className="flex gap-3 items-stretch">
                      <textarea
                        ref={inputRef}
                        value={problemInput}
                        onChange={(e) => setProblemInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="e.g. survival decision-making"
                        autoFocus
                        rows={3}
                        className="flex-1 min-w-0 bg-transparent border border-text-ghost text-text text-[15px] py-3.5 px-5 outline-none resize-none rounded-xl"
                      />
                      <button
                        onClick={handleRun}
                        disabled={!problemInput.trim()}
                        className="shrink-0 w-16 flex items-center justify-center transition-colors bg-white text-black cursor-pointer hover:bg-white/80 rounded-xl disabled:bg-text-ghost disabled:text-text-dim disabled:cursor-default"
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
              {/* Graph — Agrex renders from `replay.instance` and mounts
                  its own timeline at the bottom. UI overlays go through
                  Graph's context. */}
              <div className="flex-1 min-w-0 h-full">
                <Graph
                  replay={replay}
                  onNodeClick={handleNodeClick}
                  uiState={{
                    currentStage,
                    dismissedOutputIds: dismissedOutputs,
                    outputApprovals,
                  }}
                  sidebarCollapsed={sidebarCollapsed}
                  timelineCollapsedChange={setTimelineCollapsed}
                  onExitReplay={replay.mode === "replay" ? exitReplay : undefined}
                />
              </div>

              {/* ── Review hint toast ── */}
              {reviewActive && !isEnvSpec && !reviewHintDismissed && (
                <div
                  className="animate-slide-up absolute left-[192px] right-[192px] z-20 bg-surface/80 backdrop-blur-xl border border-border px-4 py-2.5 rounded-xl shadow-lg shadow-black/20 flex items-center justify-between"
                  style={{
                    bottom: timelineCollapsed ? 162 : 254,
                    transition: "bottom 250ms cubic-bezier(0.23, 1, 0.32, 1)",
                  }}
                >
                  <span className="text-[12px] text-text-dim">
                    Click on the glowing output nodes in the graph to review them.
                  </span>
                  <button
                    onClick={() => setReviewHintDismissed(true)}
                    className="ml-3 shrink-0 w-6 h-6 flex items-center justify-center rounded-full bg-transparent border-none text-text-faint hover:text-text cursor-pointer text-[12px]"
                  >
                    ✕
                  </button>
                </div>
              )}

              {/* ── Stage completion bar ── */}
              {reviewActive && (
                <div
                  className="animate-slide-up absolute left-[192px] right-[192px] z-20 bg-surface/80 backdrop-blur-xl border border-border px-6 py-4 rounded-2xl shadow-xl shadow-black/30"
                  style={{
                    bottom: timelineCollapsed ? 16: 106,
                    transition: "bottom 250ms cubic-bezier(0.23, 1, 0.32, 1)",
                  }}
                >
                  {isEnvSpec ? (
                    /* ENV SPEC — upload mode */
                    <div>
                      <span className="text-[11px] uppercase tracking-[1.5px] text-text-muted">
                        Environment Specification Required
                      </span>
                      <div className="text-[13px] text-text-muted mt-1 mb-3">
                        Upload or paste the environment specification JSON.
                      </div>
                      <EnvSpecUpload
                        onSubmit={(data) =>
                          sendReviewResponse(Stage.GET_ENV_SPEC, data)
                        }
                      />
                    </div>
                  ) : (
                    /* Human review mode */
                    <>
                      <div className="flex items-center justify-between mb-3">
                        <div>
                          <span className="text-[11px] uppercase tracking-[1.5px] text-text-muted">
                            Human Review Required
                          </span>
                          <div className="text-[13px] text-text-muted mt-1">
                            Review generated artifacts before continuing.
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
                                setModalMode("sequence");
                                setShowOutputModal(true);
                              }}
                              className="text-[12px] uppercase tracking-[1px] cursor-pointer px-5 py-2 bg-transparent border border-border text-text-muted rounded-lg hover:bg-surface-hover"
                            >
                              View Outputs ({stageOutputs.length})
                            </button>
                          )}
                        </div>
                      </div>

                      <div
                        className="overflow-hidden rounded-xl border border-border-subtle bg-black/20"
                        style={{
                          height: timelineCollapsed
                            ? "min(560px, calc(100vh - 110px))"
                            : "min(480px, calc(100vh - 200px))",
                        }}
                      >
                        {reviewPanel}
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
                  mode={modalMode}
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

      {/* Knowledge graph panel — delta for current run, click to expand */}
      {!showIdle && (
        <KnowledgeGraphPanel
          runId={runId}
          memoryAgent={memoryAgent}
        />
      )}

    </div>
  );
}
