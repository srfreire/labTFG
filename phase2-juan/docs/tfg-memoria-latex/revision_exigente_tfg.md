# Revision exigente de la memoria TFG

Documento revisado: `JUANFREIREALVAREZ_TFG.pdf` y fuentes LaTeX en `phase2-juan/docs/tfg-memoria-latex/`.

## 1. Resumen ejecutivo

La memoria esta en un estado academico solido: el alcance se entiende, los objetivos son verificables y hay una evaluacion bastante mas concreta de lo habitual para un TFG de desarrollo. El riesgo principal no es la falta de trabajo, sino la presentacion: hay fallos visibles en indices, apendices y bibliografia que un tribunal mixto puede penalizar aunque no entre al codigo.

Los tres problemas mas graves son:

1. El fuente principal actual no incluye `capitulos/apendicef.tex`, aunque el texto remite a diagramas de arquitectura. Esto desordena apendices y deja fuera material que el lector espera.
2. El indice de figuras muestra numeracion fuera de orden en el capitulo 3: aparece `3.2`, luego `3.6`, luego `3.1`. Es un fallo muy visible.
3. La bibliografia tiene al menos un dato incorrecto confirmado: Robertson y Zaragoza esta citado como vol. 3, pp. 333-389, pero el DOI confirma vol. 4, no. 1-2, pp. 1-174.

Nota global estimada, si se entrega asi: **8,0/10 - 8,3/10**. Con los problemas de numeracion, apendices y bibliografia corregidos, subiria razonablemente a **8,6/10 - 8,9/10**.

## 2. Puntuacion por rubrica

| Bloque | Item | Nota | Peso | Que falta para subir |
|---|---:|---:|---:|---|
| Documentacion | Portada | 8,0 | 0,25 | Confirmar si la ETSE exige certificacion/hoja de autorizacion. Existe `00-certificacion.tex`, pero no se incluye. |
| Documentacion | Indice y numeracion | 6,5 | 0,5 | Corregir orden de figuras 3.1/3.2/3.6 y numeracion de apendices/tablas tras el apendice E. |
| Documentacion | Extension maxima | 8,0 | 1,0 | 105 paginas totales; cuerpo principal 58 paginas. Parece razonable, pero conviene confirmar limite exacto ETSE/USC. |
| Documentacion | Correccion y legibilidad | 8,0 | 1,5 | Reducir tablas densas y suavizar pasajes con tono demasiado narrativo o meta. |
| Documentacion | Resumen | 8,5 | 1,5 | Esta claro; anadir una frase mas concreta sobre "que se evalua" y no solo "como". |
| Documentacion | Introduccion | 8,5 | 2,0 | Buen problema y objetivos. Falta anticipar mejor limitaciones y alcance exacto de "validar/observar". |
| Documentacion | Estructura | 7,0 | 0,5 | Falta `apendicef` en el `main` actual y no esta incluida la certificacion. |
| Documentacion | Conclusiones/ampliaciones | 8,0 | 2,0 | Buen cierre, pero la reflexion final repite la idea de amplitud/agentes. |
| Documentacion | Bibliografia | 7,0 | 0,75 | Corregir Robertson/Zaragoza, homogeneizar editoriales/venues y anadir URL a Railsback/Grimm. |
| Calidad TFG | Alcance y objetivos | 8,5 | 2,0 | Objetivos cubiertos; reforzar cada objetivo con evidencia concreta en una tabla principal, no solo apendice. |
| Calidad TFG | Requisitos | 8,0 | 2,0 | Requisitos completos; tablas algo densas y algun RNF podria vincularse mejor a prueba. |
| Calidad TFG | Tecnologias/diseno/implementacion | 8,5 | 3,0 | Muy buen nivel; corregir diagramas fuera de orden y mover diagramas de arquitectura al apendice correcto o mantenerlos en capitulo 3. |
| Calidad TFG | Pruebas | 8,0 | 3,0 | Buenas pruebas; falta una frase mas defensiva sobre validez externa y sobre que las 387 pruebas no sustituyen validacion cientifica. |
| Defensa | Claridad defendible | 8,0 | 15% | Las ideas principales estan, pero los errores visibles distraerian al tribunal antes de llegar a lo bueno. |

## 3. Hallazgos por prioridad

### Critico 1 - Apendice de diagramas no incluido

Ubicacion: `JUANFREIREALVAREZ_TFG.tex`, lineas 108-125.

Que ocurre: el documento incluye A, B, C, D, E, despues salta directamente a `apendiceg`, `licenza` y bibliografia. No se incluye `capitulos/apendicef.tex`, aunque ese archivo existe y contiene `fig:arquitectura` y `fig:memoria-simulacion`.

