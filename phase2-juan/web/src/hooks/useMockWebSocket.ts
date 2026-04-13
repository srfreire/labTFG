/**
 * Mock WebSocket hook — simulates the full pipeline with fake data.
 * Activate by adding ?mock to the URL: http://localhost:5173/?mock
 */
import { useState, useCallback, useRef } from 'react'
import type { AgentState, PipelineStep, ChatMessage, ReplayData, TrackerData, AnalystData, ChartSpec, SimAgent, CriticalEvent, DecisionTrace } from '../types'
import { AGENT_COLORS } from '../constants'

const INITIAL_AGENTS: AgentState[] = [
  { name: 'Orchestrator', status: 'idle', color: '#94a3b8' },
  { name: 'Architect', status: 'idle', color: '#4ade80' },
  { name: 'Tracker', status: 'idle', color: '#fbbf24' },
  { name: 'Analyst', status: 'idle', color: '#a78bfa' },
  { name: 'Reporter', status: 'idle', color: '#f472b6' },
]

// --- Mock data generators ---

function mockCriticalEvents(): CriticalEvent[] {
  return [
    { step: 3, agent_id: 'drive_reduction_rl', type: 'consumption', severity: 0.5, description: 'drive_reduction_rl consumió food (reward=1.0)' },
    { step: 8, agent_id: 'drive_reduction_rl', type: 'starvation', severity: 0.7, description: 'drive_reduction_rl energía crítica: 12.3' },
    { step: 9, agent_id: 'drive_reduction_rl', type: 'energy_spike', severity: 0.8, description: 'drive_reduction_rl energía subió 45.0 (12.3→57.3)' },
    { step: 14, agent_id: 'pi_negative_feedback', type: 'consumption', severity: 0.5, description: 'pi_negative_feedback consumió food (reward=1.0)' },
    { step: 16, agent_id: 'drive_reduction_rl', type: 'decision_confidence_drop', severity: 0.7, description: 'drive_reduction_rl perdió confianza en su decisión: gap Q-values bajó de 2.10 a 0.35' },
    { step: 18, agent_id: 'drive_reduction_rl', type: 'strategy_shift', severity: 0.6, description: 'drive_reduction_rl cambió de \'move_up\' a \'eat\'' },
    { step: 22, agent_id: 'pi_negative_feedback', type: 'starvation', severity: 0.9, description: 'pi_negative_feedback energía crítica: 5.1' },
  ]
}

function mockReplay(): ReplayData {
  const W = 8, H = 8, STEPS = 30
  const frames = []
  let ax = 1, ay = 1, bx = 6, by = 6

  const resources = [
    { type: 'food', x: 3, y: 2 }, { type: 'food', x: 5, y: 1 },
    { type: 'food', x: 2, y: 5 }, { type: 'food', x: 6, y: 3 },
    { type: 'food', x: 4, y: 6 }, { type: 'food', x: 1, y: 4 },
  ]

  for (let step = 0; step < STEPS; step++) {
    const dirs: [number, number][] = [[-1,0],[1,0],[0,-1],[0,1],[0,0]]
    const [dax, day] = dirs[Math.floor(Math.random() * 4)]
    ax = Math.max(0, Math.min(W - 1, ax + dax))
    ay = Math.max(0, Math.min(H - 1, ay + day))
    const [dbx, dby] = dirs[Math.floor(Math.random() * 5)]
    bx = Math.max(0, Math.min(W - 1, bx + dbx))
    by = Math.max(0, Math.min(H - 1, by + dby))

    frames.push({
      step,
      agents: [
        { id: 'drive_reduction_rl', x: ax, y: ay, alive: step < 28 },
        { id: 'pi_negative_feedback', x: bx, y: by, alive: true },
      ],
      resources: resources.filter(() => Math.random() > 0.15),
      actions: [
        { agent_id: 'drive_reduction_rl', action: dax === 0 && day === 0 ? 'stay' : 'move', reward: Math.random() > 0.7 ? 1 : 0 },
        { agent_id: 'pi_negative_feedback', action: dbx === 0 && dby === 0 ? 'stay' : 'move', reward: Math.random() > 0.85 ? 1 : 0 },
      ],
    })
  }

  return { grid_width: W, grid_height: H, total_steps: STEPS, frames, critical_events: mockCriticalEvents(), traces: mockReplayTraces() }
}

