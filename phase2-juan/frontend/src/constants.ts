import type { AgentState } from './types'

const FROM_COLORS_MAP: Record<string, string> = {
  user: 'rgba(255,255,255,0.5)',
  orchestrator: '#94a3b8',
  architect: '#4ade80',
  tracker: '#fbbf24',
  analyst: '#a78bfa',
  reporter: '#f472b6',
}

const PIPELINE_AGENTS = ['Orchestrator', 'Architect', 'Tracker', 'Analyst', 'Reporter'] as const
export const AGENT_COLORS = [
  FROM_COLORS_MAP.architect,
  FROM_COLORS_MAP.tracker,
  FROM_COLORS_MAP.analyst,
  FROM_COLORS_MAP.reporter,
  '#38bdf8',
  '#fb923c',
] as const

export const INITIAL_AGENTS: AgentState[] = PIPELINE_AGENTS.map((name) => ({
  name,
  status: 'idle',
  color: FROM_COLORS_MAP[name.toLowerCase()],
}))
export function getFromColor(name: string): string {
  return FROM_COLORS_MAP[name.toLowerCase()] || '#fff'
}
export function withAlpha(color: string, alphaHex: string): string {
  return color + alphaHex
}

export const FROM_COLORS = FROM_COLORS_MAP
export const KG_LABEL_COLORS: Record<string, string> = {
  Paradigm: '#4ade80',
  Postulate: '#a78bfa',
  Formulation: '#38bdf8',
  Model: '#fbbf24',
  Paper: '#f472b6',
  Author: '#fb923c',
  BrainRegion: '#22c55e',
  Equation: '#60a5fa',
  Variable: '#c084fc',
  Parameter: '#94a3b8',
}

export const KG_LABEL_DEFAULT = '#94a3b8'

export function kgLabelColor(label: string): string {
  return KG_LABEL_COLORS[label] ?? KG_LABEL_DEFAULT
}

const KG_NODE_TITLE_KEYS = ['name', 'title', 'id', 'doi'] as const
export function kgNodeTitle(
  node: { id: string; props: Record<string, unknown> },
  fallbackLen = 12,
): string {
  for (const key of KG_NODE_TITLE_KEYS) {
    const v = node.props[key]
    if (typeof v === 'string' && v) return v
  }
  return node.id.slice(0, fallbackLen)
}
export const TOOL_LABELS: Record<string, string> = {
  create_environment: 'Creando entorno',
  run_simulation: 'Simulando',
  list_available_models: 'Buscando modelos',
  observe_simulation: 'Observando',
  analyze_results: 'Analizando',
  generate_report: 'Generando informe',
  validate_spec: 'Validando spec',
  read_predictions: 'Leyendo predicciones',
  get_simulation_events: 'Leyendo eventos',
  get_agent_trajectory: 'Trayectoria',
  get_agent_state: 'Estado agente',
  list_critical_events: 'Eventos críticos',
  get_event_window: 'Ventana de eventos',
  get_decision_trace: 'Traza de decisión',
  compare_decision_traces: 'Comparando decisiones',
  list_state_keys: 'Variables disponibles',
  create_chart: 'Generando gráfica',
  list_past_experiments: 'Historial',
  get_experiment_analysis: 'Comparando',
  read_research: 'Investigación',
  compile_report: 'Compilando PDF',
}
