export const AGENT_COLORS = ['#4ade80', '#fbbf24', '#a78bfa', '#f472b6', '#38bdf8', '#fb923c'] as const

export const FROM_COLORS: Record<string, string> = {
  user: 'rgba(255,255,255,0.5)',
  orchestrator: '#94a3b8',
  tracker: '#fbbf24',
  analyst: '#a78bfa',
  reporter: '#f472b6',
}

// Friendly labels for internal agent tool calls
export const TOOL_LABELS: Record<string, string> = {
  // Orchestrator tools
  create_environment: 'Creando entorno',
  run_simulation: 'Ejecutando simulación',
  list_available_models: 'Buscando modelos',
  observe_simulation: 'Llamando al Tracker',
  analyze_results: 'Llamando al Analyst',
  generate_report: 'Generando informe',
  // Architect
  validate_spec: 'Validando especificación',
  // Tracker & Analyst
  get_simulation_events: 'Leyendo eventos',
  get_agent_trajectory: 'Analizando trayectoria',
  get_agent_state: 'Inspeccionando estado',
  // Reporter
  read_research: 'Leyendo investigación',
  compile_report: 'Compilando PDF',
}
