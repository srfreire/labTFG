import type { ReplayData, TrackerData, AnalystData, ChartSpec, CriticalEvent, DecisionTrace } from '../types'

/*
 * Datos del modo mock reconstruidos a partir de una RUN REAL del laboratorio:
 * benchmark/reports/2026-06-30-caso2-lab (paradigma "regulación homeostática",
 * seed 42, grid 10×10, food×8, 60 pasos). De los 4 modelos de esa run se curan
 * los 3 más ilustrativos; los números, episodios, patrones y comparaciones son
 * los que produjeron el Tracker y el Analyst reales.
 */

const DRIVE = 'continuous_drive_dynamics'
const HRL = 'drive_reduction_td_q'
const AI = 'active_inference_efe'

const EAT_DRIVE = [11, 23, 40, 56] // consumos reales del modelo drive-dynamics
const EAT_HRL = [24, 45] // consumos reales del modelo HRL TD-Q
const AI_DEATH_STEP = 18 // el modelo de inferencia activa muere por inanición

/* Energía normalizada [0,1] — anclada a los valores reales de la run. */
function energyDrive(step: number): number {
  let e = 0.72 + Math.sin(step * 0.25) * 0.05 - step * 0.001
  for (const s of EAT_DRIVE) if (step >= s) e += 0.04 * Math.exp(-(step - s) / 6)
  return Math.max(0.55, Math.min(0.85, e))
}
function energyHRL(step: number): number {
  let e = 0.7 - step * 0.004
  for (const s of EAT_HRL) if (step >= s) e += 0.12 * Math.exp(-(step - s) / 8)
  return Math.max(0.3, Math.min(0.8, e))
}
/* Inferencia activa: crisis desde el inicio (0.45→0.26), come en el paso 6
 * (→0.56) y colapsa linealmente hasta 0.0 en el paso 18. null = ya muerto. */
function energyAI(step: number): number | null {
  if (step > AI_DEATH_STEP) return null
  if (step <= 5) return +(0.45 - step * 0.038).toFixed(3)
  if (step === 6) return 0.56
  return +Math.max(0, 0.51 - (step - 7) * (0.51 / 11)).toFixed(3)
}

/* Acumulación de drive del modelo drive-dynamics: crece y se reinicia al comer. */
function driveSignal(step: number): number {
  let last = 0
  for (const s of EAT_DRIVE) if (s <= step) last = s
  return +((step - last) * 0.0018).toFixed(4)
}

export function mockCriticalEvents(): CriticalEvent[] {
  return [
    { step: 5, agent_id: AI, type: 'starvation', severity: 0.99, description: 'active_inference_efe energía crítica: 0.26 (bajo el umbral 0.5)' },
    { step: 6, agent_id: AI, type: 'consumption', severity: 0.5, description: 'active_inference_efe consumió food — energía se recuperó 0.26→0.56' },
    { step: 11, agent_id: DRIVE, type: 'consumption', severity: 0.4, description: 'continuous_drive_dynamics consumió food tras cruzar el umbral de urgencia (drive=0.0196)' },
    { step: 18, agent_id: AI, type: 'death', severity: 1.0, description: 'active_inference_efe murió por agotamiento de energía (0.0) en el paso 18' },
    { step: 23, agent_id: DRIVE, type: 'consumption', severity: 0.4, description: 'continuous_drive_dynamics consumió food (búsqueda local eficiente)' },
    { step: 24, agent_id: HRL, type: 'consumption', severity: 0.5, description: 'drive_reduction_td_q primer consumo tras 24 pasos de exploración' },
    { step: 40, agent_id: DRIVE, type: 'consumption', severity: 0.4, description: 'continuous_drive_dynamics consumió food (3.º)' },
    { step: 45, agent_id: HRL, type: 'consumption', severity: 0.5, description: 'drive_reduction_td_q segundo consumo' },
    { step: 46, agent_id: HRL, type: 'decision_confidence_drop', severity: 0.7, description: 'drive_reduction_td_q perdió confianza: el margen entre los dos mejores Q-values cayó bajo el umbral' },
    { step: 56, agent_id: DRIVE, type: 'consumption', severity: 0.4, description: 'continuous_drive_dynamics consumió food (4.º) — supervivencia completa con 73% de reposo' },
  ]
}

