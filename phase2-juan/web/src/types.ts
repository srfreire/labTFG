export interface AgentState {
  name: string
  status: 'idle' | 'working' | 'done'
  color: string
  activeTool?: string
}

export interface PipelineStep {
  step: string
  status: 'pending' | 'done'
}

export interface ChatMessage {
  id: string
  from: 'user' | 'orchestrator' | 'tracker' | 'analyst' | 'reporter'
  text: string
  card?: DataCard
  tracker?: TrackerData
  analyst?: AnalystData
  replay?: ReplayData
  charts?: ChartSpec[]
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
  type: 'consumption' | 'starvation' | 'energy_spike' | 'strategy_shift'
  severity: number
  description: string
}

export interface ReplayData {
  grid_width: number
  grid_height: number
  total_steps: number
  frames: ReplayFrame[]
  critical_events?: CriticalEvent[]
}
