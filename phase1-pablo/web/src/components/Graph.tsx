import { createContext, useContext, useMemo } from 'react';
import {
  Agrex,
  type AgrexHandle,
  type AgrexNode,
  type AgrexNodeProps,
  type AgrexEdge,
  type UseAgrexReplay,
} from '@ppazosp/agrex';
import '@xyflow/react/dist/style.css';
import '@ppazosp/agrex/styles.css';
import { Globe, Eye, Pencil, FlaskConical, FileSearch } from 'lucide-react';
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
  const isVectorDb = node.id.includes('vector');
  const accent = isVectorDb ? '#a78bfa' : '#38bdf8';
  const gradientId = isVectorDb ? 'db-stack-vector' : 'db-stack-kg';
  const borderColor =
    status === 'running' ? theme.statusRunning
    : status === 'error' ? theme.statusError
    : accent;

  return (
    <div
      className="relative flex flex-col items-center justify-center"
      style={{ width: 108, height: 88 }}
    >
      <NodeHandles />
      <svg
        width="76"
        height="60"
        viewBox="0 0 76 60"
        aria-hidden="true"
        style={{
          overflow: 'visible',
          animation: status === 'running' ? 'agrex-running-ring 1.5s ease-in-out infinite' : undefined,
        }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={accent} stopOpacity="0.32" />
            <stop offset="100%" stopColor={theme.nodeFill} stopOpacity="1" />
          </linearGradient>
        </defs>
        <path
          d="M 13 15 C 13 8.4 24.2 3 38 3 C 51.8 3 63 8.4 63 15 L 63 43 C 63 49.6 51.8 55 38 55 C 24.2 55 13 49.6 13 43 Z"
          fill={`url(#${gradientId})`}
          stroke={borderColor}
          strokeWidth="1.6"
        />
        <ellipse
          cx="38"
          cy="15"
          rx="25"
          ry="12"
          fill={`${accent}24`}
          stroke={borderColor}
          strokeWidth="1.6"
        />
        <path
          d="M 13 28 C 13 34.6 24.2 40 38 40 C 51.8 40 63 34.6 63 28"
          fill="none"
          stroke={borderColor}
          strokeOpacity="0.72"
          strokeWidth="1.4"
        />
        <path
          d="M 13 42 C 13 48.6 24.2 54 38 54 C 51.8 54 63 48.6 63 42"
          fill="none"
          stroke={borderColor}
          strokeOpacity="0.72"
          strokeWidth="1.4"
        />
        <ellipse
          cx="38"
          cy="15"
          rx="12"
          ry="4.7"
          fill={`${accent}26`}
          stroke={accent}
          strokeOpacity="0.45"
          strokeWidth="1"
        />
      </svg>
      <div
        className="mt-0.5 text-center"
        style={{
          maxWidth: 104,
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
  read_file: Eye,
  write_file: Pencil,
  run_tests: FlaskConical,
  search_papers: FileSearch,
};

const EDGE_COLORS = {
  memory_retrieve: 'rgba(56,189,248,0.55)',
  memory_store: 'rgba(34,197,94,0.55)',
};

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
        // Demo has no replay → Agrex's embedded timeline doesn't mount, so
        // the floating StatsBar would otherwise render. Turn it off.
        // Live/replay: the embedded timeline owns stats (`timelineProps.showStats`),
        // and Agrex's own gate hides the floating bar when the timeline is up.
        showStats={!demo}
        fitOnUpdate={!demo}
        animateEdges
        keyboardShortcuts={!demo}
        // Embedded timeline — rendered only when `replay` is provided and
        // `replay.mode !== "idle"`. Stats live inside the timeline panel, so
        // the floating StatsBar auto-hides (gated by `!timelineVisible`).
        showTimeline={!demo}
        timelineProps={{
          jumpMarkerKind: 'stage',
          onCollapsedChange: timelineCollapsedChange,
          onExit: onExitReplay,
          showStats: true,
          // App-scoped persistKey so previous runs under the package
          // default (`agrex.timeline.collapsed`) don't carry over a stale
          // "1" and open the timeline collapsed on fresh visits. New key
          // starts missing → Agrex defaults to expanded.
          persistKey: 'decisionlab.agrex.timeline.collapsed',
        }}
      />
    </UIStateContext.Provider>
  );
}
