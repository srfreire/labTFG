# Notas del orador — Defensa TFG Fase 2

Guion de las notas de ponente (`<aside class="notes">`) del deck, una sección por diapositiva.
Los bloques **❓ Si me preguntan** son respuestas preparadas a preguntas del tribunal, no forman parte del discurso principal.

---

## 1 · Portada

Esta portada dura poco, unos veinte segundos, pero conviene que yo tenga clarísimo el marco antes de arrancar. El título completo es **«laboratorio virtual para simular y analizar paradigmas de toma de decisiones humanas mediante agentes inteligentes»**. Un *paradigma de decisión* es, en cristiano, una teoría de cómo alguien (una persona o un animal) elige entre opciones: por ejemplo, ir a por la comida más cercana o guardar energía para más tarde. Yo defiendo **este TFG**, tutorizado por Eduardo Sánchez Vila.

Lo primero que debe entender el tribunal es que el trabajo son **dos fases que se complementan**. La Fase 1, de mi compañero Pablo, parte de la descripción de un paradigma en lenguaje natural y produce un **modelo en Python que se puede ejecutar**. Este TFG es la **infraestructura** que coge ese modelo y lo pone a funcionar: lo ejecuta, lo observa, lo analiza, redacta un informe y guarda memoria de lo aprendido.

Todo eso lo hacen **cinco agentes** —programas gobernados por un modelo de lenguaje, cada uno con un papel—: un **Orchestrator** que coordina y cuatro especialistas (Architect, Tracker, Analyst, Reporter). Las caras que se ven en la portada son ellos; volverán en cada diapo.

> **❓ Si me preguntan qué es mío y qué de mi compañero: la frontera entre las dos fases son solo **tres funciones** (`decide`, `update`, `get_state`). Él construye el modelo que decide; yo lo convierto en un experimento que se puede observar y revisar. Esa frontera tan fina es una de las decisiones de diseño de las que más orgulloso estoy, y la explico en la diapo cuatro.**

---

## 2 · Un problema abierto, iterado entre tres

Aquí cuento de dónde salió el proyecto, porque explica muchas decisiones posteriores. Nació de una **propuesta abierta de Eduardo Sánchez Vila**, apoyada en un **trabajo de fin de máster previo** (de Denis Yamunaque) que ya intuía la idea de un entorno de simulación, pero con un alcance limitado.

La clave es que **no había una especificación cerrada de partida**. El alcance, la arquitectura y la propia división en dos fases se fueron decidiendo **entre los tres** —Eduardo, mi compañero Pablo y yo— en reuniones de diseño. Es honesto decirlo así ante el tribunal: parte del trabajo fue definir el problema, no solo resolverlo.

Y el problema concreto que identificamos es este: **un modelo que compila y respeta la interfaz todavía no es un experimento**. Que un programa arranque no dice nada de si su comportamiento es interesante o correcto. Falta ejecutarlo en condiciones controladas, mirar sus decisiones paso a paso, compararlo con otros y conservar evidencia que alguien pueda revisar después. Ese es exactamente el hueco que llena este TFG.

El reto técnico central, que menciono de pasada, fue coordinar todo ese recorrido **sin acoplar las dos fases**, es decir, sin que un cambio en el trabajo de mi compañero Pablo me obligara a rehacer el mío.

> **❓ Si me preguntan cómo fijamos el límite entre fases si la propuesta era abierta: con un contrato mínimo de tres funciones, tan pequeño que ninguna de las dos fases tuvo que coordinar sus versiones con la otra. Es la idea de la diapo siguiente.**

---

## 3 · Dos fases, una frontera fina

Esta es la diapo de la integración, la decisión de la que más orgulloso estoy. Recuerdo el reparto: la Fase 1 convierte lenguaje natural en un modelo Python; este TFG lo **ejecuta, observa, analiza, informa y recuerda**.

