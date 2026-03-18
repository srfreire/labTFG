/**
 * Mock WebSocket hook — simulates the full pipeline with fake data.
 * Activate by adding ?mock to the URL: http://localhost:5173/?mock
 */
import { useState, useCallback, useRef } from 'react'
import type { AgentState, PipelineStep, ChatMessage, ReplayData, TrackerData, AnalystData } from '../types'

const INITIAL_AGENTS: AgentState[] = [
  { name: 'Orchestrator', status: 'idle', color: '#94a3b8' },
  { name: 'Architect', status: 'idle', color: '#4ade80' },
  { name: 'Tracker', status: 'idle', color: '#fbbf24' },
  { name: 'Analyst', status: 'idle', color: '#a78bfa' },
  { name: 'Reporter', status: 'idle', color: '#f472b6' },
]

// --- Mock data generators ---

function mockReplay(): ReplayData {
  const W = 8, H = 8, STEPS = 30
  const frames = []
  let ax = 1, ay = 1, bx = 6, by = 6

  const resources = [
    { type: 'food', x: 3, y: 2 }, { type: 'food', x: 5, y: 1 },
    { type: 'food', x: 2, y: 5 }, { type: 'food', x: 6, y: 3 },
    { type: 'food', x: 4, y: 6 }, { type: 'food', x: 1, y: 4 },
    { type: 'water', x: 7, y: 0 }, { type: 'water', x: 0, y: 7 },
  ]

  for (let step = 0; step < STEPS; step++) {
    const dirs = [[-1,0],[1,0],[0,-1],[0,1],[0,0]]
    const [dax, day] = dirs[Math.floor(Math.random() * 4)]
    ax = Math.max(0, Math.min(W - 1, ax + dax))
    ay = Math.max(0, Math.min(H - 1, ay + day))
    const [dbx, dby] = dirs[Math.floor(Math.random() * 5)]
    bx = Math.max(0, Math.min(W - 1, bx + dbx))
    by = Math.max(0, Math.min(H - 1, by + dby))

    const actions = [
      { agent_id: 'QLearning', action: dax === 0 && day === 0 ? 'stay' : 'move', reward: Math.random() > 0.7 ? 1 : 0 },
      { agent_id: 'RandomWalker', action: dbx === 0 && dby === 0 ? 'stay' : 'move', reward: Math.random() > 0.85 ? 1 : 0 },
    ]

    frames.push({
      step,
      agents: [
        { id: 'QLearning', x: ax, y: ay, alive: step < 28 },
        { id: 'RandomWalker', x: bx, y: by, alive: true },
      ],
      resources: resources.filter(() => Math.random() > 0.15),
      actions,
    })
  }

  return { grid_width: W, grid_height: H, total_steps: STEPS, frames }
}

function mockTracker(): TrackerData {
  return {
    summary: 'Resumen de la simulación con 2 agentes durante 30 pasos.',
    trajectories: {
      QLearning: {
        steps_survived: 28,
        resources_consumed: 7,
        actions: { move: 20, eat: 7, stay: 1 },
      },
      RandomWalker: {
        steps_survived: 30,
        resources_consumed: 3,
        actions: { move: 27, eat: 3 },
      },
    },
    episodes: [
      { agent: 'QLearning', type: 'learning', step: 5, description: 'El agente comenzó a dirigirse hacia recursos' },
      { agent: 'QLearning', type: 'stuck', steps: [18, 19, 20, 21, 22], description: 'El agente se quedó inmóvil durante 5 pasos consecutivos' },
      { agent: 'RandomWalker', type: 'competition', step: 12, description: 'Ambos agentes compitieron por el mismo recurso' },
    ],
  }
}

function mockAnalyst(): AnalystData {
  return {
    patterns: [
      {
        id: 'P1', type: 'estrategia', agents: ['QLearning'],
        description: 'QLearning aprendió a moverse hacia los recursos tras los primeros 5 pasos, formando un patrón de búsqueda dirigida',
        evidence: 'Entre los pasos 1-5 el movimiento era aleatorio (tasa de acierto 12%), pero a partir del paso 6 subió al 45%',
      },
      {
        id: 'P2', type: 'recursos', agents: ['QLearning', 'RandomWalker'],
        description: 'Ambos agentes compitieron por el mismo recurso en el paso 12, pero solo RandomWalker logró recogerlo por estar más cerca',
        evidence: 'En el paso 12, QLearning estaba a 3 celdas del recurso en (3,5), RandomWalker a 1 celda',
      },
      {
        id: 'P3', type: 'anomaly', agents: ['QLearning'],
        description: 'QLearning dejó de moverse entre los pasos 18-22, sugiriendo que su modelo entró en un ciclo sin exploración',
        evidence: '5 acciones consecutivas de tipo "stay" entre los pasos 18 y 22',
      },
    ],
    comparisons: [
      {
        agents: ['QLearning', 'RandomWalker'],
        metric: 'Recursos recogidos',
        values: { QLearning: 7, RandomWalker: 3 },
        insight: 'QLearning recogió más del doble de recursos porque aprendió a dirigirse hacia ellos en vez de moverse al azar',
      },
      {
        agents: ['QLearning', 'RandomWalker'],
        metric: 'Pasos sobrevividos',
        values: { QLearning: 28, RandomWalker: 30 },
        insight: 'RandomWalker sobrevivió toda la simulación gracias a que encontró comida de forma uniforme, mientras que QLearning se quedó atascado al final',
      },
      {
        agents: ['QLearning', 'RandomWalker'],
        metric: 'Tasa de movimiento',
        values: { QLearning: 0.73, RandomWalker: 0.97 },
        insight: 'RandomWalker se movió casi en cada paso, mientras que QLearning pasó un 27% del tiempo quieto esperando',
      },
    ],
    metrics: {
      QLearning: {
        'pasos vivo': 28,
        'recursos comidos': 7,
        'tasa supervivencia': 0.93,
        'acciones totales': 28,
      },
      RandomWalker: {
        'pasos vivo': 30,
        'recursos comidos': 3,
        'tasa supervivencia': 1.0,
        'acciones totales': 30,
      },
    },
  }
}

