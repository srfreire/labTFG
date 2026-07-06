demo.webm — grabación del mock animado del dashboard (DecisionLab), generada a
partir de mock/hero-mock.html. Se usa en la slide 1 (fondo en loop silenciado) y
en la slide 3 (demo). Reproduce en Chrome/Firefox/Edge y Safari reciente.

Para sustituirla por una grabación real de tu demo:
  - Coloca tu vídeo como demo.mp4 en esta carpeta.
  - El deck lo prioriza sobre el webm (mp4 va primero en las <source>).

Para regenerar el webm desde el mock:
  1. Servir el deck (python3 -m http.server 8080 desde presentacion-defensa/).
  2. Grabar mock/hero-mock.html (1280x720, ~15.6 s = una vuelta del loop).
