// Agent state (for the pipeline agent panel / sidebar interstitials)
export interface AgentState {
  name: string;
  status: "idle" | "working" | "done" | "failed";
  color: string;
  error?: string;
}

// Pipeline stages (mirrors backend Stage enum)
export enum Stage {
  RESEARCH = "research",
  MEMORY_RESEARCH = "memory_research",
  REVIEW_RESEARCH = "review_research",
  FORMALIZE = "formalize",
  MEMORY_FORMALIZE = "memory_formalize",
  REVIEW_FORMALIZE = "review_formalize",
  GET_ENV_SPEC = "get_env_spec",
  REASON = "reason",
  MEMORY_REASON = "memory_reason",
  REVIEW_REASON = "review_reason",
  BUILD = "build",
  MEMORY_BUILD = "memory_build",
  REVIEW_BUILD = "review_build",
  DONE = "done",
}

export type StageStatus = "pending" | "running" | "done" | "error";

export type NodeKind = "agent" | "sub_agent" | "tool" | "file" | "search" | "output";

// Per-kind meta shapes
export type NodeMeta =
  | { kind: "agent"; output?: string }
  | { kind: "sub_agent"; output?: string; paradigm?: string }
  | { kind: "tool"; args: Record<string, unknown> }
  | { kind: "file"; path: string; content?: string }
  | { kind: "search"; query: string; results?: string[] }
  | { kind: "output"; stage: string };

export interface GraphNode {
  id: string;
  kind: NodeKind;
  label: string;
  parent_id?: string;
  status: "running" | "done" | "error";
  meta: Record<string, unknown>;
}

export type EdgeKind = "spawn" | "write" | "read" | "layout";

export interface GraphEdge {
  source: string;
  target: string;
  edge_kind?: EdgeKind;
}

// Backend -> Frontend messages
export type ServerMessage =
  | { type: "stage"; ts: number; label: string; color?: string }
  | { type: "marker"; ts: number; kind: string; label?: string; color?: string }
  | { type: "node_add"; node: GraphNode }
  | { type: "edge_add"; edge: GraphEdge }
  | {
      type: "node_update";
      id: string;
      status?: "running" | "done" | "error";
      label?: string;
      metadata?: Record<string, unknown>;
    }
  | { type: "review_request"; stage: Stage.REVIEW_RESEARCH; data: ReviewResearchData }
  | { type: "review_request"; stage: Stage.REVIEW_FORMALIZE; data: ReviewFormalizeData }
  | { type: "review_request"; stage: Stage.GET_ENV_SPEC; data: { message?: string } }
  | { type: "review_request"; stage: Stage.REVIEW_REASON; data: ReviewReasonData }
  | { type: "review_request"; stage: Stage.REVIEW_BUILD; data: ReviewBuildData }
  | { type: "rerun"; target: string; paradigm: string; reason: string }
  | { type: "graph_clear"; from_stage: Stage }
  | { type: "pipeline_done" }
  | { type: "error"; message: string }
  | { type: "state_sync"; nodes: GraphNode[]; edges: GraphEdge[]; stage: Stage }
  | { type: "agents"; agents: Array<{ name: string; color: string }> }
  | {
      type: "agent_status";
      agent: string;
      status: "idle" | "working" | "done" | "failed";
      error?: string;
    }
  | { type: "agent_tool"; agent: string; tool: string }
  | { type: "run_start"; run_id: string };

// Knowledge Graph snapshot (from /api/kg/snapshot)
export interface KGNode {
  id: string;
  label: string;        // Neo4j label (Paradigm, Variable, ...)
  display: string;      // human-readable display string
  run_count: number;    // total MERGEs that have touched this node
  last_run_at: string | null; // ISO timestamp of the most recent MERGE
  properties: Record<string, unknown>;
}

export interface KGRelation {
  id: string;
  source: string;       // KGNode.id
  target: string;       // KGNode.id
  type: string;         // relation type (SUPPORTS, AUTHORED, ...)
  run_id: string | null;
  properties: Record<string, unknown>;
}

// `current_run_node_ids` is populated by the snapshot endpoint when called
// with `?run_id=`. It contains the elementIds of nodes touched in that
// run, joined from the Postgres node_run_observations table (P0-004).
export interface KGSnapshot {
  nodes: KGNode[];
  relations: KGRelation[];
  current_run_node_ids: string[];
}

// Frontend -> Backend messages
export type ClientMessage =
  | { type: "start"; problem: string; until_stage?: Stage }
  | { type: "review_response"; stage: Stage.REVIEW_RESEARCH; data: { approved: string[]; additional?: string | null } }
  | { type: "review_response"; stage: Stage.REVIEW_FORMALIZE; data: { selected: Record<string, number[]> } }
  | { type: "review_response"; stage: Stage.GET_ENV_SPEC; data: { env_spec: Record<string, unknown> } }
  | { type: "review_response"; stage: Stage.REVIEW_REASON; data: { decisions: Record<string, { approved?: boolean; feedback?: string; rerun_formalizer?: boolean }> } }
  | { type: "review_response"; stage: Stage.REVIEW_BUILD; data: { decisions: Record<string, { approved?: boolean; feedback?: string; rerun_reasoner?: boolean }> } }
  | { type: "cancel" }
  | { type: "router_prompt"; message: string };

