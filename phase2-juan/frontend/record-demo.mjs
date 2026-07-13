import { chromium } from '@playwright/test'

const BASE = process.env.BASE_URL || 'http://localhost:5173'
const OUT = process.env.OUT_DIR || '/private/tmp/claude-501/-Users-juanfreire-Documents-academic-labtfg/0bbbed98-4d3d-4af2-ab4e-fdde667db56d/scratchpad/rec'
const W = 1920, H = 1080
const pause = (ms) => new Promise(r => setTimeout(r, ms))

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({
  viewport: { width: W, height: H },
  deviceScaleFactor: 2,
  recordVideo: { dir: OUT, size: { width: W, height: H } },
})
const page = await context.newPage()

async function clickBtn(name, waitFor) {
  const btn = page.getByRole('button', { name })
  await btn.waitFor({ state: 'visible', timeout: 20_000 })
  await btn.click()
  if (waitFor) await waitFor()
}

// scroll suave centrando el elemento — se lee mejor en vídeo que el salto instantáneo
async function smoothTo(locator) {
  await locator.evaluate(el => el.scrollIntoView({ behavior: 'smooth', block: 'center' }))
}

// coloca el elemento arriba del contenedor del chat, sin animación (punto de partida)
async function scrollElemToTop(selector) {
  await page.evaluate(sel => {
    const c = document.querySelector('[data-testid="chat-scroll"]')
    const el = document.querySelector(sel)
    if (!c || !el) return
    const cRect = c.getBoundingClientRect(), tRect = el.getBoundingClientRect()
    c.scrollTop = Math.max(0, c.scrollTop + (tRect.top - cRect.top) - 12)
  }, selector)
}

// scroll CONTINUO y suave del chat hasta dejar el target a la vista, con easing propio
// (un único movimiento fluido, en vez de saltar centrando elemento por elemento)
async function slowScrollTo(selector, duration) {
  await page.evaluate(({ selector, duration }) => new Promise(resolve => {
    const c = document.querySelector('[data-testid="chat-scroll"]')
    const el = document.querySelector(selector)
    if (!c || !el) return resolve()
    const startTop = c.scrollTop
    const cRect = c.getBoundingClientRect(), tRect = el.getBoundingClientRect()
    const endTop = Math.max(0, Math.min(c.scrollHeight - c.clientHeight, startTop + (tRect.bottom - cRect.bottom) + 24))
    const t0 = performance.now()
    const ease = t => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2)
    const step = now => {
      const p = Math.min(1, (now - t0) / duration)
      c.scrollTop = startTop + (endTop - startTop) * ease(p)
      if (p < 1) requestAnimationFrame(step); else resolve()
    }
    requestAnimationFrame(step)
  }), { selector, duration })
}

await page.goto(`${BASE}/?mock&light`)
await page.getByRole('heading', { name: 'DecisionLab' }).waitFor()
await pause(1600)

// 1) usuario describe el problema con sus palabras
await page.getByText('Quiero estudiar la regulación homeostática del hambre').click()
await page.getByText('Environment Spec').waitFor({ timeout: 20_000 })
await page.getByText('Modelos de Fase 1 disponibles').waitFor({ timeout: 20_000 })
await pause(2200)

// 2) elegir los tres modelos → llega a "Lanza la simulación"
await clickBtn('Compara los tres modelos', () =>
  page.getByRole('button', { name: 'Lanza la simulación' }).waitFor({ timeout: 20_000 }))
await pause(1600)

// 3) lanzar la simulación → aparece el replay
await clickBtn('Lanza la simulación')
await pause(1400)

// 4) reproducir el replay animado a 1x (default) — la parte estrella
const replay = page.getByTestId('sim-replay').first()
await smoothTo(replay)
await pause(1200)
const controls = replay.locator('button') // 0 reset · 1 back · 2 play · 3 fwd · 4 speed
await controls.nth(2).click() // play (velocidad por defecto 1x)
// esperar a que el replay LLEGUE al último paso en vez de un pause fijo:
// evita cortarlo a medias (parecía "rápido") y elimina los segundos vacíos de después.
// Se lee el contador scoped (data-testid="replay-step"), NO el textContent del panel
// entero: ese incluía el dígito de la velocidad ("Step 60 / 601×") y el regex lo mezclaba.
await page.waitForFunction(() => {
  const el = document.querySelector('[data-testid="replay-step"]')
  const m = el && (el.textContent || '').match(/Step\s+(\d+)\s*\/\s*(\d+)/)
  return !!m && m[1] === m[2]
}, null, { timeout: 20_000 }).catch(() => {})
await pause(900) // beat corto al terminar, sin aire muerto

// 5) registrar las trayectorias
await clickBtn('Registra las trayectorias')
await pause(1800)

// 6) analizar → salida del Analyst con UN scroll continuo y suave (tarjeta → charts → trazas)
await clickBtn('Analiza los resultados', () =>
  page.getByTestId('analysis-charts').first().waitFor({ timeout: 20_000 }))
await page.getByTestId('decision-traces').first().waitFor({ timeout: 20_000 })
await pause(1200)
await scrollElemToTop('[data-testid="analyst-card"]') // arrancar por la cabecera del análisis
await pause(1600)
await slowScrollTo('[data-testid="decision-traces"]', 8500) // recorrido fluido hasta las trazas
await pause(1600)

// 7) informe → abrir de verdad el visor del PDF y recorrer sus páginas
await clickBtn('Informe completo, calidad estándar', () =>
  page.getByRole('button', { name: 'Muéstrame la evolución del drive del modelo drive-dynamics' })
    .waitFor({ timeout: 20_000 }))

const preview = page.getByTestId('pdf-preview').first()
await preview.waitFor({ state: 'visible', timeout: 20_000 })
// esperar a que las páginas del PDF terminen de cargar (si no, se ve el visor en blanco)
await page.waitForFunction(() => {
  const imgs = document.querySelectorAll('[data-testid="pdf-preview"] img')
  return imgs.length > 0 && Array.from(imgs).every(i => i.complete && i.naturalWidth > 0)
}, null, { timeout: 20_000 }).catch(() => {})
await smoothTo(preview)
await pause(1600)

// recorrer las páginas dentro del visor para que se vea "abierto"
const scroller = page.getByTestId('pdf-preview-scroll').first()
const maxScroll = await scroller.evaluate(el => el.scrollHeight - el.clientHeight)
for (let i = 1; i <= 3; i++) {
  await scroller.evaluate((el, top) => el.scrollTo({ top, behavior: 'smooth' }), (maxScroll * i) / 3)
  await pause(1300)
}

// ampliar el PDF: click en una página con contenido → visor grande
const pages = preview.locator('button')
await pages.nth(2).click()
await page.getByTestId('pdf-zoom').waitFor({ state: 'visible', timeout: 10_000 })
await pause(3000)
await page.keyboard.press('Escape') // cerrar el zoom
await pause(1200)

await context.close()
await browser.close()

const path = await page.video().path()
console.log('VIDEO_PATH=' + path)
