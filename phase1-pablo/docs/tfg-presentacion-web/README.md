# Presentación web de la defensa (fase 1)

Versión HTML animada de `../tfg-memoria-latex/presentacion.tex`, con el lenguaje visual de la web de DecisionLab (`phase1-pablo/web`) en modo claro: Satoshi + IBM Plex Mono, colores de rol de los agentes, aristas discontinuas animadas y paneles con borde suave.

## Uso

Abrir `index.html` en un navegador (doble clic vale — las fuentes están en `assets/fonts`, no necesita red) o servirlo:

```bash
python3 -m http.server 8000
# http://localhost:8000
```

## Controles

- `→` `↓` `Espacio` — siguiente paso o diapositiva
- `←` `↑` — paso o diapositiva anterior
- `Inicio` / `Fin` — primera y última diapositiva
- `F` — pantalla completa
- Clic (dos tercios derechos / tercio izquierdo) y gesto táctil también navegan
- La URL guarda la posición (`#7`), así que se puede recargar sin perder el sitio

## Estructura

- `index.html` — las 22 diapositivas, con los diagramas rehechos como SVG + HTML animados por pasos
- `deck.css` — sistema de diseño (tokens en modo claro derivados de `web/src/index.css`) y primitivas de diagrama (nodos, cilindros, aristas, grupos)
- `deck.js` — navegación, fragmentos (`data-frag`), estados running/done (`data-run`/`data-done`), ventanas de visibilidad (`data-show-at`/`data-hide-at`) y contadores animados (`.count`)
- Imprimir a PDF: hay estilos de impresión que colocan una diapositiva por página con todo revelado