export function mockReplay(): ReplayData {
  const W = 10, H = 10, STEPS = 60
  const frames = []
  const pos: Record<string, { x: number; y: number }> = {
    [DRIVE]: { x: 5, y: 5 }, [HRL]: { x: 2, y: 2 }, [AI]: { x: 7, y: 3 },
  }

  const resources = [
    { type: 'food', x: 3, y: 2 }, { type: 'food', x: 5, y: 1 }, { type: 'food', x: 8, y: 4 },
    { type: 'food', x: 2, y: 6 }, { type: 'food', x: 6, y: 7 }, { type: 'food', x: 4, y: 3 },
    { type: 'food', x: 9, y: 8 }, { type: 'food', x: 1, y: 9 },
  ]
  const dirs: [number, number][] = [[-1, 0], [1, 0], [0, -1], [0, 1], [0, 0]]
  // drive-dynamics reposa el 73% del tiempo; los demás exploran
  const stayBias: Record<string, number> = { [DRIVE]: 0.73, [HRL]: 0.2, [AI]: 0.15 }

  for (let step = 0; step < STEPS; step++) {
    const aiAlive = step <= AI_DEATH_STEP
    for (const id of [DRIVE, HRL, AI]) {
      if (id === AI && !aiAlive) continue
      const staying = Math.random() < stayBias[id]
      const [dx, dy] = staying ? [0, 0] : dirs[Math.floor(Math.random() * 4)]
      pos[id].x = Math.max(0, Math.min(W - 1, pos[id].x + dx))
      pos[id].y = Math.max(0, Math.min(H - 1, pos[id].y + dy))
    }
    const ate = (id: string) =>
      (id === DRIVE && EAT_DRIVE.includes(step)) ||
      (id === HRL && EAT_HRL.includes(step)) ||
      (id === AI && step === 6)

    frames.push({
      step,
      agents: [
        { id: DRIVE, x: pos[DRIVE].x, y: pos[DRIVE].y, alive: true },
        { id: HRL, x: pos[HRL].x, y: pos[HRL].y, alive: true },
        { id: AI, x: pos[AI].x, y: pos[AI].y, alive: aiAlive },
      ],
      resources: resources.filter(() => Math.random() > 0.1),
      actions: [DRIVE, HRL, AI].map(id => ({
        agent_id: id,
        action: ate(id) ? 'eat' : 'move',
        reward: ate(id) ? 1 : 0,
      })),
    })
  }

  return { grid_width: W, grid_height: H, total_steps: STEPS, frames, critical_events: mockCriticalEvents(), traces: mockReplayTraces(STEPS) }
}

