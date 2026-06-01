export interface AgentState {
  name: string
  status: 'idle' | 'working' | 'done'
  color: string
  activeTool?: string
}

export interface ChatMessage {
  id: string
  from: 'user' | 'orchestrator' | 'tracker' | 'analyst' | 'reporter'
  text: string
  card?: DataCard
  reports?: ReportArtifact[]
  tracker?: TrackerData
  analyst?: AnalystData
  replay?: ReplayData
  charts?: ChartSpec[]
  traces?: DecisionTrace[]
}

export interface ReportArtifact {
  key: string
  filename: string
}

export interface ChartSpec {
  id: string
  type: 'line' | 'bar' | 'heatmap'
  title: string
  x_label: string
  y_label: string
  series: ChartSeries[]
  image_path?: string
}

export interface ChartSeries {
  name: string
  color?: string
  data: { x: number | string; y: number }[]
}

export interface DataCard {
  title: string
  data: Record<string, string>
}

export interface TrackerData {
  summary: string
  trajectories: Record<string, {
    steps_survived: number
    resources_consumed: number
    actions: Record<string, number>
  }>
  episodes: Array<{
    agent: string
    type: string
    step?: number
    steps?: number[]
    description: string
  }>
}

export interface AnalystData {
  patterns: Array<{
    id: string
    type: string
    agents: string[]
    description: string
    evidence: string
  }>
  comparisons: Array<{
    agents: string[]
    metric: string
    values: Record<string, number>
    insight: string
  }>
  metrics: Record<string, Record<string, number>>
}

export interface DecisionTrace {
  agent_id: string
  step: number
  perception: Record<string, unknown> | null
  pre_state: Record<string, unknown> | null
  post_state: Record<string, unknown>
  available_actions: string[] | null
  action_chosen: { name: string; params: Record<string, unknown> }
  outcome: { reward: number; action_result: Record<string, unknown> }
}

export interface ReplayFrame {
  step: number
  agents: { id: string; x: number; y: number; alive: boolean }[]
  resources: { type: string; x: number; y: number }[]
  actions: { agent_id: string; action: string; reward: number }[]
}

export interface SimAgent {
  id: string
  color: string
}

export interface CriticalEvent {
  step: number
  agent_id: string
  type: 'consumption' | 'starvation' | 'energy_spike' | 'strategy_shift' | 'decision_confidence_drop'
  severity: number
  description: string
  data?: Record<string, unknown>
}

export interface ReplayData {
  grid_width: number
  grid_height: number
  total_steps: number
  frames: ReplayFrame[]
  critical_events?: CriticalEvent[]
  traces?: Record<number, DecisionTrace[]>
}

// Knowledge graph — matches /api/knowledge/graph response shape
export interface KGNode {
  id: string
  label: string
  props: Record<string, unknown>
}

export interface KGEdge {
  id: string
  source: string
  target: string
  type: string
  props: Record<string, unknown>
}

export interface KGSnapshot {
  nodes: KGNode[]
  edges: KGEdge[]
  current_run_node_ids: string[]
}

export interface KGMemory {
  id: string
  content: string
  namespace: string
  run_id: string
  memory_type: string
  source_stage: string
  created_at: string | null
}

export interface KGMemoryPage {
  items: KGMemory[]
  total: number
  page: number
  page_size: number
}

export interface KGTrailStep {
  edge: { id: string; type: string; props: Record<string, unknown> }
  node: KGNode
}

export interface KGProvenance {
  node: KGNode
  trail: KGTrailStep[]
}
