# Bibliografia tecnica relevante para la memoria

Este documento recoge las referencias que conviene citar en el TFG antes de
redactar la memoria en LaTeX. No significa que todas deban aparecer con el mismo
peso: la memoria tiene limite de extension, asi que las referencias marcadas
como "nucleares" deberian ir en el estado del arte o en la arquitectura, y las
"de apoyo" pueden usarse solo si ayudan a justificar una decision concreta.

## Mapa rapido de citas

```text
Sistema de Pablo
  |
  +-- Pipeline de agentes
  |     ReAct, Toolformer, AutoGen, ChatDev, SWE-agent
  |
  +-- Generacion de codigo y validacion
  |     Codex, Program Synthesis, PICARD, Self-Refine, Reflexion
  |
  +-- Recuperacion de conocimiento
  |     RAG, DPR, BM25, RRF, Self-RAG, CRAG
  |
  +-- Memoria y grafo de conocimiento
        Generative Agents, MemoryBank, MemGPT, Knowledge Graphs,
        GraphRAG, HippoRAG, Topic-sensitive PageRank
```

## Recuperacion aumentada y busqueda hibrida

### Lewis et al. (2020) - Retrieval-Augmented Generation

- Clave sugerida: `lewis2020rag`
- Fuente: <https://arxiv.org/abs/2005.11401>
- Prioridad: nuclear.
- Uso en la memoria: base conceptual de usar memoria no parametrica externa
  para mejorar respuestas generadas por modelos de lenguaje.
- Relacion con el sistema: `retrieve_knowledge` aporta contexto externo a los
  agentes antes de que generen informes, formulaciones, especificaciones o
  codigo. Nuestro sistema no entrena un RAG end-to-end; aplica el patron de
  recuperacion en tiempo de inferencia.

### Karpukhin et al. (2020) - Dense Passage Retrieval

- Clave sugerida: `karpukhin2020dpr`
- Fuente: <https://arxiv.org/abs/2004.04906>
- Prioridad: de apoyo.
- Uso en la memoria: justificar la recuperacion densa por embeddings como
  complemento a metodos lexicos.
- Relacion con el sistema: Qdrant `memories_dense` usa embeddings para recuperar
  hechos semanticamente cercanos aunque no compartan las mismas palabras.

### Robertson y Zaragoza (2009) - BM25 and Beyond

- Clave sugerida: `robertson2009bm25`
- Fuente: <https://ir.webis.de/anthology/2009.ftir_journal-ir0anthology0volumeA3A4.0/>
- Prioridad: nuclear para la busqueda hibrida.
- Uso en la memoria: fundamentar BM25 como tecnica clasica de recuperacion
  lexica probabilistica.
- Relacion con el sistema: Qdrant `memories_sparse` usa BM25 nativo para nombres,
  simbolos, autores, identificadores y terminos exactos.

### Cormack, Clarke y Buettcher (2009) - Reciprocal Rank Fusion

- Clave sugerida: `cormack2009rrf`
- Fuente: <https://research.google/pubs/reciprocal-rank-fusion-outperforms-condorcet-and-individual-rank-learning-methods/>
- Prioridad: nuclear para explicar fusion.
- Uso en la memoria: justificar una fusion robusta sin entrenamiento entre
  rankings heterogeneos.
- Relacion con el sistema: los resultados densos, BM25 y de grafo se combinan
  mediante RRF antes del reranking.

### Asai et al. (2023) - Self-RAG

- Clave sugerida: `asai2023selfrag`
- Fuente: <https://arxiv.org/abs/2310.11511>
- Prioridad: de apoyo.
- Uso en la memoria: citar como antecedente de recuperacion reflexiva, donde el
  sistema decide si recuperar y evalua utilidad del contexto.
- Relacion con el sistema: nuestra implementacion no entrena tokens de
  reflexion; se parece en la idea de no inyectar recuperacion de forma ciega.

### Yan et al. (2024) - Corrective Retrieval-Augmented Generation

- Clave sugerida: `yan2024crag`
- Fuente: <https://arxiv.org/abs/2401.15884>
- Prioridad: nuclear para CRAG.
- Uso en la memoria: justificar el evaluador de calidad de resultados y el
  fallback a web cuando la memoria interna no es suficiente.
- Relacion con el sistema: `crag.py` clasifica resultados recuperados como
  correctos, ambiguos o incorrectos, y puede complementar con busqueda web.

## Grafos de conocimiento y memoria a largo plazo

### Hogan et al. (2021) - Knowledge Graphs

- Clave sugerida: `hogan2021knowledgegraphs`
- Fuente: <https://arxiv.org/abs/2003.02320>
- Prioridad: nuclear para Neo4j.
- Uso en la memoria: introducir los grafos de conocimiento como representacion
  de entidades, relaciones, consultas y extraccion de conocimiento.
