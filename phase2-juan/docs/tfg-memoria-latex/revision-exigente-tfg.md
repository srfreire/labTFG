# Revisión exigente del TFG

Documento revisado: `JUANFREIREALVAREZ_TFG.pdf` y fuentes LaTeX asociadas.
Fecha de revisión: 2026-07-01.
Alcance: diagnóstico académico, formal, narrativo y bibliográfico. No se ha reescrito la memoria.

## 1. Resumen ejecutivo

La memoria está en un estado alto para entrega: estructura completa de TFG tipo B, objetivos claros, trazabilidad entre fases, pruebas con datos, apéndices útiles y bibliografía mayoritariamente verificada. El PDF compila con `tectonic` sin errores y sin `Overfull`/`Underfull` relevantes; solo quedan avisos menores de `inputenc` ignorado por motor UTF-8 y un aviso PGF no bloqueante.

Los tres puntos que un tribunal detectaría antes son: 1) la defensa del uso de Codex como juez externo sigue siendo el flanco metodológico más preguntable, aunque ya está bastante bien acotado; 2) la terminología técnica inglesa es abundante y necesita una política única de traducción/cursiva/primera aparición; 3) la extensión total es alta por apéndices y bibliografía, aunque el cuerpo principal son 55 páginas no blancas.

El texto suena bastante humano. No hay un problema general de "sabor a IA"; sí aparecen pasajes algo ensayísticos en desarrollo y conclusiones, y varias tablas densas que un tribunal poco técnico puede leer como acumulación de nombres.

La bibliografía ha mejorado respecto al estado anterior: no he detectado citas fantasma ni referencias huérfanas. Las 24 referencias citadas están presentes en bibliografía y las URLs/DOI principales resuelven. Quedan matices de estilo y de año/venue en referencias recientes, no errores graves.

## 2. Puntuación estimada según rúbrica

| Ítem | Nota /10 | Peso | Qué falta para subir |
|---|---:|---:|---|
| Portada | 8.5 | 0.25 | Contiene centro, titulación, autor, tutor, título y fecha. Solo falta contrastar con plantilla oficial si exige curso académico, mes o formato exacto de tutor. |
| Índice y numeración | 9 | 0.5 | Índice, figuras y cuadros existen; numeración coherente tras compilación. Revisar de nuevo después de cualquier edición. |
| Extensión máxima | 8 | 1 | PDF: 105 páginas físicas; cuerpo principal: 58 páginas árabes menos 3 blancas = 55. Confirmar cómo computan apéndices y bibliografía en el reglamento aplicado. |
| Corrección y legibilidad | 8 | 1.5 | Buena redacción. Para subir: reducir densidad de tablas, unificar anglicismos y evitar frases largas con demasiados nombres técnicos. |
| Resumen | 8.5 | 1.5 | Claro y centrado. Puede subir si añade una frase cuantitativa mínima: dos casos, 387 pruebas, informes PDF reales. |
| Introducción | 8.5 | 2 | Problema, objetivo y fases quedan claros. Para subir: definir antes o en nota breve términos como `pipeline`, Knowledge Backbone, RAG y `tool call`. |
| Estructura | 9 | 0.5 | Estructura tipo B completa. Los apéndices están justificados. Revisar si "Licencia" debe ir antes/después de bibliografía según plantilla ETSE. |
| Conclusiones y ampliaciones | 8.5 | 2 | Buen enlace con objetivos. Para subir: añadir una mini-tabla objetivo -> evidencia -> sección, o enumerar explícitamente cada objetivo cumplido. |
| Bibliografía | 8.5 | 0.75 | Sin fantasma/huérfanas y URLs verificadas. Para subir: homogeneizar estilo de arXiv/DOI/OpenReview/libro e incorporar ISBN o DOI faltante donde proceda. |
| Alcance y cumplimiento de objetivos | 8.5 | 2 | Alcance adecuado. Puede subir con una tabla explícita de cumplimiento objetivo-evidencia. |
| Especificación de requisitos | 8 | 2 | Requisitos claros y trazados. Para subir: adelantar algún criterio de aceptación observable al capítulo principal, no dejar casi todo en apéndice. |
| Tecnologías, diseño e implementación | 8.5 | 3 | Sólido y defendible. Para subir: explicar con una frase simple las tecnologías de infraestructura la primera vez que aparecen. |
| Pruebas | 8.5 | 3 | Buen enfoque mixto con pruebas, casos, juez externo y revisión experta. Para subir: remarcar todavía más que dos casos y una semilla no generalizan rendimiento. |
| Defensa documental | 8.5 | 15% orientativo | Permite una defensa clara. Riesgos: preguntas sobre juez LLM, coste/latencia, frontera entre fases y por qué la rejilla 2D basta. |

