{
  "patterns": [
    {
      "id": "P1",
      "type": "estrategia",
      "agents": ["continuous-drive-dynamics-with-urgency-threshold-policy"],
      "description": "Estrategia de espera con intervención umbral: el agente permaneció inactivo el 73% del tiempo (44 de 60 acciones fueron 'stay'), activándose solo cuando su impulso interno superó un umbral crítico. En el paso 7 su drive alcanzó 0.0256 en modo FORAGE, desencadenando búsqueda dirigida (3 movimientos consecutivos hacia abajo) que culminó en alimentación exitosa en el paso 11. Tras cada consumo, el drive se reseteó a 0.0 y el agente retornó inmediatamente al modo REST, repitiendo el patrón 4 veces (pasos 11, 23, 40, 56)",
      "evidence": "En el paso 6, drive=0.0144 con modo REST. En el paso 7, drive=0.0256 activó modo FORAGE. En el paso 8, drive=0.0342 intensificó búsqueda. Tras consumo en paso 11, drive volvió a 0.0 y modo cambió a REST. El agente consumió 4 recursos con eficiencia energética máxima: 4 recompensas / 60 pasos = 0.067 recompensas por paso"
    },
    {
      "id": "P2",
      "type": "estrategia",
      "agents": ["drive-reduction-td-q-learning-model-free"],
      "description": "Exploración constante sin convergencia de aprendizaje: el agente mantuvo 80% de acciones de movimiento (58 de 60) distribuyéndose casi uniformemente entre direcciones (move_up=14, move_down=13, move_right=12, move_left=7). A pesar de dos consumos exitosos, su tabla Q no desarrolló preferencias claras. En el paso 23, antes del primer consumo, todos sus valores Q eran 0.0, indicando ausencia de aprendizaje acumulado tras 23 pasos de experiencia",
      "evidence": "Paso 23: Q-values={move_up:0.0, move_down:0.0, move_left:0.0, move_right:0.0, stay:0.0, eat:0.0}, hunger_level=2.3, drive=5.29. Paso 46: tras segundo consumo, el agente mostró Q-values ligeramente negativos pero sin diferenciación entre acciones. Total: 2 recursos en 60 pasos = 0.033 recompensas por paso, mitad de eficiencia del modelo drive-dynamics"
    },
    {
      "id": "P3",
      "type": "temporal",
      "agents": ["expected-free-energy-policy-selection-with-allostatic-prior-shifting"],
      "description": "Colapso energético irreversible tras ventana crítica única: el agente inició con energía 0.45 y experimentó caída lineal (pérdida de 0.05 por paso) durante 6 pasos hasta alcanzar 0.26. Logró un único consumo en el paso 6 que elevó su energía a 0.56, pero nunca encontró un segundo recurso. La energía continuó decayendo hasta 0.01 en el paso 17 y llegó a 0.0 en el paso 18, terminando la simulación por agotamiento",
      "evidence": "Energía: paso 0=0.45, paso 5=0.26, paso 6=0.56 (consumo), paso 11=0.31, paso 17=0.01, paso 18=0.0 (muerte). Durante los 12 pasos finales realizó 11 acciones de movimiento exploratorio sin patrón dirigido, con valores Q prácticamente idénticos entre acciones (diferencias menores a 0.0002 en el paso 17), sugiriendo decisiones cercanas al azar"
    },
    {
      "id": "P4",
      "type": "comportamiento",
      "agents": ["hierarchical-precision-weighted-prediction-error-minimization-gradient-descent-ode"],
      "description": "Exploración infructuosa con señal de error persistente: el agente ejecutó 83% de movimientos (50 de 60 acciones) alternando direcciones sin establecer patrones espaciales coherentes. Sus valores Q permanecieron en rango negativo estrecho (entre -0.05 y -0.09) durante toda la simulación, con diferencias mínimas entre acciones. Los errores de predicción (eps_1, eps_2) mostraron oscilaciones sin corrección sistemática, indicando que el sistema de minimización de error no convergió a una política efectiva",
      "evidence": "Paso 0: Q-values entre -1.43 y -1.61, F=0.88. Paso 30: Q-values entre -0.076 y -0.089, F=0.12. A pesar de 30 pasos de ajuste gradiente, la señal F de energía libre solo disminuyó marginalmente y los Q-values mantuvieron rangos comprimidos. El agente no consumió ningún recurso en 60 pasos, eficiencia=0.0"
    },
    {
      "id": "P5",
      "type": "comportamiento",
      "agents": ["continuous-drive-dynamics-with-urgency-threshold-policy", "drive-reduction-td-q-learning-model-free"],
      "description": "Divergencia conductual entre modelos basados en impulso: ambos utilizan señal de 'drive' pero con dinámicas opuestas. El modelo continuous-drive mostró regulación homeostática perfecta (drive osciló entre 0.0 y 0.055, activando búsqueda solo al superar umbral). El modelo Q-learning mostró acumulación monotónica de drive (de 1.0 en paso 10 a valores crecientes) sin mecanismo de reseteo, generando exploración perpetua sin fases de descanso",
      "evidence": "Continuous-drive paso 11: drive=0.055 antes de comer, 0.0 después. Q-learning paso 10: drive=1.0, paso 23: drive=5.29, paso 46: drive=0.0 solo tras consumo. La ausencia de regulación homeostática en Q-learning resultó en comportamiento de búsqueda constante menos eficiente (2 vs 4 consumos)"
    },
    {
      "id": "P6",
      "type": "recursos",
      "agents": ["continuous-drive-dynamics-with-urgency-threshold-policy", "drive-reduction-td-q-learning-model-free", "expected-free-energy-policy-selection-with-allostatic-prior-shifting", "hierarchical-precision-weighted-prediction-error-minimization-gradient-descent-ode"],
      "description": "Desigualdad espacial en acceso a recursos: el agente continuous-drive inició en posición (1,0) cerca del cluster de recursos en y=2-3, permitiéndole encontrar comida rápidamente en movimientos cortos. El agente hierarchical-precision inició en (1,8), zona lejana del cluster principal, requiriendo navegación extensa sin éxito. El agente expected-free-energy inició en (2,1), encontró un recurso en (4,3) tras 6 pasos pero no pudo localizar un segundo a tiempo",
      "evidence": "En el paso 10, ocho recursos estaban concentrados en región x=0-9, y=1-6. Continuous-drive alcanzó (1,3) tras 11 pasos. Hierarchical-precision estaba en (3,7) tras 10 pasos, lejos del cluster. Expected-free-energy murió en (6,3), rodeado de recursos que no localizó en 12 pasos post-consumo"
    },
    {
      "id": "P7",
      "type": "comportamiento",
      "agents": ["drive-reduction-td-q-learning-model-free"],
      "description": "Pérdida catastrófica de confianza en decisión: en el paso 46, inmediatamente después de su segundo consumo exitoso, el agente experimentó colapso completo en diferenciación de valores Q. Su tabla pasó de mostrar preferencias claras en el paso 45 (registradas por el detector de eventos con gap=0.576) a valores Q prácticamente uniformes (todos entre 0.0 y -0.027) en el paso 46. Este fenómeno indica que el evento de recompensa alta desestabilizó su función de valor en lugar de reforzarla",
      "evidence": "El sistema de detección registró en paso 46: 'perdió confianza en su decisión: gap Q-values bajó de 0.58 a 0.00'. En el paso 46, hunger_level volvió a 0.0 tras el consumo, reseteando completamente su señal de drive y colapsando la diferenciación aprendida. Esto sugiere interferencia entre la señal homeostática (hunger) y el aprendizaje por refuerzo (Q-values)"
    }
  ],
  "comparisons": [
    {
      "agents": ["continuous-drive-dynamics-with-urgency-threshold-policy", "drive-reduction-td-q-learning-model-free"],
      "metric": "Recursos consumidos totales",
      "values": {
        "continuous-drive-dynamics-with-urgency-threshold-policy": 4,
        "drive-reduction-td-q-learning-model-free": 2
      },
      "insight": "El modelo de umbral homeostático superó al Q-learning en eficiencia de forrajeo (4 vs 2 consumos) porque alternó entre reposo y búsqueda dirigida, mientras que el Q-learning mantuvo exploración continua sin desarrollar patrones efectivos. La regulación por drive con reseteo post-consumo generó intervalos de búsqueda cortos y eficientes"
    },
    {
      "agents": ["continuous-drive-dynamics-with-urgency-threshold-policy", "expected-free-energy-policy-selection-with-allostatic-prior-shifting"],
      "metric": "Proporción de acciones de espera",
      "values": {
        "continuous-drive-dynamics-with-urgency-threshold-policy": 0.73,
        "expected-free-energy-policy-selection-with-allostatic-prior-shifting": 0.16
      },
      "insight": "El modelo continuous-drive conservó energía mediante espera estratégica (73% de acciones), mientras que el modelo free-energy mantuvo exploración activa (84% movimientos) hasta su muerte. La ausencia de modo de reposo en free-energy aceleró su colapso energético, demostrando que la exploración sin regulación homeostática es letal en entornos con escasez"
    },
    {
      "agents": ["hierarchical-precision-weighted-prediction-error-minimization-gradient-descent-ode", "drive-reduction-td-q-learning-model-free"],
      "metric": "Recursos encontrados",
      "values": {
        "hierarchical-precision-weighted-prediction-error-minimization-gradient-descent-ode": 0,
        "drive-reduction-td-q-learning-model-free": 2
      },
      "insight": "Ambos modelos mantuvieron exploración constante (83% y 80% de movimientos respectivamente), pero el Q-learning logró 2 consumos mientras que el modelo jerárquico no encontró ninguno. La diferencia radica en la señal de refuerzo: Q-learning usó señal homeostática clara (hunger_level) que reaccionó a consumos, mientras que el modelo jerárquico minimizó error de predicción sin señal de recompensa explícita, resultando en exploración sin propósito"
    },
    {
      "agents": ["continuous-drive-dynamics-with-urgency-threshold-policy", "hierarchical-precision-weighted-prediction-error-minimization-gradient-descent-ode"],
      "metric": "Pasos sobrevividos",
      "values": {
        "continuous-drive-dynamics-with-urgency-threshold-policy": 60,
        "hierarchical-precision-weighted-prediction-error-minimization-gradient-descent-ode": 60
      },
      "insight": "Ambos sobrevivieron los 60 pasos, pero con resultados opuestos: continuous-drive lo logró mediante 4 consumos exitosos, mientras que hierarchical-precision sobrevivió sin consumir nada, sugiriendo que su tasa de consumo de energía basal era suficientemente baja o inexistente. Esto indica diferencias fundamentales en los sistemas de supervivencia implementados"
    }
  ],
  "metrics": {
    "continuous-drive-dynamics-with-urgency-threshold-policy": {
      "pasos sobrevividos": 60,
      "recursos consumidos": 4,
      "recompensa total": 4.0,
      "eficiencia forrajeo": 0.067,
      "tasa movimiento": 0.27,
      "tasa espera": 0.73
    },
    "drive-reduction-td-q-learning-model-free": {
      "pasos sobrevividos": 60,
      "recursos consumidos": 2,
      "recompensa total": 2.0,
      "eficiencia forrajeo": 0.033,
      "tasa movimiento": 0.8,
      "tasa espera": 0.2
    },
    "expected-free-energy-policy-selection-with-allostatic-prior-shifting": {
      "pasos sobrevividos": 19,
      "recursos consumidos": 1,
      "recompensa total": 1.0,
      "eficiencia forrajeo": 0.053,
      "energía inicial": 0.45,
      "energía final": 0.0,
      "tasa caída energética": 0.024
    },
    "hierarchical-precision-weighted-prediction-error-minimization-gradient-descent-ode": {
      "pasos sobrevividos": 60,
      "recursos consumidos": 0,
      "recompensa total": 0.0,
      "eficiencia forrajeo": 0.0,
      "tasa movimiento": 0.83,
      "rango valores Q": 0.032
    }
  },
  "hypotheses": [
    "Si se incrementa la densidad de recursos en el ambiente (de 8 a 16 recursos), se espera que el modelo hierarchical-precision logre al menos un consumo porque sus errores de predicción tendrían mayor oportunidad de correlacionarse con gradientes hacia comida, mientras que el modelo continuous-drive mantendría su alta eficiencia pero con intervalos de espera más cortos debido a mayor disponibilidad percibida",
    "Si se modifica el modelo drive-reduction-td-q-learning para preservar su tabla Q después de consumos (en lugar de resetear con hunger_level), se espera que desarrolle preferencias espaciales estables y aumente su eficiencia de forrajeo a niveles cercanos al modelo continuous-drive, porque actualmente cada consumo borra su aprendizaje previo generando el patrón de exploración perpetua observado"
  ]
}