// Simulation agent colors — fallback palette, overridden at runtime by backend via WS
// Source of truth: SIM_AGENT_COLORS in api.py
export const AGENT_COLORS = ['#4ade80', '#fbbf24', '#a78bfa', '#f472b6', '#38bdf8', '#fb923c'] as const

// Chat message sender colors — both cases needed because backend sends capitalized
// names while some internal references use lowercase
export const FROM_COLORS: Record<string, string> = {
  user: 'rgba(255,255,255,0.5)',
  orchestrator: '#94a3b8',
  Orchestrator: '#94a3b8',
  architect: '#4ade80',
  Architect: '#4ade80',
  tracker: '#fbbf24',
  Tracker: '#fbbf24',
  analyst: '#a78bfa',
  Analyst: '#a78bfa',
  reporter: '#f472b6',
  Reporter: '#f472b6',
}

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
  // Tracker & Analyst
  get_simulation_events: 'Leyendo eventos',
  get_agent_trajectory: 'Trayectoria',
  get_agent_state: 'Estado agente',
  list_past_experiments: 'Historial',
  get_experiment_analysis: 'Comparando',
  // Reporter
  read_research: 'Investigación',
  compile_report: 'Compilando PDF',
}
