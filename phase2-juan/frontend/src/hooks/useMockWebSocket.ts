import { useState, useCallback, useRef } from 'react'
import type { AgentState, ChatMessage, SimAgent } from '../types'
import { AGENT_COLORS, INITIAL_AGENTS } from '../constants'
import { mockReplay, mockTracker, mockAnalyst, mockCharts, mockDecisionTraces } from './mockData'

const delay = (ms: number) => new Promise(r => setTimeout(r, ms))
const STEPS = ['architect', 'models', 'simulation', 'tracker', 'analyst', 'reporter', 'followup'] as const
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
      text: 'El **Architect** ha diseñado el entorno de simulación: un grid 10×10 con food ×8 regenerable.',
      card: {
        title: 'Environment Spec',
        data: {
          Grid: '10 × 10',
          'Acciones posibles': 'move_up, move_down, move_left, move_right, eat, stay',
          Recursos: 'food ×8 (regenera)',
        },
      },
    })

    setAgent('Orchestrator', 'working', 'list_available_models')
    await delay(900)
    addMsg({
      from: 'orchestrator',
      text: 'He encontrado **3 modelos de Fase 1** compatibles con la **regulación homeostática**. ¿Cuáles quieres ejecutar en este entorno? Puedo correr varios a la vez y comparar sus trayectorias.',
      card: {
        title: 'Modelos de Fase 1 disponibles',
        data: {
          'homeostatic-regulation/continuous-drive-dynamics': 'Drive-dynamics ODE · umbral de urgencia',
          'homeostatic-reinforcement-learning/drive-reduction-td-q': 'HRL drive-reduction · Q-learning TD',
          'interoceptive-active-inference/expected-free-energy': 'Inferencia activa · energía libre esperada + alostasis',
        },
      },
      suggestions: ['Compara los tres modelos', 'Ejecuta solo el modelo drive-dynamics'],
    })
    setAgent('Orchestrator', 'done')
  }, [addMsg, setAgent])

  const runModels = useCallback(async () => {
    setAgent('Orchestrator', 'working', 'read_predictions')
    await delay(1100)
    addMsg({
      from: 'orchestrator',
      text: 'Perfecto — ejecutaré los **tres modelos** en el mismo entorno para compararlos.\n\nSegún la teoría de **regulación homeostática**, espero que:\n- El modelo **drive-dynamics** conserve energía en reposo hasta que el drive cruce su umbral de urgencia, y entonces busque comida\n- El **HRL (TD-Q)** explore más y aprenda las asociaciones estado-recompensa poco a poco\n- La **inferencia activa** mantenga la homeostasis vía priors alostáticos… aunque es el mecanismo más frágil si su política no se reorienta a tiempo\n\n¿Lanzo la simulación?',
      suggestions: ['Lanza la simulación'],
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
      text: `Simulación completada: **3 agentes** durante **60 pasos**. Se detectaron **${replay.critical_events?.length ?? 0} eventos críticos** — incluida la **muerte por inanición** del modelo de inferencia activa en el paso 18. Puedes explorar el replay; se ralentiza automáticamente en los momentos importantes.\n\nTe recomiendo que el **Tracker** registre las trayectorias antes de analizar.`,
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
      text: 'El **Tracker** ha registrado las trayectorias de **3 agentes** (99 eventos, tripleta joinable consistente).\n\nEpisodios detectados:\n- **drive-dynamics**: reposo estratégico y primer consumo tras cruzar el umbral (paso 11)\n- **active-inference**: consumo en el paso 6, y **colapso post-recuperación → muerte en el paso 18**\n- **HRL (TD-Q)**: exploración activa, primer consumo en el paso 24\n- **HRL (TD-Q)**: pérdida de confianza en la decisión en el paso 46\n\n¿Paso el **Analyst** sobre estos datos?',
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
      text: 'El **Analyst** ha encontrado **5 patrones**, realizado **3 comparaciones** y generado **3 gráficas** (energía, distribución de acciones y acumulación de drive).\n\nLo más llamativo: el modelo de **drive-dynamics** ganó en eficiencia (4 recursos, 73% de reposo) y la **inferencia activa** murió pese a haber comido, porque sus Q-values uniformemente altos no diferenciaron las acciones.\n\nAntes de redactar, dime el **alcance del informe**: ¿uno completo comparativo, o enfocado en el modelo que murió? ¿calidad estándar o detallada?',
      analyst: mockAnalyst(),
      charts: mockCharts(),
      traces: mockDecisionTraces(),
      suggestions: ['Informe completo, calidad estándar', 'Enfócalo en la inferencia activa que murió'],
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
      text: 'El **Reporter** ha compilado el informe PDF (LaTeX real, no fallback): `experiments/caso2/informe_final.pdf`. Incluye el entorno, los 3 modelos, los patrones y las gráficas — y documenta con fidelidad la muerte por inanición del modelo de inferencia activa.',
      reports: [{
        key: 'experiments/caso2/informe_final.pdf',
        filename: 'informe_final.pdf',
      }],
    })
    await delay(300)
    addMsg({
      from: 'orchestrator',
      text: '¿Quieres explorar algo más? Algunas opciones:',
      suggestions: [
        'Muéstrame la evolución del drive del modelo drive-dynamics',
        'Analiza qué pasó en los pasos 6-18 con la inferencia activa',
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
      text: `He revisado de nuevo los datos registrados para responder a *"${text}"*. En el modelo **drive-dynamics**, el drive se acumula en reposo y se reinicia a 0 justo tras cada consumo (pasos 11, 23, 40 y 56), lo que confirma el acoplamiento urgencia→acción esperado por la teoría homeostática.`,
      suggestions: ['Genera un informe solo del modelo que murió', 'Empezar un nuevo experimento'],
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
      case 'models': await runModels(); break
      case 'simulation': await runSimulation(); break
      case 'tracker': await runTracker(); break
      case 'analyst': await runAnalyst(); break
      case 'reporter': await runReporter(); break
      case 'followup': await runFollowup(text); break
    }
    if (stepRef.current < STEPS.length - 1) stepRef.current += 1

    setThinking(false)
    runningRef.current = false
  }, [addMsg, runArchitect, runModels, runSimulation, runTracker, runAnalyst, runReporter, runFollowup])

  return { connected: true, agents, messages, thinking, simAgents, envCard: null, send }
}
