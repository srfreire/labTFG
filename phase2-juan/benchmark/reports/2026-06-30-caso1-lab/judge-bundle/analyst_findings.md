{
  "patterns": [
    {
      "id": "P1",
      "type": "comportamiento",
      "agents": ["classical-wiener-process-with-per-action-accumulators"],
      "description": "El agente de proceso de Wiener mostró dominio mediante acumulación estocástica de evidencia que alcanzó sistemáticamente el umbral de decisión (1.5) para la acción 'eat' en 10 ocasiones. Su tiempo de decisión osciló entre 36-65 pasos, reflejando un proceso deliberativo que integra ruido gaussiano con tasas de deriva adaptativas.",
      "evidence": "Consumió 10 recursos (pasos 8, 20, 24, 28, 32, 35, 38, 41, 44, 52). En el paso 8, evidence_accumulator[eat]=0.73 con drift_rate=1.0; tras comer, decision_time=65 y Q[eat]=0.10. En el paso 32, evidence_accumulator[eat]=0.81 con drift_rate=1.16, indicando ajuste adaptativo basado en historia de recompensas."
    },
    {
      "id": "P2",
      "type": "estrategia",
      "agents": ["drive-reduction-ode-with-goal-directed-valuation"],
      "description": "El agente de reducción de impulso adoptó una estrategia de conservación energética tras alcanzar saciedad, manifestada en 47 acciones 'stay' (78% del comportamiento). Tras el consumo en el paso 10, su energía E subió a 0.99 y el peso competitivo w_c cayó de 0.31 a 0.12, reduciendo drásticamente la motivación para buscar recursos.",
      "evidence": "Consumió en pasos 3, 10 y 35. En el paso 10: pre-consumo E=0.70, w_c=0.31; post-consumo E=0.99, w_c=0.12. En paso 11 cambió de 'move_left' a 'stay'. En el paso 35: E=1.0, w_c=0.12, manteniendo estado de saciedad. Solo 13 movimientos en 60 pasos totales."
    },
    {
      "id": "P3",
      "type": "comportamiento",
      "agents": ["rescorlawagner-cached-value-agent-with-softmax-action-selection"],
      "description": "El agente Rescorla-Wagner quedó atrapado en un bloqueo pavloviano donde la acción 'eat' fue penalizada sistemáticamente (Q=-1e9) cuando no había recursos en su posición. Sus Q-values para movimientos permanecieron uniformemente negativos (-0.01), impidiendo el aprendizaje de patrones espaciales efectivos.",
      "evidence": "Paso 0: Q[eat]=-1e9 (bloqueado). Paso 30: Q[move_down/left/right]=-0.01, Q[eat]=-1e9, hunger_level=1.0. Nunca consumió recursos a pesar de 50 movimientos. Valores pavlovianos estancados en 0.0 para 8 estados visitados."
    },
    {
      "id": "P4",
      "type": "comportamiento",
      "agents": ["attribute-reweighting-algebraic-model"],
      "description": "El agente de reponderación de atributos mostró exploración activa (59 movimientos) pero valores de acción moderados (0.3-0.5) y alta señal de conflicto (0.60-0.69) que indican incertidumbre persistente sobre qué atributos (salud vs. sabor) priorizar. Su activación de meta cayó progresivamente de 0.5 a 0.10.",
      "evidence": "Nunca consumió recursos. Paso 0: Q[move_left]=0.53, conflict_signal=0.60, goal_activation=0.5. Paso 30: Q[move_down]=0.40, conflict_signal=0.69, goal_activation=0.10. 9 cambios estratégicos detectados, sin convergencia espacial."
    },
    {
      "id": "P5",
      "type": "temporal",
      "agents": ["classical-wiener-process-with-per-action-accumulators"],
      "description": "El agente Wiener experimentó 17 caídas de confianza decisional (decision_confidence_drop) donde el gap entre Q-values cayó desde 1.33 a valores cercanos a 0.0-0.26. Este patrón refleja el reseteo del acumulador de evidencia tras cada decisión, una propiedad intrínseca del proceso de difusión estocástico.",
      "evidence": "Paso 2: gap cayó de 1.33 a 0.0. Paso 10: gap cayó de 1.33 a 0.09. Paso 32: gap cayó de 1.33 a 0.16. Estas caídas ocurren sistemáticamente después de que el acumulador alcanza el umbral, con posterior recuperación mediante acumulación de nueva evidencia."
    },
    {
      "id": "P6",
      "type": "estrategia",
      "agents": ["dual-q-table-with-fixed-exponential-decay-arbitration", "weighted-linear-summation-with-state-dependent-attribute-weights-algebraic"],
      "description": "Los agentes con arbitraje modelo-libre/modelo-basado y suma lineal ponderada lograron consumos tardíos únicos (paso 53) tras extensas exploraciones. El agente Dual-Q mostró omega=0.95 (fuerte sesgo modelo-libre) y el agente de suma lineal w_abs=0.89 (dominancia de atributos abstractos sobre inmediatos).",
      "evidence": "Dual-Q paso 53: Q[eat]=0.47 pre-consumo, omega=0.95, h=1.0; post-consumo Q[eat]=0.0005, h=0.72. Suma lineal paso 53: V_o=0.65, w_abs=0.89, w_imm=0.11; post-consumo gap Q-values cayó de 0.63 a 0.01 (paso 54)."
    },
    {
      "id": "P7",
      "type": "recursos",
      "agents": ["classical-wiener-process-with-per-action-accumulators"],
      "description": "El agente Wiener estableció un patrón de explotación concentrada entre los pasos 30-44, consumiendo 5 recursos en 15 pasos (tasa 0.33 recursos/paso), sugiriendo detección y persistencia en zonas ricas en recursos mediante ajuste de tasas de deriva basado en recompensas recientes.",
      "evidence": "Consumos en pasos 32, 35, 38, 41, 44 (intervalo 30-44). En paso 32: drift_rate[eat]=1.16, reward_history[eat]=0.16. En paso 35: drift_rate[eat]=1.20, reward_history[eat]=0.20. Incremento progresivo de la deriva hacia 'eat'."
    }
  ],
  "comparisons": [
    {
      "agents": ["classical-wiener-process-with-per-action-accumulators", "drive-reduction-ode-with-goal-directed-valuation"],
      "metric": "Recursos consumidos",
      "values": {
        "classical-wiener-process-with-per-action-accumulators": 10,
        "drive-reduction-ode-with-goal-directed-valuation": 3
      },
      "insight": "El proceso de Wiener superó 3.3x al agente de reducción de impulso porque mantuvo exploración activa balanceada (50 movimientos vs. 13), mientras que la saciedad homeostática del segundo indujo pasividad tras alcanzar E=1.0"
    },
    {
      "agents": ["classical-wiener-process-with-per-action-accumulators", "rescorlawagner-cached-value-agent-with-softmax-action-selection"],
      "metric": "Eficiencia de aprendizaje",
      "values": {
        "classical-wiener-process-with-per-action-accumulators": 0.17,
        "rescorlawagner-cached-value-agent-with-softmax-action-selection": 0.0
      },
      "insight": "El Wiener logró tasa de éxito 0.17 (10 consumos/60 pasos) mientras Rescorla-Wagner falló completamente (0/60). El bloqueo pavloviano de 'eat' (Q=-1e9) impidió al segundo explorar la acción de consumo incluso cuando hunger_level=1.0"
    },
    {
      "agents": ["attribute-reweighting-algebraic-model", "classical-wiener-process-with-per-action-accumulators"],
      "metric": "Cambios estratégicos",
      "values": {
        "attribute-reweighting-algebraic-model": 9,
        "classical-wiener-process-with-per-action-accumulators": 3
      },
      "insight": "El agente de reponderación cambió estrategia 3x más que el Wiener, pero alta volatilidad (conflict_signal=0.60-0.69) sin convergencia espacial resultó en 0 consumos. El Wiener mostró estabilidad con ajustes específicos de deriva post-recompensa"
    },
    {
      "agents": ["dual-q-table-with-fixed-exponential-decay-arbitration", "weighted-linear-summation-with-state-dependent-attribute-weights-algebraic"],
      "metric": "Pasos hasta primer consumo",
      "values": {
        "dual-q-table-with-fixed-exponential-decay-arbitration": 53,
        "weighted-linear-summation-with-state-dependent-attribute-weights-algebraic": 53
      },
      "insight": "Ambos agentes convergieron simultáneamente en el paso 53, sugiriendo que la complejidad de arbitraje (Dual-Q) y ponderación dependiente de estado (Suma lineal) requirieron extensas exploraciones antes de generar valores de acción suficientemente altos para 'eat'"
    },
    {
      "agents": ["drive-reduction-ode-with-goal-directed-valuation", "classical-wiener-process-with-per-action-accumulators"],
      "metric": "Tasa de inactividad",
      "values": {
        "drive-reduction-ode-with-goal-directed-valuation": 0.78,
        "classical-wiener-process-with-per-action-accumulators": 0.0
      },
      "insight": "La reducción de impulso produjo 78% de inactividad (47 'stay'/60 pasos) vs. 0% del Wiener. La dinámica homeostática (E→1.0, w_c→0.12) eliminó motivación competitiva, mientras el proceso estocástico mantuvo exploración continua sin saciedad modelada"
    }
  ],
  "metrics": {
    "classical-wiener-process-with-per-action-accumulators": {
      "tasa supervivencia": 1.0,
      "recursos consumidos": 10,
      "eficiencia alimentación": 0.17,
      "movimientos totales": 50,
      "tiempo decisión promedio": 48.2
    },
    "drive-reduction-ode-with-goal-directed-valuation": {
      "tasa supervivencia": 1.0,
      "recursos consumidos": 3,
      "eficiencia alimentación": 0.05,
      "tasa inactividad": 0.78,
      "energía final": 0.75
    },
    "dual-q-table-with-fixed-exponential-decay-arbitration": {
      "tasa supervivencia": 1.0,
      "recursos consumidos": 1,
      "omega final": 0.90,
      "pasos hasta consumo": 53,
      "intentos eat fallidos": 5
    },
    "rescorlawagner-cached-value-agent-with-softmax-action-selection": {
      "tasa supervivencia": 1.0,
      "recursos consumidos": 0,
      "movimientos totales": 50,
      "estados visitados": 8,
      "Q medio movimientos": -0.01
    },
    "attribute-reweighting-algebraic-model": {
      "tasa supervivencia": 1.0,
      "recursos consumidos": 0,
      "cambios estrategia": 9,
      "conflicto promedio": 0.64,
      "activación meta final": 0.10
    },
    "weighted-linear-summation-with-state-dependent-attribute-weights-algebraic": {
      "tasa supervivencia": 1.0,
      "recursos consumidos": 1,
      "peso abstracto final": 0.89,
      "pasos hasta consumo": 53,
      "movimientos totales": 52
    }
  },
  "hypotheses": [
    "Si aumentamos la tasa de decaimiento de energía (E) en el modelo de reducción de impulso, esperamos que el agente mantenga w_c elevado por más tiempo, incrementando movimientos exploratorios y recursos consumidos, porque la saciedad se desvanecería más rápido evitando la trampa de inactividad prolongada",
    "Si reducimos el umbral de acumulación de evidencia en el proceso de Wiener de 1.5 a 1.0, esperamos decisiones más rápidas (menor decision_time) pero potencialmente menos precisas, resultando en más intentos de 'eat' fallidos y posible reducción en eficiencia total de consumo por decisiones prematuras basadas en evidencia insuficiente"
  ]
}