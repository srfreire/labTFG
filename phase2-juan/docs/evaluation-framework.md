# Marco de evaluación de la Fase 2 — fundamentación bibliográfica

> Documento de trabajo para el capítulo de evaluación de la memoria (Juan Freire).
> Reúne el marco por capas y las referencias con respaldo en literatura revisada.
> Generado a partir de investigación bibliográfica multifuente (jun. 2026).

## Idea central

La Fase 2 mezcla dos naturalezas distintas que **no deben medirse con la misma vara**:

- un **backbone determinista** (motor de simulación, Tracker, almacenamiento/recuperación
  del KG) → métricas duras, objetivas, reproducibles;
- una **capa de juicio LLM** (Architect, Analyst, Reporter) cuyas salidas son abiertas
  y no tienen una única respuesta correcta → golden scenarios + LLM-as-judge + revisión
  humana.

Esta separación está respaldada por la taxonomía de *cómputo de métricas* del survey de
LLM-agentes de KDD'25 (Mohammadi et al.), que distingue tres métodos complementarios:
**code/rule-based** (el más determinista y objetivo), **LLM-as-a-judge** y
**human-in-the-loop** (gold standard para lo subjetivo). El marco de tres capas de abajo
es una instanciación directa de esa taxonomía.

## Las tres capas

### Capa 1 — Backbone determinista (métricas duras)
La literatura recomienda **preferir comprobaciones deterministas siempre que exista un
ground truth programático**, porque los jueces LLM son no deterministas y sesgados hacia
rasgos estilísticos sobre la corrección (Agent-Diff, arXiv:2602.11224).

- **Tracker — fidelidad**: inyectar N eventos conocidos, verificar registro completo sin
  pérdida ni duplicados; episodios/trayectorias derivadas contra ground truth. Recall/exactitud.
- **Simulación — determinismo/reproducibilidad**: misma semilla → misma trayectoria.
- **KG retrieval** (alimenta Analyst/Reporter): hechos sembrados en top-k, latencia p95,
  coste. *Heredable directo de la suite `retrieval-quality` de la Fase 1 → continuidad.*
- **Contrato de éxito por estado**, no por traza: definir el éxito como el *cambio esperado
  en el estado del entorno* (state-diff) en lugar de emparejar llamadas a herramientas;
  permite detectar efectos colaterales no deseados (Agent-Diff). EnvSimBench ejemplifica
  dos métricas binarias exact-match (Feedback Match, Config Match).

### Capa 2 — Juicio LLM (Architect, Analyst, Reporter)
Para salidas abiertas, **LLM-as-a-judge** es un método validado: jueces fuertes (GPT-4)
alcanzan **>80 % de acuerdo con preferencias humanas, al nivel del acuerdo entre humanos**
(Zheng et al. 2023). Pero hay que **endurecerlo** contra una taxonomía de sesgos bien
documentada (posición, verbosidad, self-enhancement, autoridad, bandwagon… ~12 sesgos en
CALM, arXiv:2410.02736; incluso jueces frontera pueden quedar cerca del azar en
discriminaciones difíciles).

Buenas prácticas (Anthropic eng. guide; Shen et al. 2026):
- **Calibrar** el juez contra expertos humanos antes de confiar en él (baja divergencia).
- **Un juez aislado por dimensión** evaluada, no un único juez para todo.
- **Rúbricas estructuradas/recursivas** explícitas: mejoran fiabilidad e interpretabilidad
  (RRD: +17.7 pp de exactitud en JudgeBench para GPT-4o). *Matiz: las rúbricas mejoran pero
  no resuelven del todo la fiabilidad.*

**Golden scenarios** para esta capa: construir modelos de *verdad conocida* (uno que
forrajea óptimo, uno que aprende, uno aleatorio) y medir si el pipeline recupera esa verdad
(¿el Analyst detecta el patrón sembrado? precision/recall sobre escenarios de ground truth).
Apoyo metodológico: REAL (réplicas deterministas, arXiv:2504.11543) y EnvSimBench
(labels producidos por un ejecutor no-LLM, arXiv:2605.07247).

