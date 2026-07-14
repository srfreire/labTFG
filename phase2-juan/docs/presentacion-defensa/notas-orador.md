# Guion de defensa — TFG Fase 2

Guion en primera persona, para leerse de corrido ante el tribunal. Una sección por diapositiva.
Las **negritas** son anclas para leer de un vistazo.

---

## 1 · Portada

Buenos días. Soy Juan Freire Álvarez y vengo a defender mi Trabajo de Fin de Grado, titulado «laboratorio virtual para simular y analizar paradigmas de toma de decisiones humanas mediante agentes inteligentes», dirigido por Eduardo Sánchez Vila.

Y antes de nada, tengo que explicar qué es un **paradigma de decisión**: una teoría de cómo alguien, persona o animal, elige entre opciones, como ir a por la comida cercana o guardar energía para después.

En una frase: es un **laboratorio para poner modelos de decisión de estos paradigmas a funcionar**, observarlos y dejar constancia de lo que hacen. Lo mueve un grupo de agentes inteligentes, los que veis en la portada, y los iré presentando a lo largo de la charla.

---

## 2 · Un problema abierto, iterado entre tres

Pero antes de entrar en el sistema, empiezo por el origen, porque explica muchas de las decisiones que vienen después. El proyecto nació de una **propuesta abierta** de Eduardo, sobre un trabajo de fin de máster previo que él mismo había tutorizado, que esbozaba la idea pero con un alcance corto. No partíamos de una especificación cerrada: el alcance, la arquitectura y la división en dos fases los decidimos **entre los tres**, en reuniones de diseño. Es decir, parte del trabajo fue **definir el problema, no solo resolverlo**.

Dándole vueltas llegamos a una separación natural: crear los modelos por un lado y simularlos por otro. La Fase 1, la de mi compañero Pablo, se encarga de lo primero: a partir de la descripción de un paradigma, genera el código de un modelo de decisión que compila y respeta una interfaz común.

¿Y cuál es el problema? Que **un modelo que compila y respeta la interfaz todavía no es un experimento**. Falta ejecutarlo en condiciones controladas, mirar sus decisiones paso a paso, compararlo con otros y dejar evidencia que alguien pueda revisar. Ese hueco es el que llena mi trabajo, y el reto era recorrer ese camino **sin acoplar las dos fases**.

---

## 3 · Dos fases, una frontera fina

Vuelvo a esas dos fases para explicar cómo hicimos la división. En vez de que mi código dependa del suyo por herencia o por una librería común, uso **duck typing**: no exijo que el modelo sea de un tipo concreto, solo compruebo que sepa hacer tres cosas. El nombre viene de la metáfora: si camina como un pato y hace cuac como un pato, lo trato como un pato.

Esas tres funciones son el contrato entero. `decide` elige una acción a partir de lo que percibe, `update` aprende de la recompensa, y `get_state` enseña su estado interno para que yo pueda dibujarlo. Lo que percibe es una lista corta: posición, tamaño del tablero, paso, recursos y resultado de la última acción. El resultado es que las dos fases **evolucionan por separado, sin coordinar versiones**: desacoplamiento, extensibilidad e interoperabilidad, las tres propiedades que buscaba esa frontera.

---

## 4 · Demo · El sistema en marcha

Con el contrato claro, toca ver el sistema entero funcionando. Antes de arrancar el vídeo sitúo lo que van a ver: es el panel de la aplicación web. A la izquierda converso con el Orchestrator en lenguaje natural; en el centro está la simulación animada, que puedo reproducir paso a paso; y alrededor hay métricas, los eventos que el Tracker marcó y el estado de cada agente. Todo llega por un **único canal permanente, un WebSocket**, así que la pantalla refleja cada paso en el momento en que ocurre.

El recorrido es el caso de uso principal: describo un problema con mis palabras, el Orchestrator propone modelos y un entorno, el Architect genera la especificación, se simula, se observa en directo, se analiza, y el Reporter genera un **informe PDF descargable**. De principio a fin, **sin tocar código**.

