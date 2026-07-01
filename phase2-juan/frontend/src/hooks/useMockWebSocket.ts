import { useState, useCallback, useRef } from 'react'
import type { AgentState, ChatMessage, SimAgent } from '../types'
import { AGENT_COLORS, INITIAL_AGENTS } from '../constants'
import { mockReplay, mockTracker, mockAnalyst, mockCharts, mockDecisionTraces } from './mockData'

const delay = (ms: number) => new Promise(r => setTimeout(r, ms))
const STEPS = ['architect', 'simulation', 'tracker', 'analyst', 'reporter', 'followup'] as const
type Step = (typeof STEPS)[number]
const RESTART_HINTS = ['nuevo', 'otra', 'otro', 'empez', 'reinicia', 'de cero', 'desde el principio']

export function useMockWebSocket() {
  const [agents, setAgents] = useState(INITIAL_AGENTS)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [thinking, setThinking] = useState(false)
  const [simAgents, setSimAgents] = useState<SimAgent[]>([])
  const idRef = useRef(0)
  const runningRef = useRef(false)
  const stepRef = useRef(0)

  const addMsg = useCallback((msg: Omit<ChatMessage, 'id'>) => {
    setMessages(prev => [...prev, { ...msg, id: String(++idRef.current) }])
  }, [])

  const setAgent = useCallback((name: string, status: AgentState['status'], activeTool?: string) => {
    setAgents(prev => prev.map(a => a.name === name ? { ...a, status, activeTool } : a))
  }, [])

  const runArchitect = useCallback(async () => {
    setAgent('Orchestrator', 'working')
    await delay(700)
    setAgent('Architect', 'working', 'validate_spec')
    setAgent('Orchestrator', 'working', 'create_environment')
    await delay(1400)
    setAgent('Architect', 'done')
    addMsg({
      from: 'orchestrator',
      text: 'El **Architect** ha diseñado el entorno de simulación: un grid 8×8 con food ×6.',
      card: {
        title: 'Environment Spec',
        data: {
          Grid: '8 × 8',
          'Acciones posibles': 'move_up, move_down, move_left, move_right, eat, stay',
          Recursos: 'food ×6',
        },
      },
    })

    setAgent('Orchestrator', 'working', 'read_predictions')
    await delay(900)
    addMsg({
      from: 'orchestrator',
      text: 'Según la teoría de **regulación homeostática**, esperamos que:\n- El agente **drive_reduction** coma más agresivamente cuando su energía baje\n- El agente **PI** mantenga niveles más estables pero sea menos eficiente\n- Ambos muestren saciación: dejar de comer tras alcanzar el set point\n\n¿Procedemos con la simulación?',
      suggestions: ['Lanza la simulación', 'Compara los dos modelos'],
    })
    setAgent('Orchestrator', 'done')
  }, [addMsg, setAgent])

  const runSimulation = useCallback(async () => {
    setAgent('Orchestrator', 'working', 'run_simulation')
    await delay(2000)
    const replay = mockReplay()
    const ids = replay.frames[0].agents.map(a => a.id)
    setSimAgents(ids.map((id, i) => ({ id, color: AGENT_COLORS[i % AGENT_COLORS.length] })))
    addMsg({
      from: 'orchestrator',
      text: `Simulación completada: **2 agentes** durante **30 pasos**. Se detectaron **${replay.critical_events?.length ?? 0} eventos críticos**. Puedes explorar el replay — se ralentiza automáticamente en los momentos importantes.\n\nTe recomiendo que el **Tracker** registre las trayectorias antes de analizar.`,
      replay,
      suggestions: ['Registra las trayectorias con el Tracker'],
    })
    setAgent('Orchestrator', 'done')
  }, [addMsg, setAgent])

  const runTracker = useCallback(async () => {
    setAgent('Tracker', 'working', 'list_critical_events')
    setAgent('Orchestrator', 'working', 'observe_simulation')
    await delay(800)
    setAgent('Tracker', 'working', 'get_decision_trace')
    await delay(700)
    setAgent('Tracker', 'working', 'get_event_window')
    await delay(700)
    setAgent('Tracker', 'working', 'get_agent_trajectory')
    await delay(900)
    setAgent('Tracker', 'done')
    addMsg({
      from: 'orchestrator',
      text: 'El **Tracker** ha registrado las trayectorias de **2 agentes**.\n\nEpisodios detectados:\n- **drive_reduction_rl**: aprendió a dirigirse a recursos (paso 5)\n- **drive_reduction_rl**: energía crítica en paso 8 (12.3)\n- **drive_reduction_rl**: cambio de estrategia en paso 18\n- **pi_negative_feedback**: competencia por recursos en paso 14\n\n¿Paso el **Analyst** sobre estos datos?',
      tracker: mockTracker(),
      suggestions: ['Analiza los resultados'],
    })
    setAgent('Orchestrator', 'done')
  }, [addMsg, setAgent])

  const runAnalyst = useCallback(async () => {
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
    addMsg({
      from: 'orchestrator',
      text: 'El **Analyst** ha encontrado **3 patrones**, realizado **3 comparaciones** y generado **3 gráficas** (incluyendo evolución de Q-values por acción).\n\nCon esto ya puedo redactar el informe final.',
      analyst: mockAnalyst(),
      charts: mockCharts(),
      traces: mockDecisionTraces(),
      suggestions: ['Genera el informe PDF'],
    })
    setAgent('Orchestrator', 'done')
  }, [addMsg, setAgent])

  const runReporter = useCallback(async () => {
    setAgent('Reporter', 'working', 'read_research')
    setAgent('Orchestrator', 'working', 'generate_report')
    await delay(1000)
    setAgent('Reporter', 'working', 'compile_report')
    await delay(1500)
    setAgent('Reporter', 'done')
    addMsg({
      from: 'orchestrator',
      text: 'El **Reporter** ha generado el informe PDF: `experiments/mock/analisis_homeostatic_regulation.pdf`.',
      reports: [{
        key: 'experiments/mock/analisis_homeostatic_regulation.pdf',
        filename: 'analisis_homeostatic_regulation.pdf',
      }],
    })
    await delay(300)
    addMsg({
      from: 'orchestrator',
      text: '¿Quieres explorar algo más? Algunas opciones:',
      suggestions: [
        'Muéstrame la evolución de la Q-table',
        'Analiza qué pasó en los pasos 6-12',
        'Empezar un nuevo experimento',
      ],
    })
    setAgent('Orchestrator', 'done')
  }, [addMsg, setAgent])

  const runFollowup = useCallback(async (text: string) => {
    setAgent('Orchestrator', 'working', 'analyze_results')
    await delay(1200)
    addMsg({
      from: 'orchestrator',
      text: `He revisado de nuevo los datos registrados para responder a *"${text}"*. Los **Q-values** de \`eat\` dominan en cuanto la energía baja del set point, lo que confirma la saciación esperada.`,
      suggestions: ['Genera un informe solo del agente PI', 'Empezar un nuevo experimento'],
    })
    setAgent('Orchestrator', 'done')
  }, [addMsg, setAgent])

  const send = useCallback(async (text: string) => {
    if (runningRef.current) return
    runningRef.current = true

    addMsg({ from: 'user', text })

    const wantsRestart = RESTART_HINTS.some(h => text.toLowerCase().includes(h))
    if (wantsRestart && stepRef.current >= STEPS.indexOf('reporter')) {
      setAgents(INITIAL_AGENTS)
      setSimAgents([])
      stepRef.current = 0
    }

    const step: Step = STEPS[Math.min(stepRef.current, STEPS.length - 1)]
    setThinking(true)

    switch (step) {
      case 'architect': await runArchitect(); break
      case 'simulation': await runSimulation(); break
      case 'tracker': await runTracker(); break
      case 'analyst': await runAnalyst(); break
      case 'reporter': await runReporter(); break
      case 'followup': await runFollowup(text); break
    }
    if (stepRef.current < STEPS.length - 1) stepRef.current += 1

    setThinking(false)
    runningRef.current = false
  }, [addMsg, runArchitect, runSimulation, runTracker, runAnalyst, runReporter, runFollowup])

  return { connected: true, agents, messages, thinking, simAgents, envCard: null, send }
}
