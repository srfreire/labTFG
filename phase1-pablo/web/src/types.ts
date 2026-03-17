// Pipeline stages (mirrors backend Stage enum)
export enum Stage {
  RESEARCH = "research",
  REVIEW_RESEARCH = "review_research",
  FORMALIZE = "formalize",
  REVIEW_FORMALIZE = "review_formalize",
  GET_ENV_SPEC = "get_env_spec",
  REASON = "reason",
  REVIEW_REASON = "review_reason",
  BUILD = "build",
  REVIEW_BUILD = "review_build",
  DONE = "done",
}

export type StageStatus = "pending" | "running" | "done" | "error";

export type NodeKind = "agent" | "sub_agent" | "tool" | "file" | "search";

// Per-kind meta shapes
export type NodeMeta =
  | { kind: "agent"; output?: string }
  | { kind: "sub_agent"; output?: string; paradigm?: string }
  | { kind: "tool"; args: Record<string, unknown> }
  | { kind: "file"; path: string; content?: string }
  | { kind: "search"; query: string; results?: string[] };

export interface GraphNode {
  id: string;
  kind: NodeKind;
  label: string;
  parent_id?: string;
  status: "running" | "done" | "error";
  meta: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
}

// Backend -> Frontend messages
export type ServerMessage =
  | { type: "stage_change"; stage: Stage; status: StageStatus }
  | { type: "node_add"; node: GraphNode }
  | { type: "edge_add"; edge: GraphEdge }
  | { type: "node_update"; id: string; status: "running" | "done" | "error" }
  | { type: "review_request"; stage: Stage.REVIEW_RESEARCH; data: ReviewResearchData }
  | { type: "review_request"; stage: Stage.REVIEW_FORMALIZE; data: ReviewFormalizeData }
  | { type: "review_request"; stage: Stage.GET_ENV_SPEC; data: Record<string, never> }
  | { type: "review_request"; stage: Stage.REVIEW_REASON; data: ReviewReasonData }
  | { type: "review_request"; stage: Stage.REVIEW_BUILD; data: ReviewBuildData }
  | { type: "rerun"; target: string; paradigm: string; reason: string }
  | { type: "graph_clear"; from_stage: Stage }
  | { type: "pipeline_done" }
  | { type: "error"; message: string }
  | { type: "state_sync"; nodes: GraphNode[]; edges: GraphEdge[]; stage: Stage };

// Frontend -> Backend messages
export type ClientMessage =
  | { type: "start"; problem: string }
  | { type: "review_response"; stage: Stage.REVIEW_RESEARCH; data: { approved: string[] } }
  | { type: "review_response"; stage: Stage.REVIEW_FORMALIZE; data: { selected: Record<string, number[]> } }
  | { type: "review_response"; stage: Stage.GET_ENV_SPEC; data: { env_spec: Record<string, unknown> } }
  | { type: "review_response"; stage: Stage.REVIEW_REASON; data: { decisions: Record<string, { approved: boolean; feedback?: string }> } }
  | { type: "review_response"; stage: Stage.REVIEW_BUILD; data: { decisions: Record<string, { approved: boolean; feedback?: string }> } }
  | { type: "cancel" };

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
    title: string;
    formulations: Array<{ id: number; content: string }>;
  }>;
}

export interface ReviewReasonData {
  specs: Array<{
    id: string;
    paradigm: string;
    name: string;
    description: string;
    variables: any[];
    parameters: any[];
    rules: any[];
    decision_logic: any;
  }>;
}

export interface ReviewBuildData {
  models: Array<{
    slug: string;
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

// Agent color mapping
export const AGENT_COLORS: Record<string, string> = {
  researcher: "#4a9eff",
  formalizer: "#9b59b6",
  reasoner: "#ff6b4a",
  builder: "#fbbf24",
};

// Tool icon mapping
export const TOOL_ICONS: Record<string, string> = {
  web_search: "Search",
  read_file: "FileText",
  write_file: "FilePlus",
  run_tests: "FlaskConical",
  launch_deep_research: "Microscope",
};