Nota global ponderada estimada: **8.4/10**. Con cambios localizados en terminología, extensión percibida, tablas y defensa metodológica puede acercarse a **8.7-8.9**.

## 3. Hallazgos por prioridad

### Crítico

| Ubicación | Qué está mal | Por qué penaliza | Corrección propuesta |
|---|---|---|---|
| `capitulos/05-pruebas.tex:121-158`, p. 47-50 | El uso de Codex como juez externo está mejor delimitado, pero todavía se apoya en que es "de otra familia". Eso reduce sesgo de autoevaluación, pero no demuestra independencia metodológica fuerte. | Un miembro técnico puede preguntar si un LLM puede validar a otro y si hay acuerdo humano medido. | Añadir tras el párrafo de independencia: "La independencia entre familias de modelos no convierte el juicio en verdad de referencia; solo reduce el riesgo de autoevaluación. Por eso las puntuaciones se interpretan como una auditoría de consistencia factual y se contrastan con revisión experta, no como validación científica automática." |
| `capitulos/05-pruebas.tex:257-283`, p. 53-54 | La limitación de dos casos, una semilla y juez aproximado aparece al final. Está bien, pero conviene anticiparla justo antes de presentar puntuaciones 88/100 y 86/100. | Si el tribunal ve las notas antes de la limitación, puede leerlas como generalización excesiva. | Antes de la tabla de resultados: "Las puntuaciones no miden rendimiento general del laboratorio, sino fidelidad factual en dos ejecuciones instrumentadas concretas." |
| Extensión global del PDF | 105 páginas físicas, 91 páginas árabes hasta bibliografía; cuerpo principal no blanco de 55 páginas. | Un tribunal poco técnico puede reaccionar a la longitud antes de distinguir cuerpo/apéndices. | En defensa o nota interna: preparar frase breve: "El cuerpo principal ocupa 55 páginas efectivas; el resto son apéndices técnicos, capturas y bibliografía." |

### Importante