Lo importante es *cómo* encajan las dos fases. En lugar de que mi código dependa del suyo con herencia o con una librería compartida, uso lo que se llama **«duck typing»**: mi laboratorio no exige que el modelo sea de un tipo concreto, solo comprueba que sepa hacer **tres cosas**. La metáfora es la de siempre: «si camina como un pato y hace cuac como un pato, lo trato como un pato». Da igual quién lo escribió o cómo, mientras cumpla las tres funciones.

Esas tres funciones son el contrato entero: `decide` (mira lo que percibe y elige una acción), `update` (aprende de la recompensa que recibió) y `get_state` (enseña sus tripas para que yo pueda dibujarlas). Lo que el modelo «percibe» es una lista corta de datos: su posición, el tamaño del tablero, el paso en que va, los recursos y el resultado de su última acción. A quien conozca el campo le sonará al *aprendizaje por refuerzo*, y no es casualidad: ese formato admite desde un Q-learning clásico hasta estrategias más deliberativas.

Esta decisión responde a tres requisitos no funcionales del proyecto: desacoplamiento, extensibilidad e interoperabilidad. El resultado práctico es que **las dos fases evolucionan por separado, sin coordinar versiones**.

> **❓ Si me preguntan por qué duck typing y no una clase base de la que ambos heredaran: una clase base crearía una dependencia de paquete y nos obligaría a coordinar cada versión. Con el contrato fino, el laboratorio solo comprueba al cargar el modelo que expone las tres funciones, y ya está.**

---

## 4 · Demo · El sistema en marcha

Antes de arrancar el vídeo lo enmarco para que se sepa qué se está mirando: es el **panel de control (dashboard) de la aplicación web**. A la izquierda, un chat donde converso con el Orchestrator en lenguaje natural; en el centro, el entorno de simulación animado, que puedo **reproducir paso a paso** como si fuera un vídeo; y alrededor, tarjetas con métricas, los eventos que el Tracker marcó como importantes y el estado de cada agente.

Un detalle técnico que merece la pena señalar: todo lo que se ve llega por un **único canal permanente** (un WebSocket) entre el navegador y el servidor. Eso significa que la pantalla refleja cada paso del proceso **en el momento en que ocurre**, sin tener que estar preguntando al servidor cada poco. Se ve un proceso vivo, no una pantalla que se refresca.

El recorrido que muestra la demo es el caso de uso principal: **describo un problema con mis palabras** → el Orchestrator me propone modelos y un entorno → el Architect genera la especificación de ese entorno → se simula → se observa en directo → se analiza → y el Reporter genera un **informe PDF que puedo descargar**. De extremo a extremo, sin tocar código.

> **❓ Si me preguntan por qué ese canal permanente y no consultar al servidor cada pocos segundos: porque consultar cada poco añade retraso y multiplica las peticiones; con un solo canal el usuario ve el proceso al instante. El precio es que la complejidad de sincronizar se mueve al servidor, y asumo ese coste a conciencia.**

---

## 5 · Seis objetivos específicos

Seis objetivos específicos, que enuncio brevemente porque estructuran todo lo demás: **(1)** generar la especificación del entorno a partir de lenguaje natural; **(2)** ejecutar uno o varios modelos a la vez sin que se acoplen entre sí; **(3)** registrar su comportamiento de forma ordenada (eventos, trayectorias, episodios, variables internas); **(4)** analizar patrones y contrastarlos con lo que ya se sabía; **(5)** generar un informe PDF; y **(6)** guardar memorias que se puedan reutilizar en experimentos posteriores.

Un matiz honesto que quiero decir en voz alta: estos objetivos **no estaban fijados de antemano**, crecieron con cada iteración de diseño, coherente con que la propuesta era abierta. Luego se tradujeron en requisitos concretos —13 funcionales y 14 no funcionales, priorizados con el método MoSCoW— y en cinco casos de uso.