---

## 5 · Seis objetivos específicos

Vista la herramienta por fuera, paso a lo que me propuse. El proyecto se concreta en **seis objetivos**. Uno, generar la especificación del entorno desde lenguaje natural. Dos, ejecutar uno o varios modelos a la vez sin que se acoplen. Tres, registrar su comportamiento de forma ordenada. Cuatro, analizar patrones y contrastarlos con lo que ya se sabía. Cinco, generar un informe PDF. Y seis, guardar memorias reutilizables. Todos ellos están desarrollados en la memoria con más detalle, junto con sus requisitos funcionales y no funcionales, pero por falta de tiempo no me detendré en ellos aquí.

Un matiz: no estaban fijados de antemano, crecieron con cada iteración, coherente con que la propuesta era abierta. Luego se tradujeron en requisitos concretos, **trece funcionales y catorce no funcionales** priorizados con MoSCoW, y en cinco casos de uso.

---

## 6 · Qué puede hacer el usuario

Esos objetivos se aterrizan en requisitos y en cinco casos de uso, con un **único actor humano: el usuario investigador**. Todo lo demás son sistemas externos que no maneja directamente, así que quedan **fuera del límite**.

Los cinco casos son el recorrido de la demo: ejecutar una simulación, comparar modelos, analizar resultados, generar el informe y consultar experimentos anteriores, para contrastar en cada etapa con experimentos pasados. Y dos sistemas externos los alimentan: la **Fase 1** aporta los modelos, y **OpenRouter** es el músculo de lenguaje.

---

## 7 · Sobre qué se construye

Hasta aquí, qué hace y para quién; ahora, sobre qué se construye: el marco teórico que da sentido a todo lo anterior. Sitúo el trabajo respecto a lo que ya existe y, aun así, **no invento una técnica nueva, combino cuatro líneas que ya estaban**.

La primera, **simular para validar**: esta fase del TFG nace para validar los modelos de la Fase 1, porque un modelo no solo describe un mecanismo, necesita ejecutarse para ver qué resultados da; y validar no termina cuando compila. La segunda, **recuperación y memoria**: es sobre lo que se construye el núcleo de la memoria compartida que explicaré más tarde; técnicas como el RAG o los grafos de conocimiento se han vuelto ya metodologías de recuperación estándar en este tipo de sistemas agénticos. La tercera, **varios agentes cooperando** en roles con un orden fijo, frente al agente único que no deja nada auditable; es la idea sobre la que monto el sistema de cinco agentes. Y la cuarta, **el uso de herramientas y coding agents**: agentes que razonan y actúan mediante llamadas a herramientas —tool calls auditables, donde el anfitrión valida e invoca, no el modelo— y agentes que programan sobre repos reales. En mi trabajo aparece en dos planos: en el desarrollo, subagentes adversariales que revisan el código antes de fusionarlo; y en los agentes en ejecución, las llamadas a herramientas que el Tracker registra.

Mi arquitectura se coloca en un punto de ese mapa: **cooperativa, centralizada y por capas**.

---

## 8 · Una arquitectura por capas, y dónde se despliega

Con ese mapa detrás, entro en mi arquitectura: una **estructura de cinco capas**, y cada una solo habla con la de al lado. Presentación es lo que ve el usuario, lo que pudisteis ver en la demo anterior, el panel con el chat, la simulación y el replay, más una API ligera que expone el canal. Orquestación es el Orchestrator, que decide qué agente actúa. Agentes son los cuatro especialistas. Simulación tiene el cargador de modelos de la Fase 1, el motor del mundo 2D y las gráficas que utiliza el Analyst. Y persistencia son cuatro almacenes: **PostgreSQL, MinIO, Qdrant y Neo4j**, cada uno elegido por cómo se consulta el dato.

Sobre el despliegue: en producción todo corre en **Railway**; en local, con **Docker Compose** en un comando. Fuera queda el servicio externo por API: OpenRouter, el modelo de lenguaje.

