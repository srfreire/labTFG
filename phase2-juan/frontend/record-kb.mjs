import { chromium } from '@playwright/test'

// Records a REAL chat request against the Railway backend. The local (latest,
// light-mode) frontend connects to ws://localhost/ws; we intercept that socket
// with Playwright's routeWebSocket and relay it to the real Railway WS using
// node's native WebSocket (reliable — vite's own wss proxy EPIPEs). So this needs
// NO vite proxy / VITE_API_ORIGIN: just `npm run dev` and run this script.
const BASE = process.env.BASE_URL || 'http://localhost:5173'
const RAILWAY_WS = 'wss://phase2-server-production.up.railway.app/ws'
const OUT = '/private/tmp/claude-501/-Users-juanfreire-Documents-academic-labtfg/96da4f0f-8036-40f0-a2a9-3dbee236e331/scratchpad/reckb'
const Q = '¿qué modelos exploran con poca energía?'
const W = 1440, H = 900
const pause = (ms) => new Promise(r => setTimeout(r, ms))

const browser = await chromium.launch({ headless: true })
const ctx = await browser.newContext({
  viewport: { width: W, height: H },
  deviceScaleFactor: 2,
  recordVideo: { dir: OUT, size: { width: W, height: H } },
})

// relay the app's /ws to the real Railway backend
await ctx.routeWebSocket(/\/ws(\?|$)/, route => {
  const server = new WebSocket(RAILWAY_WS)
  const queue = []
  let open = false
  server.onopen = () => { open = true; queue.forEach(m => server.send(m)); queue.length = 0 }
  server.onmessage = e => { try { route.send(e.data) } catch {} }
  server.onclose = () => { try { route.close() } catch {} }
  server.onerror = () => {}
  route.onMessage(m => { if (open) server.send(m); else queue.push(m) })
  route.onClose(() => { try { server.close() } catch {} })
})

const page = await ctx.newPage()
await page.goto(`${BASE}/?light`)
await page.getByRole('heading', { name: 'DecisionLab' }).waitFor()

// input is disabled until the WS connects; wait for the idle placeholder
const input = page.getByPlaceholder('Describe un paradigma de decisión...')
await input.waitFor({ timeout: 30_000 })
await pause(700)

await input.click()
await input.type(Q, { delay: 45 })
await pause(500)
await input.press('Enter')

// wait until the request finishes: input goes busy ("Esperando…") then idle again
await page.getByPlaceholder(/Esperando/).waitFor({ timeout: 20_000 }).catch(() => {})
await page.getByPlaceholder('Describe un paradigma de decisión...').waitFor({ timeout: 100_000 })
await pause(2500)

// dump the exact answer text (for the speaker notes)
const answerText = await page.evaluate(() => {
  const cont = document.querySelector('div.overflow-y-auto')
  const last = cont && cont.lastElementChild
  return last ? last.innerText : ''
})
console.log('ANSWER_START>>>' + answerText + '<<<ANSWER_END')

// scroll through the whole answer so it can be read (small inset + zoom)
const cont = page.locator('div.overflow-y-auto').first()
await cont.evaluate(el => { const l = el.lastElementChild; if (l) l.scrollIntoView({ block: 'start' }) })
await pause(1600)
const steps = 7
for (let i = 1; i <= steps; i++) {
  await cont.evaluate((el, f) => el.scrollTo({ top: el.scrollHeight * f, behavior: 'smooth' }), i / steps)
  await pause(1500)
}
await pause(1200)

await ctx.close()
await browser.close()
console.log('VIDEO_PATH=' + await page.video().path())
