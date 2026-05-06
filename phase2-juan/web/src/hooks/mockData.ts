/**
 * Static mock data generators for useMockWebSocket.
 * Separated to keep the hook itself readable.
 */
import type { ReplayData, TrackerData, AnalystData, ChartSpec, CriticalEvent, DecisionTrace } from '../types'

// --- Energy formulas (shared between charts and replay traces) ---

function energyA(step: number): number {
  return Math.max(0, 80 - step * 3 + Math.sin(step * 0.5) * 20 + (step === 8 ? -40 : 0) + (step === 9 ? 45 : 0))
}

function energyB(step: number): number {
  return 70 + Math.sin(step * 0.3) * 8
}

// --- Generators ---

export function mockCriticalEvents(): CriticalEvent[] {
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

export function mockReplay(): ReplayData {
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

  return { grid_width: W, grid_height: H, total_steps: STEPS, frames, critical_events: mockCriticalEvents(), traces: mockReplayTraces(STEPS) }
}

export function mockTracker(): TrackerData {
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

export function mockAnalyst(): AnalystData {
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

export function mockCharts(): ChartSpec[] {
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
          data: Array.from({ length: 28 }, (_, i) => ({ x: i, y: energyA(i) })),
        },
        {
          name: 'pi_negative_feedback', color: '#fbbf24',
          data: Array.from({ length: 30 }, (_, i) => ({ x: i, y: energyB(i) })),
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

export function mockDecisionTraces(): DecisionTrace[] {
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

function mockReplayTraces(steps: number): Record<number, DecisionTrace[]> {
  const actions = ['eat', 'move_up', 'move_down', 'move_left', 'move_right', 'stay']
  const traces: Record<number, DecisionTrace[]> = {}

  for (let step = 0; step < steps; step++) {
    const eA = energyA(step)
    const eB = energyB(step)
    const driveA = Math.min(1, Math.max(0, 1 - eA / 100))
    const qEat = 0.5 + step * 0.4 + Math.sin(step * 0.3) * 0.5
    const qMove = 0.3 + step * 0.15 + Math.cos(step * 0.4) * 0.3
    const qStay = 0.1 + step * 0.05
    const chosenA = qEat > qMove ? 'eat' : 'move_right'

    traces[step] = [
      {
        agent_id: 'drive_reduction_rl', step,
        perception: { x: Math.floor(Math.random() * 8), y: Math.floor(Math.random() * 8), grid_width: 8, grid_height: 8, step, resources: { food: [{ x: 3, y: 2 }] } },
        pre_state: { energy: +eA.toFixed(1), drive: +driveA.toFixed(2), epsilon: +(0.25 - step * 0.005).toFixed(3), q_table: { eat: +qEat.toFixed(1), move_right: +qMove.toFixed(1), stay: +qStay.toFixed(1), move_up: +(qMove * 0.8).toFixed(1) } },
        post_state: { energy: +(eA + (chosenA === 'eat' ? 15 : -2)).toFixed(1), drive: +Math.min(1, Math.max(0, driveA + (chosenA === 'eat' ? -0.3 : 0.02))).toFixed(2), epsilon: +(0.25 - step * 0.005 - 0.001).toFixed(3), q_table: { eat: +(qEat + 0.1).toFixed(1), move_right: +qMove.toFixed(1), stay: +qStay.toFixed(1), move_up: +(qMove * 0.8).toFixed(1) } },
        available_actions: actions,
        action_chosen: { name: chosenA, params: {} },
        outcome: { reward: chosenA === 'eat' ? 15 : 0, action_result: chosenA === 'eat' ? { consumed: true, resource_type: 'food' } : {} },
      },
      {
        agent_id: 'pi_negative_feedback', step,
        perception: { x: Math.floor(Math.random() * 8), y: Math.floor(Math.random() * 8), grid_width: 8, grid_height: 8, step, resources: { food: [{ x: 5, y: 1 }] } },
        pre_state: { energy: +eB.toFixed(1), error_signal: +(0.3 + Math.sin(step * 0.2) * 0.15).toFixed(2), proportional_control: 0.15, integral_control: 0.08, total_control_signal: 0.23 },
        post_state: { energy: +(eB - 2).toFixed(1), error_signal: +(0.3 + Math.sin(step * 0.2) * 0.15 + 0.05).toFixed(2), proportional_control: 0.18, integral_control: 0.09, total_control_signal: 0.27 },
        available_actions: actions,
        action_chosen: { name: actions[1 + Math.floor(Math.random() * 4)], params: {} },
        outcome: { reward: 0, action_result: {} },
      },
    ]
  }

  // Override step 16 with the specific mock data for chat traces
  traces[16] = mockDecisionTraces()
  return traces
}