---

## 9 · Una rejilla 2D común

Bajo de la arquitectura al detalle, y arranco por el mundo. El entorno donde viven los modelos es una **rejilla en dos dimensiones**; esta es la base que nos dio el trabajo de fin de máster de Eduardo. Es deliberadamente sencillo: no busco un mundo rico, sino un **escenario común** donde paradigmas muy distintos se midan en igualdad de condiciones. Es lo justo para compararlos.

Tiene cinco piezas: el entorno, el agente, los recursos, los eventos, que una vez escritos no se tocan más, y el modelo de decisión, que lo aporta la Fase 1. La separación que más me importa es entre **cuerpo y mente**: el agente es el cuerpo, su posición, su energía, su historia; el modelo es la mente, cómo elige. Al separarlos, cambio la forma de decidir sin tocar el mundo, y corro varios paradigmas a la vez. Cada evento guarda, por paso: cuándo fue, qué acción tomó, qué recompensa recibió, qué percibía y en qué estado quedó. Y un matiz: cada modelo teórico se encarna en **uno o varios agentes** dentro de la misma rejilla —por defecto uno, pero puedo pedir varios del mismo modelo—, así comparo en igualdad de condiciones.

---

## 10 · El Orchestrator conduce a los demás

Dentro de esas capas, la que manda es esta. El Orchestrator es el director de orquesta, la única pieza que conoce el proceso entero. Un punto que conviene dejar claro, porque suele generar preguntas: **el orden no lo improvisa el modelo**. La secuencia está escrita de antemano, y al modelo solo le dejo elegir desviaciones puntuales: una consulta extra, repetir un paso, descartar un intento fallido. Y qué modelos simular tampoco lo decide él: **lo elige el usuario**; el Orchestrator solo se los presenta y espera su elección.

Tiene **tres tareas que no delega**: prepara el contexto antes de llamar a cada agente, agrupa los mensajes de la conversación y los guarda en la base de datos por lotes en vez de uno a uno, y retransmite en directo por el canal.

---

## 11 · Cuatro agentes, cuatro cambios de representación

Si el Orchestrator dirige, los cuatro agentes ejecutan. La mejor forma de entenderlos es verlos como una **cadena de traducciones**: cada uno coge la información en un formato y la deja en otro para el siguiente, más cerca del informe.

El **Architect** traduce lenguaje natural a especificación del entorno: convierte mi petición en un tablero 2D concreto y lo valida antes de construirlo. El **Tracker** traduce simulación a observaciones: registra eventos, trayectorias y episodios, y es un **observador puro, no escribe en la memoria**. Lo crítico lo detecta con reglas de código: consumos, inanición, muertes, saltos de energía, cambios en la acción dominante, caídas de confianza. Es decir: **el código marca las señales, el modelo pone la síntesis** —elige qué episodios importan y redacta la observación que usarán los demás. El **Analyst** traduce observaciones a patrones: es el único que consulta la memoria por su cuenta, contrasta con la teoría y genera las gráficas, incluida la comparativa multi-modelo. Y el **Reporter** traduce patrones a PDF: redacta y compila con LaTeX. Aquí **no maquilla los datos, no inventa cifras**. Si algo falla, hay un respaldo mínimo, pero la evaluación comprueba que lo que entrego es el PDF real, no ese respaldo.

---

## 12 · Knowledge Backbone

La memoria ha salido ya varias veces; ahora la abro. Es la memoria del sistema, compartida con la Fase 1. Se accede de forma **centralizada, por el Orchestrator**, salvo el Analyst. Y no es un almacén, **son cuatro**, cada uno elegido por cómo se consulta el dato.

**PostgreSQL** es la verdad estructurada: cada decisión, recompensa y estado, paso a paso y reproducible. **MinIO** guarda lo pesado que no cabe en una fila: los PDF con sus figuras y los ficheros de los modelos de la Fase 1. **Qdrant** es la memoria de episodios —un episodio es un tramo de una simulación pasada, con sus decisiones y recompensas— y los recupera por significado; lo amplío en la siguiente. Y **Neo4j** es el conocimiento del dominio: un grafo de paradigmas, autores y papers que guarda de dónde sale cada afirmación, para poder citar la fuente.