> **❓ Si me preguntan si se cumplieron todos: sí, los seis, y así lo recojo en las conclusiones. Además, la evaluación instrumentada con dos casos reales (los enseño al final) comprueba que el recorrido completo es fiel de principio a fin, no solo que cada pieza funciona por separado.**

---

## 6 · Qué puede hacer el usuario

Los objetivos se aterrizan en **requisitos** —13 funcionales y 14 no funcionales, priorizados con MoSCoW— y en **cinco casos de uso** con un **único actor humano**, el *usuario investigador*. Todo lo demás son sistemas externos que el usuario no opera directamente, por eso quedan **fuera del límite** del laboratorio.

Los cinco casos son el recorrido de la demo: **Ejecutar simulación**, **Comparar modelos** —que incluye ejecutar—, **Analizar resultados**, **Generar informe PDF** —que incluye analizar— y **Consultar experimentos** anteriores. Los coloreo con el agente que lidera cada uno para enlazar con la arquitectura.

Dos sistemas externos los alimentan: la **Primera fase** aporta los modelos que se ejecutan y comparan, y **OpenRouter** (más los servicios semánticos) da el músculo de lenguaje que usan los agentes al analizar y consultar.

> **❓ Si me preguntan por qué OpenRouter queda fuera del límite: porque el usuario no lo invoca; lo usan los agentes por dentro. El actor solo habla con el laboratorio.**

---

## 7 · Sobre qué se construye

Aquí sitúo el trabajo respecto a lo que ya existe. El mensaje que quiero dejar es honesto: **no invento una técnica nueva, combino cuatro líneas que ya estaban ahí**. Las repaso por encima; no hace falta que el tribunal retenga los nombres, solo la idea de cada bloque.

**(a) Simular para validar.** En ciencia se usan modelos que no solo describen un mecanismo con palabras, sino que lo **ejecutan** para ver qué patrones emergen. Y la validación no termina cuando el programa compila: hay que comprobar que hace lo correcto. Autores de referencia: Epstein, Railsback y Grimm, Sargent.

**(b) Varios agentes de IA cooperando.** En lugar de un único agente que lo hace todo y no deja nada auditable, se reparte el trabajo en **roles especializados que actúan en un orden fijo**. Es la idea de sistemas como MetaGPT.

**(c) Recuperación y memoria.** Combinar búsqueda por significado y búsqueda por palabra exacta sobre un grafo de conocimiento, para que el sistema recuerde y consulte lo que ya sabe. Es la base de las técnicas RAG y GraphRAG.

**(d) Herramientas y agentes que programan.** Modelos que razonan y **actúan llamando a herramientas** cuyo uso queda registrado, e incluso agentes que escriben código sobre repositorios reales. Una idea clave de esta línea es la **auto-revisión**: el agente critica y corrige sus propias salidas antes de darlas por buenas (Self-Refine, Reflexion). En este trabajo aparece como **subagentes adversariales que revisan el código** del agente principal antes de fusionarlo. Referencias: ReAct, Self-Refine, Reflexion, SWE-bench.

Mi arquitectura se coloca en un punto concreto de ese mapa: **cooperativa** (los agentes colaboran, no compiten), **centralizada** (un coordinador manda) y **por capas** (roles en orden).

> **❓ Si me preguntan cuál es la novedad si solo combino: está en la **integración**. Un laboratorio que recibe modelos de fuera, los ejecuta en un entorno común y deja evidencia persistente y auditable de todo el recorrido. Ninguna de esas técnicas por separado cubre ese camino completo.**

---

## 8 · Una arquitectura por capas, y dónde se despliega

Presento la arquitectura como una tarta de **cinco capas**, de arriba abajo. La idea que quiero transmitir es que cada capa tiene una única responsabilidad y solo habla con la de al lado.

**Presentación**: lo que ve el usuario —el panel web con el chat, la simulación y el replay— más una API ligera en el servidor que expone el canal de comunicación.

**Orquestación**: el Orchestrator, que lleva el estado de la conversación y decide qué agente actúa en cada momento.

