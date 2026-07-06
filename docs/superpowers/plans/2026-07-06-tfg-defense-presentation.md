# TFG Defense Presentation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reveal.js HTML slide deck (20 slides, castellano) for Juan Freire's TFG Phase 2 defense, reusing the frontend design tokens and animated with GSAP in a contained, professional register.

**Architecture:** A self-contained static project under `phase2-juan/docs/presentacion-defensa/`. `index.html` holds all slides; `css/theme.css` derives from `css/tokens.css` (copied from the frontend design system); `js/deck.js` initialises reveal.js and wires GSAP timelines to reveal's `fragmentshown`/`slidechanged` events; `js/animations.js` is a registry of per-slide timelines. Conceptual diagrams are hand-built HTML/SVG animated with GSAP; UI slides reuse existing real screenshots.

**Tech Stack:** reveal.js (core), GSAP (core), highlight.js, Satoshi + IBM Plex Mono (self-hosted fonts), plain HTML/CSS/JS. No build step — served as static files.

## Global Constraints

- Language of all slide content: **castellano**.
- Target length: **20 slides** for ~20 min.
- Animation register: **contained and professional** — soft entrances, diagrams that draw on advance; no particles, no aggressive morphing.
- Reuse `frontend/docs/design/tokens.css` verbatim; do **not** author a new DESIGN.md.
- Agent color code (from tokens): Architect `#4ade80`, Tracker `#fbbf24`, Analyst `#a78bfa`, Reporter `#f472b6`, Orchestrator `#94a3b8`.
- Base background `#0a0a0a`; fonts Satoshi (body) + IBM Plex Mono (labels/code/data).
- Must export to PDF via reveal's `?print-pdf`; must work offline (self-hosted fonts, vendored libs).
- Data used in slides must match the memoria verbatim (see spec §5). Never invent figures.
- The demo video (`assets/video/demo.mp4`) is supplied by the user; until then use a placeholder poster.
- Verification is visual: serve the deck and screenshot with Playwright (webapp-testing skill) or open in a browser. There are no unit tests.
- Deliverable path root: `phase2-juan/docs/presentacion-defensa/` (referred to below as `<root>`).
- Source of truth for content: `docs/superpowers/specs/2026-07-06-tfg-defense-presentation-design.md`.

---

### Task 1: Project scaffold — reveal.js, tokens, fonts, empty deck renders

**Files:**
- Create: `<root>/index.html`
- Create: `<root>/css/tokens.css` (copy of `frontend/docs/design/tokens.css`)
- Create: `<root>/css/theme.css`
- Create: `<root>/js/deck.js`
- Create: `<root>/vendor/` (reveal.js + gsap + highlight.js, vendored)
- Create: `<root>/assets/fonts/` (Satoshi + IBM Plex Mono)
- Create: `<root>/README.md`

**Interfaces:**
- Produces: a served deck at `http://localhost:8080` showing a single title slide with `#0a0a0a` background, Satoshi heading, IBM Plex Mono label. `js/deck.js` calls `Reveal.initialize({ hash: true, transition: 'fade' })`.

- [ ] **Step 1: Vendor the libraries**

Download into `<root>/vendor/`:
```bash
cd <root> && mkdir -p vendor assets/fonts css js
# reveal.js
curl -L https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reveal.js -o vendor/reveal.js
curl -L https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reveal.css -o vendor/reveal.css
# GSAP
curl -L https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js -o vendor/gsap.min.js
# highlight.js (core + a dark base we override)
curl -L https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/lib/core.min.js -o vendor/highlight.min.js
curl -L https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/python.min.js -o vendor/highlight-python.min.js
```
Expected: five files present in `vendor/`. If a CDN 404s, pin the nearest available patch version and note it in `README.md`.

- [ ] **Step 2: Self-host fonts**

Download Satoshi (Fontshare) and IBM Plex Mono (Google Fonts / GitHub) woff2 into `assets/fonts/` and write `css/fonts.css` with `@font-face` for `Satoshi` (400/500/600) and `IBM Plex Mono` (400/500/600). If Satoshi woff2 is not fetchable offline, document the fallback `system-ui` in `README.md` and still write the `@font-face` with a local path so it works once dropped in.