export function mockTracker(): TrackerData {
  return {
    summary: 'Simulación de 60 pasos con 3 agentes de distintas arquitecturas cognitivas homeostáticas: 2 sobrevivieron completos y el modelo de inferencia activa murió por agotamiento de energía en el paso 18.',
    trajectories: {
      [DRIVE]: {
        steps_survived: 60,
        resources_consumed: 4,
        actions: { stay: 44, move_down: 7, eat: 4, move_right: 2, move_up: 1, move_left: 2 },
      },
      [HRL]: {
        steps_survived: 60,
        resources_consumed: 2,
        actions: { move_up: 14, move_down: 13, move_right: 12, stay: 12, move_left: 7, eat: 2 },
      },
      [AI]: {
        steps_survived: 19,
        resources_consumed: 1,
        actions: { move_down: 5, move_right: 5, move_up: 4, stay: 3, eat: 1, move_left: 1 },
      },
    },
    episodes: [
      { agent: DRIVE, type: 'exploitation', steps: [0, 11], description: 'Estrategia conservadora inicial: permaneció en reposo (modo REST) durante 7 pasos con energía estable (0.68-0.66), hasta que su drive aumentó lo suficiente para activar búsqueda activa y consumir en el paso 11, demostrando un umbral de urgencia eficaz.' },
      { agent: DRIVE, type: 'foraging_success', step: 23, description: 'Explotación pasiva post-consumo: permaneció mayormente en stay hasta el paso 22; un movimiento estratégico (move_right) le permitió consumir de nuevo en el paso 23, mostrando búsqueda local eficiente.' },
      { agent: AI, type: 'foraging_success', step: 6, description: 'Consumo exitoso en el paso 6 en la posición (4,3): la energía se recuperó de 0.26 a 0.56, pero el prior alostático mu_p=0.656 no logró reorientar su política hacia conservación sostenible.' },
      { agent: AI, type: 'starvation', steps: [7, 18], description: 'Colapso post-recuperación: pese al consumo del paso 6, siguió explorando de forma errática (11 movimientos en 12 pasos) sin localizar recursos. La energía declinó linealmente de 0.51 a 0.0, muriendo por agotamiento en el paso 18. Fallo crítico en el balance exploración-explotación.' },
      { agent: HRL, type: 'exploration', steps: [0, 24], description: 'Exploración inicial activa con distribución balanceada de acciones. El patrón de movimiento diversificado le permitió descubrir y consumir el primer recurso en el paso 24, tras cambiar de stay a move_up en el paso 23.' },
      { agent: HRL, type: 'state_change', step: 46, description: 'Pérdida de confianza en la decisión: el margen entre los dos mejores Q-values se estrechó bajo el umbral crítico, indicando un equilibrio exploración-explotación inestable en fase tardía de aprendizaje.' },
    ],
  }
}

