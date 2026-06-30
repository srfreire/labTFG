# Veredicto

pass con reservas

# Tabla de evidencias

| Criterio | Juicio | Ruta de evidencia |
|---|---|---|
| 1. Fidelidad del entorno (Architect) | Entorno coherente para homeostasis/interocepción: rejilla 10x10, 8 recursos `food`, `energy_content=[1,10]`, regeneración y acciones estándar. Como en caso1, el spec es mínimo y deja campos descriptivos nulos. | `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso2-lab/judge-bundle/env_spec.json` |
| 2. Fidelidad de observación (Tracker) | Conteos principales correctos: 4/2/1/0 consumos, muerte de Active inference tras 19 registros y acciones agregadas coincidentes. Reservas: un episodio dice `60 de 72 acciones totales` para Predictive coding, incompatible con 60 pasos; y el gap TD-Q 0.58 -> 0.0 no sale directamente de `q_values`. | `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso2-lab/judge-bundle/tracker_output.json`; `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso2-lab/judge-bundle/trajectories/*.json`; `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso2-lab/judge-bundle/metrics.json` |
| 3. Calidad del análisis (Analyst) | Buen análisis central: identifica reposo estratégico de Drive-dynamics, colapso energético de Active inference y fracaso de Predictive coding. Reservas: porcentajes/denominadores de movimiento y convergencia Q se expresan con demasiada fuerza, y el detector de gap 0.58 no está fundamentado en los JSON. | `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso2-lab/judge-bundle/analyst_findings.md`; trayectorias en `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso2-lab/judge-bundle/trajectories/` |
| 4. Fidelidad del informe (Reporter) | PDF real de LaTeX, no fallback, 9 paginas, visualmente legible y sin secciones vacías visibles. Los totales y la tabla de perfiles son mayormente fieles. Reservas: conserva narrativas de Q-values/gaps poco reproducibles y trata la cercanía espacial como explicación fuerte. | `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso2-lab/judge-bundle/report.pdf`; `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso2-lab/judge-bundle/metrics.json` |
| 5. Robustez del pipeline | Pipeline sólido: `joinable_triple.consistent=true`, 8/8 documentos en Postgres/Qdrant dense/sparse, determinismo `identical=true`, PDF real, 4 gráficos y sin fallback. | `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso2-lab/judge-bundle/metrics.json` |
| 6. Juicio global y puntuación | Pasa porque el comportamiento observado está bien capturado en lo esencial, pero las reservas son más visibles que en caso1: episodios con denominadores erróneos y claims de gap/convergencia no verificables. | Todo el bundle en `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso2-lab/judge-bundle/` |

# Hallazgos por criterio

## 1. Fidelidad del entorno (Architect)

El entorno es adecuado para comparar modelos homeostáticos, interoceptivos y predictivos: `env_spec.json` define rejilla 10x10, acciones `move_up`, `move_down`, `move_left`, `move_right`, `eat`, `stay`, y 8 recursos `food` regenerativos con `energy_content=[1,10]`. Esto permite observar reposo, búsqueda, consumo, agotamiento energético y fracaso de navegación.

La especificación vuelve a ser escueta: campos como `name`, `description`, `reward`, `termination` y `max_steps` no aparecen informativos en el resumen leído. Sin embargo, `metrics.json` confirma `steps=60` y el experimento efectivamente produce diferencias observables.

## 2. Fidelidad de observación (Tracker)

Los agregados del Tracker son fieles. `tracker_output.json` reporta Drive-dynamics con 4 consumos y acciones `stay=44`, `move_down=7`, `eat=4`, `move_right=2`, `move_up=1`, `move_left=2`, coincidiendo con `homeostatic-regulation_continuous-drive-dynamics-with-urgency-threshold-policy.json`. TD-Q tiene 2 consumos en pasos 24 y 45; Active inference tiene 19 pasos y 1 consumo en paso 6; Predictive coding tiene 0 consumos y 60 pasos.

La infraestructura de observación es consistente: `metrics.json` indica `events=199`, que coincide con 60+60+19+60 registros, `joinable_triple` con `written=8`, `postgres_rows=8`, `qdrant_dense=8`, `qdrant_sparse=8`, `consistent=true`, y determinismo `identical=true`.

Las reservas son concretas. El episodio de Predictive coding dice "83% de acciones fueron movimiento (60 de 72 acciones totales)", pero la trayectoria tiene 60 acciones totales: 50 movimientos, 10 `stay`, 0 `eat`. El 83% es correcto como 50/60, pero "60 de 72" es incorrecto. El episodio TD-Q afirma gap 0.58 -> 0.0 en paso 46; desde `q_values`, el gap es 0.020999 en paso 45 y 0.0269 en paso 46, salvo que exista otro detector no documentado.