| Ubicación | Qué está mal | Por qué penaliza | Corrección propuesta |
|---|---|---|---|
| `capitulos/00-introducion.tex:78-92`, p. 3-4 | `pipeline`, Orchestrator y agentes se explican, pero `pipeline` queda en inglés sin regla clara. | Terminología visible y repetida. | Primera aparición: "un flujo de agentes (`pipeline`, en la terminología del sistema)". Después usar "flujo" en prosa y `pipeline` solo como nombre técnico. |
| `capitulos/01-estado-del-arte.tex:88-127`, p. 5-6 | RAG, `dense retrieval`, `embeddings`, BM25, RRF, GraphRAG, grafo e índice disperso aparecen en pocos párrafos. Hay explicación, pero la carga de siglas sigue siendo alta. | Un lector no técnico entiende la idea, pero puede perder la función de cada pieza. | Añadir una frase puente antes de RRF: "En resumen, el sistema usa dos maneras de buscar: una por parecido de significado y otra por coincidencia literal de palabras." |
| `capitulos/03-diseño.tex:20-35`, p. 15 | "orquestación agéntica" puede sonar a jerga si no se reformula. | Es una de las tres decisiones principales; debe ser inmediatamente entendible. | Cambiar por "orquestación de agentes" o añadir: "es decir, decidir qué agente actúa y con qué información". |
| `capitulos/03-diseño.tex:45-161`, p. 15-16 | Dos figuras UML muy seguidas al inicio del capítulo. Compila bien, pero visualmente puede arrancar denso. | El tribunal poco técnico puede desconectar al empezar diseño. | Insertar una frase de lectura antes de la segunda figura: "La primera figura muestra dónde se ejecuta cada pieza; la segunda baja al nivel de componentes software." |
| `capitulos/04-desarroll.tex:21-49`, p. 33-34 | El contraste con el ciclo clásico es interesante, pero algunas afirmaciones son amplias: "los modelos actuales actúan como ejecutores principales". | Puede sonar más a ensayo sobre IA que a desarrollo del TFG. | Sustituir por: "En este proyecto, cuando los modelos actuaron como ejecutores principales..." |
| `capitulos/04-desarroll.tex:280-304`, p. 40 | La tabla de tecnologías es muy densa: 12 filas con nombres, proveedores y librerías. | Penaliza legibilidad; parece inventario. | Dividir mentalmente o en texto: primero componentes propios; después servicios externos. Si no se divide, añadir una frase: "La tabla no enumera dependencias menores, sino las piezas que condicionan decisiones de diseño." |
| `capitulos/04-desarroll.tex:397-413`, p. 43 | Otra tabla densa de verificación. Es útil, pero se suma a varias tablas cercanas. | Puede dar sensación de documentación pesada. | Recortar texto de celdas y mover una explicación al párrafo anterior. |
| `capitulos/06-conclusiones.tex:130-150`, p. 58 | La reflexión final es humana, pero algo editorial. | En una memoria técnica conviene que el cierre no parezca manifiesto. | Versión más sobria: "La asistencia de agentes permitió desplazar esfuerzo desde la escritura de código hacia especificación, revisión y verificación. Ese cambio hizo viable una plataforma más amplia, pero las decisiones de alcance, arquitectura y aceptación siguieron dependiendo del autor." |

### Menor

| Ubicación | Qué está mal | Por qué penaliza | Corrección propuesta |
|---|---|---|---|
| Todo el documento | Alternan `backend`, `frontend`, cliente web, API, interfaz, dashboard. | No rompe, pero resta uniformidad. | Usar "cliente web" en prosa; `frontend` solo en tecnología/código. Usar "backend" como componente técnico una vez definido. |
| Todo el documento | `Knowledge Backbone`, backbone, capa compartida, memoria compartida, grafo. | Puede parecer que son piezas distintas. | Definir jerarquía estable: Knowledge Backbone = capa compartida; grafo de conocimiento = parte en Neo4j; memorias = parte en Qdrant/PostgreSQL. |
| `capitulos/05-pruebas.tex:76-82`, p. 48 | "verificación determinista de anclaje" es preciso pero denso. | Concepto clave para defensa. | Añadir ejemplo breve: "por ejemplo, que los consumos contados por el informe coincidan con los eventos registrados." |
| `capitulos/apendicec.tex:53-56`, p. 68 | Mezcla estados `PASA`, `Manual` y conteos en la misma tabla. | Puede parecer que lo manual no está verificado. | Añadir nota: "`Manual` indica pruebas ejecutadas sobre entorno vivo, no ausencia de comprobación." |
| `capitulos/apendicee.tex`, p. 73-81 | Galería de interfaz con muchas capturas y poco texto explicativo. | Las figuras pueden parecer decorativas. | Añadir frase inicial: "Estas capturas documentan los estados inspeccionables de una sesión completa." |

## 4. Terminología unificada