**Agentes**: los cuatro especialistas —Architect, Tracker, Analyst, Reporter—.

**Simulación**: el cargador que trae los modelos de la Fase 1, el motor que ejecuta el mundo 2D y el módulo que dibuja las gráficas del análisis.

**Persistencia**: cuatro almacenes de datos distintos —PostgreSQL, MinIO, Qdrant y Neo4j— cada uno elegido por cómo se consulta el dato.

**Dónde se despliega**: en producción **todo corre en Railway** —un frontend, un backend y los cuatro almacenes como servicios—; en local se levanta con **Docker Compose** en un solo comando. Fuera del despliegue quedan los servicios **externos** por API: OpenRouter (el LLM) y los semánticos Voyage y ZeroEntropy.

> **❓ Si me preguntan por qué cuatro almacenes y no uno: porque los datos no se consultan igual. Unos se buscan por identificador o fecha (una base de datos clásica), otros son archivos grandes (un almacén de objetos), otros se buscan por parecido (una base vectorial) y otros por sus relaciones (un grafo). Uso la herramienta adecuada a cada pregunta, y las mantengo coherentes con identificadores compartidos. Lo detallo en las dos diapos siguientes.**

---

## 9 · Una rejilla 2D común

El entorno donde viven los modelos es una **rejilla en dos dimensiones**, como un tablero. Quiero ser transparente: es **deliberadamente sencillo**. No busco un mundo rico, sino un escenario común donde paradigmas muy distintos se puedan medir en las mismas condiciones, que es lo justo para poder compararlos.

Ese mundo se compone de cinco conceptos: el **entorno**, el **agente**, los **recursos**, los **eventos** (un registro que, una vez escrito, no se toca nunca más) y el **modelo de decisión**, que es la pieza que aporta la Fase 1.

La separación importante, y que conviene explicar despacio, es entre el **cuerpo** y la **mente**. El agente es el cuerpo —quién es y dónde está: su posición, su energía, su historia—. El modelo de decisión es la mente —cómo elige—. Al separarlos, puedo cambiar la forma de decidir sin tocar el mundo, y correr varios paradigmas a la vez en el mismo tablero.

Cada evento guarda, por cada paso: en qué momento fue, qué agente actuó, qué acción tomó, qué recompensa recibió, qué percibía y en qué estado interno quedó. Esa es la materia prima de todo lo que viene después.

> **❓ Si me preguntan si no es demasiado simple una rejilla 2D: es una limitación que reconozco y elegí a propósito. Mi aportación está en la infraestructura de observación, no en la riqueza del mundo. Ampliar el entorno —a espacios continuos o multi-agente— es una de las líneas de continuación que propongo al final.**

---

## 10 · El Orchestrator conduce a los demás

El Orchestrator es el director de orquesta: la **única pieza que conoce el proceso completo**. Lleva el hilo de la conversación, sabe qué herramientas hay disponibles y decide a qué agente le toca actuar en cada momento.

Un punto que quiero dejar claro porque suele generar preguntas: el orden general **no lo improvisa el modelo de lenguaje**. La secuencia de pasos está escrita de antemano —es una «secuencia canónica»— y al modelo solo se le deja elegir **desviaciones puntuales**: hacer una consulta extra, repetir un paso, descartar un intento que salió mal. No le entrego la planificación completa, precisamente para que el proceso sea auditable y repetible.

Tiene tres tareas que no delega en nadie. Primera, **prepara el contexto** antes de llamar a cada agente, buscándole de antemano lo que va a necesitar. Segunda, **agrupa las escrituras en la base de datos** y las hace de golpe al final, para controlar el gasto y no saturar la memoria del modelo. Tercera, **retransmite en directo** todo lo que pasa por el canal permanente.

Un detalle fino: cuando la conversación se hace muy larga, los turnos antiguos se resumen con una **plantilla fija, escrita por código, no por el modelo**. Así el resumen es siempre igual de fiable y no introduce alucinaciones.