- [ ] **Step 3: Write `css/tokens.css`**

Copy `frontend/docs/design/tokens.css` verbatim into `<root>/css/tokens.css` (keep the `:root { --color-* … }` block). This is the single source of design values.

- [ ] **Step 4: Write `css/theme.css` (base only)**

```css
@import "./tokens.css";
@import "./fonts.css";

.reveal { font-family: var(--font-sans); color: var(--color-text); }
.reveal .slides { text-align: left; }
:root { --r-background-color: var(--color-bg); }
.reveal h1, .reveal h2, .reveal h3 { font-family: var(--font-sans); font-weight: var(--weight-semibold); letter-spacing: -0.01em; text-transform: none; line-height: var(--leading-tight); }
.reveal .label { font-family: var(--font-mono); font-size: 0.7rem; letter-spacing: 2px; text-transform: uppercase; color: var(--color-text-faint); }
.reveal .mono { font-family: var(--font-mono); }
```

- [ ] **Step 5: Write `index.html` with one title slide**

```html
<!doctype html><html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Defensa TFG — Laboratorio virtual</title>
<link rel="stylesheet" href="vendor/reveal.css">
<link rel="stylesheet" href="css/theme.css">
</head><body>
<div class="reveal"><div class="slides">
  <section data-slide="portada">
    <div class="label">TFG · Enxeñaría Informática · USC</div>
    <h1>Laboratorio virtual de paradigmas de decisión</h1>
  </section>
</div></div>
<script src="vendor/reveal.js"></script>
<script src="vendor/gsap.min.js"></script>
<script src="js/deck.js"></script>
</body></html>
```

- [ ] **Step 6: Write `js/deck.js`**

```js
Reveal.initialize({ hash: true, transition: 'fade', transitionSpeed: 'slow', width: 1280, height: 720, margin: 0.06 });
```

- [ ] **Step 7: Serve and screenshot**

Run: `cd <root> && python3 -m http.server 8080` then screenshot `http://localhost:8080` with Playwright (webapp-testing skill).
Expected: black `#0a0a0a` slide, uppercase mono label, Satoshi (or system-ui fallback) heading. No console errors.

- [ ] **Step 8: Commit**

```bash
git add <root> && git commit -m "feat[defensa]: scaffold reveal.js deck with design tokens"
```

---

### Task 2: Theme components — panels, agent colors, layout, counters

**Files:**
- Modify: `<root>/css/theme.css`
- Create: `<root>/css/components.css`
- Modify: `<root>/index.html` (add `<link>` + a demo showcase slide, removed in Task 4)

**Interfaces:**
- Produces reusable CSS classes consumed by every later task:
  - `.panel` — frosted glass card (`background: var(--color-surface-frosted); backdrop-filter: blur(24px); border: 1px solid var(--color-border); border-radius: var(--radius-2xl); box-shadow: var(--shadow-panel);`)
  - `.agent--architect|--tracker|--analyst|--reporter|--orchestrator` — sets `--agent` custom prop to the token color; `.panel.agent--x` tints border to `color-mix(in srgb, var(--agent) 25%, transparent)` and adds a colored title.
  - `.grid-2`, `.grid-3` — CSS grid layouts with `gap: var(--space-6)`.
  - `.stat` (big number) + `.stat__num` (mono, `4rem`) + `.stat__label`.
  - `.chip` — pill using `--radius-full`, mono, `0.7rem`.

- [ ] **Step 1: Write `css/components.css`** with the classes above, using only token variables (no hardcoded colors except `color-mix` over tokens).

- [ ] **Step 2: Add a temporary showcase slide** to `index.html` containing one `.panel.agent--analyst` with a title, one `.grid-3` of `.stat`s (13 / 14 / 5), and three `.chip`s.

- [ ] **Step 3: Serve and screenshot**; confirm frosted panel, purple-tinted border, three big mono numbers, pills. Adjust spacing to match the dense dashboard feel.

- [ ] **Step 4: Commit**