function mockTracker(): TrackerData {
  return {
    summary: 'Simulación con 2 agentes de regulación homeostática durante 30 pasos.',
    trajectories: {
      drive_reduction_rl: {
        steps_survived: 28,
        resources_consumed: 7,
        actions: { move_up: 8, move_down: 4, move_left: 3, move_right: 5, eat: 7, stay: 1 },
      },
      pi_negative_feedback: {
        steps_survived: 30,
        resources_consumed: 3,
        actions: { move_up: 9, move_down: 7, move_left: 5, move_right: 6, eat: 3 },
      },
    },
    episodes: [
      { agent: 'drive_reduction_rl', type: 'learning', step: 5, description: 'El agente comenzó a dirigirse hacia recursos tras aprender Q-values iniciales' },
      { agent: 'drive_reduction_rl', type: 'starvation', step: 8, description: 'Energía bajó a nivel crítico (12.3) antes de encontrar comida' },
      { agent: 'drive_reduction_rl', type: 'strategy_shift', step: 18, description: 'Cambió de exploración a explotación al aprender la ubicación de recursos' },
      { agent: 'pi_negative_feedback', type: 'competition', step: 14, description: 'Compitió con drive_reduction_rl por el mismo recurso' },
    ],
  }
}

function mockAnalyst(): AnalystData {
  return {
    patterns: [
      {
        id: 'P1', type: 'estrategia', agents: ['drive_reduction_rl'],
        description: 'El agente drive_reduction aprendió a moverse hacia los recursos tras los primeros 5 pasos, formando un patrón de búsqueda dirigida basado en Q-values',
        evidence: 'Entre los pasos 1-5 el movimiento era aleatorio (tasa de acierto 12%), pero a partir del paso 6 subió al 45%',
      },
      {
        id: 'P2', type: 'recursos', agents: ['drive_reduction_rl', 'pi_negative_feedback'],
        description: 'El modelo PI mantuvo niveles de energía más estables gracias a su mecanismo de control proporcional-integral, pero fue menos eficiente recolectando',
        evidence: 'Desviación estándar de energía: PI=8.2, Drive=15.7. Recursos: PI=3, Drive=7',
      },
      {
        id: 'P3', type: 'anomaly', agents: ['drive_reduction_rl'],
        description: 'El agente drive_reduction experimentó un pico crítico de hambre en el paso 8, con energía cayendo a 12.3 antes de recuperarse',
        evidence: 'Energía paso 7: 58.1, paso 8: 12.3, paso 9: 57.3 (tras consumo exitoso)',
      },
    ],
    comparisons: [
      {
        agents: ['drive_reduction_rl', 'pi_negative_feedback'],
        metric: 'Recursos recogidos',
        values: { drive_reduction_rl: 7, pi_negative_feedback: 3 },
        insight: 'Drive reduction recogió más del doble porque su señal de impulso le motiva a buscar comida activamente cuando tiene hambre',
      },
      {
        agents: ['drive_reduction_rl', 'pi_negative_feedback'],
        metric: 'Estabilidad energética',
        values: { drive_reduction_rl: 15.7, pi_negative_feedback: 8.2 },
        insight: 'PI fue más estable gracias a su mecanismo de control integral que suaviza las oscilaciones, aunque a costa de menor recolección',
      },
      {
        agents: ['drive_reduction_rl', 'pi_negative_feedback'],
        metric: 'Pasos sobrevividos',
        values: { drive_reduction_rl: 28, pi_negative_feedback: 30 },
        insight: 'PI sobrevivió toda la simulación con regulación conservadora, drive_reduction murió por agotamiento tras no encontrar comida a tiempo',
      },
    ],
    metrics: {
      drive_reduction_rl: {
        'pasos vivo': 28,
        'recursos comidos': 7,
        'tasa supervivencia': 0.93,
      },
      pi_negative_feedback: {
        'pasos vivo': 30,
        'recursos comidos': 3,
        'tasa supervivencia': 1.0,
      },
    },
  }
}