> **❓ Si me preguntan que, si el modelo apenas planifica, para qué usar un modelo de lenguaje como orquestador: aporta justo lo que el código no sabe hacer —interpretar lo que el usuario quiere en lenguaje natural y decidir esas desviaciones puntuales—. La columna vertebral va codificada a propósito, para que el pipeline sea auditable y reproducible.**

---

## 11 · Cuatro agentes, cuatro cambios de representación

La forma más útil de entender los cuatro agentes es verlos como una cadena de **traducciones**: cada uno toma la información en un formato y la deja en otro, más cerca del informe final.

**Architect**: traduce *lenguaje natural → especificación del entorno*. Convierte mi petición en la descripción de un tablero 2D concreto (tamaño, acciones, recursos) y la valida antes de construirlo. No juzga si un modelo es correcto; solo se encarga de que el entorno sea compatible con lo que pido.

**Tracker**: traduce *simulación → observaciones*. Registra eventos, trayectorias y episodios. Es importante: es un **observador puro, no escribe en la memoria compartida**. Y detecta lo que merece atención con **reglas fijas de código**, antes de que ningún modelo interprete nada: consumos, riesgo de morir de hambre, muertes, saltos bruscos de energía, cambios en la acción dominante, caídas de confianza del modelo.

**Analyst**: traduce *observaciones → patrones*. Es el **único agente que consulta la memoria por su cuenta**: contrasta lo observado con lo que la teoría postulaba y genera las gráficas, incluida la comparativa cuando se corren varios modelos a la vez.

**Reporter**: traduce *patrones → PDF*. Redacta el informe y lo compila con LaTeX. Y lo hace **sin red de seguridad**: si la compilación falla, falla de verdad, no se inventa un PDF alternativo. Prefiero un error visible a un informe silenciosamente degradado.

> **❓ Si me preguntan por qué separo Tracker y Analyst: para mantener la frontera entre los **hechos** de la simulación y las **conclusiones**. El Tracker registra sin interpretar; el Analyst interpreta. Y como el detector de eventos críticos es código determinista, los puntos de atención los calcula una regla, no se los inventa el modelo.**

---

## 12 · Knowledge Backbone

Esta es la memoria del sistema, compartida con la Fase 1. Se accede a ella de forma **centralizada, a través del Orchestrator** (con la única excepción del Analyst). Lo interesante es que no es un almacén, sino **cuatro**, y cada uno se eligió por *cómo se consulta el dato*, no por capricho. En cada tarjeta puse un ejemplo real para que se entienda.

**PostgreSQL** es la **verdad estructurada**: cada decisión, cada recompensa y cada estado, paso a paso y reproducible. Es donde miro si quiero saber exactamente qué pasó en el paso 19 del caso 1.

**MinIO** guarda los **entregables pesados** que no caben en una fila de una tabla: los informes PDF y sus figuras, que se sirven por una dirección web.

**Qdrant** es la **memoria de experiencias**: permite recuperar episodios pasados por su significado y por su término exacto en la misma consulta. Es la pieza que amplío en la diapo siguiente, porque es la más técnica.

**Neo4j** es el **conocimiento del dominio**: un grafo con paradigmas, autores y papers, que además guarda **de dónde sale cada afirmación**. Así, cuando el sistema dice algo, puede citar la fuente (por ejemplo, «esto lo postula Rangel en 2013»).

Sobre cómo se llena: cuando el Tracker termina, un componente descompone sus observaciones en hechos pequeños y los guarda bajo una misma etiqueta, con el **mismo identificador compartido** en todos los almacenes, para poder cruzarlos después. Dos servicios externos por API refuerzan la parte semántica: **Voyage AI** genera los **embeddings** —convierte cada texto en un vector para poder buscarlo por significado— y **ZeroEntropy** hace **reranking** —reordena por relevancia los resultados recuperados antes de usarlos—. Ambos son **opcionales**: si sus claves de API no están, esa capa se apaga.