Por que penaliza: el lector ve referencias a diagramas de arquitectura y espera un apendice especifico. Si el PDF final queda sin ese apendice, parece un error de ensamblado. Si queda incluido por restos de compilacion anteriores, el problema es peor: fuente y PDF no son reproducibles.

Correccion concreta:

```tex
\include{capitulos/apendicee}
\cleardoublepage
\include{capitulos/apendicef}
\cleardoublepage
\include{capitulos/apendiceg}
```

Despues compilar dos veces y revisar `.toc`, `.lof` y `.lot`.

### Critico 2 - Indice de figuras fuera de orden

Ubicacion: PDF, indice de figuras; fuente en `capitulos/03-diseño.tex`, lineas 36-105 y 105-161.

Que ocurre: el indice lista `3.2 Diagrama de componentes UML` en pagina 16, luego `3.6`, y despues `3.1 Diagrama de despliegue UML` en pagina 28.

Por que penaliza: es de las primeras paginas que mira un tribunal. Da sensacion de documento recompuesto a ultima hora.

Correccion concreta: no dejar el diagrama de despliegue como `figure[p]` si el texto lo presenta antes. Usar el mismo criterio que el diagrama de componentes:

```tex
\begin{figure}[H]
...
\caption[Diagrama de despliegue UML]{...}
\label{fig:despliegue-uml}
\end{figure}
```

Si no cabe bien, mover ambos diagramas al apendice de arquitectura y en el capitulo 3 sustituir por una referencia breve.

### Importante 1 - Certificacion preparada pero no incluida

Ubicacion: existe `capitulos/00-certificacion.tex`, pero `JUANFREIREALVAREZ_TFG.tex` no la incluye.

Que ocurre: hay un archivo de certificacion, pero no entra en el PDF.

Por que penaliza: si el reglamento o plantilla de la ETSE la espera, falta una pieza administrativa. Aunque no puntue mucho, es un fallo de entrega.

Correccion concreta: confirmar con plantilla oficial/tutor. Si aplica, incluir despues de portada:

```tex
\include{capitulos/00-titulo}
\cleardoublepage
\include{capitulos/00-certificacion}
\cleardoublepage
```

### Importante 2 - Error bibliografico confirmado en BM25

Ubicacion: `capitulos/bibliografia.tex`, lineas 12-16.

Que ocurre: la referencia dice vol. 3, no. 1-2, pp. 333-389. Crossref para DOI `10.1561/1500000019` devuelve vol. 4, no. 1-2, pp. 1-174.

Correccion lista:

```tex
S. E. Robertson and H. Zaragoza, ``The probabilistic relevance framework:
BM25 and beyond,'' \emph{Found. Trends Inf. Retr.}, vol.~4, no.~1--2,
pp.~1--174, 2009. Accessed: Jun. 2026. [Online]. Available:
\url{https://doi.org/10.1561/1500000019}
```

### Importante 3 - Acronimos sin disciplina de primera aparicion

Ubicaciones representativas: `00-introducion.tex` lineas 17-26; `01-estado-del-arte.tex` lineas 46, 88-99; `05-pruebas.tex` lineas 20-24.

Problema: aparecen `TFG`, `TFM`, `LLM`, `RAG`, `BM25`, `RRF`, `UML`, `API`, `SQL`, `PDF` y `WebSocket`. Algunos se entienden por contexto, pero no todos se definen con patron uniforme.

Correccion concreta: usar primera aparicion con nombre expandido + sigla, y despues solo sigla. Ejemplo:

> La recuperacion aumentada con generacion (\textit{retrieval-augmented generation}, RAG) ...

> Los modelos de lenguaje de gran tamano (\textit{large language models}, LLM) ...

### Importante 4 - El capitulo de pruebas confiesa reservas pero no las cierra

Ubicacion: `05-pruebas.tex`, lineas 168-219.

Problema: se indica "aprobado con reservas" y se mencionan errores locales en CASO1/CASO2. Eso es honesto, pero un tribunal puede preguntar: "si ya sabe que hay errores, por que no estan corregidos?".

Correccion propuesta: anadir una frase de cierre:

> Las reservas detectadas no se incorporan como conclusiones cientificas del trabajo; se mantienen como errores locales de las salidas generadas y quedan acotadas por la verificacion determinista de anclaje. La decision de conservarlas en la memoria responde a que forman parte de la evaluacion del laboratorio: muestran que la infraestructura permite detectar desviaciones del Analyst o del Reporter frente a los datos de simulacion.

### Importante 5 - Tablas densas en requisitos y pruebas

Ubicacion: PDF pagina 11; `02-especificacion-de-requisitos.tex`, tabla de RF.