export function mockAnalyst(): AnalystData {
  return {
    patterns: [
      {
        id: 'P1', type: 'estrategia', agents: [DRIVE],
        description: 'Estrategia de conservación energética mediante umbral de urgencia: el agente permaneció en reposo hasta que su drive alcanzó un nivel crítico, momento en que activó búsqueda focalizada y logró 4 consumos exitosos con 73% de acciones stay',
        evidence: 'En el paso 0 drive=0.0 con energía=0.78 mantuvo modo REST durante 6 pasos. En el paso 6 drive=0.014 cruzó el umbral y cambió a búsqueda activa. En el paso 11 ejecutó eat exitosamente y el drive se reinició a 0.0, volviendo a REST inmediatamente',
      },
      {
        id: 'P2', type: 'estrategia', agents: [HRL],
        description: 'Exploración activa con aprendizaje Q lento: el agente distribuyó acciones de forma balanceada, consumiendo recursos tras 24 pasos de exploración, pero con baja eficiencia general comparado con el modelo de drive continuo',
        evidence: 'Distribución uniforme de movimientos con 20% stay vs 73% del agente de drive. Primer consumo en el paso 24 tras exploración extensa. Segundo consumo en el paso 45. Total: 2 recursos en 60 pasos',
      },
      {
        id: 'P3', type: 'comportamiento', agents: [AI],
        description: 'Fallo catastrófico post-recuperación en el agente de energía libre esperada: tras consumir en el paso 6 y recuperar energía de 0.26 a 0.56, continuó explorando sin ajustar su política, muriendo por agotamiento en el paso 18',
        evidence: 'Entre los pasos 0-6 la energía cayó de 0.45 a 0.26. En el paso 6 consumió y recuperó a 0.56. Entre los pasos 7-18 realizó 11 movimientos sin nuevos consumos, con la energía declinando hasta 0.0. Los valores de energía libre esperada fueron uniformemente altos (>8.5) sin diferenciación clara entre acciones',
      },
      {
        id: 'P4', type: 'temporal', agents: [DRIVE],
        description: 'Acoplamiento entre la señal de drive y el cambio conductual: transiciones limpias entre los modos REST y EAT basadas en umbrales de drive, con reinicio inmediato tras el consumo',
        evidence: 'En el paso 11 pre-consumo: drive=0.055, modo=EAT, Q_eat=0.055 fue máximo. Post-consumo: drive=0.0, modo=REST, todos los Q-values=0.0. La velocidad del drive aumentó de 0.0004 (paso 0) a 0.011 (paso 11), indicando acumulación gradual de urgencia homeostática',
      },
      {
        id: 'P5', type: 'anomalía', agents: [AI],
        description: 'Colapso del prior alostático sin efecto protector: a pesar de tener mu_p=0.656 en el paso 7 tras recuperarse, la distribución sobre estados concentró toda la certeza en el estado inmediato sin generar políticas conservadoras',
        evidence: 'En el paso 7: mu_p=0.656 (prior alto), pero q_s concentró el valor 0.90 en el estado actual. Los costes esperados C variaron poco entre acciones (rango -1.17 a -0.013). La acción elegida fue move_up en vez de stay o búsqueda conservadora',
      },
    ],
    comparisons: [
      {
        agents: [DRIVE, HRL],
        metric: 'Recursos consumidos',
        values: { [DRIVE]: 4, [HRL]: 2 },
        insight: 'El modelo de dinámicas continuas de drive con umbral de urgencia superó en eficiencia al Q-learning libre de modelo porque el umbral homeostático permitió conservar energía mediante reposo estratégico',
      },
      {
        agents: [DRIVE, HRL],
        metric: 'Proporción de acciones stay',
        values: { [DRIVE]: 0.73, [HRL]: 0.2 },
        insight: 'La política de umbral generó comportamiento pasivo dominante hasta alcanzar necesidad crítica, mientras que el agente Q-learning mantuvo exploración activa constante, con mayor gasto energético sin ganancia proporcional',
      },
      {
        agents: [AI, DRIVE],
        metric: 'Pasos sobrevividos',
        values: { [AI]: 19, [DRIVE]: 60 },
        insight: 'El agente de energía libre esperada murió en el paso 18 porque sus Q-values uniformemente altos no diferenciaron entre acciones arriesgadas y conservadoras, mientras que el modelo de drive generó señales claras que acoplaron urgencia con acción',
      },
    ],
    metrics: {
      [DRIVE]: { 'pasos vivo': 60, 'recursos comidos': 4, 'tasa supervivencia': 1.0, 'proporción reposo': 0.73 },
      [HRL]: { 'pasos vivo': 60, 'recursos comidos': 2, 'tasa supervivencia': 1.0, 'proporción movimiento': 0.8 },
      [AI]: { 'pasos vivo': 19, 'recursos comidos': 1, 'tasa supervivencia': 0.32, 'energía final': 0.0 },
    },
  }
}