| Término elegido | Variantes a controlar | Regla propuesta |
|---|---|---|
| flujo de agentes | pipeline, flujo, recorrido, ciclo | Usar "flujo" en explicación general; `pipeline` solo en primera aparición o cuando se nombre el mecanismo técnico. |
| Orchestrator | orquestador, coordinador, agente coordinador | Mantener "Orchestrator" como nombre propio; definir una vez como coordinador de sesión. |
| agentes especializados | subagentes, agentes, componentes | Para Architect/Tracker/Analyst/Reporter usar "agentes especializados"; reservar "subagentes" para agentes usados durante desarrollo. |
| Knowledge Backbone | backbone, capa compartida, capa de conocimiento | Mantener nombre propio. Explicación: capa compartida de memoria, documentos y grafo. |
| grafo de conocimiento | Knowledge Graph, grafo, Neo4j | "Grafo de conocimiento" para concepto; "Neo4j" para tecnología. |
| memoria de simulación | memoria compartida, observaciones persistidas | Usar para observaciones recuperables de simulaciones. |
| recuperación aumentada | RAG, recuperación externa | Definir RAG una vez; después usar "recuperación aumentada" salvo nombres propios. |
| índice denso | dense retrieval, embeddings | "Índice denso"; explicar `embedding` como vector semántico en primera aparición. |
| índice disperso | sparse, BM25 nativo | "Índice disperso"; `sparse` solo entre paréntesis/cursiva si hace falta. |
| llamada a herramienta | tool call, llamada a función | Prosa: "llamada a herramienta"; `tool call` en primera aparición y apéndice. |
| juez externo | Codex, evaluador externo, LLM-as-a-judge | "Juez externo" para el rol; "Codex" para la implementación; "LLM-as-a-judge" para método citado. |
| informe | reporte, report, PDF del Reporter | En castellano, "informe"; "Reporter" solo para el agente. |

## 5. Inventario de inconsistencias de formato

| Ubicación | Inconsistencia | Acción |
|---|---|---|
| `JUANFREIREALVAREZ_TFG.tex` | `\usepackage[utf8]{inputenc}` con motor UTF-8 produce warning ignorado. | No afecta al PDF. Si se quiere compilar limpio del todo, retirar `inputenc` cuando se use XeTeX/tectonic. |
| Log de compilación | Aviso PGF: "Returning node center instead of a point on node border". | Menor. Revisar solo si alguna flecha TikZ toca centros de nodos de forma rara. |
| Todo el documento | Anglicismos con tratamiento irregular: `pipeline`, `backend`, `frontend`, `tool calls`, `sparse`, `coding agents`, `dashboard`, `replay`. | Primera aparición en cursiva con traducción; después uso consistente. |
| `capitulos/03-diseño.tex` y `apendicef.tex` | Figuras UML usan mezclas de inglés técnico (`Frontend`, `Backend Phase 2`, `LLM providers`) y español. | Aceptable si son nombres de componente, pero conviene homogeneizar etiquetas visibles: "Backend fase 2", "Proveedores LLM". |
| Tablas de capítulos 4 y 5 | Celdas largas con varias ideas por celda. | Reducir o separar con punto y coma; evitar que una tabla haga de párrafo comprimido. |
| Índice de cuadros | El texto habla de tablas, pero LaTeX genera "Índice de cuadros". | Si se quiere coherencia visible: redefinir `\tablename` y `\listtablename` a "Tabla"/"Índice de tablas". |
| Bibliografía | Estilo IEEE-like bastante homogéneo, pero mezcla arXiv, DOI, OpenReview, PDF de IJCAI y libro sin ISBN. | Aceptable. Para subir nota, añadir DOI/venue completo cuando exista e ISBN en libro. |

## 6. Informe de bibliografía

Verificación web realizada sobre las 24 referencias citadas. Fuentes consultadas: arXiv, ACM Digital Library, OpenReview, IJCAI, INFORMS/SSRN, IEEE/ACM, Wiley, Taylor & Francis, eLife, PubMed y University of Chicago Press. No hay referencias fantasma ni huérfanas.