Problema: la tabla es legible, pero densa. Un miembro poco tecnico puede desconectar.

Correccion: partir requisitos funcionales en dos tablas: RF-01 a RF-07 "flujo principal" y RF-08 a RF-13 "persistencia, historial e interfaz".

### Menor 1 - Frases con tono demasiado narrativo o coloquial

Ubicacion: `00-introducion.tex`, lineas 7-15; `06-conclusiones.tex`, reflexion final.

Problema: el tono es humano, pero algunas frases son demasiado personales para el cuerpo tecnico.

Propuesta para introduccion:

Texto actual:

> Aquella base era todavía limitada, pero tenía algo valioso: una forma clara de convertir una idea de investigación en un sistema observable.

Version mas academica:

> Aunque aquella base tenía un alcance limitado, introducía una idea central para este trabajo: transformar una propuesta de investigación en un sistema observable y ejecutable.

### Menor 2 - Listas de apendices en una frase demasiado larga

Ubicacion: `00-introducion.tex`, lineas 142-148.

Correccion lista:

> Los apendices recogen el manual tecnico, el manual de usuario, el detalle de la bateria de pruebas, la trazabilidad de requisitos, la galeria de la interfaz, el catalogo de \textit{tool calls} y la licencia. La bibliografia reune las referencias sobre agentes inteligentes, simulacion, recuperacion aumentada, grafos de conocimiento, evaluacion de agentes y modelos de decision.

## 4. Terminologia unificada

| Termino elegido | Variantes detectadas o a vigilar | Criterio |
|---|---|---|
| Orchestrator | orquestador, agente coordinador | Mantener `Orchestrator` como nombre propio del componente; explicar una vez que actua como coordinador. |
| Knowledge Backbone | capa de conocimiento compartida, backbone, Knowledge Graph, grafo | Usar `Knowledge Backbone` para la capa completa; `Knowledge Graph` solo para la vista/grafo Neo4j. |
| pipeline | flujo, cadena, secuencia canonica | Elegir: `pipeline` para el mecanismo del sistema; `flujo` para explicacion general. Evitar alternarlos como sinonimos tecnicos. |
| modelos de decision | modelos, agentes simulados, paradigmas | `modelo de decision` para codigo ejecutable; `agente simulado` solo cuando esta instanciado en el entorno; `paradigma` para la teoria. |
| observacion | registro, traza, evento, episodio | `observacion` como artefacto global; `evento`, `trayectoria` y `episodio` como subtipos. |
| informe PDF | reporte, report, informe | Mantener `informe PDF`; `Reporter` solo como agente. |
| LLM | modelo de lenguaje, modelo, proveedor | Definir una vez `modelo de lenguaje de gran tamano (LLM)` y no usar `modelo` solo cuando pueda confundirse con modelo de decision. |
| memoria de simulacion | observacion persistida, memoria reutilizable | Elegir `memoria de simulacion` para lo persistido en Qdrant/PostgreSQL. |

## 5. Inconsistencias de formato

| Ubicacion | Inconsistencia | Accion |
|---|---|---|
| Indice de figuras | Numeracion 3.2, 3.6, 3.1, 3.3... | Corregir flotantes o mover diagramas al apendice. |
| Indice general / apendices | `apendicef.tex` existe pero no esta incluido en `main` | Incluirlo o eliminar referencias y archivo. |
| Indice de tablas | Tablas del catalogo aparecen como F.*, no G.*, si se esperaba apendice G | Recompilar tras incluir `apendicef`; limpiar auxiliares. |
| Bibliografia | Mezcla arXiv, DOI, OpenReview, editorial sin URL | Mantener estilo IEEE, pero anadir URL/fecha a libro si se quiere homogeneidad. |
| Terminos ingleses | `pipeline`, `tool calls`, `coding agents`, `dashboard`, `replay`, `reranking` | Mantener cursiva en anglicismos comunes salvo nombres propios/API. |
| Tablas | Algunas tablas tecnicas usan letra pequena y celdas largas | Dividir tablas densas o mover detalle a apendice. |
| Capitulos | `04-desarroll.tex` nombre de archivo en gallego/cortado; no afecta PDF | No es urgente, pero conviene evitar nombres ambiguos en fuente final. |

## 6. Informe de bibliografia

Verificacion realizada con DOI/arXiv/OpenReview/IJCAI/ACM/Princeton cuando fue posible. Las citas en LaTeX coinciden con las referencias: no se detectan referencias fantasma ni huerfanas.

