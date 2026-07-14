# Guion de defensa — TFG Fase 2

Guion en primera persona, para leerse de corrido ante el tribunal. Una sección por diapositiva.
Las **negritas** son anclas para leer de un vistazo.

---

## 1 · Portada

**Buenos días. Soy Juan Freire Álvarez** y vengo a defender mi Trabajo de Fin de Grado, «laboratorio virtual para simular y analizar paradigmas de toma de decisiones humanas mediante agentes inteligentes», dirigido por Eduardo Sánchez Vila.

Y antes de nada, tengo que explicar qué es un **paradigma de decisión**: una teoría de cómo alguien, persona o animal, elige entre opciones, como ir a por la comida cercana o guardar energía para después.

En una frase: es un **laboratorio para poner modelos de decisión a funcionar**, observarlos y dejar constancia de lo que hacen. Lo mueve un grupo de **agentes inteligentes**, los que ven en la portada, y los iré presentando a lo largo de la charla.

---

## 2 · Un problema abierto, iterado entre tres

Pero antes de entrar en el sistema, empiezo por el origen, porque explica muchas de las decisiones que vienen después. El proyecto nació de una **propuesta abierta** de Eduardo, sobre un trabajo de fin de máster previo que él mismo había tutorizado, que apuntaba la idea pero con un alcance corto. No partíamos de una especificación cerrada: el alcance, la arquitectura y la división en dos fases los decidimos **entre los tres**, en reuniones de diseño. Lo digo con honestidad, parte del trabajo fue **definir el problema, no solo resolverlo**.

¿Y cuál es el problema? Que **un modelo que compila y respeta la interfaz todavía no es un experimento**. Falta ejecutarlo en condiciones controladas, mirar sus decisiones paso a paso, compararlo con otros y dejar evidencia que alguien pueda revisar. Ese hueco es el que llena mi trabajo, y el reto era recorrer ese camino **sin acoplar las dos fases**.

---

## 3 · Dos fases, una frontera fina

Vuelvo a esas dos fases, porque cómo encajan es la decisión de la que más orgulloso estoy. En vez de que mi código dependa del suyo por herencia o por una librería común, uso **duck typing**: no exijo que el modelo sea de un tipo concreto, solo compruebo que sepa hacer **tres cosas**. Como dice la metáfora, si camina como un pato y hace cuac como un pato, lo trato como un pato.

Esas tres funciones son el contrato entero. **`decide`** elige una acción a partir de lo que percibe, **`update`** aprende de la recompensa, y **`get_state`** enseña sus tripas para que yo pueda dibujarlas. Lo que percibe es una lista corta: posición, tamaño del tablero, paso, recursos y resultado de la última acción. A quien conozca el campo le sonará al **aprendizaje por refuerzo**, y no es casualidad. El resultado es que las dos fases **evolucionan por separado, sin coordinar versiones**.

---

## 4 · Demo · El sistema en marcha

Con el contrato claro, toca ver el sistema entero funcionando. Antes de arrancar el vídeo sitúo lo que van a ver: es el **panel de la aplicación web**. A la izquierda converso con el **Orchestrator** en lenguaje natural; en el centro está la **simulación animada**, que puedo reproducir paso a paso; y alrededor hay métricas, los eventos que el Tracker marcó y el estado de cada agente. Todo llega por un **único canal permanente, un WebSocket**, así que la pantalla refleja cada paso en el momento en que ocurre.

El recorrido es el **caso de uso principal**: describo un problema con mis palabras, el Orchestrator propone modelos y un entorno, el Architect genera la especificación, se simula, se observa en directo, se analiza, y el Reporter genera un **informe PDF descargable**. De principio a fin, **sin tocar código**.

---

## 5 · Seis objetivos específicos