export function mockCharts(): ChartSpec[] {
  return [
    {
      id: 'chart_1',
      type: 'line',
      title: 'Evolución de energía (normalizada) por agente',
      x_label: 'Paso',
      y_label: 'Energía',
      series: [
        { name: DRIVE, color: '#4ade80', data: Array.from({ length: 60 }, (_, i) => ({ x: i, y: +energyDrive(i).toFixed(3) })) },
        { name: HRL, color: '#fbbf24', data: Array.from({ length: 60 }, (_, i) => ({ x: i, y: +energyHRL(i).toFixed(3) })) },
        {
          name: AI, color: '#a78bfa',
          data: Array.from({ length: AI_DEATH_STEP + 1 }, (_, i) => ({ x: i, y: energyAI(i) ?? 0 })),
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
        { name: DRIVE, color: '#4ade80', data: [{ x: 'stay', y: 44 }, { x: 'move_down', y: 7 }, { x: 'eat', y: 4 }, { x: 'move_right', y: 2 }, { x: 'move_left', y: 2 }, { x: 'move_up', y: 1 }] },
        { name: HRL, color: '#fbbf24', data: [{ x: 'stay', y: 12 }, { x: 'move_down', y: 13 }, { x: 'eat', y: 2 }, { x: 'move_right', y: 12 }, { x: 'move_left', y: 7 }, { x: 'move_up', y: 14 }] },
        { name: AI, color: '#a78bfa', data: [{ x: 'stay', y: 3 }, { x: 'move_down', y: 5 }, { x: 'eat', y: 1 }, { x: 'move_right', y: 5 }, { x: 'move_left', y: 1 }, { x: 'move_up', y: 4 }] },
      ],
    },
    {
      id: 'chart_3',
      type: 'line',
      title: 'Acumulación de drive y reinicio al consumir (Drive-dynamics ODE)',
      x_label: 'Paso',
      y_label: 'Drive',
      series: [
        { name: `${DRIVE}:drive`, color: '#4ade80', data: Array.from({ length: 60 }, (_, i) => ({ x: i, y: driveSignal(i) })) },
      ],
    },
  ]
}

export function mockDecisionTraces(): DecisionTrace[] {
  return [
    {
      agent_id: DRIVE,
      step: 11,
      perception: { x: 4, y: 3, grid_width: 10, grid_height: 10, step: 11, resources: { food: [{ x: 4, y: 3 }, { x: 5, y: 1 }] } },
      pre_state: { energy_level: 0.66, setpoint: 0.8, drive: 0.0196, previous_drive: 0.0144, drive_velocity: 0.011, behavioural_mode: 1, q_values: { eat: 0.055, move_down: 0.031, stay: 0.012, move_right: 0.009 } },
      post_state: { energy_level: 0.79, setpoint: 0.8, drive: 0.0, previous_drive: 0.0196, drive_velocity: 0.0, behavioural_mode: 0, q_values: { eat: 0.0, move_down: 0.0, stay: 0.0, move_right: 0.0 } },
      available_actions: ['eat', 'move_up', 'move_down', 'move_left', 'move_right', 'stay'],
      action_chosen: { name: 'eat', params: {} },
      outcome: { reward: 1, action_result: { consumed: true, resource_type: 'food' } },
    },
    {
      agent_id: AI,
      step: 7,
      perception: { x: 4, y: 4, grid_width: 10, grid_height: 10, step: 7, resources: { food: [{ x: 8, y: 4 }] } },
      pre_state: { energy: 0.51, mu_p: 0.656, rho: 0.42, q_values: { move_up: 8.71, move_down: 8.69, move_right: 8.66, stay: 8.62 } },
      post_state: { energy: 0.465, mu_p: 0.651, rho: 0.44, q_values: { move_up: 8.70, move_down: 8.68, move_right: 8.65, stay: 8.61 } },
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
    const eD = energyDrive(step)
    const drive = driveSignal(step)
    const driveEats = EAT_DRIVE.includes(step)
    const aiEnergy = energyAI(step)

    const perStep: DecisionTrace[] = [
      {
        agent_id: DRIVE, step,
        perception: { x: 4 + (step % 3), y: 3, grid_width: 10, grid_height: 10, step, resources: { food: [{ x: 4, y: 3 }] } },
        pre_state: { energy_level: +eD.toFixed(3), setpoint: 0.8, drive: +drive.toFixed(4), behavioural_mode: driveEats ? 1 : 0, q_values: { eat: +(driveEats ? 0.055 : 0.0).toFixed(3), move_down: +(drive * 1.5).toFixed(3), stay: +(drive * 0.5).toFixed(3) } },
        post_state: { energy_level: +(driveEats ? eD + 0.13 : eD).toFixed(3), setpoint: 0.8, drive: +(driveEats ? 0 : drive).toFixed(4), behavioural_mode: 0, q_values: { eat: 0.0, move_down: 0.0, stay: 0.0 } },
        available_actions: actions,
        action_chosen: { name: driveEats ? 'eat' : 'stay', params: {} },
        outcome: { reward: driveEats ? 1 : 0, action_result: driveEats ? { consumed: true, resource_type: 'food' } : {} },
      },
      {
        agent_id: HRL, step,
        perception: { x: 2 + (step % 5), y: 2 + (step % 4), grid_width: 10, grid_height: 10, step, resources: { food: [{ x: 5, y: 1 }] } },
        pre_state: { hunger_level: +(0.3 + step * 0.006).toFixed(3), homeostatic_setpoint: 0.5, drive: +(step * 0.09).toFixed(2), hRPE: +(Math.sin(step * 0.3) * 0.2).toFixed(3), q_values: { move_up: +(0.4 + step * 0.01).toFixed(2), move_right: +(0.35 + step * 0.008).toFixed(2), stay: +(0.2 + step * 0.004).toFixed(2), eat: +(EAT_HRL.includes(step) ? 0.9 : 0.15).toFixed(2) } },
        post_state: { hunger_level: +(0.3 + step * 0.006 + (EAT_HRL.includes(step) ? -0.2 : 0.004)).toFixed(3), homeostatic_setpoint: 0.5, drive: +(step * 0.09).toFixed(2), hRPE: +(Math.sin(step * 0.3) * 0.2 + 0.05).toFixed(3), q_values: { move_up: +(0.4 + step * 0.01).toFixed(2), move_right: +(0.35 + step * 0.008).toFixed(2), stay: +(0.2 + step * 0.004).toFixed(2), eat: +(EAT_HRL.includes(step) ? 1.0 : 0.15).toFixed(2) } },
        available_actions: actions,
        action_chosen: { name: EAT_HRL.includes(step) ? 'eat' : actions[1 + Math.floor(Math.random() * 4)], params: {} },
        outcome: { reward: EAT_HRL.includes(step) ? 1 : 0, action_result: EAT_HRL.includes(step) ? { consumed: true, resource_type: 'food' } : {} },
      },
    ]

    if (aiEnergy !== null) {
      const aiEats = step === 6
      perStep.push({
        agent_id: AI, step,
        perception: { x: 4, y: 3 + (step % 3), grid_width: 10, grid_height: 10, step, resources: { food: [{ x: 8, y: 4 }] } },
        pre_state: { energy: +aiEnergy.toFixed(3), mu_p: +(0.65 - step * 0.002).toFixed(3), rho: 0.42, q_values: { move_up: +(8.7 - step * 0.01).toFixed(2), move_down: +(8.68 - step * 0.01).toFixed(2), move_right: +(8.66 - step * 0.01).toFixed(2), stay: +(8.62 - step * 0.01).toFixed(2) } },
        post_state: { energy: +Math.max(0, aiEnergy - (aiEats ? -0.3 : 0.045)).toFixed(3), mu_p: +(0.65 - step * 0.002).toFixed(3), rho: 0.44, q_values: { move_up: +(8.69 - step * 0.01).toFixed(2), move_down: +(8.67 - step * 0.01).toFixed(2), move_right: +(8.65 - step * 0.01).toFixed(2), stay: +(8.61 - step * 0.01).toFixed(2) } },
        available_actions: actions,
        action_chosen: { name: aiEats ? 'eat' : 'move_up', params: {} },
        outcome: { reward: aiEats ? 1 : 0, action_result: aiEats ? { consumed: true, resource_type: 'food' } : {} },
      })
    }

    traces[step] = perStep
  }

  traces[11] = [mockDecisionTraces()[0], ...(traces[11]?.slice(1) ?? [])]
  traces[7] = [...(traces[7]?.slice(0, 2) ?? []), mockDecisionTraces()[1]]
  return traces
}