```bash
git add <root>/css <root>/index.html && git commit -m "feat[defensa]: theme components (panels, agent colors, stats)"
```

---

### Task 3: GSAP timeline harness

**Files:**
- Create: `<root>/js/animations.js`
- Modify: `<root>/js/deck.js`
- Modify: `<root>/index.html` (load `animations.js`)

**Interfaces:**
- Produces global `SlideAnim` registry consumed by every diagram task:
  - `SlideAnim.register(slideId, buildFn)` where `buildFn(sectionEl)` returns a **paused** `gsap.timeline()`.
  - `deck.js` builds the timeline on `slidechanged` (lazily, once per slide) and, on each `fragmentshown`, calls `timeline.play()` up to the next labelled point, OR plays the whole timeline on slide entry if the slide registered no fragments. Timelines reset (`timeline.progress(0).pause()`) on `slidechanged` away.
  - Convention: a diagram animates by `data-anim` targets inside its `<section>`; build functions use `sectionEl.querySelectorAll('[data-anim=...]')`.

- [ ] **Step 1: Write `js/animations.js`**

```js
window.SlideAnim = (() => {
  const builders = new Map();
  const live = new Map(); // slideId -> timeline
  return {
    register(id, fn) { builders.set(id, fn); },
    build(id, el) {
      if (live.has(id)) return live.get(id);
      const fn = builders.get(id); if (!fn) return null;
      const tl = fn(el); live.set(id, tl); return tl;
    },
    reset(id) { const tl = live.get(id); if (tl) tl.progress(0).pause(); },
    get(id) { return live.get(id); },
  };
})();
```

- [ ] **Step 2: Wire `deck.js`**

```js
Reveal.initialize({ hash: true, transition: 'fade', transitionSpeed: 'slow', width: 1280, height: 720, margin: 0.06 });
function slideId(ev){ return ev.currentSlide?.dataset?.slide; }
Reveal.on('slidechanged', ev => {
  const prev = ev.previousSlide?.dataset?.slide; if (prev) SlideAnim.reset(prev);
  const id = slideId(ev); if (!id) return;
  const tl = SlideAnim.build(id, ev.currentSlide);
  if (tl && ev.currentSlide.querySelectorAll('.fragment').length === 0) tl.play();
});
Reveal.on('fragmentshown', ev => {
  const id = ev.fragment.closest('section')?.dataset?.slide;
  const tl = id && SlideAnim.get(id); if (tl) tl.play();
});
```

- [ ] **Step 3: Smoke test** — register a throwaway timeline on the showcase slide that fades a `.stat` in; serve, navigate to it, confirm it animates once and resets when leaving. Remove the throwaway after confirming.

- [ ] **Step 4: Commit**

```bash
git add <root>/js <root>/index.html && git commit -m "feat[defensa]: GSAP timeline harness wired to reveal events"
```

---

### Task 4: Slides 1–3 — Portada, Problema, Demo

**Files:**
- Modify: `<root>/index.html` (replace showcase slide with slides 1–3)
- Create: `<root>/assets/img/` (copy `ui-01-dashboard-inicial.png` for the demo poster)
- Create: `<root>/assets/video/README.txt` (note: drop `demo.mp4` here)

**Interfaces:** Consumes `.label`, `.panel` from Tasks 1–2.

- [ ] **Step 1: Copy the poster image**

```bash
cp phase2-juan/docs/tfg-memoria-latex/figuras/ui-01-dashboard-inicial.png <root>/assets/img/
```

- [ ] **Step 2: Write the three slides** in `index.html`:

Slide 1 (portada): full-bleed `<video autoplay muted loop playsinline poster="assets/img/ui-01-dashboard-inicial.png">` with `<source src="assets/video/demo.mp4">`, dark overlay, title `Laboratorio virtual para la simulación y análisis de paradigmas de decisión humana con agentes inteligentes`, subtitle `Juan Freire Alvarez · Fase 2`, `Director: Eduardo M. Sánchez Vila · USC`.

