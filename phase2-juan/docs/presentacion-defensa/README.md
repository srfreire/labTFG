# Presentación de defensa — TFG Fase 2

Deck en **reveal.js** con el design system del frontend (tokens propios) y
animaciones **GSAP** en registro contenido. 20 diapositivas, castellano, ~20 min.

## Servir

```bash
cd phase2-juan/docs/presentacion-defensa
python3 -m http.server 8080
# abrir http://localhost:8080
```

Es estático y autocontenido (librerías y fuentes vendorizadas en `vendor/` y
`assets/fonts/`), funciona sin conexión.

## Navegar

- **→ / espacio**: avanzar (revela fragmentos y dispara las animaciones)
- **← / ↑**: retroceder
- **Esc / O**: vista general de diapositivas
- **S**: notas del ponente
- **F**: pantalla completa

## El vídeo de la demo

Ya incluido: `assets/video/demo.webm` — grabación del **mock animado del dashboard**
(`mock/hero-mock.html`), usado en la **slide 1** (fondo en loop silenciado) y en la
**slide 3** (demo). Para sustituirlo por una grabación real de tu demo, coloca un
`assets/video/demo.mp4`: el deck lo prioriza sobre el webm.

Regenerar el webm desde el mock: servir el deck y grabar `mock/hero-mock.html`
(1280×720, ~15,6 s = una vuelta del loop). Ver `assets/video/README.txt`.

## Exportar a PDF (plan B para el proyector)

Abrir `http://localhost:8080/?print-pdf` e imprimir a PDF desde el navegador
(Chrome recomendado; fondos activados, márgenes ninguno). Una página por slide.

## Estructura

```
index.html            las 20 slides
css/tokens.css        copia de frontend/docs/design/tokens.css (fuente de verdad)
css/theme.css         tema reveal sobre los tokens
css/components.css     paneles, colores por agente, stats, layout de slides
css/diagrams.css       nodos, aristas SVG, gantt, mini-grid
js/deck.js            init de reveal + wiring GSAP + autoplay de vídeo
js/animations.js       registro de timelines (SlideAnim) + helper drawEdge
js/slides-anim.js      timelines GSAP por slide
assets/img/            screenshots reales de la UI (de la memoria)
assets/fonts/          Satoshi + IBM Plex Mono (self-hosted)
vendor/               reveal.js, gsap, highlight.js
```

## Notas

- Fuentes: Satoshi (Fontshare, pesos 400/500/700 — el semibold mapea a 700) e
  IBM Plex Mono. Si faltaran, degrada a `system-ui`.
- Colores por agente (tokens): Architect verde, Tracker ámbar, Analyst púrpura,
  Reporter rosa, Orchestrator slate.
- Versiones vendorizadas: reveal.js 5.1.0, gsap 3.12.5, highlight.js 11.9.0.