// Review data types
export interface ReviewResearchData {
  paradigms: Array<{
    slug: string;
    title: string;
    summary: string;
    content?: string;
  }>;
}

export interface ReviewFormalizeData {
  paradigms: Array<{
    slug: string;
    title?: string;
    content?: string;
    formulations: Array<{ id: number; name?: string; content: string }>;
  }>;
}

export interface ReviewReasonData {
  specs: Array<{
    id: string;
    spec_id?: string;
    paradigm: string;
    name: string;
    status?: "invalid";
    problems?: Array<Record<string, unknown>>;
    description?: string;
    variables?: any[];
    parameters?: any[];
    rules?: any[];
    decision_logic?: any;
    env_mapping?: Record<string, unknown>;
    full_spec?: Record<string, unknown>;
  }>;
}

export interface ReviewBuildData {
  models: Array<{
    slug: string;
    paradigm?: string;
    status?: "invalid";
    problems?: Array<Record<string, unknown>>;
    code: string;
    test_results: string;
    passed: boolean;
  }>;
}

// Stage display config
export const STAGE_CONFIG: Array<{
  stage: Stage;
  label: string;
  indented: boolean;
}> = [
  { stage: Stage.RESEARCH, label: "RESEARCH", indented: false },
  { stage: Stage.REVIEW_RESEARCH, label: "REVIEW", indented: true },
  { stage: Stage.FORMALIZE, label: "FORMALIZE", indented: false },
  { stage: Stage.REVIEW_FORMALIZE, label: "REVIEW", indented: true },
  { stage: Stage.GET_ENV_SPEC, label: "ENV SPEC", indented: false },
  { stage: Stage.REASON, label: "REASON", indented: false },
  { stage: Stage.REVIEW_REASON, label: "REVIEW", indented: true },
  { stage: Stage.BUILD, label: "BUILD", indented: false },
  { stage: Stage.REVIEW_BUILD, label: "REVIEW", indented: true },
];

// Stages after which the Memory Agent runs (before their REVIEW)
export const MEMORY_AGENT_STAGES = new Set<Stage>([
  Stage.RESEARCH,
  Stage.FORMALIZE,
  Stage.REASON,
  Stage.BUILD,
]);

// Mapping work stage → its dedicated MEMORY_X stage (mirrors the backend
// _MEMORY_STAGE_OF dict). Used by the sidebar to read memory-tick status
// directly from `stages[MEMORY_X]` instead of inferring it from a separate
// agent_status side-channel.
export const MEMORY_STAGE_OF: Partial<Record<Stage, Stage>> = {
  [Stage.RESEARCH]: Stage.MEMORY_RESEARCH,
  [Stage.FORMALIZE]: Stage.MEMORY_FORMALIZE,
  [Stage.REASON]: Stage.MEMORY_REASON,
  [Stage.BUILD]: Stage.MEMORY_BUILD,
};

// Agent color mapping
export const AGENT_COLORS: Record<string, string> = {
  researcher: "#4a9eff",
  formalizer: "#9b59b6",
  reasoner: "#ff6b4a",
  builder: "#fbbf24",
  memory_agent: "#22d3ee",
};

// Tool icon mapping
export const TOOL_ICONS: Record<string, string> = {
  web_search: "Search",
  read_file: "FileText",
  write_file: "FilePlus",
  run_tests: "FlaskConical",
  launch_deep_research: "Microscope",
  search_papers: "FileSearch",
};

// ---------------------------------------------------------------------------
// Replay types
// ---------------------------------------------------------------------------
// `AgrexEvent` and `ReplayMode` now come from `@ppazosp/agrex`. Only the
// backend-specific `PastRun` descriptor stays here.

export interface MemoryStageResult {
  status: "ok" | "failed";
  nodes_created?: number;
  nodes_merged?: number;
  relations_created?: number;
  facts_stored?: number;
  duplicates_skipped?: number;
  conflicts_resolved?: number;
  duration_ms?: number;
  error?: string;
}

export interface PastRun {
  run_id: string;
  problem: string;
  status: "done" | "cancelled" | "failed";
  started_at: string;
  artifact_count: number | null;
  // Set only on partial runs (--until X). NULL means "ran the full pipeline".
  final_stage: string | null;
  // Per-stage Memory Agent results, keyed by agent name ("researcher", ...).
  memory_results: Record<string, MemoryStageResult> | null;
}
