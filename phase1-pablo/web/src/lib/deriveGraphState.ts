import type { GraphNode, GraphEdge, Stage, StageStatus, AgentState } from "../types";

export interface DerivedGraphState {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stages: Record<Stage, StageStatus>;
  currentStage: Stage | null;
  agents: AgentState[];
  approvals: Record<string, boolean>;
}

function emptyStages(): Record<Stage, StageStatus> {
  return {} as Record<Stage, StageStatus>;
}

function emptyState(): DerivedGraphState {
  return {
    nodes: [],
    edges: [],
    stages: emptyStages(),
    currentStage: null,
    agents: [],
    approvals: {},
  };
}

function stepOne(state: DerivedGraphState, ev: Record<string, any>): DerivedGraphState {
  switch (ev.type) {
    case "stage_change":
      return {
        ...state,
        stages: { ...state.stages, [ev.stage]: ev.status },
        currentStage: ev.status === "running" ? ev.stage : state.currentStage,
      };
    case "node_add":
      return { ...state, nodes: [...state.nodes, ev.node] };
    case "edge_add":
      return { ...state, edges: [...state.edges, ev.edge] };
    case "node_update":
      return {
        ...state,
        nodes: state.nodes.map((n) => (n.id === ev.id ? { ...n, status: ev.status } : n)),
      };
    case "graph_clear":
      return { ...state, nodes: [], edges: [] };
    case "agents":
      return {
        ...state,
        agents: ev.agents.map((a: any) => ({ name: a.name, color: a.color, status: "idle" as const })),
      };
    case "agent_status":
      return {
        ...state,
        agents: state.agents.map((a) => (a.name === ev.agent ? { ...a, status: ev.status } : a)),
      };
    case "review_decision": {
      if (ev.approved && typeof ev.approved === "object") {
        return { ...state, approvals: { ...state.approvals, ...(ev.approved as Record<string, boolean>) } };
      }
      return state;
    }
    default:
      return state;
  }
}

export function deriveGraphState(events: readonly Record<string, any>[]): DerivedGraphState {
  let state = emptyState();
  for (const ev of events) state = stepOne(state, ev);
  return state;
}
