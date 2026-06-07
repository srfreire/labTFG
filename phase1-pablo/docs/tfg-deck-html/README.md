# Deck HTML/PDF

Presentación del TFG de Pablo Pazos Parada creada como páginas HTML y renderizada
a PDF.

El estilo toma los tokens visuales del web de Pablo (`phase1-pablo/web`):

- fondo negro;
- superficies frosted oscuras;
- bordes finos blancos;
- tipografía Satoshi/IBM Plex Mono como preferencia;
- acentos verde, ámbar, azul, rojo y cian;
- lenguaje visual de nodos, timeline y grafo.

## Archivos

- `index.html`: slides en HTML.
- `deck.css`: sistema visual y reglas de impresión 16:9.
- `assets/logo_usc.png`: logo convertido desde la plantilla LaTeX.
- `pablo-tfg-deck.pdf`: PDF renderizado.

## Render

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless \
  --disable-gpu \
  --no-pdf-header-footer \
  --print-to-pdf=pablo-tfg-deck.pdf \
  "file://$PWD/index.html"
```
