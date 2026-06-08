import { createContext, useContext, useMemo, useState } from 'react';
import {
  Agrex,
  type AgrexHandle,
  type AgrexEvent,
  type AgrexNode,
  type AgrexNodeProps,
  type AgrexEdge,
  type UseAgrexReplay,
} from '@ppazosp/agrex';
import '@xyflow/react/dist/style.css';
import '@ppazosp/agrex/styles.css';
import { Globe, Pencil, FlaskConical, Database, FileSearch, FileText, FileInput } from 'lucide-react';
import FileTypeLogo from './nodes/FileTypeLogo';
import NodeHandles from './nodes/NodeHandles';

/* ── UI overlay state ─────────────────────────────────────────────
 * Renderers need app-side state (review stage, output approvals,
 * dismissal) that isn't part of the event stream. Previously we
 * baked it into each AgrexNode's metadata at render time via a
 * transformation layer. With the reducer now owning the
 * GraphNode→AgrexNode translation and Agrex rendering straight from
 * `replay.instance`, we instead read it from a context the
 * renderers consume.
 */
export interface GraphUIState {
  currentStage?: string | null;
  dismissedOutputIds?: Set<string>;
  outputApprovals?: Record<string, boolean>;
}

const UIStateContext = createContext<GraphUIState>({});
const useUIState = () => useContext(UIStateContext);

/* ── Custom renderers for node types agrex doesn't have ──────── */

function SearchRenderer({ status, theme }: AgrexNodeProps) {
  const borderColor =
    status === 'running' ? theme.statusRunning
    : status === 'done' ? theme.statusDone
    : status === 'error' ? theme.statusError
    : theme.nodeBorder;

  return (
    <div
      className="w-[32px] h-[32px] rounded-full flex items-center justify-center"
      style={{
        border: `1px solid ${borderColor}`,
        background: theme.nodeFill,
        animation: status === 'running' ? 'agrex-running-ring 1.5s ease-in-out infinite' : undefined,
      }}
    >
      <NodeHandles />
      <Globe size={14} style={{ color: theme.nodeIcon }} />
    </div>
  );
}

function OutputRenderer({ node, status, theme }: AgrexNodeProps) {
  const { currentStage, dismissedOutputIds, outputApprovals } = useUIState();
  const approval = outputApprovals?.[node.id];
  const rejected = approval === false;
  const decided = approval !== undefined;
  const dismissed = dismissedOutputIds?.has(node.id) ?? false;
  const glow =
    status === 'done' &&
    !dismissed &&
    !decided &&
    typeof currentStage === 'string' &&
    currentStage.startsWith('review_');

  const borderColor =
    status === 'done' ? theme.statusDone
    : status === 'running' ? theme.statusRunning
    : status === 'error' ? theme.statusError
    : theme.nodeBorder;

  // Descriptive filename lives in metadata.displayLabel (the renderer-
  // facing name) since node.label is used for toolIcons lookup.
  const descriptive = (node.metadata?.displayLabel as string | undefined) ?? node.label;

  const S = 48;
  const H = Math.round((S * 2) / Math.sqrt(3));

  return (
    <div
      className="relative"
      style={{ width: S, height: H, opacity: rejected ? 0.35 : 1 }}
    >
      <svg
        width={S} height={H} viewBox={`0 0 ${S} ${H}`}
        className="absolute top-0 left-0 overflow-visible"
        style={{
          filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.2))',
          ...(glow
            ? { animation: 'output-glow 2s ease-in-out infinite' }
            : status === 'running'
              ? { animation: 'agrex-running-drop 1.5s ease-in-out infinite' }
              : {}),
        }}
      >
        <path
          d="M 19.6,3.4 Q 24,1 28.4,3.4 L 42.6,11.3 Q 47,13.75 47,18.75 L 47,36.25 Q 47,41.25 42.6,43.7 L 28.4,51.6 Q 24,54 19.6,51.6 L 5.4,43.7 Q 1,41.25 1,36.25 L 1,18.75 Q 1,13.75 5.4,11.3 Z"
          fill={theme.nodeFill}
          stroke={borderColor}
          strokeWidth="1.5"
        />
      </svg>
      <div
        className="absolute inset-0 flex items-center justify-center"
        style={{ cursor: status === 'done' ? 'pointer' : 'default' }}
      >
        <NodeHandles />
        <FileTypeLogo label={descriptive} size={22} />
      </div>
    </div>
  );
}