Slide 2 (problema) `data-slide="problema"`: headline `De un paradigma descrito a un experimento revisable`. Three fragment lines: `Fase 1 produce modelos de decisión ejecutables.` / `¿Cómo se ejecutan, observan y comparan de forma trazable?` / `Fase 2: cerrar el recorrido de modelo a evidencia.`

Slide 3 (demo) `data-slide="demo"`: `.label` = `DEMO`, and the same `<video controls poster=...>` near-fullscreen. Caption `El sistema en marcha` (mono, dim).

- [ ] **Step 3: Serve and screenshot** slides 1–3. Confirm the poster shows (video absent is fine), title legible over overlay, demo slide fills the frame.

- [ ] **Step 4: Commit**

```bash
git add <root> && git commit -m "feat[defensa]: slides 1-3 (portada, problema, demo)"
```

---

### Task 5: Slides 4–5 — Dos fases + Contrato DecisionModel

**Files:**
- Modify: `<root>/index.html`
- Modify: `<root>/js/animations.js`
- Modify: `<root>/index.html` (load highlight.js + register python)

**Interfaces:** Consumes `SlideAnim.register`, `.panel`, agent colors.

- [ ] **Step 1: Slide 4 (`data-slide="dos-fases"`)** — headline `Dos fases, una frontera fina`. Two `.panel`s in `.grid-2`: left `Fase 1 · Pablo Pazos` → `Lenguaje natural → modelo Python ejecutable`; right `Fase 2 · Juan Freire` → `Ejecutar · observar · analizar · informar · recordar`. A center arrow `[data-anim="bridge"]` between them. Register a timeline that draws the arrow (`scaleX 0→1`) and fades panels in.

- [ ] **Step 2: Slide 5 (`data-slide="contrato"`)** — headline `Un contrato mínimo: duck typing`. A `<pre><code class="language-python">` block:

```python
class DecisionModel(Protocol):
    def decide(self, perception: dict) -> Action: ...        # elegir acción (solo lectura)
    def update(self, action, reward, new_perception): ...     # ajustar estado interno
    def get_state(self) -> dict: ...                          # exponer internals (q_values)
```
Sidebar note: `Sin herencia, sin dependencias estáticas. Ambas fases evolucionan por separado.`

- [ ] **Step 3: Load + init highlight.js** in `index.html`:
```html
<script src="vendor/highlight.min.js"></script>
<script src="vendor/highlight-python.min.js"></script>
```
and in `deck.js` after init: `hljs.highlightAll();`. Add a mono/dark code style in `theme.css` using token colors.

- [ ] **Step 4: Serve and screenshot** slides 4–5; confirm arrow animates on advance and the code is syntax-highlighted and readable at projector size (≥20px).

- [ ] **Step 5: Commit**

```bash
git add <root> && git commit -m "feat[defensa]: slides 4-5 (dos fases, contrato DecisionModel)"
```

---

### Task 6: Slides 6–7 — Objetivos + Requisitos (counters)

**Files:**
- Modify: `<root>/index.html`, `<root>/js/animations.js`

**Interfaces:** Consumes `.stat`, `SlideAnim`.

- [ ] **Step 1: Slide 6 (`data-slide="objetivos"`)** — headline `Seis objetivos específicos`. A `.grid-3` (or list with fragments) of six items: `Generar la especificación del entorno` · `Ejecutar modelos sin acoplamiento` · `Registrar el comportamiento de forma estructurada` · `Analizar patrones` · `Generar informe PDF` · `Persistir memorias reutilizables`.

- [ ] **Step 2: Slide 7 (`data-slide="requisitos"`)** — headline `Requisitos, de un vistazo`. A `.grid-3` of three `.stat`: `5` `Casos de uso`, `13` `Requisitos funcionales`, `14` `Requisitos no funcionales`. Below, three `.chip`s: `Degradación controlada` · `Recuperación segura NL-SQL` · `Determinismo reproducible`.

