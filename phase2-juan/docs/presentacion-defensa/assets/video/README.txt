demo.webm — grabación del FRONTEND REAL en modo mock (sin backend), no una
recreación. Se usa en la slide 1 (fondo en loop silenciado) y en la slide 3 (demo).
Reproduce en Chrome/Firefox/Edge y Safari reciente.

Para sustituirla por una grabación de una sesión real (con backend):
  - Coloca tu vídeo como demo.mp4 en esta carpeta.
  - El deck lo prioriza sobre el webm (mp4 va primero en las <source>).

Para regenerar el webm desde el modo mock del frontend:
  1. cd phase2-juan/frontend && npm install && npm run dev   (Vite en :5173)
  2. Abrir  http://localhost:5173/?mock
  3. Grabar 1280x720 recorriendo el flujo con las sugerencias del chat:
     chip inicial -> "Lanza la simulación" (dar a Play en el replay) ->
     "Registra las trayectorias" -> "Analiza los resultados" -> "Genera el informe".