| Clave | Estado | Observacion |
|---|---|---|
| `lewis2020rag` | OK | arXiv `2005.11401` resuelve y titulo/autores coinciden. |
| `robertson2009bm25` | Dato erroneo | DOI existe, pero volumen/paginas estan mal: debe ser vol. 4, no. 1-2, pp. 1-174. |
| `cormack2009rrf` | OK | DOI ACM existe; paginas 758-759 correctas. |
| `edge2024graphrag` | OK | arXiv `2404.16130` resuelve. |
| `hogan2021knowledgegraphs` | OK | arXiv resuelve; falta DOI ACM si se quiere version final de revista. |
| `hong2024metagpt` | OK con matiz | OpenReview resuelve. Conviene revisar autores: la lista larga oficial empieza por Sirui Hong y Mingchen Zhuge; la entrada actual usa `S. Hong, X. Zheng...`, posible orden incompleto segun version. |
| `guo2024llmbased` | OK | IJCAI 2024, paper 890, PDF resuelve. |
| `yao2023react` | OK | arXiv resuelve; ICLR 2023 coherente. |
| `madaan2023selfrefine` | OK | arXiv resuelve. |
| `shinn2023reflexion` | OK | arXiv resuelve. |
| `jimenez2024swebench` | OK | OpenReview/SWE-bench confirman ICLR 2024. |
| `cui2025effects` | OK | DOI resuelve en Crossref; Management Science 2026. |
| `butler2024dear` | OK | DOI IEEE resuelve; ICSE-SEIP 2025 pp. 319-329. |
| `epstein1999abm` | OK | DOI resuelve; Complexity 4(5), 41-60. |
| `railsback2019abm` | OK incompleto | Princeton University Press confirma libro. Se podria anadir URL y fecha de acceso por homogeneidad, aunque no es obligatorio para libro. |
| `sargent2013vv` | OK | DOI resuelve; Journal of Simulation 7(1), 12-24. |
| `mohammadi2025agenteval` | OK | DOI ACM resuelve; KDD 2025 pp. 6129-6139. |
| `zheng2023judge` | OK | arXiv resuelve; NeurIPS 2023 coherente. |
| `li2024judges` | OK | arXiv resuelve. |
| `calm2024biases` | OK | arXiv resuelve. |
| `wilson2019tenrules` | OK | DOI/eLife resuelve; articulo e49547. |
| `palminteri2017falsification` | OK | DOI Elsevier resuelve; TICS 21(6), 425-433. |
| `charnov1976mvt` | OK | DOI Elsevier resuelve; Theoretical Population Biology 9(2), 129-136. |
| `macarthur1966dietbreadth` | OK | DOI resuelve; American Naturalist 100(916), 603-609. |

## 7. Repeticiones y solapamientos

| Idea repetida | Ubicaciones | Accion recomendada |
|---|---|---|
| La asistencia de agentes desplaza el trabajo a especificacion/revision/verificacion | `04-desarroll.tex` inicio, secciones 4.1-4.2, `06-conclusiones.tex` reflexion final | Mantener desarrollo como explicacion principal; en conclusiones resumir en 3-4 lineas sin repetir "plataforma mas amplia". |
| El sistema observa, analiza y genera PDF | Resumen, introduccion, descripcion del sistema, conclusiones | Correcto como hilo conductor, pero variar: resumen = aportacion; introduccion = objetivo; conclusiones = evidencia de cumplimiento. |
| Knowledge Backbone como capa compartida | Introduccion, diseno 3.7, desarrollo, apendices | Mantener en diseno; en introduccion explicar solo en una frase para no adelantar demasiado. |
| Validacion no cientifica automatica | Pruebas 5.1, 5.4, conclusiones 6.3 | Bien planteado. Consolidar una frase unica: "la infraestructura valida fidelidad de observacion, no verdad neurocientifica". |
| Detalle de herramientas/tool calls | Diseno 3.4, apendice G | En diseno mantener patron y ejemplos; en apendice dejar catalogo completo. |

## 8. Fuentes externas consultadas

- Crossref API para DOIs, especialmente `10.1561/1500000019`, `10.1145/1571941.1572114`, `10.1287/mnsc.2025.00535`, `10.1145/3711896.3736570`.
- arXiv API/paginas para `2005.11401`, `2404.16130`, `2003.02320`, `2210.03629`, `2303.17651`, `2303.11366`, `2306.05685`, `2412.05579`, `2410.02736`.
- OpenReview: `https://openreview.net/forum?id=VtmBAGCN7o` y `https://openreview.net/forum?id=VTF8yNQM66`.
- IJCAI: `https://www.ijcai.org/proceedings/2024/890`.
- Princeton University Press: `https://press.princeton.edu/books/paperback/9780691190839/agent-based-and-individual-based-modeling`.
- Regulamento TFG Enxenaria Informatica USC en Lex.gal: `https://www.lex.gal/es/normativa/detalle/10854`.
