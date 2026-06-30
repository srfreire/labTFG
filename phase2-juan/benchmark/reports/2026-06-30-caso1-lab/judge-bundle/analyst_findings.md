{
  "patterns": [
    {
      "id": "P1",
      "type": "comportamiento",
      "agents": ["classical-wiener-process-with-per-action-accumulators"],
      "description": "Proceso de Wiener con acumuladores por acción demostró forrajeo exitoso con 10 recursos consumidos mediante decisiones basadas en acumulación de evidencia ruidosa. Sus acumuladores de evidencia alcanzaron el umbral de 1.5 repetidamente, generando decisiones 'eat' cuando la evidencia acumulada para comer superaba a las alternativas.",
      "evidence": "En el paso 8, evidence_accumulator['move_left']=1.5 llevó a movimiento, seguido por evidence_accumulator['eat']=1.5 en el paso siguiente (consumición exitosa). En el paso 20, evidence_accumulator['move_up']=1.5 precede inmediatamente a una consumición. Entre los pasos 20 y 44 el agente consumió 7 recursos en 24 pasos, demostrando convergencia efectiva hacia zonas productivas mediante deriva estocástica guiada por Q-values."
    },
    {
      "id": "P2",
      "type": "comportamiento",
      "agents": ["drive-reduction-ode-with-goal-directed-valuation"],
      "description": "El modelo de reducción de impulso con valuación dirigida por metas exhibió saciedad homeostática tras consumir, produciendo inmovilidad masiva. Tras alcanzar E=0.99 en el paso 10, el agente ejecutó 47 acciones 'stay' de 60 totales, reflejando saturación del sistema de regulación interna.",
      "evidence": "En el paso 10, tras consumir, E saltó de 0.7 a 0.99, w_e aumentó de 0.69 a 0.88, y los Q-values de todas las acciones de movimiento se volvieron negativos (move_up=-0.039, move_left=-0.036). En el paso 11, con E=0.99, el agente eligió 'stay' (Q=0.0) sobre todas las alternativas negativas. Este patrón persistió durante 25 pasos, hasta que E cayó lo suficiente para reactivar forrajeo en el paso 35 (tercera y última consumición)."
    },
    {
      "id": "P3",
      "type": "estrategia",
      "agents": ["classical-wiener-process-with-per-action-accumulators"],
      "description": "El proceso de Wiener mostró pérdida recurrente de confianza decisional con 17 eventos de estrechamiento de margen entre sus dos mejores Q-values, lo que indujo exploración estocástica beneficiosa. Estos momentos de incertidumbre no bloquearon el forrajeo sino que aumentaron la variabilidad conductual.",
      "evidence": "Eventos de 'decision_confidence_drop' ocurrieron en los pasos 2, 4, 6, 8, 10, 12, 14, 18, 20, 24, 28, 32, 35, 38, 41, 44, 52 y 58. Estos coinciden con transiciones frecuentes entre acciones y con consumiciones exitosas (8, 20, 24, 28, 32, 35, 38, 41, 44, 52), sugiriendo que la incertidumbre facilitó la búsqueda activa en lugar de inhibirla."
    },
    {
      "id": "P4",
      "type": "comportamiento",
      "agents": ["attribute-reweighting-algebraic-model"],
      "description": "El modelo algebraico de re-ponderación de atributos falló completamente en forrajeo (0 consumiciones), a pesar de ejecutar 59 movimientos activos. Sus Q-values permanecieron homogéneos y bajos, sin convergencia hacia políticas efectivas.",
      "evidence": "En el paso 0, Q-values: move_left=0.53, move_right=0.52, move_up=0.43, move_down=0.43, eat=0.0. En el paso 30, tras 30 pasos de experiencia: move_left=0.40, move_down=0.40, move_right=0.33, move_up=0.33, eat=0.0. Los valores se comprimieron sin aprender la asociación entre ubicación y recursos. El agente mostró 5 cambios de estrategia (pasos 9, 28, 34, 40, 45) sin estabilización."
    },
    {
      "id": "P5",
      "type": "comportamiento",
      "agents": ["rescorlawagner-cached-value-agent-with-softmax-action-selection"],
      "description": "El agente con aprendizaje Rescorla-Wagner y caché de valores falló totalmente (0 consumiciones) pese a su paradigma de error de predicción. Los Q-values negativos uniformes y la penalización extrema de 'eat' bloquearon el aprendizaje de asociaciones recurso-ubicación.",
      "evidence": "En el paso 0, tras la primera acción, el modelo asignó Q['eat']=-1000000000.0 (penalización por comer sin recurso presente), mientras Q['move_up']=Q['move_down']=Q['move_left']=Q['move_right']=-0.01. Esta asimetría extrema entre exploración espacial (penalizada levemente) y consumición (penalizada catastróficamente) impidió aprender cuándo y dónde comer era apropiado."
    },
    {
      "id": "P6",
      "type": "temporal",
      "agents": ["dual-q-table-with-fixed-exponential-decay-arbitration"],
      "description": "El sistema dual Q con arbitraje de decaimiento exponencial logró solo 1 consumición en el paso 53, tras ejecutar 6 intentos 'eat' fallidos. La arbitraje modelo-free/model-based convergió tardíamente.",
      "evidence": "En el paso 53, q_values['eat']=0.471 (combinación de Q_MF y Q_MB con omega=0.951), pero tras consumir exitosamente, q_values['eat'] cayó a 0.0005 en el post_state. Los 5 'eat' fallidos previos no actualizaron eficientemente Q_MF, sugiriendo lentitud en la integración de evidencia sobre ubicaciones productivas. El agente necesitó 53 pasos para converger a su primera consumición exitosa."
    },
    {
      "id": "P7",
      "type": "recursos",
      "agents": ["classical-wiener-process-with-per-action-accumulators", "drive-reduction-ode-with-goal-directed-valuation"],
      "description": "Los dos agentes exitosos exhibieron patrones temporales opuestos: el proceso de Wiener mantuvo forrajeo continuo (10 consumiciones distribuidas uniformemente), mientras que reducción de impulso concentró consumiciones tempranas (3 en los pasos 3, 10, 35) seguidas de inactividad prolongada.",
      "evidence": "Wiener: consumiciones en pasos 8, 20, 24, 28, 32, 35, 38, 41, 44, 52 (espaciamiento medio ~5 pasos). Drive-reduction: consumiciones en pasos 3, 10, 35 (intervalos de 7 y 25 pasos), con 47 'stay' acumulados. El primero optimiza tasa de adquisición; el segundo optimiza conservación energética post-consumición."
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
      "insight": "El proceso de Wiener con acumulación estocástica de evidencia superó al modelo homeostático en 3.3×. La exploración continua sin inhibición por saciedad permitió al Wiener capitalizar múltiples oportunidades, mientras que la regulación energética del drive-reduction indujo pasividad prolongada tras alcanzar E=0.99."
    },
    {
      "agents": ["classical-wiener-process-with-per-action-accumulators", "attribute-reweighting-algebraic-model"],
      "metric": "Acciones de movimiento",
      "values": {
        "classical-wiener-process-with-per-action-accumulators": 50,
        "attribute-reweighting-algebraic-model": 59
      },
      "insight": "A pesar de moverse menos, el Wiener logró 10 consumiciones mientras el modelo algebraico no logró ninguna. La diferencia radica en la dirección del movimiento: el Wiener acumuló evidencia que guió movimientos hacia zonas productivas, mientras el modelo algebraico ejecutó exploración desorganizada sin convergencia espacial."
    },
    {
      "agents": ["dual-q-table-with-fixed-exponential-decay-arbitration", "weighted-linear-summation-with-state-dependent-attribute-weights-algebraic"],
      "metric": "Intentos de consumición",
      "values": {
        "dual-q-table-with-fixed-exponential-decay-arbitration": 6,
        "weighted-linear-summation-with-state-dependent-attribute-weights-algebraic": 2
      },
      "insight": "El sistema dual Q intentó comer 6 veces logrando 1 éxito (tasa 16.7%), mientras que la suma lineal ponderada intentó 2 veces logrando 1 éxito (tasa 50%). Ambos agentes lograron 1 consumición, pero el dual Q desperdició más oportunidades por desalineación entre sus sistemas modelo-free y model-based."
    },
    {
      "agents": ["rescorlawagner-cached-value-agent-with-softmax-action-selection", "attribute-reweighting-algebraic-model"],
      "metric": "Tasa de exploración",
      "values": {
        "rescorlawagner-cached-value-agent-with-softmax-action-selection": 0.833,
        "attribute-reweighting-algebraic-model": 0.983
      },
      "insight": "Ambos agentes fracasaron en forrajeo, pero por mecanismos distintos. El Rescorla-Wagner ejecutó 10 'stay' (16.7% inactividad) debido a penalizaciones negativas uniformes que desincentivaron movimiento. El modelo algebraico mantuvo exploración constante (98.3% movimiento) pero sin aprendizaje efectivo de asociaciones espaciales."
    }
  ],
  "metrics": {
    "classical-wiener-process-with-per-action-accumulators": {
      "recursos consumidos": 10,
      "pasos sobrevividos": 60,
      "tasa de éxito en consumición": 1.0,
      "eficiencia espacial": 0.17
    },
    "drive-reduction-ode-with-goal-directed-valuation": {
      "recursos consumidos": 3,
      "pasos sobrevividos": 60,
      "tasa de inactividad": 0.78,
      "eficiencia energética": 0.05
    },
    "attribute-reweighting-algebraic-model": {
      "recursos consumidos": 0,
      "pasos sobrevividos": 60,
      "cambios de estrategia": 5,
      "eficiencia de exploración": 0.0
    },
    "dual-q-table-with-fixed-exponential-decay-arbitration": {
      "recursos consumidos": 1,
      "pasos sobrevividos": 60,
      "intentos fallidos de consumición": 5,
      "pasos hasta primera consumición": 53
    },
    "rescorlawagner-cached-value-agent-with-softmax-action-selection": {
      "recursos consumidos": 0,
      "pasos sobrevividos": 60,
      "error de predicción promedio": 0.0,
      "bloqueo por penalización": 1.0
    },
    "weighted-linear-summation-with-state-dependent-attribute-weights-algebraic": {
      "recursos consumidos": 1,
      "pasos sobrevividos": 60,
      "tasa de éxito en consumición": 0.5,
      "pasos hasta primera consumición": 53
    }
  },
  "hypotheses": [
    "Si se aumenta el umbral de evidencia del proceso de Wiener de 1.5 a 2.0, se espera reducción en la frecuencia de cambios de acción y posible aumento en eficiencia de consumición, porque decisiones más conservadoras filtrarían ruido estocástico y concentrarían movimientos hacia zonas de mayor evidencia acumulada.",
    "Si se implementa decaimiento temporal de la energía interna (E) en el modelo de reducción de impulso, se esperaría reactivación más temprana del forrajeo tras saciedad, porque el agente no permanecería bloqueado en 'stay' durante 25 pasos sino que respondería gradualmente a la disminución de E, permitiendo consumiciones adicionales y mayor supervivencia."
  ]
}