Vista la herramienta por fuera, paso a lo que me propuse. El proyecto se concreta en **seis objetivos**. Uno, generar la **especificación del entorno** desde lenguaje natural. Dos, **ejecutar uno o varios modelos** a la vez sin que se acoplen. Tres, **registrar su comportamiento** de forma ordenada. Cuatro, **analizar patrones** y contrastarlos con lo que ya se sabía. Cinco, **generar un informe PDF**. Y seis, **guardar memorias reutilizables**.

Un matiz honesto: no estaban fijados de antemano, crecieron con cada iteración, coherente con que la propuesta era abierta. Luego se tradujeron en requisitos concretos, **trece funcionales y catorce no funcionales** priorizados con **MoSCoW**, y en **cinco casos de uso**.

---

## 6 · Qué puede hacer el usuario

Esos objetivos se aterrizan en requisitos y en **cinco casos de uso**, con un **único actor humano: el usuario investigador**. Todo lo demás son sistemas externos que no maneja directamente, así que quedan **fuera del límite**.

Los cinco casos son el recorrido de la demo: **ejecutar una simulación**, **comparar modelos**, **analizar resultados**, **generar el informe** y **consultar experimentos** anteriores. Cada uno lleva el color del agente que lo lidera. Y dos sistemas externos los alimentan: la **Fase 1** aporta los modelos, y **OpenRouter**, con los servicios semánticos, el músculo de lenguaje.

---

## 7 · Sobre qué se construye

Hasta aquí, qué hace y para quién; ahora, sobre qué se construye. Sitúo el trabajo respecto a lo que ya existe, y prefiero ser honesto: **no invento una técnica nueva, combino cuatro líneas que ya estaban**.

La primera, **simular para validar**: modelos que no solo describen un mecanismo, sino que lo ejecutan para ver qué patrones emergen; y validar no termina cuando compila. Ahí están Epstein, Railsback y Grimm, o Sargent. La segunda, **varios agentes cooperando** en roles con un orden fijo, frente al agente único que no deja nada auditable; es la idea de MetaGPT. La tercera, **recuperación y memoria**: búsqueda por significado y por palabra exacta sobre un almacén vectorial —la base de **RAG**— más un grafo de conocimiento aparte —la base de **GraphRAG**—, que fusiono en una sola consulta. Y la cuarta, **agentes que razonan, actúan llamando a herramientas y revisan sus propias salidas**; en mi trabajo aparece en dos planos: en el desarrollo, subagentes adversariales que revisan el código antes de fusionarlo —ahí encaja **Self-Refine/Reflexion**—; y en los agentes en ejecución, que operan en modo **ReAct**, con las llamadas a herramientas que registra el Tracker.

Mi arquitectura se coloca en un punto de ese mapa: **cooperativa, centralizada y por capas**.

---

## 8 · Una arquitectura por capas, y dónde se despliega

Con ese mapa detrás, entro en mi arquitectura: una **tarta de cinco capas**, y cada una solo habla con la de al lado. **Presentación** es lo que ve el usuario, el panel con el chat, la simulación y el replay, más una API ligera que expone el canal. **Orquestación** es el Orchestrator, que decide qué agente actúa. **Agentes** son los cuatro especialistas. **Simulación** tiene el cargador de modelos de la Fase 1, el motor del mundo 2D y las gráficas. Y **persistencia** son cuatro almacenes: **PostgreSQL, MinIO, Qdrant y Neo4j**, cada uno elegido por cómo se consulta el dato.

Sobre el despliegue: en producción todo corre en **Railway**; en local, con **Docker Compose** en un comando. Fuera quedan los servicios externos por API: **OpenRouter**, el modelo de lenguaje, y los semánticos **Voyage y ZeroEntropy**.

---

## 9 · Una rejilla 2D común

Bajo de la arquitectura al detalle, y arranco por el mundo. El entorno donde viven los modelos es una **rejilla en dos dimensiones**. Es **deliberadamente sencillo**, y soy transparente con eso: no busco un mundo rico, sino un **escenario común** donde paradigmas muy distintos se midan en igualdad de condiciones. Es lo justo para compararlos.