- [ ] **Step 3: Register counter timeline** for slide 7 in `animations.js` — animate each `.stat__num` from 0 to its value via a GSAP tween on a proxy object updating `textContent` (integers). Example:
```js
SlideAnim.register('requisitos', el => {
  const tl = gsap.timeline({ paused: true });
  el.querySelectorAll('.stat__num').forEach(n => {
    const end = +n.dataset.to, o = { v: 0 };
    tl.to(o, { v: end, duration: 0.9, ease: 'power1.out',
      onUpdate: () => n.textContent = Math.round(o.v) }, 0);
  });
  return tl;
});
```
Set `data-to="5|13|14"` and initial text `0` on the stat nums.

- [ ] **Step 4: Serve and screenshot**; confirm counters roll up on slide entry.

- [ ] **Step 5: Commit**

```bash
git add <root> && git commit -m "feat[defensa]: slides 6-7 (objetivos, requisitos con contadores)"
```

---

### Task 7: Slide 8 — Arquitectura (GSAP deployment diagram)

**Files:**
- Modify: `<root>/index.html`, `<root>/js/animations.js`
- Create: `<root>/css/diagrams.css`

**Interfaces:** Consumes `SlideAnim`, tokens. Produces `.node`, `.edge` diagram primitives reused by Tasks 9–10, 12.

- [ ] **Step 1: Write `css/diagrams.css`** — `.diagram` (relative container), `.node` (bordered token-surface box, mono label), `.node--api|--orch` accent variants, `.edge` (SVG line/path styled with `--color-border`).

- [ ] **Step 2: Slide 8 (`data-slide="arquitectura"`)** — headline `Arquitectura`. Five `.node`s laid out: `Navegador · React 19 + Vite`, `API · FastAPI + WebSocket`, `Orchestrator · OpenRouter` (center, `--orch`), `Fase 1 · modelos Python`, `Infraestructura · Postgres·MinIO·Qdrant·Neo4j`. SVG `.edge`s connecting browser↔API↔orchestrator↔{fase1, infra}. Tag each node/edge with `data-anim`.

- [ ] **Step 3: Register timeline** — fade/scale nodes in center-out, then draw edges via `strokeDashoffset` tween. No fragments; plays on slide entry.

- [ ] **Step 4: Serve and screenshot**; confirm nodes appear center-out and edges draw. Legible labels.

- [ ] **Step 5: Commit**

```bash
git add <root> && git commit -m "feat[defensa]: slide 8 (arquitectura, diagrama GSAP)"
```

---

### Task 8: Slides 9–10 — Dominio 2D + Orchestrator

**Files:**
- Modify: `<root>/index.html`, `<root>/js/animations.js`

**Interfaces:** Consumes `.node`, `.edge`, `SlideAnim`.

- [ ] **Step 1: Slide 9 (`data-slide="dominio"`)** — headline `El dominio: una rejilla 2D`. Left: a small CSS-grid `8×8` with a couple of agent dots (agent colors) and green resource dots. Right: two `.panel`s — `Agent` → `quién y dónde` and `DecisionModel` → `cómo decide`, noting the deliberate separation and immutable events. Register a timeline that pops an agent dot from one cell to an adjacent one (single hop, `x/y` tween) to suggest movement.

- [ ] **Step 2: Slide 10 (`data-slide="orchestrator"`)** — headline `Orchestrator: coordinador único`, agent color slate. Bullets (fragments): `Secuencia canónica de tool calls; el LLM solo elige desviaciones.` · `Pre-recupera contexto del Knowledge Backbone.` · `Difiere la persistencia; transmite en vivo por WebSocket.`

- [ ] **Step 3: Serve and screenshot** slides 9–10; confirm the grid renders and the dot hops.

- [ ] **Step 4: Commit**

```bash
git add <root> && git commit -m "feat[defensa]: slides 9-10 (dominio 2D, orchestrator)"
```

---

### Task 9: Slide 11 — Los 4 agentes (star diagram, worked example)

**Files:**
- Modify: `<root>/index.html`, `<root>/js/animations.js`

**Interfaces:** Consumes agent colors, `.node`, `SlideAnim`.