> **❓ Si me preguntan qué pasa si esos servicios externos no están: la capa semántica se apaga con elegancia —no hay memoria indexada ni reordenación de resultados—, pero simular, observar, analizar e informar sigue funcionando igual. Es una degradación controlada, no una caída.**

---

## 13 · Una consulta recorre toda la memoria

La idea de esta diapo es sencilla de contar aunque por dentro tenga varias piezas: **cuando el usuario hace una pregunta, esa misma pregunta se lanza a la vez contra los cuatro almacenes**, y el Orchestrator junta todo lo que devuelven en un único contexto. Cada almacén sabe responder a algo que los otros no saben; por eso uso los cuatro en vez de quedarme con uno.

El corazón es **Qdrant**, y aquí conviene ir despacio porque es lo más técnico. Guardo la memoria de experiencias de dos formas que se complementan. La primera es **búsqueda por significado** —en la jerga, «densa»—: cada texto se convierte en una lista de números que captura su sentido, así que si pregunto por «explorar con poca energía» encuentra episodios que hablan de *drive* o de homeostasis aunque no repitan esas palabras. La segunda es **búsqueda por término exacto** —«dispersa», con un método clásico llamado BM25—: es la fiable cuando busco algo literal como «Rangel 2013» o «DDM-v2», que es justo lo que la búsqueda por significado tiende a diluir.

¿Cómo junto las dos listas de resultados? Con **Reciprocal Rank Fusion (RRF)**, que es más humilde de lo que suena: no entrena nada ni usa un modelo, solo mira en qué puesto quedó cada resultado en cada lista y premia a los que salen arriba en ambas. Que sea una simple regla aritmética, reproducible y sin entrenamiento, es una virtud.

Las otras tres tiendas aportan lo que Qdrant no puede. **PostgreSQL** da los hechos del run sin ambigüedad —modelo, caso, paso, recompensa— con un filtro exacto (`WHERE case='CASO1' AND step=19`). **Neo4j** guarda los postulados de la teoría y de dónde salen, para poder decir contra qué se contrasta lo observado (`(exploración)←[POSTULA]—(Rangel 2013)`). Y **MinIO** devuelve los entregables ya hechos —informes y figuras— servidos por una dirección web.

El desenlace de la diapo es esa fusión: el Orchestrator junta significado, hechos exactos, dominio y artefactos en **un solo contexto** y responde **anclado en la memoria** —no improvisa, se apoya en lo que el sistema ya sabe—.

> **❓ Si me preguntan por qué no uso solo búsqueda semántica moderna: porque cada pregunta necesita una mezcla distinta. La semántica se pierde con autores, identificadores y citas literales —ahí gana BM25—, y ni la densa ni la dispersa saben dar un hecho exacto, una relación entre conceptos o un archivo. RRF me deja fundir significado, hechos, dominio y artefactos sin entrenar nada.**

---

## 14 · Un nuevo bucle de desarrollo

Cambio de tercio: esta parte es sobre **cómo desarrollé el trabajo**, no sobre el sistema. Presento un anillo de cuatro estaciones alrededor de un mismo centro, y la idea es que **cada tarea es un contrato verificable**. El ciclo es: 1 especificar → 2 ejecutar → 3 revisar → 4 aceptar o ajustar, y vuelta a empezar con la siguiente tarea.

Lo que quiero que se vea en el diagrama es un reparto: de las cuatro estaciones, **tres son mías** (especificar, revisar, aceptar) y solo una, ejecutar, es del agente de IA. Y resulta que **ejecutar —escribir el código— es justo lo que dejó de ser lo caro**. Por eso el peso del trabajo se desplazó a especificar bien y verificar, que es lo que puse en el centro.