- Relacion con el sistema: Neo4j almacena `Paradigm`, `Paper`, `Variable`,
  `Postulate`, `Formulation`, `Model` y relaciones tipadas.

### Edge et al. (2024) - GraphRAG

- Clave sugerida: `edge2024graphrag`
- Fuente: <https://arxiv.org/abs/2404.16130>
- Prioridad: nuclear si se explica recuperacion con grafo.
- Uso en la memoria: situar el uso de grafos como indice sobre corpus privados
  frente al RAG plano basado solo en chunks.
- Relacion con el sistema: no implementamos exactamente GraphRAG con resumen de
  comunidades; si implementamos una memoria con entidades y relaciones que se
  puede recorrer localmente para aportar contexto multi-hop.

### Gutierrez et al. (2024) - HippoRAG

- Clave sugerida: `gutierrez2024hipporag`
- Fuente: <https://papers.nips.cc/paper_files/paper/2024/hash/6ddc001d07ca4f319af96a3024f6dbd1-Abstract-Conference.html>
- Prioridad: nuclear para memoria KG + PageRank.
- Uso en la memoria: referencia moderna para memoria a largo plazo que combina
  LLMs, grafos de conocimiento y Personalized PageRank.
- Relacion con el sistema: nuestra recuperacion de grafo usa enlazado de
  entidades y traversal local; la idea es afin a memoria relacional recuperable,
  aunque no replica el algoritmo completo de HippoRAG.

### Haveliwala (2002) - Topic-sensitive PageRank

- Clave sugerida: `haveliwala2002topicsensitive`
- Fuente: <https://ir.webis.de/anthology/2002.wwwconf_conference-2002.50/>
- Prioridad: de apoyo.
- Uso en la memoria: justificar ranking personalizado o sensible al contexto en
  grafos.
- Relacion con el sistema: util como antecedente si se explica el scoring local
  de vecinos o la inspiracion de Personalized PageRank.

### Park et al. (2023) - Generative Agents

- Clave sugerida: `park2023generativeagents`
- Fuente: <https://arxiv.org/abs/2304.03442>
- Prioridad: nuclear para memoria de agentes.
- Uso en la memoria: citar la arquitectura de agentes con observacion, memoria,
  reflexion y planificacion.
- Relacion con el sistema: MemoryAgent no simula humanos, pero si convierte
  experiencias aceptadas del pipeline en memoria recuperable para decisiones
  futuras.

### Zhong et al. (2023) - MemoryBank

- Clave sugerida: `zhong2023memorybank`
- Fuente: <https://arxiv.org/abs/2305.10250>
- Prioridad: de apoyo.
- Uso en la memoria: justificar memoria persistente con importancia, olvido y
  refuerzo temporal.
- Relacion con el sistema: `pipeline_memories` tiene importancia, confianza,
  access count, decaimiento y supersesion.

### Packer et al. (2023) - MemGPT

- Clave sugerida: `packer2023memgpt`
- Fuente: <https://arxiv.org/abs/2310.08560>
- Prioridad: de apoyo.
- Uso en la memoria: explicar el problema de ventana de contexto limitada y la
  idea de memoria jerarquica gestionada fuera del prompt inmediato.
- Relacion con el sistema: MinIO, Postgres, Neo4j y Qdrant actuan como memoria
  externa que no cabe en el contexto del modelo.

## Agentes, herramientas y flujo multiagente

### Yao et al. (2022/2023) - ReAct

- Clave sugerida: `yao2023react`
- Fuente: <https://arxiv.org/abs/2210.03629>
- Prioridad: nuclear para agentes con herramientas.
- Uso en la memoria: fundamentar la intercalacion de razonamiento y acciones
  sobre herramientas externas.
- Relacion con el sistema: los agentes llaman herramientas como `web_search`,
  `retrieve_knowledge`, `read_report`, `write_report` o `run_tests`.

### Schick et al. (2023) - Toolformer

- Clave sugerida: `schick2023toolformer`
- Fuente: <https://arxiv.org/abs/2302.04761>
- Prioridad: de apoyo.
- Uso en la memoria: antecedente de modelos que saben cuando usar APIs externas.
- Relacion con el sistema: nuestras herramientas estan orquestadas por prompts y
  schemas, no por autoentrenamiento como Toolformer.

### Wu et al. (2023) - AutoGen

- Clave sugerida: `wu2023autogen`
- Fuente: <https://arxiv.org/abs/2308.08155>
- Prioridad: de apoyo.
- Uso en la memoria: contextualizar aplicaciones LLM con multiples agentes,
  herramientas y participacion humana.
- Relacion con el sistema: el pipeline no es conversacional entre agentes, pero
  si divide responsabilidades entre agentes especializados y revision humana.

### Qian et al. (2023/2024) - ChatDev

- Clave sugerida: `qian2024chatdev`
- Fuente: <https://arxiv.org/abs/2307.07924>
- Prioridad: de apoyo.
- Uso en la memoria: antecedente de desarrollo de software mediante agentes
  especializados en fases.
