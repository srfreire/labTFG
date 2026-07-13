demo.mp4 / demo.webm — grabación del FRONTEND REAL en modo mock (sin backend),
no una recreación. 1920x1080 (1080p). Se usa en la slide 3 (demo). El deck
prioriza demo.mp4 sobre demo.webm en las <source>.

Las versiones 720p antiguas (blurry en proyector) quedan en _backup-720p/.

Para regenerar en 1080p (automático, con Playwright):
  1. cd phase2-juan/frontend && npm install && npm run dev   (Vite en :5173)
  2. node record-demo.mjs
     - conduce el flujo mock a 1920x1080 (deviceScaleFactor 2, replay a 0.5x)
     - imprime VIDEO_PATH=... (un .webm VP8 de Playwright)
  3. Convertir a los formatos finales con ffmpeg:
     ffmpeg -y -i <VIDEO_PATH> -c:v libx264 -crf 20 -preset slow \
       -pix_fmt yuv420p -movflags +faststart -an demo.mp4
     ffmpeg -y -i <VIDEO_PATH> -c:v libvpx-vp9 -crf 30 -b:v 0 -row-mt 1 \
       -pix_fmt yuv420p -an demo.webm

El flujo grabado: chip inicial -> "Compara los tres modelos" -> "Lanza la
simulación" -> "Registra las trayectorias" -> "Analiza los resultados" ->
"Informe completo, calidad estándar" -> Play en el replay (0.5x) -> charts +
descarga del informe.