Esto cambia lo que significa «especificar». Ya no es escribir un párrafo de requisitos, sino algo más parecido a un **plan de implementación**: lo bastante concreto para que el agente no tenga que rellenar huecos con decisiones propias. Muchas de esas especificaciones las escribí en clave de **pruebas primero** (TDD): defino antes qué debe cumplir, y eso hace de contrato.

Cada contrato fija cuatro cosas: qué comportamiento nuevo aparece, qué archivos cambian, qué pruebas se añaden y qué invariantes no se pueden romper. Usé Linear como memoria operativa del proyecto, entre marzo y junio de 2026.

> **❓ Si me preguntan qué mérito de ingeniería tiene el trabajo si el código lo genera un agente: tres de las cuatro estaciones siguen siendo humanas. Lo que cambió es el nivel de abstracción, no la responsabilidad: pasé de pensar «cómo escribo esto» a pensar «qué quiero exactamente que ocurra». Esa frase, de hecho, es la que cierra la presentación.**

---

## 15 · Quién decide, quién implementa

Concreto el reparto de responsabilidades entre el humano y el agente. **El humano decide**: el alcance, los contratos de integración, el diseño visual, las prioridades y —esto es clave— la **aceptación final**. Ninguna salida se aceptó solo por venir generada.

**El agente implementa**: módulos acotados, pruebas, migraciones de base de datos, refactorizaciones y depuración local. Pero solo cuando la especificación fija bien el comportamiento; si el contrato es ambiguo, el resultado también lo será.

La idea que quiero que quede es que **el riesgo cambió de sitio**. Antes el riesgo era no llegar a escribir una pieza a tiempo. Ahora es **aceptar una pieza que parece correcta sin comprobar si respeta el sistema**. Por eso reviso siempre el cambio contra la tarea: un código puede compilar perfectamente y aun así rechazarlo, porque amplía el alcance o mete una abstracción que nadie pidió.

Tengo un ejemplo real que cuento si hay tiempo: las llamadas a herramientas daban por hecho que siempre venían bien formadas; una que llegó a medias convirtió un simple error del modelo en una excepción del servidor. La solución fue leer los datos de forma **defensiva** y añadir pruebas con entradas mal formadas. El fallo no era del agente: el contrato no había previsto ese caso raro.

En la práctica repartí las herramientas: Codex para el backend, la persistencia y las pruebas; Claude Code para el frontend y la interacción. Nada rígido, pero funcionó bien así.

> **❓ Si me preguntan cómo garantizo no aceptar código incorrecto pero convincente: con tres capas. Las pruebas como contrato, una revisión combinada (mi lectura del cambio más subagentes revisores de alta confianza) y una verificación manual sobre la aplicación ya en marcha.**

---

## 16 · Verificar el desarrollo, evaluar el sistema

Esta diapo une dos cosas: cómo verifiqué el desarrollo y cómo evalué el sistema terminado. Ambas responden a la misma pregunta incómoda: si escribir el código dejó de ser lo caro, **¿qué garantiza que lo generado es correcto?**

En **verificación**, lo concreto: **387 pruebas automáticas** más pruebas de extremo a extremo en el navegador; mi regla fue que sin prueba una tarea no está terminada. A eso sumo la revisión combinada, la verificación en vivo, y una **puerta automática** que en cada subida de código comprueba estilo y pruebas antes de dejar pasar nada.

La **evaluación** es más sutil, porque aquí no hay una única respuesta correcta —no es como comprobar que 2+2 da 4—. Uso tres familias de comprobación: la **automática** (binaria: pasa o no pasa), un **modelo de lenguaje como juez** para las salidas abiertas, y la **revisión humana**. Y me apoyo en dos principios. Primero: **la verdad son los datos de la simulación, no la teoría**; evalúo si la observación es fiel a lo que ocurrió, no si el paradigma acierta sobre el mundo. Segundo: **quien evalúa no es quien fue evaluado** —el laboratorio razona con Claude, así que el juez es Codex, de otra familia—. La nota se da sobre una rúbrica de seis criterios.