- [ ] **Step 1: Slide 11 (`data-slide="agentes"`)** — headline `Cuatro agentes, cuatro cambios de representación`. Four `.node`s with `data-anim="agent"` in a row, each an agent color and a one-line transform:
  - Architect (green): `NL + contexto → especificación JSON`
  - Tracker (amber): `ejecución → observaciones (eventos, trayectorias, episodios)`
  - Analyst (purple): `observaciones → patrones, métricas, gráficas`
  - Reporter (pink): `análisis → LaTeX → PDF (tectonic)`
  Connect them with `.edge` arrows left→right.

- [ ] **Step 2: Register the worked timeline**:
```js
SlideAnim.register('agentes', el => {
  const tl = gsap.timeline({ paused: true });
  const nodes = el.querySelectorAll('[data-anim="agent"]');
  const edges = el.querySelectorAll('[data-anim="edge"]');
  nodes.forEach((n, i) => {
    tl.fromTo(n, { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out' }, i * 0.35);
    tl.to(n, { boxShadow: `0 0 24px ${getComputedStyle(n).getPropertyValue('--agent')}66`, duration: 0.3 }, i * 0.35 + 0.2);
    if (edges[i]) tl.fromTo(edges[i], { strokeDashoffset: 200 }, { strokeDashoffset: 0, duration: 0.3 }, i * 0.35 + 0.3);
  });
  return tl;
});
```
No fragments; plays on entry (or split into fragments if you want click-through — set 4 `.fragment` markers and the harness will step it).

- [ ] **Step 3: Serve and screenshot**; confirm each agent lights in its color in sequence.

- [ ] **Step 4: Commit**

```bash
git add <root> && git commit -m "feat[defensa]: slide 11 (4 agentes, diagrama estrella GSAP)"
```

---

### Task 10: Slide 12 — Knowledge Backbone (GSAP assemble)

**Files:**
- Modify: `<root>/index.html`, `<root>/js/animations.js`

**Interfaces:** Consumes `.node`, `.edge`, `SlideAnim`.

- [ ] **Step 1: Slide 12 (`data-slide="knowledge"`)** — headline `Knowledge Backbone: memoria compartida`. Four store `.node`s assembling around a center label `Orchestrator`:
  - `PostgreSQL` → `metadatos, historial, simulation_observations`
  - `MinIO` → `PDF y artefactos binarios`
  - `Qdrant` → `memorias densas + sparse BM25`
  - `Neo4j` → `grafo de paradigmas y procedencia`
  Footnote chip: `Voyage AI (embeddings) · ZeroEntropy (reranking) — opcionales, con degradación controlada`.

- [ ] **Step 2: Register timeline** — the four store nodes fly in from the corners (`x/y` from offset to 0, staggered) then edges draw to center.

- [ ] **Step 3: Serve and screenshot**; confirm assemble animation and all four stores labelled correctly.

- [ ] **Step 4: Commit**

```bash
git add <root> && git commit -m "feat[defensa]: slide 12 (knowledge backbone, diagrama GSAP)"
```

---

### Task 11: Slide 13 — UI en detalle (screenshots)

**Files:**
- Modify: `<root>/index.html`
- Copy: three screenshots into `<root>/assets/img/`

**Interfaces:** Consumes `.panel`, `.grid-3`.

- [ ] **Step 1: Copy screenshots**

```bash
cp phase2-juan/docs/tfg-memoria-latex/figuras/ui-06-analyst-patrones.png \
   phase2-juan/docs/tfg-memoria-latex/figuras/ui-07-decision-traces.png \
   phase2-juan/docs/tfg-memoria-latex/figuras/ui-09-reporter-pdf.png <root>/assets/img/
```

- [ ] **Step 2: Slide 13 (`data-slide="ui"`)** — headline `La interfaz, en detalle`. `.grid-3` of three framed screenshots with mono captions: `Patrones del Analyst` · `Decision traces (Q-values)` · `Informe PDF del Reporter`. Each image in a `.panel` with `border-radius` and a subtle border. Fragments reveal them one by one.

- [ ] **Step 3: Serve and screenshot**; confirm images load, are sharp, captions legible.

- [ ] **Step 4: Commit**

```bash
git add <root> && git commit -m "feat[defensa]: slide 13 (UI en detalle, screenshots)"
```

---

### Task 12: Slides 14–15 — Bucle de desarrollo + Coordinación

