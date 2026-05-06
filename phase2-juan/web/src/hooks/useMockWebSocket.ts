/**
 * Mock WebSocket hook — simulates the full pipeline with fake data.
 * Activate by adding ?mock to the URL: http://localhost:5173/?mock
 */
import { useState, useCallback, useRef } from 'react'
import type { AgentState, ChatMessage, SimAgent } from '../types'
import { AGENT_COLORS, INITIAL_AGENTS } from '../constants'
import { mockReplay, mockTracker, mockAnalyst, mockCharts, mockDecisionTraces } from './mockData'

const delay = (ms: number) => new Promise(r => setTimeout(r, ms))

export function useMockWebSocket() {
  const [agents, setAgents] = useState(INITIAL_AGENTS)
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
    addMsg({
      from: 'orchestrator',
      text: 'El **Tracker** ha registrado las trayectorias de **2 agentes**.\n\nEpisodios detectados:\n- **drive_reduction_rl**: aprendió a dirigirse a recursos (paso 5)\n- **drive_reduction_rl**: energía crítica en paso 8 (12.3)\n- **drive_reduction_rl**: cambio de estrategia en paso 18\n- **pi_negative_feedback**: competencia por recursos en paso 14',
      tracker: mockTracker(),
    })
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
    addMsg({
      from: 'orchestrator',
      text: 'El **Analyst** ha encontrado **3 patrones**, realizado **3 comparaciones** y generado **3 gráficas** (incluyendo evolución de Q-values por acción).',
      analyst: mockAnalyst(),
      charts: mockCharts(),
      traces: mockDecisionTraces(),
    })
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
    await delay(300)

    // 6. Done
    setAgent('Orchestrator', 'done')
    setThinking(false)
    addMsg({
      from: 'orchestrator',
      text: '¿Quieres explorar algo más? Algunas opciones:\n- "Muéstrame la evolución de la Q-table"\n- "Analiza qué pasó en los pasos 6-12"\n- "Genera un informe solo del agente PI"\n- "Empezar un nuevo experimento con otro modelo"',
    })

    runningRef.current = false
  }, [addMsg, setAgent])

  return { connected: true, agents, messages, thinking, simAgents, send }
}