function DatabaseRenderer({ node, status, theme }: AgrexNodeProps) {
  const borderColor =
    status === 'running' ? theme.statusRunning
    : status === 'done' ? theme.statusDone
    : status === 'error' ? theme.statusError
    : theme.nodeBorder;

  return (
    <div
      className="relative flex flex-col items-center justify-center"
      style={{ width: 156, height: 130 }}
    >
      <NodeHandles />
      <div
        className="flex items-center justify-center"
        style={{
          width: 90,
          height: 90,
          borderRadius: 8,
          border: `1.5px solid ${borderColor}`,
          background: theme.nodeFill,
          animation: status === 'running' ? 'agrex-running-ring 1.5s ease-in-out infinite' : undefined,
        }}
      >
        <Database size={52} strokeWidth={1.85} aria-hidden="true" style={{ color: theme.nodeIcon }} />
      </div>
      <div
        className="mt-1 text-center"
        style={{
          maxWidth: 156,
          color: theme.foreground,
          fontSize: 11,
          fontWeight: 650,
          lineHeight: 1.1,
        }}
      >
        {node.label}
      </div>
    </div>
  );
}

/* ── Statics (declared outside component to avoid re-creation) ── */

const NODE_RENDERERS = {
  search: SearchRenderer,
  output: OutputRenderer,
  database: DatabaseRenderer,
};

// Match the icons the graph actually renders: SearchRenderer uses Globe for
// kind="search" nodes, so the Legend's web_search entry uses Globe too.
const TOOL_ICONS = {
  web_search: Globe,
  write_file: Pencil,
  run_tests: FlaskConical,
  search_papers: FileSearch,
  read_report: FileText,
  'Environment spec input': FileInput,
};

const EDGE_COLORS = {
  read: 'rgba(56,189,248,0.55)',
  reads: 'rgba(56,189,248,0.55)',
  write: 'rgba(251,191,36,0.55)',
  writes: 'rgba(251,191,36,0.55)',
  memory_retrieve: 'rgba(56,189,248,0.55)',
  memory_store: 'rgba(251,191,36,0.55)',
};

function formatElapsed(ms: number): string {
  const totalSeconds = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function formatCompact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(Math.round(n));
}

function collectRunStats(events: AgrexEvent[]) {
  const nodeIds = new Set<string>();
  const usageByNode = new Map<string, { tokens: number; cost: number }>();
  let firstTs: number | undefined;
  let lastTs: number | undefined;

  for (const event of events) {
    const ts = Number(event.ts);
    if (Number.isFinite(ts)) {
      firstTs = firstTs === undefined ? ts : Math.min(firstTs, ts);
      lastTs = lastTs === undefined ? ts : Math.max(lastTs, ts);
    }

    if (event.type === 'node_add') {
      const node = event.node as AgrexNode | undefined;
      if (node?.id) nodeIds.add(node.id);
    }

    if (event.type !== 'node_update' || typeof event.id !== 'string') continue;
    const metadata = event.metadata as Record<string, unknown> | undefined;
    const tokens = typeof metadata?.tokens === 'number' ? metadata.tokens : undefined;
    const cost = typeof metadata?.cost === 'number' ? metadata.cost : undefined;
    if (tokens === undefined && cost === undefined) continue;
    usageByNode.set(event.id, {
      tokens: tokens ?? usageByNode.get(event.id)?.tokens ?? 0,
      cost: cost ?? usageByNode.get(event.id)?.cost ?? 0,
    });
  }

  let tokens = 0;
  let cost = 0;
  for (const usage of usageByNode.values()) {
    tokens += usage.tokens;
    cost += usage.cost;
  }

  return {
    nodeCount: nodeIds.size,
    durationMs:
      firstTs !== undefined && lastTs !== undefined ? Math.max(0, lastTs - firstTs) : 0,
    tokens,
    cost,
  };
}

function ReplayRunStats({
  replay,
  collapsed,
}: {
  replay: UseAgrexReplay;
  collapsed: boolean;
}) {
  if (replay.mode === 'idle' || replay.events.length === 0) return null;
  const stats = collectRunStats(replay.events);
  return (
    <div
      className="absolute left-1/2 z-30 flex -translate-x-1/2 items-center gap-4 rounded-lg border px-3 py-1.5 text-[11px] tabular-nums pointer-events-none"
      style={{
        bottom: collapsed ? 44 : 96,
        background: 'color-mix(in srgb, var(--agrex-bg, #0a0a0a) 82%, transparent)',
        borderColor: 'var(--agrex-node-border, rgba(255,255,255,0.15))',
        color: 'var(--agrex-fg, #fff)',
        backdropFilter: 'blur(14px)',
      }}
    >
      <span className="opacity-50">nodes</span>
      <strong>{stats.nodeCount}</strong>
      <span className="opacity-50">run time</span>
      <strong>{formatElapsed(stats.durationMs)}</strong>
      <span className="opacity-50">tokens</span>
      <strong>{formatCompact(stats.tokens)}</strong>
      <span className="opacity-50">cost</span>
      <strong>${stats.cost.toFixed(2)}</strong>
    </div>
  );
}