function mockCharts(): ChartSpec[] {
  return [
    {
      id: 'chart_1',
      type: 'line',
      title: 'Evolución de energía por agente',
      x_label: 'Paso',
      y_label: 'Energía',
      series: [
        {
          name: 'drive_reduction_rl', color: '#4ade80',
          data: Array.from({ length: 28 }, (_, i) => ({
            x: i, y: Math.max(0, 80 - i * 3 + Math.sin(i * 0.5) * 20 + (i === 8 ? -40 : 0) + (i === 9 ? 45 : 0)),
          })),
        },
        {
          name: 'pi_negative_feedback', color: '#fbbf24',
          data: Array.from({ length: 30 }, (_, i) => ({
            x: i, y: 70 + Math.sin(i * 0.3) * 8,
          })),
        },
      ],
    },
    {
      id: 'chart_2',
      type: 'bar',
      title: 'Distribución de acciones',
      x_label: 'Acción',
      y_label: 'Cantidad',
      series: [
        {
          name: 'drive_reduction_rl', color: '#4ade80',
          data: [{ x: 'eat', y: 7 }, { x: 'move_down', y: 4 }, { x: 'move_left', y: 3 }, { x: 'move_right', y: 5 }, { x: 'move_up', y: 8 }, { x: 'stay', y: 1 }],
        },
        {
          name: 'pi_negative_feedback', color: '#fbbf24',
          data: [{ x: 'eat', y: 3 }, { x: 'move_down', y: 7 }, { x: 'move_left', y: 5 }, { x: 'move_right', y: 6 }, { x: 'move_up', y: 9 }, { x: 'stay', y: 0 }],
        },
      ],
    },
    {
      id: 'chart_3',
      type: 'line',
      title: 'Evolución Q-values por acción (drive_reduction_rl)',
      x_label: 'Paso',
      y_label: 'Q-valor',
      series: [
        {
          name: 'drive_reduction_rl:eat', color: '#4ade80',
          data: Array.from({ length: 28 }, (_, i) => ({
            x: i, y: Math.round((0.5 + i * 0.4 + Math.sin(i * 0.3) * 0.5) * 100) / 100,
          })),
        },
        {
          name: 'drive_reduction_rl:move_up', color: '#38bdf8',
          data: Array.from({ length: 28 }, (_, i) => ({
            x: i, y: Math.round((0.3 + i * 0.15 + Math.cos(i * 0.4) * 0.3) * 100) / 100,
          })),
        },
        {
          name: 'drive_reduction_rl:stay', color: '#f472b6',
          data: Array.from({ length: 28 }, (_, i) => ({
            x: i, y: Math.round((0.1 + i * 0.05) * 100) / 100,
          })),
        },
      ],
    },
  ]
}

function mockDecisionTraces(): DecisionTrace[] {
  return [
    {
      agent_id: 'drive_reduction_rl',
      step: 16,
      perception: { x: 3, y: 4, grid_width: 8, grid_height: 8, step: 16, resources: { food: [{ x: 3, y: 4 }, { x: 5, y: 1 }] } },
      pre_state: { energy: 25.3, drive: 0.82, epsilon: 0.15, q_table: { eat: 12.3, move_right: 8.1, stay: 5.4, move_left: 3.2 } },
      post_state: { energy: 40.3, drive: 0.31, epsilon: 0.14, q_table: { eat: 12.8, move_right: 8.1, stay: 5.4, move_left: 3.2 } },
      available_actions: ['eat', 'move_up', 'move_down', 'move_left', 'move_right', 'stay'],
      action_chosen: { name: 'eat', params: {} },
      outcome: { reward: 15, action_result: { consumed: true, resource_type: 'food' } },
    },
    {
      agent_id: 'pi_negative_feedback',
      step: 16,
      perception: { x: 5, y: 3, grid_width: 8, grid_height: 8, step: 16, resources: { food: [{ x: 5, y: 1 }, { x: 6, y: 3 }] } },
      pre_state: { energy: 62.1, error_signal: 0.31, proportional_control: 0.15, integral_control: 0.08, total_control_signal: 0.23 },
      post_state: { energy: 60.1, error_signal: 0.42, proportional_control: 0.21, integral_control: 0.10, total_control_signal: 0.31 },
      available_actions: ['eat', 'move_up', 'move_down', 'move_left', 'move_right', 'stay'],
      action_chosen: { name: 'move_up', params: {} },
      outcome: { reward: 0, action_result: {} },
    },
  ]
}