**Files:**
- Modify: `<root>/index.html`, `<root>/js/animations.js`

**Interfaces:** Consumes `.node`, `.edge`, `.panel`, `SlideAnim`.

- [ ] **Step 1: Slide 14 (`data-slide="bucle"`)** — headline `Un nuevo bucle de desarrollo`. Four `.node`s in a cycle: `Especificar` → `Ejecutar` → `Revisar` → `Aceptar / Ajustar`, arrows forming a loop (Ajustar → back to Especificar). Subtitle: `Implementar deja de ser lo caro; especificar y verificar pasan al centro.` Register a timeline drawing the loop edges in order.

- [ ] **Step 2: Slide 15 (`data-slide="coordinacion"`)** — headline `Cómo nos coordinamos`. Two `.panel`s: left `Frontera mínima` → `3 métodos compartidos; sin coordinar releases durante meses`; right `Linear como memoria operativa` → `criterios de aceptación, dependencias, prioridades, paralelismo`. Bottom line: `Reparto: el humano decide alcance, contratos y aceptación; el agente implementa módulos acotados, pruebas y refactores.`

- [ ] **Step 3: Serve and screenshot** slides 14–15; confirm the loop edges draw and panels read clearly.

- [ ] **Step 4: Commit**

```bash
git add <root> && git commit -m "feat[defensa]: slides 14-15 (bucle de desarrollo, coordinacion)"
```

---

### Task 13: Slides 16–17 — Cronograma + Verificación

**Files:**
- Modify: `<root>/index.html`, `<root>/js/animations.js`

**Interfaces:** Consumes `.panel`, `SlideAnim`.

- [ ] **Step 1: Slide 16 (`data-slide="cronograma"`)** — headline `Marzo–junio 2026`. Build a lightweight HTML Gantt: rows = `Diseño + contrato`, `Núcleo + CLI`, `Frontend + WebSocket + replay`, `Comparativa multi-modelo`, `Tracker / Analyst / Reporter`, `Persistencia (Postgres/MinIO)`, `Knowledge Backbone + NL-SQL`, `Despliegue + evaluación`; columns = Mar/Abr/May/Jun. Each bar is a token-colored div positioned by month. Register a timeline that grows the bars (`scaleX 0→1`, `transform-origin:left`) staggered.

- [ ] **Step 2: Slide 17 (`data-slide="verificacion"`)** — headline `La verificación, el nuevo cuello de botella`. Three `.panel`s: `Pruebas como contrato` → `pytest · Playwright · compilación LaTeX`; `Revisión combinada` → `lectura humana + subagentes de alta confianza`; `Ejecución instrumentada` → `métricas duras contra la simulación`.

- [ ] **Step 3: Serve and screenshot** slides 16–17; confirm Gantt bars grow and are positioned in the right months.

- [ ] **Step 4: Commit**

```bash
git add <root> && git commit -m "feat[defensa]: slides 16-17 (cronograma, verificacion)"
```

---

### Task 14: Slides 18–19 — Evaluación + Resultados

**Files:**
- Modify: `<root>/index.html`, `<root>/js/animations.js`

**Interfaces:** Consumes `.panel`, `.stat`, counter pattern from Task 6.

- [ ] **Step 1: Slide 18 (`data-slide="evaluacion"`)** — headline `Cómo se evalúa`. Two principle chips: `Verdad de referencia = datos de simulación, no teoría` · `Evaluado (Claude) ≠ evaluador (Codex)`. Two `.panel`s: `CASO 1 · valor / forrajeo` → `6 paradigmas · rejilla 8×8 · 360 eventos · 15 consumos`; `CASO 2 · homeostasis` → `4 paradigmas · rejilla 10×10 · 199 eventos · 7 consumos`.

- [ ] **Step 2: Slide 19 (`data-slide="resultados"`)** — headline `Resultados`. Three check rows: `Tripleta joinable ✓ (Postgres = Qdrant denso = Qdrant sparse)` · `Determinismo con semilla 42 ✓` · `PDF compilado con tectonic ✓`. Two big `.stat` verdict cards using the counter tween: `88/100 · CASO 1` and `86/100 · CASO 2`, each with the one-line Codex remark (short). Register counters (`data-to="88"`, `data-to="86"`).