### Capa 3 — Revisión humana (gold standard)
Las decisiones humanas son el patrón oro contra el que se **meta-evalúa** el juez LLM. La
meta-evaluación se hace midiendo el acuerdo juez-humano con (Li et al. 2024, §6):
**Accuracy, Pearson, Spearman, Kendall's Tau, Cohen's Kappa, ICC** (la métrica depende del
tipo de dato: categórico/ordinal/continuo). La revisión humana se reserva para lo subjetivo
y lo crítico, y se reduce a medida que el juez demuestra bajo divergencia.

## Dos pilares complementarios que pedía el encargo

### A) Validación de los MODELOS de decisión que el laboratorio simula
Distinto de evaluar los agentes LLM: es validar la *ciencia* del modelo generado. Marco
canónico — **Wilson & Collins 2019** ("Ten simple rules…"):
- **Parameter recovery**: simular con parámetros conocidos, ajustar, comprobar que se
  recuperan (correlación simulado vs. recuperado; detectar *parameter trading*).
- **Model recovery**: matriz de confusión — datos de un modelo deben ser mejor ajustados
  por ese mismo modelo.
- **Posterior predictive checks**: simular el modelo ganador con parámetros ajustados y
  comprobar que reproduce patrones cualitativos/cuantitativos de los datos reales.
- **Análisis model-independent** previo al ajuste.

Complemento: **Palminteri et al. 2017** sobre la importancia de la *falsación* (no basta con
que un modelo ajuste; debe poder fallar donde otros fallan). Esto justifica los golden
scenarios como prueba de falsación.

### B) Faithfulness / consistencia factual del Reporter
El Reporter genera informes; hay que medir que **los números/afirmaciones del informe
coinciden con los datos de simulación** (no alucina). Métodos:
- **QAGS** (Wang, Cho & Lewis 2020): generar preguntas sobre el resumen y la fuente; si las
  respuestas coinciden → consistente. Interpretable (señala el token inconsistente).
- **SummaC** (Laban et al. 2022): detección de inconsistencias vía NLI a nivel de frase
  agregado a documento.
- **SelfCheckGPT** (Manakul et al. 2023): detección de alucinación zero-resource por
  consistencia entre muestras (sin ground truth externo).
- Survey de referencia: **Ji et al. 2023**, hallucination en NLG.

## Mapa agente → tipo de métrica

| Agente | Métrica dura (Capa 1) | Golden scenario (Capa 2) | Funcional binaria | Humano/LLM-judge (Capas 2-3) |
|---|---|---|---|---|
| Architect | — | spec expresa el comportamiento esperado | parsea schema + un modelo corre en él | coherencia con el paradigma |
| Tracker | recall de eventos, determinismo | — | — | — |
| Analyst | retrieval top-k, p95 | detecta el patrón sembrado (precision/recall) | — | calidad del análisis (juez aislado) |
| Reporter | — | números del informe = datos de simulación (QAGS/SummaC) | compila LaTeX + secciones obligatorias | calidad narrativa |
| Orchestrator | latencia, coste $ | tasa de éxito end-to-end | pipeline completa sin intervención | — |

Para el end-to-end, AgentBench (Liu et al. 2023) avala el *task-success-rate* en entornos
interactivos como métrica establecida. Una suite útil puede **empezar pequeña** (20-50
tareas de fallos reales; Anthropic) — apropiado como punto de partida iterativo, no como
base de conclusiones con potencia estadística (para eso, ~200-600+ muestras).

## Bibliografía

**Taxonomía / marco general**
- Mohammadi, Li, Lo, Yip (2025). *Evaluation of LLM-based Agents* (survey). KDD'25.
  DOI 10.1145/3711896.3736570 · arXiv:2507.21504.

**LLM-as-a-judge: validez, sesgos, meta-evaluación**
- Zheng et al. (2023). *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.* NeurIPS 2023. arXiv:2306.05685.
- Li et al. (2024). *LLMs-as-Judges: A Comprehensive Survey* (métricas de acuerdo, §6). arXiv:2412.05579.
- Ye et al. / CALM (2024). *Justice or Prejudice? Quantifying Biases in LLM-as-a-Judge.* arXiv:2410.02736.
- Shen et al. (2026). Rúbricas recursivas (RRD) para juicio fiable. arXiv:2602.05125.
- Anthropic (2025). *Demystifying evals for AI agents* (best practices; cita como guía de práctica).