| Clave | Estado | Observación |
|---|---|---|
| `lewis2020rag` | OK | arXiv `2005.11401` y NeurIPS 2020 corresponden a RAG. |
| `robertson2009bm25` | OK | DOI `10.1561/1500000019` resuelve a "The Probabilistic Relevance Framework: BM25 and Beyond", vol. 3, no. 1-2. |
| `cormack2009rrf` | OK | DOI `10.1145/1571941.1572114`, SIGIR 2009, pp. 758-759. |
| `edge2024graphrag` | OK | arXiv `2404.16130`; 2024 como preprint inicial es correcto. |
| `hogan2021knowledgegraphs` | OK | arXiv `2003.02320`; ACM CSUR 54(4), art. 71. |
| `hong2024metagpt` | OK | OpenReview `VtmBAGCN7o`, ICLR 2024. |
| `guo2024llmbased` | OK | IJCAI 2024 proceedings, artículo 890, pp. 8048-8057; DOI ACM también localizable. |
| `yao2023react` | OK | arXiv `2210.03629`, ICLR 2023. |
| `madaan2023selfrefine` | OK | arXiv `2303.17651`. |
| `shinn2023reflexion` | OK | arXiv `2303.11366`; citar como preprint es aceptable. |
| `jimenez2024swebench` | OK | OpenReview `VTF8yNQM66`, ICLR 2024; arXiv `2310.06770` también existe. |
| `cui2025effects` | OK con matiz | DOI `10.1287/mnsc.2025.00535`; la cita usa Management Science 2026. La clave interna 2025 no importa, pero el texto debe mantener 2026 si cita versión de revista. |
| `butler2024dear` | OK | DOI `10.1109/ICSE-SEIP66354.2025.00034`, ICSE-SEIP 2025, pp. 319-329; arXiv `2410.18334` existe. |
| `epstein1999abm` | OK | DOI Wiley resuelve a Complexity 4(5), pp. 41-60. |
| `railsback2019abm` | OK parcial | Libro real, 2ª edición, Princeton University Press, 2019. Añadir ISBN si se quiere cita completa. |
| `sargent2013vv` | OK | DOI `10.1057/jos.2012.20`, Journal of Simulation 7(1), pp. 12-24. |
| `mohammadi2025agenteval` | OK | DOI `10.1145/3711896.3736570`, "Evaluation and Benchmarking of LLM Agents: A Survey", KDD 2025, pp. 6129-6139. |
| `zheng2023judge` | OK | arXiv `2306.05685`, MT-Bench/Chatbot Arena; respalda uso y límites de LLM-as-a-judge. |
| `li2024judges` | OK | arXiv `2412.05579`, survey LLMs-as-judges. |
| `calm2024biases` | OK | arXiv `2410.02736`, sesgos en LLM-as-a-judge. |
| `wilson2019tenrules` | OK | DOI `10.7554/eLife.49547`, eLife 2019. |
| `palminteri2017falsification` | OK | DOI `10.1016/j.tics.2017.03.011`, Trends in Cognitive Sciences 21(6), pp. 425-433. |
| `charnov1976mvt` | OK | DOI `10.1016/0040-5809(76)90040-X`, Theoretical Population Biology 9(2), pp. 129-136. |
| `macarthur1966dietbreadth` | OK | DOI `10.1086/282454`, The American Naturalist 100(916), pp. 603-609. |

Referencias fantasma: **ninguna**.
Referencias huérfanas: **ninguna**.

Fuentes web principales usadas para la comprobación: arXiv para RAG, GraphRAG, ReAct, Self-Refine, Reflexion y jueces LLM; ACM para BM25, RRF y Mohammadi; OpenReview para MetaGPT y SWE-bench; IJCAI para Guo; SSRN/INFORMS para Cui; IEEE/ACM para Butler; Wiley/Taylor/PubMed/eLife/University of Chicago para simulación y conducta.