// --- The hook ---

const delay = (ms: number) => new Promise(r => setTimeout(r, ms))

export function useMockWebSocket() {
  const [agents, setAgents] = useState<AgentState[]>(INITIAL_AGENTS)
  const [pipeline, setPipeline] = useState<PipelineStep[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [thinking, setThinking] = useState(false)
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
      text: 'El **Architect** ha diseñado el entorno de simulación: un grid 8×8 con food ×6, water ×2. Ahora voy a buscar los modelos disponibles y lanzar la simulación.',
      card: {
        title: 'Environment Spec',
        data: {
          Grid: '8 × 8',
          'Acciones posibles': 'move_up, move_down, move_left, move_right, eat',
          Recursos: 'food ×6, water ×2',
          Pasos: '30',
        },
      },
    })
    setPipeline([{ step: 'arch', status: 'done' }])
    await delay(500)

    // 2. Simulation
    setAgent('Orchestrator', 'working', 'run_simulation')
    await delay(2000)
    const replay = mockReplay()
    addMsg({
      from: 'orchestrator',
      text: 'Simulación completada: **2 agentes** durante **30 pasos**. Puedes explorar el replay paso a paso. Ahora el Tracker va a observar qué pasó.',
      replay,
    })
    setPipeline(p => [...p, { step: 'sim', status: 'done' }])
    await delay(500)

    // 3. Tracker
    setAgent('Tracker', 'working', 'get_simulation_events')
    setAgent('Orchestrator', 'working', 'observe_simulation')
    await delay(1000)
    setAgent('Tracker', 'working', 'get_agent_trajectory')
    await delay(1200)
    setAgent('Tracker', 'done')
    const tracker = mockTracker()
    addMsg({
      from: 'orchestrator',
      text: 'El **Tracker** ha registrado las trayectorias de **2 agentes**.\n\nEpisodios detectados:\n- **QLearning**: comenzó a dirigirse hacia recursos a partir del paso 5\n- **QLearning**: se quedó inmóvil durante 5 pasos consecutivos (pasos 18-22)\n- **RandomWalker**: compitió con QLearning por un recurso en el paso 12\n\nAhora el Analyst va a buscar patrones.',
      tracker,
    })
    setPipeline(p => [...p, { step: 'track', status: 'done' }])
    await delay(500)

    // 4. Analyst
    setAgent('Analyst', 'working', 'get_simulation_events')
    setAgent('Orchestrator', 'working', 'analyze_results')
    await delay(800)
    setAgent('Analyst', 'working', 'get_agent_trajectory')
    await delay(1000)
    setAgent('Analyst', 'working', 'get_agent_state')
    await delay(800)
    setAgent('Analyst', 'done')
    const analyst = mockAnalyst()
    addMsg({
      from: 'orchestrator',
      text: 'El **Analyst** ha encontrado **3 patrones** y realizado **3 comparaciones** entre los agentes. Ahora el Reporter va a generar el informe PDF.',
      analyst,
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
      text: 'El **Reporter** ha generado el informe PDF en `output/report.pdf`.',
    })
    setPipeline(p => [...p, { step: 'repo', status: 'done' }])
    await delay(300)

    // 6. Final summary
    setAgent('Orchestrator', 'done')
    setThinking(false)
    addMsg({
      from: 'orchestrator',
      text: 'Pipeline completo. **QLearning** fue más eficiente recogiendo recursos (7 vs 3), pero su tendencia a quedarse quieto le costó 2 pasos de vida. **RandomWalker** sobrevivió toda la simulación gracias a su movimiento constante, aunque fue menos eficiente.\n\nEl informe PDF con todos los detalles está en `output/report.pdf`. ¿Quieres hacer otra simulación con parámetros diferentes?',
    })

    runningRef.current = false
  }, [addMsg, setAgent])

  return { connected: true, agents, pipeline, messages, thinking, send }
}