Tiene cinco piezas: el **entorno**, el **agente**, los **recursos**, los **eventos**, que una vez escritos no se tocan más, y el **modelo de decisión**, que lo aporta la Fase 1. La separación que más me importa es entre **cuerpo y mente**: el agente es el cuerpo, su posición, su energía, su historia; el modelo es la mente, cómo elige. Al separarlos, cambio la forma de decidir sin tocar el mundo, y corro varios paradigmas a la vez. Cada evento guarda, por paso: cuándo fue, qué acción tomó, qué recompensa recibió, qué percibía y en qué estado quedó.

---

## 10 · El Orchestrator conduce a los demás

Dentro de esas capas, la que manda es esta. El Orchestrator es el **director de orquesta**, la única pieza que conoce el proceso entero. Un punto que conviene dejar claro, porque suele generar preguntas: **el orden no lo improvisa el modelo**. La secuencia está escrita de antemano, y al modelo solo le dejo elegir **desviaciones puntuales**: una consulta extra, repetir un paso, descartar un intento fallido. No le entrego la planificación completa, y lo hago aposta, para que el proceso sea **auditable y repetible**.

Tiene **tres tareas que no delega**: prepara el contexto antes de llamar a cada agente, agrupa las escrituras y las hace de golpe al final para controlar el gasto, y retransmite en directo por el canal. Y un detalle, lo que llamo **autocompactación**: cuando la conversación se hace muy larga, los turnos antiguos se resumen con una **plantilla fija escrita por código, no por el modelo**, así el resumen es fiable y no mete alucinaciones.

---

## 11 · Cuatro agentes, cuatro cambios de representación

Si el Orchestrator dirige, los cuatro agentes ejecutan. La mejor forma de entenderlos es verlos como una **cadena de traducciones**: cada uno coge la información en un formato y la deja en otro, más cerca del informe.

El **Architect** traduce lenguaje natural a especificación del entorno: convierte mi petición en un tablero 2D concreto y lo valida antes de construirlo. El **Tracker** traduce simulación a observaciones: registra eventos, trayectorias y episodios, y es un **observador puro, no escribe en la memoria**. Lo crítico lo detecta con **reglas de código**: consumos, inanición, muertes, saltos de energía, cambios en la acción dominante, caídas de confianza. Esas señales las marca el código; lo que aporta el modelo es la **síntesis**: decide qué episodios son significativos y redacta la observación estructurada que usan los demás. El **Analyst** traduce observaciones a patrones: es el único que consulta la memoria por su cuenta, contrasta con la teoría y genera las gráficas, incluida la comparativa multi-modelo. Y el **Reporter** traduce patrones a PDF: redacta y compila con LaTeX. Aquí **no maquilla los datos, no inventa cifras**. Si algo falla, hay un respaldo mínimo, pero la evaluación comprueba que lo que entrego es el **PDF real**, no ese respaldo.

---

## 12 · Knowledge Backbone

La memoria ha salido ya varias veces; ahora la abro. Es la memoria del sistema, compartida con la Fase 1. Se accede de forma **centralizada, por el Orchestrator**, salvo el Analyst. Y no es un almacén, **son cuatro**, cada uno elegido por cómo se consulta el dato.

**PostgreSQL** es la verdad estructurada: cada decisión, recompensa y estado, paso a paso y reproducible. **MinIO** guarda lo pesado que no cabe en una fila: los PDF y sus figuras, **y también los ficheros de los modelos de la Fase 1**. **Qdrant** es la memoria de experiencias: recupera episodios por significado y por término exacto en la misma consulta; la amplío en la siguiente. Y **Neo4j** es el conocimiento del dominio: un grafo con paradigmas, autores y papers, que guarda **de dónde sale cada afirmación**, para poder citar la fuente.