Conviene decir **de dónde salen los dos casos**, aunque ya no lo ponga en pantalla: no me los inventé para la demo, son **dos ejecuciones instrumentadas reales de modelos de la Fase 1** —los que aporta mi compañero Pablo—, con las que compruebo la **fidelidad de observación de extremo a extremo**. El **caso 1** (valor y forrajeo): 6 paradigmas en un tablero 8×8, 360 eventos, 15 consumos, nota 88 sobre 100. El **caso 2** (homeostasis e interocepción): 4 paradigmas en 10×10, 199 eventos, 7 consumos, nota 86. Ambos «aprobado con reservas».

> **❓ Si me preguntan si es fiable que un modelo juzgue a otro: tomo tres precauciones. Son de familias distintas (Claude frente a Codex), la vara de medir son datos duros verificados por código, y leo el veredicto como una **auditoría de consistencia**, no como una validación científica. Una meta-evaluación estadística más formal la dejo como trabajo futuro.**

---

## 17 · ¿Qué evalúa el juez?

Aquí detallo qué mira el juez, porque es fácil malinterpretarlo. La vara de medir son las **trayectorias de la simulación, no los papers**: se juzga la **fidelidad de la observación** —si el laboratorio contó bien lo que pasó—, no si la teoría acierta. El juez es Codex, de otra familia, y usa seis criterios, uno por cada etapa del laboratorio: entorno, observación, análisis, informe, robustez y un juicio global con nota sobre 100.

El ejemplo que más me gusta contar es del caso 2. Uno de los modelos, el de **inferencia activa**, no supo mantener su equilibrio interno y **murió de hambre en el paso 18**, tras comer una sola vez. Lo relevante es lo que hizo el laboratorio: **no rellenó ni maquilló su trayectoria**. Registró los 19 eventos que hubo, marcó la muerte por inanición y siguió comparándolo con los demás. Observó el fallo y lo comunicó tal cual, sin forzar una explicación más cómoda.

Los veredictos fueron 88 y 86 sobre 100, con reservas por imprecisiones puntuales al citar pasos concretos.

> **❓ Si me preguntan qué demuestra esa muerte por inanición: que la observación es fiel **incluso cuando el modelo fracasa**. El laboratorio no maquilla, no inventa pasos y reporta el fracaso —que es exactamente lo que se le pide a una infraestructura de laboratorio: contar lo que pasó, no lo que gustaría que hubiera pasado—.**

---

## 18 · Lo aprendido

Cierro con tres lecciones, que son la conclusión del trabajo. La idea de fondo es que importó más **la forma de conectar las piezas** que las decisiones internas de cada una.

**Una:** los contratos finos entre componentes que evolucionan a ritmos distintos valen mucho —la frontera de tres funciones nunca nos obligó a coordinar versiones—. **Dos:** centralizar el conocimiento compensa cuando cada consulta cuesta dinero y tiempo, porque da control del gasto y facilita el diagnóstico. **Tres:** observar no es lo mismo que guardar —el Tracker observa pero nunca deja memorias a medias—.

Soy honesto con los **límites**: el laboratorio no valida teorías por sí solo, depende del modelo de lenguaje y de servicios externos, el dominio es una rejilla 2D, y la escritura de conocimiento es conservadora.

Y propongo **ampliaciones**: más paradigmas y entornos (continuos, multi-agente), métricas cuantitativas estandarizadas para comparar de forma directa, poder reanudar sesiones (el historial ya se guarda, falta recuperarlo) y probarlo de verdad con investigadores del grupo —una revisión experta de qué paradigmas estudiarían y qué les ahorra trabajo—.

> **❓ Si me preguntan qué haría primero con más tiempo: una capa común de métricas estandarizadas —recompensa, eficiencia, exploración, estabilidad— para poder comparar modelos de forma directa; y la reanudación de sesiones, porque el historial ya está guardado y solo falta rehidratarlo.**

---