¿Cómo se llena? El grueso lo escribe el Tracker: cuando termina, un componente que llamo el **escritor de memoria del Tracker** parte sus observaciones en hechos y los guarda con el mismo identificador en todos los almacenes. El Reporter también aporta, pero solo su parte: deposita en **MinIO** el PDF y sus figuras ya generados.

---

## 13 · Una consulta recorre toda la memoria

Y esa memoria, ¿cómo se consulta? La idea es sencilla: cuando el usuario pregunta, esa misma pregunta se lanza **a la vez contra los cuatro almacenes**, y el Orchestrator junta lo que devuelven en un solo contexto. Cada uno responde a algo que los otros no.

El corazón es Qdrant, y voy despacio porque es lo más técnico. Guardo la memoria de dos formas complementarias. La **densa, por significado**: cada texto se convierte en una lista de números —un embedding— que captura su sentido, así que «explorar con poca energía» encuentra episodios sobre drive u homeostasis aunque no repitan esas palabras —por ejemplo, aunque hablen de «reservas bajas»—. Y la **dispersa, por término exacto, con BM25**: la fiable para algo literal como «Rangel 2013» o «DDM-v2», que la semántica tiende a diluir.

Y los otros tres completan la respuesta: **PostgreSQL** pone el hecho exacto —paso y recompensa—, **Neo4j** la teoría contra la que se contrasta y de qué paper sale, y **MinIO** el informe o la figura ya generados. El Orchestrator junta las cuatro respuestas en un solo contexto y responde apoyándose en lo que el sistema ya sabe, **sin improvisar**.

---

## 14 · Un nuevo bucle de desarrollo

Ahora que el diseño está dibujado, paso a cómo desarrollé el trabajo. El ciclo clásico del software era más o menos así: analizar, diseñar, programar y probar, con **programar en el centro, porque escribir el código era lo caro**, el cuello de botella en la mayoría de desarrollos de software. Con agentes que generan código, **ese centro se cae**, se da por resuelta la implementación y se piensa una nueva forma de desarrollar. Yo lo reorganizo en un anillo de cuatro estaciones, donde cada tarea es un **contrato verificable**: especificar, ejecutar, revisar, y aceptar o ajustar; y vuelta a empezar.

Aquí lo importante es el reparto: de las cuatro estaciones, tres son mías, especificar, revisar y aceptar, y solo una, ejecutar, es del agente. Entonces, ahora que el agente hace eso, el peso se movió a **especificar bien y verificar**. Eso cambia lo que significa especificar: ya no es un párrafo de requisitos, sino un plan concreto para que el agente no rellene huecos con decisiones propias. Muchas las escribí como **pruebas primero, en TDD**, que hacen de contrato. Así, la planificación se concreta alrededor de pasar esas pruebas como método de validación.

---

## 15 · Quién decide, quién implementa

De ese ciclo concreto el **reparto y su consecuencia**. La frontera es simple: **el agente implementa** lo acotado —módulos, pruebas, migraciones, refactores, depuración—, y **yo decido todo lo demás**: alcance, contratos, diseño, prioridades y la aceptación final. Pero solo funciona si la especificación fija el comportamiento: si el contrato es ambiguo, el resultado también, y **ninguna salida se acepta por venir generada**.

Lo importante es que **el riesgo cambió de sitio**. Antes era no llegar a escribir a tiempo; ahora es **aceptar una pieza que parece correcta pero rompe el sistema**. Por eso reviso cada cambio contra la tarea: puede compilar y aun así lo rechazo si amplía el alcance o mete una abstracción que nadie pidió. La defensa es **granularizar**: tareas pequeñas y acotadas, donde la implementación es directa y no deja hueco a la ambigüedad —que es justo donde la IA empieza a llevarme a mí, y no yo a ella—. En la práctica repartí por terreno: **Codex** en backend, persistencia y pruebas; **Claude Code** en frontend e interacción.