**Golden scenarios / ground truth determinista**
- REAL (2025). Réplicas deterministas de sitios web. arXiv:2504.11543.
- EnvSimBench (2026). Labels por ejecutor no-LLM. arXiv:2605.07247.
- Agent-Diff (2026). Contrato state-diff (éxito por estado, no por traza). arXiv:2602.11224.

**Evaluación end-to-end de agentes**
- Liu et al. (2023). *AgentBench: Evaluating LLMs as Agents.* ICLR 2024. arXiv:2308.03688.

**Validación de modelos computacionales de comportamiento**
- Wilson, R. C. & Collins, A. G. E. (2019). *Ten simple rules for the computational modeling
  of behavioral data.* eLife 8:e49547. DOI 10.7554/eLife.49547.
- Palminteri, Wyart & Koechlin (2017). *The Importance of Falsification in Computational
  Cognitive Modeling.* Trends in Cognitive Sciences 21(6):425-433. DOI 10.1016/j.tics.2017.03.011.

**Faithfulness / consistencia factual del informe**
- Ji et al. (2023). *Survey of Hallucination in Natural Language Generation.* ACM Computing
  Surveys 55(12). DOI 10.1145/3571730.
- Laban et al. (2022). *SummaC: Re-Visiting NLI-based Models for Inconsistency Detection in
  Summarization.* TACL 10.
- Wang, Cho & Lewis (2020). *Asking and Answering Questions to Evaluate the Factual
  Consistency of Summaries* (QAGS). ACL 2020.
- Manakul, Liusie & Gales (2023). *SelfCheckGPT: Zero-Resource Black-Box Hallucination
  Detection.* EMNLP 2023.

## Concreción: modelos, escenarios y estado (2026-06-24)

**Modelos sujeto** (run `7a045c0d` de Pazos, restaurada en local):
- `optimal-foraging-theory / marginal-value-theorem-...` (MVT, Charnov 1976)
- `optimal-foraging-theory / diet-breadth-...` (MacArthur & Pianka 1966)
- `reinforcement-learning / tabular-q-learning-...`
- `reinforcement-learning / actor-critic-with-softmax-policy` (Joel-Niv-Ruppin 2002)

**Baselines** (en `phase2-juan/benchmark/baselines.py`): `GreedyForagerOracle`
(techo de forrajeo) y `RandomModel` (suelo). Contrato dict, `q_values`, semilla.

**Golden scenarios concretos:** GS-0 contrato observable · GS-OFT-1 abandono de
parche · GS-OFT-2 ↑coste viaje⇒↑residencia (el más discriminativo) · GS-OFT-3
regla 0-1 dieta · GS-RL-1 curva de aprendizaje (RL vs OFT plano).

**Estado de restauración (OrbStack):** Postgres 1 run / 4 models / 21 artifacts;
MinIO objetos de modelo presentes; Neo4j 240 nodos / 42 rels; Qdrant dense 275 /
sparse 231. Verificado que los 4 modelos cargan vía `discover_models`+`load_model`.

**Capítulo:** el marco se redactó en `capitulos/05-pruebas.tex` (reestructurado a
3 capas; resultados medibles marcados como `TODO` pendientes de ejecutar el
benchmark). Citas nuevas añadidas a `capitulos/bibliografia.tex`.

## Notas de cautela (para no exagerar al citar)
- El >80 % de acuerdo juez-humano es específico de tarea/dominio (MT-Bench + Arena); acótalo.
- La guía de Anthropic es guía de ingeniería de proveedor: cítala como *best practice*, no
  como resultado empírico con tamaño de efecto.
- Varias fuentes son preprints 2024-2026: verifica la versión canónica/publicada al redactar.
- EnvSimBench es "LLM-free" solo en el etiquetado, no en la recogida de trayectorias.