## 3. Calidad del análisis (Analyst)

El Analyst acierta la estructura conductual. P1 describe bien el ciclo de Drive-dynamics: `drive=0.0256` en paso 7, búsqueda y consumo en paso 11, reset de `drive` a 0.0, y repeticiones en pasos 23, 40 y 56. P3 refleja la trayectoria de Active inference: energía 0.45 en paso 0, 0.26 en paso 5, 0.56 tras comer en paso 6, y terminación en paso 18. P4 identifica correctamente que Predictive coding no consume pese a 50 movimientos.

Hay reservas de precisión. P2 dice "80% de acciones de movimiento (58 de 60)", pero la trayectoria TD-Q tiene 46 movimientos direccionales, 12 `stay` y 2 `eat`; si se cuentan acciones no-`stay`, son 48/60 = 80%, no 58/60. P7 adopta el detector "gap=0.576" como hecho, aunque el rango directo de `q_values` no lo respalda. Además, cuando el análisis afirma que los Q-values no desarrollan preferencias claras, debería matizar que hay diferencias pequeñas y locales, no convergencia estrictamente nula.

## 4. Fidelidad del informe (Reporter)

El PDF es real: `metrics.json` marca `pdf_produced=true` y `pdf_is_real_latex=true`; `pdfinfo` muestra productor `xdvipdfmx`, 9 páginas A4 y tamaño 478302 bytes. La renderización a PNG mostró índice y páginas finales legibles, sin páginas en blanco ni defectos visuales evidentes en la muestra inspeccionada.

El informe mejora respecto a versiones previas. La tabla de perfiles de acción usa categorías correctas: Drive-dynamics 12 movimientos, 44 espera, 4 consumo; HRL 46 movimientos, 12 espera, 2 consumo; Active inference 15 movimientos, 3 espera, 1 consumo; Predictive coding 50 movimientos, 10 espera, 0 consumo. Los consumos totales 4/2/1/0 y la muerte en paso 18 son fieles.

Las reservas permanecen en afirmaciones derivadas: el PDF habla de colapso de diferenciación Q tras el paso 45 y valores "prácticamente uniformes", pero los JSON dan gaps pequeños no nulos (0.020999 en paso 45 y 0.0269 en paso 46). También trata la desigualdad espacial como confusor plausible; eso es razonable como hipótesis, pero debe quedar separado de la verdad observada.

## 5. Robustez del pipeline

El pipeline es robusto en métricas duras. `metrics.json` reporta `experiment_id=7dc5ff08-b470-4294-9924-bbc045cc3162`, `events=199`, `charts_generated=4`, `total_seconds=197.62`, coste estimado `0.9919`, latencias por etapa completas y PDF real. No hay señales de fallo de etapa ni fallback del Reporter.

La robustez semántica del análisis de eventos todavía necesita ajuste: el Tracker puede generar episodios con denominadores o gaps inconsistentes, aunque las tablas base y el almacenamiento estén correctos.

## 6. Juicio global y puntuación

El laboratorio pasa con reservas. En lo esencial, observa correctamente la simulación: Drive-dynamics gana con 4 consumos y reposo estratégico, TD-Q consume 2 veces con exploración amplia, Active inference muere tras un consumo, y Predictive coding no consume. Las reservas afectan a la capa interpretativa y episodios derivados, no a la ejecución base.

# Qué debe revisar un experto manualmente

- Corregir el episodio Tracker de Predictive coding: debe decir 50/60 movimientos, no "60 de 72 acciones totales".
- Documentar o corregir el detector de `gap` que produce 0.58 -> 0.0 para TD-Q; desde `q_values` completos los gaps son 0.020999 y 0.0269 en pasos 45-46.
- Matizar "58 de 60" en Analyst P2: 80% solo es correcto si significa acciones no-`stay` (48/60), no movimientos direccionales.
- Separar las inferencias sobre ventaja posicional inicial de los hechos observados de la trayectoria.
- Revisar si en Predictive coding se deben excluir acciones bloqueadas como `eat=-1e6` al hablar del rango de Q-values.

# Score final

85/100. La base observacional y el PDF son sólidos, y el pipeline es reproducible. Se descuentan puntos por errores concretos en episodios derivados, denominadores de movimiento y afirmaciones de gap/convergencia no trazables directamente a las trayectorias.
