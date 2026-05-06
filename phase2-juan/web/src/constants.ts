import type { AgentState } from './types'

// Simulation agent colors — fallback palette, overridden at runtime by backend via WS
// Source of truth: SIM_AGENT_COLORS in api.py
export const AGENT_COLORS = ['#4ade80', '#fbbf24', '#a78bfa', '#f472b6', '#38bdf8', '#fb923c'] as const

// Initial agent states — shared between real and mock hooks
export const INITIAL_AGENTS: AgentState[] = [
  { name: 'Orchestrator', status: 'idle', color: '#94a3b8' },
  { name: 'Architect', status: 'idle', color: '#4ade80' },
  { name: 'Tracker', status: 'idle', color: '#fbbf24' },
  { name: 'Analyst', status: 'idle', color: '#a78bfa' },
  { name: 'Reporter', status: 'idle', color: '#f472b6' },
]

// Chat message sender colors — canonical keys are lowercase;
// use getFromColor() for case-insensitive lookup
const FROM_COLORS_MAP: Record<string, string> = {
  user: 'rgba(255,255,255,0.5)',
  orchestrator: '#94a3b8',
  architect: '#4ade80',
  tracker: '#fbbf24',
  analyst: '#a78bfa',
  reporter: '#f472b6',
}

/** Case-insensitive color lookup for message senders. */
export function getFromColor(name: string): string {
  return FROM_COLORS_MAP[name.toLowerCase()] || '#fff'
}

// Re-export for places that iterate all entries (e.g. getAgentColor text matching)
export const FROM_COLORS = FROM_COLORS_MAP

// Friendly labels for internal agent tool calls
// Keep short — must fit in 200px sidebar
export const TOOL_LABELS: Record<string, string> = {
  // Orchestrator tools
  create_environment: 'Creando entorno',
  run_simulation: 'Simulando',
  list_available_models: 'Buscando modelos',
  observe_simulation: 'Observando',
  analyze_results: 'Analizando',
  generate_report: 'Generando informe',
  // Architect
  validate_spec: 'Validando spec',
  read_predictions: 'Leyendo predicciones',
  // Tracker & Analyst
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
  // Reporter
  read_research: 'Investigación',
  compile_report: 'Compilando PDF',
}
