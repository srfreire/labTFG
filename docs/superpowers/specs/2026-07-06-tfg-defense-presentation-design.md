# Presentación de defensa TFG (Fase 2) — Diseño

> Fecha: 2026-07-06
> Autor: Juan Freire Alvarez
> Estado: propuesta pendiente de revisión

## 1. Objetivo

Construir la presentación de defensa del TFG (Fase 2) como un **deck HTML con
reveal.js** que reutiliza el design system del frontend (`frontend/docs/design/`),
animado con **GSAP** en un registro *contenido y profesional*. Debe **tocar los
seis capítulos de la memoria sin profundizar**, apoyar una **demo en vivo** y
resistir un proyector (export a PDF como plan B).

Restricciones fijadas con el usuario:

- **Idioma**: castellano.
- **Duración**: ~20 min (recomendación oficial USC) → ~20 slides.
- **Alcance**: foco en Fase 2, pero explicando la integración con Fase 1
  (contrato `DecisionModel`) y **cómo se coordinó el trabajo** entre ambas fases
  (frontera fina + Linear).
- **Formato**: reveal.js.
- **Animación**: GSAP, nivel *contenido y pro* (entradas suaves, diagramas que se
  dibujan al avanzar; nada de partículas ni morphing agresivo).
- **Slide 1**: vídeo hero de un mock ejecutándose.
- **Slide de demo**: justo después del problema (slide 3), como *hook* ("enseñar
  antes de explicar"). El vídeo del mock/demo **lo graba y aporta el usuario**.

## 2. Camino simplificado (respecto a la petición original)

La petición inicial ("convertir un design system en DESIGN.md, sacar tokens y
crear HTML") ya está parcialmente hecha: existen `frontend/docs/design/system.md`
y `frontend/docs/design/tokens.css`. **No regeneramos un DESIGN.md**: reutilizamos
`tokens.css` como base del tema de reveal.js. Un paso menos.

## 3. Arquitectura técnica

Proyecto estático autocontenido, servible con cualquier servidor de ficheros.

```
phase2-juan/docs/presentacion-defensa/
  index.html                 # deck reveal.js (todas las slides)
  css/
    theme.css                # tema propio construido sobre los tokens
    tokens.css               # copia de frontend/docs/design/tokens.css
  js/
    deck.js                  # init de reveal + registro de timelines GSAP
    animations.js            # timelines GSAP por slide (enganchadas a fragments)
  assets/
    img/                     # screenshots UI (copiadas de figuras/ui-*.png)
    video/
      demo.mp4               # grabación del mock/demo que aporta el usuario
    fonts/                   # Satoshi + IBM Plex Mono (self-hosted)
  README.md                  # cómo servir, navegar, exportar PDF, colocar el vídeo
```

### Librerías

- **reveal.js** (core) — navegación, fragments, speaker notes, `?print-pdf`.
- **GSAP** (core; sin plugins de pago) — `gsap.timeline()` por slide, disparadas
  desde los eventos `fragmentshown` / `slidechanged` de reveal.
- **highlight.js** — snippet del contrato `DecisionModel`.
- Fuentes: **Satoshi** (Fontshare) + **IBM Plex Mono** (Google Fonts),
  self-hosted en `assets/fonts/` para funcionar offline en la defensa.

### Tema

`theme.css` deriva de los tokens: fondo `#0a0a0a`, paneles frosted glass
(`backdrop-filter: blur`), tipografía Satoshi + IBM Plex Mono, y la **paleta por
agente** como color semántico de cada bloque:

| Agente | Color token | Uso en slides |
|--------|-------------|---------------|
| Architect | verde `#4ade80` | bloque/acento de la spec de entorno |
| Tracker | ámbar `#fbbf24` | bloque de observación/trayectorias |
| Analyst | púrpura `#a78bfa` | bloque de análisis/gráficas |
| Reporter | rosa `#f472b6` | bloque de informe/PDF |
| Orchestrator | slate `#94a3b8` | bloque de orquestación |

### Diagramas

Los diagramas conceptuales **no son imágenes**: se construyen en HTML/SVG y se
animan con GSAP para dibujarse al avanzar con los clics del ponente. Diagramas
"hero" a construir:

1. **Pipeline de 4 agentes** (slide 10): nodos Architect→Tracker→Analyst→Reporter
   que se iluminan por color en secuencia.
2. **Recorrido de representaciones** (transversal): NL → JSON spec → observaciones
   → interpretación → PDF, dibujado paso a paso.
3. **Arquitectura de despliegue** (slide 7): Frontend / API / Orchestrator / Fase1
   / infraestructura compartida.
4. **Knowledge Backbone** (slide 11): Postgres · MinIO · Qdrant (denso+BM25) ·
   Neo4j ensamblándose.
5. **Bucle de desarrollo** (slide 13): especificar → ejecutar → revisar → aceptar.

Diagramas secundarios (casos de uso, clases, secuencia, Gantt) que ya existen en
la memoria pueden incorporarse como imagen si hiciera falta, sin recrearlos.

### Vídeo (hero + demo)

El **usuario graba** un vídeo de su mock/demo y lo coloca en
`assets/video/demo.mp4`. Se usa en dos sitios:

- **Slide 1 (hero)**: de fondo como `<video autoplay muted loop playsinline>` con
  el título superpuesto (loop corto, silenciado).
- **Slide 3 (demo)**: el mismo vídeo a pantalla ~completa con controles, como
  *hook* tras presentar el problema.

Hasta que el usuario aporte el vídeo, se deja un **placeholder** (poster estático
con una captura del dashboard y un rótulo "DEMO") para poder maquetar. No se graba
nada automáticamente en esta iteración.

### Assets reutilizados

Screenshots reales ya existentes en
`phase2-juan/docs/tfg-memoria-latex/figuras/` (se copian a `assets/img/`):

`ui-01-dashboard-inicial`, `ui-02-architect-spec`, `ui-03-simulacion-replay`,
`ui-04-analisis-charts`, `ui-05-tracker-trayectorias`, `ui-06-analyst-patrones`,
`ui-07-decision-traces`, `ui-09-reporter-pdf`, `ui-10-pipeline-accion`,
`ui-11-knowledge-graph`.

## 4. Estructura de slides (~20, castellano)

Cada slide indica capítulo de origen y tratamiento visual. El contenido procede
del mapa fiel de la memoria (no se inventan datos).

1. **Portada** — título completo, Juan Freire Alvarez, director Eduardo M. Sánchez
   Vila, USC. Fondo: vídeo hero (loop corto del demo). *(video)*
2. **El problema** — de "paradigma descrito" a "experimento observable, comparable
   y revisable". *(Intro; texto + acento)*
3. **DEMO** — vídeo del sistema funcionando, tras el problema como *hook*
   ("enseñar antes de explicar"). *(vídeo aportado por el usuario)*
4. **Dos fases, una frontera fina** — Fase 1 (Pablo): NL → modelo ejecutable;
   Fase 2 (Juan): ejecutar → observar → analizar → informar → recordar. *(Intro;
   diagrama simple)*
5. **Contrato `DecisionModel`** — duck typing, `decide` / `update` / `get_state`,
   sin herencia ni dependencias estáticas. *(código animado highlight.js)*
6. **Objetivo y 6 objetivos específicos** — spec de entorno, ejecución
   multi-modelo, registro estructurado, análisis, PDF, memoria reutilizable.
   *(Intro; lista con fragments)*
7. **Requisitos de un vistazo** — 5 casos de uso · 13 RF · 14 RNF; menciona
   degradación controlada y recuperación segura NL-SQL. *(Cap. 2; contadores +
   3 destacados)*
8. **Arquitectura** — diagrama de despliegue animado. *(Cap. 3; diagrama GSAP)*
9. **El dominio 2D** — rejilla, recursos, eventos inmutables; separación Agent
   (quién/dónde) vs DecisionModel (cómo decide). *(Cap. 3; mini-grid)*
10. **Orchestrator** — coordinador único, secuencia canónica de tool calls; el LLM
    solo elige desviaciones; pre-recupera contexto y difiere persistencia. *(Cap. 3)*
11. **Los 4 agentes especializados** — Architect/Tracker/Analyst/Reporter, cada uno
    un cambio de representación. *(Cap. 3; diagrama estrella GSAP por color)*
12. **Knowledge Backbone** — Postgres (metadatos/historial) · MinIO (PDF/artefactos)
    · Qdrant (denso + BM25) · Neo4j (grafo de procedencia); Voyage + ZeroEntropy
    opcionales. *(Cap. 3; diagrama GSAP)*
13. **La UI en detalle** — capturas que la demo rápida no cubre: patrones del
    Analyst, decision traces, PDF del Reporter. *(Cap. 3; screenshots ui-06/07/09)*
14. **Nuevo bucle de desarrollo** — especificar → ejecutar → revisar → aceptar; la
    implementación deja de ser lo caro. *(Cap. 4; diagrama de bucle GSAP)*
15. **Cómo nos coordinamos** — frontera mínima con Fase 1 (3 métodos, sin
    coordinar releases) + Linear como memoria operativa (criterios, dependencias,
    paralelismo); reparto humano vs agente. *(Cap. 4; texto + acento)*
16. **Cronograma** — Gantt marzo–junio 2026 (diseño → núcleo → web → análisis →
    persistencia → despliegue). *(Cap. 4; imagen del Gantt o barras HTML)*
17. **La verificación, nuevo cuello de botella** — 3 capas: pytest/Playwright/LaTeX
    · revisión humano+subagentes · run instrumentada con métricas duras. *(Cap. 4)*
18. **Evaluación** — dos principios (verdad = datos de simulación; evaluado ≠
    evaluador); CASO1 (valor/forrajeo, 6 paradigmas) y CASO2 (homeostasis, 4
    paradigmas). *(Cap. 5; dos tarjetas)*
19. **Resultados** — tripleta joinable ✓ (Postgres = Qdrant denso = Qdrant sparse),
    determinismo semilla 42 ✓, PDF tectonic real ✓; **juez Codex: CASO1 88/100,
    CASO2 86/100**. *(Cap. 5; contadores animados + tarjetas de veredicto)*
20. **Conclusiones, límites y cierre** — 3 lecciones (la forma de conectar > las
    piezas · centralizar el acceso a conocimiento compensa · separar observación de
    persistencia); límites (no valida teorías solo, dependencia de LLM, dominio 2D)
    y ampliaciones (más paradigmas, métricas estandarizadas, reanudación de
    sesiones); reflexión final: "de cómo lo escribo a qué quiero exactamente que
    ocurra". Cierre + gracias. *(Cap. 6)*

> La demo (slide 3) es vídeo pregrabado, no cambio a la app en vivo: cero riesgo de
> fallo de red/proyector durante la defensa.

## 5. Datos verificados a usar (de la memoria)

- Requisitos: **5 CU · 13 RF · 14 RNF**.
- CASO1: 6 paradigmas, rejilla 8×8, 6 recursos, 360 eventos, 15 consumos, tripleta
  13=13=13, latencia ~212 s, coste ≈0.94 $.
- CASO2: 4 paradigmas, rejilla 10×10, 8 recursos, 199 eventos, 7 consumos, tripleta
  9=9=9, latencia ~208 s, coste ≈1.00 $.
- Juez Codex (rúbrica 6 criterios): **88/100 (CASO1)**, **86/100 (CASO2)**.
- Stack: React 19 + Vite + Tailwind 4 · FastAPI + Uvicorn · OpenRouter · Postgres ·
  MinIO · Qdrant (denso+BM25) · Neo4j · Voyage AI · ZeroEntropy · Docker Compose.

## 6. Build / uso

- Servir: `cd phase2-juan/docs/presentacion-defensa && python3 -m http.server 8080`.
- Navegar: reveal.js (flechas / espacio); notas de orador con `s`.
- Export PDF: abrir `?print-pdf` e imprimir a PDF desde el navegador.
- Regrabar vídeo hero: `node mock/record-hero.mjs` (requiere Playwright instalado).

## 7. Fuera de alcance (YAGNI)

- No se regenera un DESIGN.md nuevo (ya existen system.md + tokens.css).
- No se recrean todos los diagramas de la memoria; solo los 5 "hero".
- No se graba ningún vídeo automáticamente: el vídeo del mock/demo lo aporta el
  usuario. Hasta entonces se maqueta con un placeholder (poster + rótulo "DEMO").
- No se cubren apéndices de la memoria (manual técnico, catálogo de tool calls).

## 8. Riesgos

- **Fuentes offline**: si Satoshi no está disponible, degradar a system-ui.
- **Vídeo pendiente**: si el usuario aún no ha aportado `demo.mp4`, el deck debe
  verse bien con el placeholder (poster estático) para poder ensayar.
- **Timing 20 min**: 20 slides ≈ 1 min/slide; ajustar recortando slides 6/16 si va
  largo.
- **Compatibilidad proyector**: `backdrop-filter` puede fallar; degradar a fondo
  sólido con opacidad.
