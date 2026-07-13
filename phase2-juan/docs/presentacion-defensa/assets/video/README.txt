demo.mp4 / demo.webm — grabación del FRONTEND REAL en modo mock (sin backend),
no una recreación. 1920x1080 (1080p). Se usa en la slide 3 (demo). El deck
prioriza demo.mp4 sobre demo.webm en las <source>.

Las versiones 720p antiguas (blurry en proyector) quedan en _backup-720p/.

Para regenerar en 1080p (automático, con Playwright):
  1. cd phase2-juan/frontend && npm install && npm run dev   (Vite en :5173)
  2. node record-demo.mjs
     - conduce el flujo mock a 1920x1080 (deviceScaleFactor 2, replay a 1x,
       pacing uniforme sin ralentizar en eventos críticos)
     - espera a que el replay llegue al paso final (data-testid="replay-step")
       y abre el visor del PDF: scroll continuo del Analyst, recorrido de las
       páginas y zoom a pantalla completa de una página; ~60s en total
     - imprime VIDEO_PATH=... (un .webm VP8 de Playwright)
  3. Convertir a los formatos finales con ffmpeg:
     ffmpeg -y -i <VIDEO_PATH> -c:v libx264 -crf 20 -preset slow \
       -pix_fmt yuv420p -movflags +faststart -an demo.mp4
     ffmpeg -y -i <VIDEO_PATH> -c:v libvpx-vp9 -crf 30 -b:v 0 -row-mt 1 \
       -pix_fmt yuv420p -an demo.webm

El flujo grabado: chip inicial -> "Compara los tres modelos" -> "Lanza la
simulación" -> "Registra las trayectorias" -> "Analiza los resultados" ->
"Informe completo, calidad estándar" -> Play en el replay (1x) -> charts +
visor del PDF (páginas del informe, con zoom a pantalla completa).

────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────
kb.mp4 / kb.webm — inset (horizontal) de la slide "retrieval": una CONSULTA REAL
al chat con la respuesta scrolleada. El usuario pregunta «¿qué modelos exploran
con poca energía?»; el Orchestrator llama a retrieve_context (KG) y responde
citando paradigmas/modelos; el vídeo hace scroll por toda la respuesta.
1088x672, ~25s. Clic sobre el vídeo en el deck para ampliarlo (lightbox).

Grabación (frontend local claro + backend REAL de Railway, sin proxy de vite):
  record-kb.mjs intercepta el /ws del frontend con Playwright routeWebSocket y lo
  RELAYEA al wss de Railway con el WebSocket nativo de node (el proxy wss de vite
  daba EPIPE). No necesita VITE_API_ORIGIN.
  1. cd phase2-juan/frontend && npm run dev
  2. node record-kb.mjs   (teclea la pregunta, espera la respuesta, hace scroll;
     vuelca la respuesta real para las notas)
  3. recortar espera + encuadrar (crop=1360:840:40:40,scale=1088:-2), concatenar
     [intro+retrieve_context] + [respuesta con scroll]; póster de la respuesta.