¿Cómo se llena? Cuando el Tracker termina, un componente que llamo el **escritor de memoria del Tracker** parte sus observaciones en hechos y los guarda con el **mismo identificador** en todos los almacenes. Dos servicios externos refuerzan lo semántico: **Voyage** genera los embeddings y **ZeroEntropy** reordena por relevancia. Los dos **opcionales**: si no están sus claves, esa capa se apaga.

---

## 13 · Una consulta recorre toda la memoria

Y esa memoria, ¿cómo se consulta? La idea es sencilla: cuando el usuario pregunta, esa misma pregunta se lanza **a la vez contra los cuatro almacenes**, y el Orchestrator junta lo que devuelven en un solo contexto. Cada uno responde a algo que los otros no.

El corazón es **Qdrant**, y voy despacio porque es lo más técnico. Guardo la memoria de dos formas complementarias. La **densa, por significado**: cada texto se convierte en números que capturan su sentido, así que «explorar con poca energía» encuentra episodios sobre drive o homeostasis aunque no repitan esas palabras. Y la **dispersa, por término exacto, con BM25**: la fiable para algo literal como «Rangel 2013» o «DDM-v2», que la semántica tiende a diluir. Junto las dos listas con **Reciprocal Rank Fusion**: no entrena nada, solo premia a los que salen arriba en ambas. Que sea una regla aritmética y reproducible es una virtud.

Sigamos con esa misma pregunta para ver qué añade cada tienda. **PostgreSQL** da el hecho exacto: en qué paso y con qué recompensa consumió cada modelo. **Neo4j** dice contra qué teoría se contrasta, por ejemplo qué postula Rangel sobre la exploración y de qué paper sale. Y **MinIO** devuelve el informe o la figura ya generados. El Orchestrator junta las cuatro respuestas en **un solo contexto** y responde apoyándose en lo que el sistema ya sabe, **sin improvisar**.

---

## 14 · Un nuevo bucle de desarrollo

Cambio de tema: esta parte va de cómo desarrollé el trabajo. El **ciclo clásico del software** era más o menos así: analizar, diseñar, programar y probar, con **programar en el centro, porque escribir el código era lo caro**. Con agentes que generan código, **ese centro se cae**. Yo lo reorganizo en un anillo de cuatro estaciones, donde cada tarea es un **contrato verificable**: especificar, ejecutar, revisar, y aceptar o ajustar; y vuelta a empezar.

Aquí lo importante es el reparto: de las cuatro estaciones, **tres son mías**, especificar, revisar y aceptar, y solo una, ejecutar, es del agente. Y ejecutar, escribir el código, es justo lo que **dejó de ser caro**. Por eso el peso se movió a **especificar bien y verificar**. Eso cambia lo que significa especificar: ya no es un párrafo de requisitos, sino un **plan concreto** para que el agente no rellene huecos con decisiones propias. Muchas las escribí como **pruebas primero, en TDD**, que hacen de contrato. Usé Linear como cuaderno de bitácora, entre marzo y junio de 2026.

---

## 15 · Quién decide, quién implementa

De ese ciclo, concreto una cosa: el reparto entre el humano y el agente. **El humano decide**: el alcance, los contratos, el diseño visual, las prioridades y, sobre todo, la **aceptación final**. Ninguna salida se aceptó solo por venir generada. **El agente implementa**: módulos acotados, pruebas, migraciones, refactores y depuración, pero solo cuando la especificación fija bien el comportamiento; si el contrato es ambiguo, el resultado también.

La idea clave es que **el riesgo cambió de sitio**. Antes era no llegar a escribir a tiempo; ahora es **aceptar una pieza que parece correcta sin comprobar si respeta el sistema**. Por eso reviso siempre el cambio contra la tarea: puede compilar y aun así lo rechazo, si amplía el alcance o mete una abstracción que nadie pidió. Un ejemplo, si hay tiempo: una llamada a herramienta que llegó a medias convirtió un error del modelo en una excepción del servidor; lo resolví leyendo los datos de forma **defensiva** y con pruebas de entradas malas. En la práctica repartí: **Codex** para backend, persistencia y pruebas; **Claude Code** para frontend e interacción.