## 7. Repeticiones y solapamientos

| Idea repetida / solapada | Ubicaciones | Acción recomendada |
|---|---|---|
| Relación fase 1 -> fase 2 | Introducción 1.1-1.4; diseño 3.2; conclusiones 6.1; apéndice A | Mantener explicación completa en introducción; en diseño solo contrato técnico; en conclusiones solo evidencia de cumplimiento. |
| Knowledge Backbone | Introducción 1.4; estado del arte; diseño; desarrollo; apéndices A/B/F/G; conclusiones | Definir una vez y luego usar según nivel: arquitectura en diseño, operación en apéndices, lección en conclusiones. |
| Desarrollo asistido por agentes | Estado del arte 1.x; desarrollo capítulo 4; reflexión final | Estado del arte: referencias. Desarrollo: método usado. Reflexión final: máximo una conclusión breve. |
| Codex como juez externo | Pruebas 5.1, 5.3, 5.4, 5.5; conclusiones | Concentrar justificación en 5.3. En 5.1 anticipar metodología y en conclusiones solo recoger límite/futuro. |
| Pruebas automatizadas | Capítulo 5; apéndice A; apéndice C | Capítulo 5: significado y resultados. Apéndice C: detalle. Apéndice A: cómo ejecutarlas. |
| Limitaciones de LLMs | Estado del arte, desarrollo, pruebas, conclusiones | Evitar repetir "alucinación/contexto/revisión humana" con palabras distintas. Cada capítulo debe tratar una dimensión distinta. |

## 8. Pasajes con tono a pulir

| Ubicación | Patrón | Reescritura propuesta |
|---|---|---|
| `capitulos/00-introducion.tex:7-16` | Tono narrativo-personal correcto, pero algo informal para tribunal conservador. | "El punto de partida fue un TFM previo tutorizado por Eduardo Manuel Sánchez Vila, que ya planteaba una primera intuición de entorno de simulación. A partir de esa base se definieron el alcance, la arquitectura y la división del proyecto en dos fases." |
| `capitulos/04-desarroll.tex:29-49` | Generalización sobre modelos actuales. | "En este proyecto, cuando los modelos actuaron como ejecutores principales, escribir una función concreta a partir de una especificación clara dejó de ser la parte más costosa. El esfuerzo se desplazó hacia especificar, revisar y verificar." |
| `capitulos/04-desarroll.tex:463-470` | "Si uno se deja llevar..." suena conversacional. | "Cuando la generación acelera el ritmo de cambios, aumenta el riesgo de aceptar modificaciones poco revisadas. Para evitarlo, ningún cambio se consideró cerrado hasta pasar revisión combinada y, cuando afectaba a la interfaz, comprobación manual." |
| `capitulos/06-conclusiones.tex:130-150` | Cierre algo ensayístico. | "La asistencia de agentes permitió abordar una plataforma más amplia, pero no eliminó la necesidad de criterio humano. La especificación, la revisión y la aceptación siguieron siendo responsabilidad del autor." |

## 9. Cambios localizados recomendados antes de entregar

1. Añadir dos frases de blindaje metodológico en `05-pruebas.tex` sobre Codex: auditoría factual, no validación científica.
2. Preparar una nota defensiva sobre extensión: cuerpo principal de 55 páginas no blancas.
3. Unificar política de anglicismos: primera aparición con traducción y cursiva; después forma estable.
4. Reducir o contextualizar las tablas más densas de los capítulos 4 y 5.
5. Añadir una frase puente para RAG/BM25/GraphRAG pensada para lector no técnico.
6. Recortar la reflexión final si se busca un tono más sobrio.
7. Opcional: configurar LaTeX para "Tabla" e "Índice de tablas" en lugar de "Cuadro/Índice de cuadros".