- Relacion con el sistema: Researcher, Formalizer, Reasoner y Builder separan
  investigacion, modelado, adaptacion e implementacion.

### Yang et al. (2024) - SWE-agent

- Clave sugerida: `yang2024sweagent`
- Fuente: <https://arxiv.org/abs/2405.15793>
- Prioridad: nuclear para Builder.
- Uso en la memoria: justificar que la interfaz con el sistema de archivos,
  edicion y ejecucion de tests afecta al rendimiento de agentes de software.
- Relacion con el sistema: Builder escribe codigo, genera tests y ejecuta
  `uv run pytest` mediante herramientas controladas.

## Generacion de codigo, validacion y refinamiento

### Chen et al. (2021) - Codex / HumanEval

- Clave sugerida: `chen2021codex`
- Fuente: <https://arxiv.org/abs/2107.03374>
- Prioridad: nuclear para generacion de codigo.
- Uso en la memoria: base para explicar generacion de programas Python desde
  descripciones en lenguaje natural y evaluacion por correccion funcional.
- Relacion con el sistema: Builder produce clases Python y tests que validan el
  contrato `DecisionModel`.

### Austin et al. (2021) - Program Synthesis with LLMs

- Clave sugerida: `austin2021programsynthesis`
- Fuente: <https://arxiv.org/abs/2108.07732>
- Prioridad: de apoyo.
- Uso en la memoria: conectar la generacion de codigo con la sintesis de
  programas a partir de especificaciones naturales.
- Relacion con el sistema: el Reasoner transforma una formulacion en una
  especificacion ejecutable; Builder sintetiza el programa.

### Scholak, Schucher y Bahdanau (2021) - PICARD

- Clave sugerida: `scholak2021picard`
- Fuente: <https://arxiv.org/abs/2109.05093>
- Prioridad: de apoyo.
- Uso en la memoria: justificar validacion estructural y generacion restringida
  para evitar salidas invalidas.
- Relacion con el sistema: no usamos PICARD, pero si schemas, Pydantic,
  validacion de JSON y tests como barreras ante salidas invalidas.

### Madaan et al. (2023) - Self-Refine

- Clave sugerida: `madaan2023selfrefine`
- Fuente: <https://arxiv.org/abs/2303.17651>
- Prioridad: de apoyo.
- Uso en la memoria: antecedente de mejora iterativa mediante feedback.
- Relacion con el sistema: las puertas de revision humana y las rutas de rerun
  permiten refinar artefactos por etapas.

### Shinn et al. (2023) - Reflexion

- Clave sugerida: `shinn2023reflexion`
- Fuente: <https://arxiv.org/abs/2303.11366>
- Prioridad: de apoyo.
- Uso en la memoria: fundamentar aprendizaje por feedback verbal y memoria
  episodica sin actualizar pesos.
- Relacion con el sistema: la memoria no cambia pesos del modelo; almacena
  conocimiento aceptado y lo recupera en ejecuciones futuras.

## Paradigmas de decision: citar solo si aparecen en los experimentos

Estas referencias no son necesarias para explicar la arquitectura, pero si son
utiles si la memoria incluye modelos generados de estos paradigmas.

- Watkins y Dayan (1992), `watkins1992qlearning`, Q-learning:
  <https://pure.royalholloway.ac.uk/en/publications/q-learning/>
- Kahneman y Tversky (1979), `kahneman1979prospect`, Prospect Theory:
  <https://econpapers.repec.org/RePEc%3Aecm%3Aemetrp%3Av%3A47%3Ay%3A1979%3Ai%3A2%3Ap%3A263-91>
- Ratcliff (1978), `ratcliff1978memoryretrieval`, drift-diffusion / memoria:
  <https://philpapers.org/rec/RATATO-2>
- Rescorla y Wagner (1972), `rescorla1972pavlovian`, aprendizaje asociativo:
  referencia clasica en *Classical Conditioning II*.

## Criterio de uso en la memoria final

Para no sobrecargar una memoria de maximo 100 paginas:

- Estado del arte: RAG, ReAct, GraphRAG/HippoRAG, Codex/SWE-agent.
- Arquitectura de memoria: BM25, RRF, CRAG, Knowledge Graphs, MemoryBank o
  MemGPT.
- Flujo de agentes: ReAct, AutoGen/ChatDev, Self-Refine/Reflexion.
- Implementacion y validacion: Codex, Program Synthesis, PICARD, SWE-agent.
- Paradigmas cognitivos: solo las referencias asociadas a los modelos realmente
  generados y evaluados.

La redaccion debe evitar afirmar que el sistema implementa exactamente todos
estos trabajos. La formula correcta es: "se inspira en", "adopta el patron de",
"comparte el objetivo de" o "usa una decision compatible con".