function mockReplayTraces(): Record<number, DecisionTrace[]> {
  const traces: Record<number, DecisionTrace[]> = {}
  traces[8] = [{
    agent_id: 'drive_reduction_rl', step: 8,
    perception: { x: 2, y: 3, grid_width: 8, grid_height: 8, step: 8, resources: { food: [{ x: 5, y: 1 }] } },
    pre_state: { energy: 12.3, drive: 0.95, epsilon: 0.2, q_table: { eat: 3.1, move_right: 4.5, stay: 1.2, move_up: 2.8 } },
    post_state: { energy: 10.3, drive: 0.98, epsilon: 0.19, q_table: { eat: 3.1, move_right: 4.8, stay: 1.2, move_up: 2.8 } },
    available_actions: ['eat', 'move_up', 'move_down', 'move_left', 'move_right', 'stay'],
    action_chosen: { name: 'move_right', params: {} },
    outcome: { reward: 0, action_result: {} },
  }]
  traces[16] = mockDecisionTraces()
  return traces
}

// --- The hook ---

const delay = (ms: number) => new Promise(r => setTimeout(r, ms))

export function useMockWebSocket() {
  const [agents, setAgents] = useState<AgentState[]>(INITIAL_AGENTS)
  const [pipeline, setPipeline] = useState<PipelineStep[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [thinking, setThinking] = useState(false)
  const [simAgents, setSimAgents] = useState<SimAgent[]>([])
  const idRef = useRef(0)
  const runningRef = useRef(false)

  const addMsg = useCallback((msg: Omit<ChatMessage, 'id'>) => {
    setMessages(prev => [...prev, { ...msg, id: String(++idRef.current) }])
  }, [])

  const setAgent = useCallback((name: string, status: AgentState['status'], activeTool?: string) => {
    setAgents(prev => prev.map(a => a.name === name ? { ...a, status, activeTool } : a))
  }, [])

  const send = useCallback(async (text: string) => {
    if (runningRef.current) return
    runningRef.current = true

    // User message
    addMsg({ from: 'user', text })
    setThinking(true)
    setAgent('Orchestrator', 'working')

    await delay(800)

    // 1. Architect
    setAgent('Architect', 'working', 'validate_spec')
    setAgent('Orchestrator', 'working', 'create_environment')
    await delay(1500)
    setAgent('Architect', 'done')
    addMsg({
      from: 'orchestrator',
      text: 'El **Architect** ha diseñado el entorno de simulación: un grid 8×8 con food ×6. Voy a buscar los modelos disponibles.',
      card: {
        title: 'Environment Spec',
        data: {
          Grid: '8 × 8',
          'Acciones posibles': 'move_up, move_down, move_left, move_right, eat, stay',
          Recursos: 'food ×6',
        },
      },
    })
    setPipeline([{ step: 'arch', status: 'done' }])
    await delay(500)

    // 1.5. Predictions
    setAgent('Orchestrator', 'working', 'read_predictions')
    await delay(800)
    addMsg({
      from: 'orchestrator',
      text: 'Según la teoría de **regulación homeostática**, esperamos que:\n- El agente **drive_reduction** coma más agresivamente cuando su energía baje\n- El agente **PI** mantenga niveles más estables pero sea menos eficiente\n- Ambos muestren saciación: dejar de comer tras alcanzar el set point\n\n¿Procedemos con la simulación?',
    })
    await delay(300)

    // 2. Simulation
    setAgent('Orchestrator', 'working', 'run_simulation')
    await delay(2000)
    const replay = mockReplay()
    const ids = replay.frames[0].agents.map(a => a.id)
    setSimAgents(ids.map((id, i) => ({ id, color: AGENT_COLORS[i % AGENT_COLORS.length] })))
    addMsg({
      from: 'orchestrator',
      text: `Simulación completada: **2 agentes** durante **30 pasos**. Se detectaron **${replay.critical_events?.length ?? 0} eventos críticos**. Puedes explorar el replay — se ralentiza automáticamente en los momentos importantes.`,
      replay,
    })
    setPipeline(p => [...p, { step: 'sim', status: 'done' }])
    await delay(500)

    // 3. Tracker
    setAgent('Tracker', 'working', 'list_critical_events')
    setAgent('Orchestrator', 'working', 'observe_simulation')
    await delay(800)
    setAgent('Tracker', 'working', 'get_decision_trace')
    await delay(700)
    setAgent('Tracker', 'working', 'get_event_window')
    await delay(800)
    setAgent('Tracker', 'working', 'get_agent_trajectory')
    await delay(1000)
    setAgent('Tracker', 'done')
    const tracker = mockTracker()
    addMsg({
      from: 'orchestrator',
      text: 'El **Tracker** ha registrado las trayectorias de **2 agentes**.\n\nEpisodios detectados:\n- **drive_reduction_rl**: aprendió a dirigirse a recursos (paso 5)\n- **drive_reduction_rl**: energía crítica en paso 8 (12.3)\n- **drive_reduction_rl**: cambio de estrategia en paso 18\n- **pi_negative_feedback**: competencia por recursos en paso 14',
      tracker,
    })
    setPipeline(p => [...p, { step: 'track', status: 'done' }])
    await delay(500)

    // 4. Analyst
    setAgent('Analyst', 'working', 'list_critical_events')
    setAgent('Orchestrator', 'working', 'analyze_results')
    await delay(500)
    setAgent('Analyst', 'working', 'get_decision_trace')
    await delay(600)
    setAgent('Analyst', 'working', 'compare_decision_traces')
    await delay(700)
    setAgent('Analyst', 'working', 'list_state_keys')
    await delay(400)
    setAgent('Analyst', 'working', 'create_chart')
    await delay(1000)
    setAgent('Analyst', 'working', 'get_event_window')
    await delay(600)
    setAgent('Analyst', 'done')
    const analyst = mockAnalyst()
    const charts = mockCharts()
    addMsg({
      from: 'orchestrator',
      text: 'El **Analyst** ha encontrado **3 patrones**, realizado **3 comparaciones** y generado **3 gráficas** (incluyendo evolución de Q-values por acción).',
      analyst,
      charts,
      traces: mockDecisionTraces(),
    })
    setPipeline(p => [...p, { step: 'anal', status: 'done' }])
    await delay(500)

    // 5. Reporter
    setAgent('Reporter', 'working', 'read_research')
    setAgent('Orchestrator', 'working', 'generate_report')
    await delay(1000)
    setAgent('Reporter', 'working', 'compile_report')
    await delay(1500)
    setAgent('Reporter', 'done')
    addMsg({
      from: 'orchestrator',
      text: 'El **Reporter** ha generado el informe PDF: `output/analisis_homeostatic_regulation.pdf`.',
    })
    setPipeline(p => [...p, { step: 'repo', status: 'done' }])
    await delay(300)

    // 6. Continuation prompt
    setAgent('Orchestrator', 'done')
    setThinking(false)
    addMsg({
      from: 'orchestrator',
      text: '¿Quieres explorar algo más? Algunas opciones:\n- "Muéstrame la evolución de la Q-table"\n- "Analiza qué pasó en los pasos 6-12"\n- "Genera un informe solo del agente PI"\n- "Empezar un nuevo experimento con otro modelo"',
    })

    runningRef.current = false
  }, [addMsg, setAgent])

  return { connected: true, agents, pipeline, messages, thinking, simAgents, send }
}