export const THEME = {
  background: '#000',
  foreground: '#fff',
  nodeFill: '#0d0d0d',
  nodeBorder: 'rgba(255,255,255,0.15)',
  nodeIcon: 'rgba(255,255,255,0.7)',
  edgeSpawn: 'rgba(255,255,255,0.35)',
  edgeWrite: 'rgba(251,191,36,0.35)',
  edgeRead: 'rgba(56,189,248,0.35)',
  statusRunning: '#f59e0b',
  statusDone: '#22c55e',
  statusError: '#ef4444',
  fontFamily: 'var(--font-sans)',
  fontMono: 'var(--font-mono)',
};

/* ── Props ─────────────────────────────────────────────────────── */

interface GraphProps {
  /** Replay-driven mode: pass the hook instance to get an embedded timeline. */
  replay?: UseAgrexReplay;
  /** Static mode: AgrexNode[] passed directly (used by DemoGraph). */
  nodes?: AgrexNode[];
  edges?: AgrexEdge[];
  onNodeClick?: (node: AgrexNode) => void;
  uiState?: GraphUIState;
  demo?: boolean;
  showDetailPanel?: boolean;
  sidebarCollapsed?: boolean;
  timelineCollapsedChange?: (collapsed: boolean) => void;
  onExitReplay?: () => void;
  agrexRef?: React.Ref<AgrexHandle>;
}

/* ── Component ─────────────────────────────────────────────────── */

export default function Graph({
  replay,
  nodes,
  edges,
  onNodeClick,
  uiState,
  demo,
  showDetailPanel = true,
  sidebarCollapsed,
  timelineCollapsedChange,
  onExitReplay,
  agrexRef,
}: GraphProps) {
  const [timelineCollapsed, setTimelineCollapsed] = useState(false);
  const handleTimelineCollapsedChange = (collapsed: boolean) => {
    setTimelineCollapsed(collapsed);
    timelineCollapsedChange?.(collapsed);
  };

  // Freeze the context value when the pieces don't change so renderers
  // only re-evaluate when the overlay actually shifts.
  const ctx = useMemo<GraphUIState>(
    () => ({
      currentStage: uiState?.currentStage,
      dismissedOutputIds: uiState?.dismissedOutputIds,
      outputApprovals: uiState?.outputApprovals,
    }),
    [uiState?.currentStage, uiState?.dismissedOutputIds, uiState?.outputApprovals],
  );

  return (
    <UIStateContext.Provider value={ctx}>
      <div className="relative h-full w-full">
        <Agrex
          ref={agrexRef}
          replay={replay}
          nodes={nodes}
          edges={edges}
          onNodeClick={onNodeClick}
          nodeRenderers={NODE_RENDERERS}
          toolIcons={TOOL_ICONS}
          edgeColors={EDGE_COLORS}
          theme={THEME}
          className="w-full h-full"
          showControls={!demo}
          showLegend={!demo}
          showToasts={!demo}
          toastPlacement="top-left"
          toastInsets={{ left: sidebarCollapsed ? 16 : 192 }}
          showDetailPanel={!demo && showDetailPanel}
          showStats={false}
          fitOnUpdate={!demo}
          animateEdges
          keyboardShortcuts={!demo}
          showTimeline={!demo}
          timelineProps={{
            jumpMarkerKind: 'stage',
            onCollapsedChange: handleTimelineCollapsedChange,
            onExit: onExitReplay,
            showStats: false,
            speeds: [1, 10, 30, 60],
            // App-scoped persistKey so previous runs under the package
            // default (`agrex.timeline.collapsed`) don't carry over a stale
            // "1" and open the timeline collapsed on fresh visits. New key
            // starts missing → Agrex defaults to expanded.
            persistKey: 'decisionlab.agrex.timeline.collapsed',
          }}
        />
        {replay && !demo && <ReplayRunStats replay={replay} collapsed={timelineCollapsed} />}
      </div>
    </UIStateContext.Provider>
  );
}