---

## 16 · Verificar el desarrollo, evaluar el sistema

Y si al final soy yo quien acepta cada cambio, hay que asegurarlo. Esta diapositiva junta cómo verifiqué el desarrollo y cómo evalué el sistema. Las dos responden a lo mismo: **si escribir código dejó de ser lo caro, ¿qué garantiza que lo generado es correcto?**

En verificación: **387 pruebas automáticas** más pruebas de extremo a extremo en el navegador; mi regla era que **sin prueba una tarea no está terminada**. A eso sumo la revisión combinada, la verificación en vivo y una **puerta automática** en cada subida.

La evaluación es más sutil, porque no hay una única respuesta correcta. Uso **tres familias**: la automática, binaria; un **modelo de lenguaje como juez** para lo abierto; y la revisión humana. Con dos principios: **la verdad son los datos de la simulación, no la teoría**; y **quien evalúa no es quien fue evaluado**, el laboratorio razona con Claude, así que el juez es **Codex**, con una rúbrica de seis criterios.

Y los dos casos son reales, ejecuciones instrumentadas de modelos de la Fase 1. El **caso 1**, valor y forrajeo: seis paradigmas en 8×8, 360 eventos, 15 consumos, **nota 88**. El **caso 2**, homeostasis: cuatro paradigmas en 10×10, 199 eventos, 7 consumos, **nota 86**. Los dos, **aprobado con reservas**.

---

## 17 · ¿Qué evalúa el juez?

Antes mencioné un juez externo; aquí detallo qué mira, porque es fácil malinterpretarlo. La vara son las **trayectorias de la simulación, no los papers**: se juzga si el laboratorio contó bien lo que pasó, no si la teoría acierta. Codex puntúa con una **rúbrica de seis criterios**, uno por cada etapa del laboratorio: si el **entorno** del Architect permite observar el comportamiento; si las **observaciones** del Tracker reflejan la simulación; si el **análisis** del Analyst está anclado en las trayectorias, sin inventar; si el **informe** del Reporter es fiel a los datos y es el PDF real; la **robustez** del pipeline de principio a fin; y un **juicio global** con la nota sobre 100.

El ejemplo que más me gusta es del caso 2. El modelo de **inferencia activa** no supo mantener su equilibrio y **murió de hambre en el paso 18**, tras comer una sola vez. Lo interesante es lo que hizo el laboratorio: **no rellenó ni maquilló su trayectoria**; registró los 19 eventos, marcó la inanición y lo siguió comparando. Observó el fallo y lo contó tal cual. Los veredictos fueron **88 y 86**, con reservas por imprecisiones al citar pasos concretos.

---

## 18 · Lo aprendido

Cierro con **tres lecciones**. La idea de fondo es que importó más **la forma de conectar las piezas** que las decisiones internas de cada una. Una: los **contratos finos** entre componentes que evolucionan a ritmos distintos valen mucho; la frontera de tres funciones nunca nos obligó a coordinar versiones. Dos: **centralizar el conocimiento** compensa cuando cada consulta cuesta, porque da control del gasto y facilita el diagnóstico. Tres: **observar no es lo mismo que guardar**; el Tracker observa, pero nunca deja memorias a medias.

Soy honesto con los **límites**: no valida teorías por sí solo, depende del modelo de lenguaje y de servicios externos, el dominio es una rejilla 2D, y la escritura de conocimiento es conservadora. Y propongo **por dónde seguir**: más paradigmas y entornos continuos o multi-agente, métricas cuantitativas estandarizadas, reanudar sesiones, y probarlo con investigadores del grupo.

Con esto termino. **Muchas gracias por su atención**; quedo a su disposición para las preguntas.