- [ ] **Step 3: Serve and screenshot** slides 18–19; confirm the 88 and 86 count up and the checks read as passed.

- [ ] **Step 4: Commit**

```bash
git add <root> && git commit -m "feat[defensa]: slides 18-19 (evaluacion, resultados Codex)"
```

---

### Task 15: Slide 20 — Conclusiones + cierre

**Files:**
- Modify: `<root>/index.html`

**Interfaces:** Consumes `.panel`, fragments.

- [ ] **Step 1: Slide 20 (`data-slide="cierre"`)** — headline `Conclusiones`. Three lesson fragments: `La forma de conectar importa más que cada pieza.` · `Centralizar el acceso al conocimiento compensa.` · `Separar observación de persistencia.` Then a muted line of limits/extensions: `Límites: no valida teorías solo · depende del LLM · dominio 2D. Ampliaciones: más paradigmas, métricas estandarizadas, reanudación de sesiones.` Final large line: `«De cómo lo escribo a qué quiero exactamente que ocurra.»` Then `Gracias.` + name/USC.

- [ ] **Step 2: Serve and screenshot**; confirm fragments reveal in order and the closing line lands.

- [ ] **Step 3: Commit**

```bash
git add <root> && git commit -m "feat[defensa]: slide 20 (conclusiones y cierre)"
```

---

### Task 16: Polish — PDF export, offline, projector fallbacks, README, full run-through

**Files:**
- Modify: `<root>/css/theme.css`, `<root>/js/deck.js`, `<root>/README.md`

**Interfaces:** none new.

- [ ] **Step 1: PDF export** — verify `http://localhost:8080/?print-pdf` lays out one slide per page. Add reveal's print CSS if needed. Screenshot two exported pages.

- [ ] **Step 2: Projector fallbacks** — add `@supports not (backdrop-filter: blur(1px)) { .panel { background: var(--color-surface); } }`. Ensure min font sizes ≥ 20px for body on slides. Confirm the deck renders with `demo.mp4` absent (poster only).

- [ ] **Step 3: Full run-through screenshot** — navigate all 20 slides via Playwright, capture each, and eyeball for overflow, contrast, and timing markers. Fix any clipping.

- [ ] **Step 4: Write `README.md`** — how to serve (`python3 -m http.server 8080`), navigate (arrows/space, `s` for notes), export PDF (`?print-pdf`), and where to drop `assets/video/demo.mp4`. Note any CDN/version pins and the Satoshi fallback.

- [ ] **Step 5: Commit**

```bash
git add <root> && git commit -m "feat[defensa]: polish, PDF export, projector fallbacks, README"
```

---

## Self-Review

**Spec coverage:** All 20 slides in spec §4 map to Tasks 4–15. Tokens/theme reuse → Tasks 1–2. GSAP harness → Task 3. Diagrams (5 hero) → Tasks 7 (arquitectura), 9 (agentes), 10 (knowledge), 12 (bucle), plus 8 (dominio hop) and 16-Gantt. Screenshots → Tasks 4, 11. Video handling (user-supplied + placeholder) → Task 4, verified Task 16. PDF export + offline + fallbacks → Task 16. Verified data (§5) placed in slides 7, 18, 19. No spec section left unimplemented.

**Placeholder scan:** No "TBD/TODO". Where full HTML for every slide is not inlined, the exact headline, bullet copy, and data values are specified verbatim, and Tasks 1–3 establish the concrete HTML/CSS/JS patterns to follow — so each slide task has unambiguous content.

**Type consistency:** `SlideAnim.register/build/reset/get` used consistently across Tasks 3, 6, 7, 9, 10, 12, 13, 14. `data-slide` ids are unique and referenced consistently. Counter pattern (`data-to` + proxy tween) defined in Task 6 and reused verbatim in Task 14. `.panel`, `.node`, `.edge`, `.stat`, agent-color classes defined in Tasks 2/7 and consumed by later tasks.
