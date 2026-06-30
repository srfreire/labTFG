{
  "patterns": [
    {
      "id": "P1",
      "type": "estrategia",
      "agents": ["continuous-drive-dynamics-with-urgency-threshold-policy"],
      "description": "Estrategia de conservación energética mediante umbral de urgencia: el agente permaneció en reposo hasta que su drive alcanzó un nivel crítico, momento en que activó búsqueda focalizada y logró 4 consumos exitosos con 73% de acciones stay",
      "evidence": "En el paso 0 drive=0.0 con energía=0.78 mantuvo modo REST durante 6 pasos consecutivos. En paso 6 drive=0.014 cruzó el umbral y cambió a búsqueda activa. En paso 11 con drive=0.055 ejecutó eat exitosamente y el drive se reinició a 0.0, volviendo a modo REST inmediatamente"
    },
    {
      "id": "P2",
      "type": "estrategia",
      "agents": ["drive-reduction-td-q-learning-model-free"],
      "description": "Exploración activa con aprendizaje Q lento: el agente distribuyó acciones de forma balanceada durante fase temprana, logrando consumir recursos tras 24 pasos de exploración, pero con baja eficiencia general comparado con el modelo basado en drive continuo",
      "evidence": "Distribución uniforme de movimientos con 20% stay vs 73% del agente de drive. Primer consumo en paso 24 tras exploración extensa. Drive evolucionó de 0.0 a 5.76 antes del consumo. Segundo consumo recién en paso 45. Total: 2 recursos en 60 pasos"
    },
    {
      "id": "P3",
      "type": "comportamiento",
      "agents": ["expected-free-energy-policy-selection-with-allostatic-prior-shifting"],
      "description": "Fallo catastrófico post-recuperación en agente de energía libre esperada: tras consumir exitosamente en el paso 6 y recuperar energía de 0.26 a 0.56, el agente continuó explorando intensamente sin ajustar su política, resultando en muerte por agotamiento en el paso 18",
      "evidence": "Entre pasos 0-6: energía cayó de 0.45 a 0.26. En paso 6 consumió y recuperó a 0.56. En paso 7 inmediatamente reanudó exploración con move_up. Entre pasos 7-18: realizó 11 movimientos sin nuevos consumos, energía declinó linealmente hasta 0.0. Los valores de energía libre esperada en todos los Q-values fueron uniformemente altos (>8.5) sin diferenciación clara entre acciones, indicando fallo del mecanismo de selección de política"
    },
    {
      "id": "P4",
      "type": "comportamiento",
      "agents": ["hierarchical-precision-weighted-prediction-error-minimization-gradient-descent-ode"],
      "description": "Exploración errática sin convergencia hacia objetivos: el agente mantuvo movimiento constante durante los 60 pasos sin lograr un solo consumo, con valores Q negativos uniformes que no reflejaron gradientes hacia recursos cercanos",
      "evidence": "0 recursos consumidos en 60 pasos. Distribución de movimientos: 83% exploración activa. En paso 0: Q-values entre -1.42 y -1.61. En paso 30: Q-values entre -0.076 y -0.089, aún sin diferenciación clara. En paso 59 con recurso en posición (5,9) a distancia 2, Q-values entre -0.071 y -0.395 sin orientación espacial efectiva. El error de predicción eps_1 mostró valores pequeños indicando que el sistema no detectó discrepancias significativas"
    },
    {
      "id": "P5",
      "type": "temporal",
      "agents": ["continuous-drive-dynamics-with-urgency-threshold-policy"],
      "description": "Acoplamiento entre señal de drive y cambio conductual: el sistema mostró transiciones limpias entre modos REST y EAT basadas en umbrales de drive, con reinicio inmediato post-consumo",
      "evidence": "En paso 11 pre-consumo: drive=0.055, modo=EAT, Q_eat=0.055 fue máximo. Post-consumo: drive=0.0, modo=REST, todos los Q-values=0.0. Velocidad del drive (drive_velocity) aumentó progresivamente: 0.0004 (paso 0) → 0.011 (paso 11), indicando acumulación gradual de urgencia homeostática"
    },
    {
      "id": "P6",
      "type": "anomalía",
      "agents": ["expected-free-energy-policy-selection-with-allostatic-prior-shifting"],
      "description": "Colapso del prior alostático sin efecto protector: a pesar de tener mu_p=0.656 en el paso 7 post-recuperación, la distribución sobre estados observados concentró toda la certeza en estados observados inmediatos sin generar políticas conservadoras",
      "evidence": "En paso 7: mu_p=0.656 (prior alto), pero q_s mostró concentración masiva en estado actual con valor 0.90. Los costos esperados C variaron poco entre acciones, con diferencias en rango -1.17 a -0.013. La acción elegida fue move_up en vez de stay o búsqueda conservadora local"
    }
  ],
  "comparisons": [
    {
      "agents": ["continuous-drive-dynamics-with-urgency-threshold-policy", "drive-reduction-td-q-learning-model-free"],
      "metric": "Recursos consumidos",
      "values": {
        "continuous-drive-dynamics-with-urgency-threshold-policy": 4,
        "drive-reduction-td-q-learning-model-free": 2
      },
      "insight": "El modelo de dinámicas continuas de drive con umbral de urgencia superó en eficiencia al Q-learning libre de modelo porque el umbral homeostático permitió conservar energía mediante reposo estratégico, mientras que el Q-learning exploró continuamente sin mecanismo de conservación innato"
    },
    {
      "agents": ["continuous-drive-dynamics-with-urgency-threshold-policy", "drive-reduction-td-q-learning-model-free"],
      "metric": "Proporción de acciones stay",
      "values": {
        "continuous-drive-dynamics-with-urgency-threshold-policy": 0.73,
        "drive-reduction-td-q-learning-model-free": 0.20
      },
      "insight": "La política de umbral generó comportamiento pasivo dominante hasta alcanzar necesidad crítica, mientras que el agente Q-learning mantuvo exploración activa constante, resultando en mayor gasto energético sin proporcional ganancia en recursos"
    },
    {
      "agents": ["expected-free-energy-policy-selection-with-allostatic-prior-shifting", "continuous-drive-dynamics-with-urgency-threshold-policy"],
      "metric": "Pasos sobrevividos",
      "values": {
        "expected-free-energy-policy-selection-with-allostatic-prior-shifting": 19,
        "continuous-drive-dynamics-with-urgency-threshold-policy": 60
      },
      "insight": "El agente de energía libre esperada murió en el paso 18 porque sus valores Q uniformemente altos no diferenciaron entre acciones arriesgadas y conservadoras, mientras que el modelo de drive generó señales claras que acoplaron urgencia con acción"
    },
    {
      "agents": ["hierarchical-precision-weighted-prediction-error-minimization-gradient-descent-ode", "drive-reduction-td-q-learning-model-free"],
      "metric": "Recursos consumidos con exploración activa",
      "values": {
        "hierarchical-precision-weighted-prediction-error-minimization-gradient-descent-ode": 0,
        "drive-reduction-td-q-learning-model-free": 2
      },
      "insight": "Ambos modelos exploraron intensamente, pero el Q-learning logró aprender asociaciones estado-acción-recompensa a partir de encuentros fortuitos, mientras que el minimizador de error de predicción jerárquico no generó gradientes efectivos hacia recursos a pesar de tener información perceptual equivalente"
    }
  ],
  "metrics": {
    "continuous-drive-dynamics-with-urgency-threshold-policy": {
      "pasos vivos": 60,
      "recursos comidos": 4,
      "tasa supervivencia": 1.0,
      "eficiencia forrajeo": 0.067,
      "proporción reposo": 0.73,
      "recompensa total": 4.0
    },
    "drive-reduction-td-q-learning-model-free": {
      "pasos vivos": 60,
      "recursos comidos": 2,
      "tasa supervivencia": 1.0,
      "eficiencia forrajeo": 0.033,
      "proporción movimiento": 0.80,
      "recompensa total": 2.0
    },
    "expected-free-energy-policy-selection-with-allostatic-prior-shifting": {
      "pasos vivos": 19,
      "recursos comidos": 1,
      "tasa supervivencia": 0.32,
      "energía inicial": 0.45,
      "energía final": 0.0,
      "energía máxima alcanzada": 0.56,
      "recompensa total": 1.0
    },
    "hierarchical-precision-weighted-prediction-error-minimization-gradient-descent-ode": {
      "pasos vivos": 60,
      "recursos comidos": 0,
      "tasa supervivencia": 1.0,
      "eficiencia forrajeo": 0.0,
      "proporción movimiento": 0.83,
      "recompensa total": 0.0
    }
  },
  "hypotheses": [
    "Si se incrementa el umbral de urgencia del agente de drive continuo, se esperaría mayor conservación energética pero riesgo de iniciar búsqueda demasiado tarde cuando los recursos estén agotados o distantes",
    "Si el agente de energía libre esperada incorpora un mecanismo de penalización por depleción energética en el cálculo de los costos C de cada acción, debería poder ajustar su política hacia conservación en estados de baja energía, evitando el colapso observado tras el paso 7"
  ]
}