---

## 16 · Verificar el desarrollo, evaluar el sistema

Y si al final soy yo quien acepta cada cambio, hay que asegurarlo. Esta diapositiva junta cómo verifiqué el desarrollo y la metodología de evaluación. Las dos responden a lo mismo: **si generar el código ya no es el cuello de botella, ¿qué garantiza que lo generado es correcto?**

En verificación: **387 pruebas automáticas** más pruebas de extremo a extremo en el navegador; mi regla era que **sin prueba una tarea no está terminada**. A eso sumo la revisión combinada, la verificación en vivo y una puerta de **integración continua** en cada subida: un control automático que corre las pruebas y bloquea el cambio si algo falla.

La evaluación es más sutil: al ser un LLM no hay una única respuesta correcta, así que hay que plantear una forma nueva de evaluar algo que cambia en cada ejecución. Uso **dos jueces**. El primero, un **modelo de lenguaje** que puntúa lo abierto, guiado por dos principios: **la verdad son los datos de la simulación, no la teoría**; y **quien evalúa no es quien fue evaluado** —el laboratorio razona con Claude, los cinco agentes que habéis visto, así que el juez es **Codex**, un modelo distinto—. El segundo juez es **humano**: una revisión experta en la que el propio Eduardo probó el sistema, con una valoración muy positiva. En el siguiente slide detallo qué mira el juez automático.

Y los dos casos son reales y **vienen de fuera**: dos problemas que nos dio Eduardo, ejecutados sobre los modelos de la Fase 1 de mi compañero. El **caso 1** va de elegir según la recompensa esperada —ir a por la comida—; el **caso 2**, de homeostasis —mantener una variable interna, como la energía, en equilibrio—. Los números están en pantalla; no me detengo en ellos.

---

## 17 · ¿Qué evalúa el juez?

Antes mencioné un juez externo; aquí detallo qué mira, porque es fácil malinterpretarlo. La vara son las **trayectorias de la simulación, no los papers**: se juzga si el laboratorio contó bien lo que pasó, no si la teoría acierta. Codex puntúa con una **rúbrica de seis criterios**, uno por cada etapa del laboratorio: si el entorno del Architect permite observar el comportamiento; si las observaciones del Tracker reflejan la simulación; si el análisis del Analyst está anclado en las trayectorias, sin inventar; si el informe del Reporter es fiel a los datos y es el PDF real; la robustez de toda la cadena de agentes de principio a fin; y un juicio global, una valoración de conjunto con la nota sobre 100.

---

## 18 · Lo aprendido

Cierro con tres lecciones. Una: **tres funciones bastaron para integrar dos fases**; esa frontera de duck typing entre componentes que evolucionan a ritmos distintos nunca nos obligó a coordinar versiones ni a estar pendientes el uno del otro: la sencillez gana al acoplamiento fuerte. Dos: **un único punto de acceso al conocimiento** compensa cuando cada consulta cuesta, porque da control del gasto, facilita el diagnóstico y hace más sencillo gestionar el contexto. Tres: **un fallo del observador no corrompe la memoria**; el Tracker observa y produce un JSON, pero la escritura ocurre después, así que nunca deja memorias a medias.

Soy honesto con los **límites**: no valida teorías por sí solo, depende del modelo de lenguaje y de servicios externos, el dominio es una rejilla 2D, y la escritura de conocimiento es conservadora. Y propongo **por dónde seguir**: más paradigmas y entornos continuos o multi-agente, métricas cuantitativas estandarizadas, reanudar sesiones, mejoras de legibilidad como nombres de modelos más claros, y evaluarlo con un **grupo experto de verdad**.

---

## 19 · ¿Preguntas?

Con esto termino. **Muchas gracias por vuestra atención**; quedo a vuestra disposición para las preguntas.
