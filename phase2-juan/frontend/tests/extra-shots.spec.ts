import { test, type Page } from '@playwright/test'
import path from 'node:path'

const FIG =
  '/Users/juanfreire/Documents/academic/labtfg/phase2-juan/docs/tfg-memoria-latex/figuras'
const BASE = 'http://localhost:5173'

test.use({ viewport: { width: 1680, height: 1050 }, deviceScaleFactor: 2 })

async function hideBadge(page: Page) {
  await page.addStyleTag({
    content: '[data-testid="mock-badge"]{display:none !important}',
  })
}

// ui-10 — pipeline en acción: un agente en estado "working" con su tool label
// y el chat "pensando", capturado a mitad de la fase del Analyst.
test('pipeline en acción (mock)', async ({ page }) => {
  await page.goto(`${BASE}/?mock`)
  await page.getByRole('heading', { name: 'DecisionLab' }).waitFor()
  await hideBadge(page)

  await page.getByText('Ejecuta una run corta con drive_reduction_rl').click()
  for (const label of [
    'Lanza la simulación',
    'Registra las trayectorias con el Tracker',
  ]) {
    const btn = page.getByRole('button', { name: label })
    await btn.waitFor({ state: 'visible', timeout: 20_000 })
    await btn.click()
  }
  // Dispara la fase del Analyst y captura a mitad de su ejecución (~3.8 s de
  // tool calls): el panel muestra al Analyst "working" + tool, el chat piensa.
  const analyze = page.getByRole('button', { name: 'Analiza los resultados' })
  await analyze.waitFor({ state: 'visible', timeout: 20_000 })
  await analyze.click()
  await page.waitForTimeout(1700)
  await hideBadge(page)
  await page.screenshot({ path: path.join(FIG, 'ui-10-pipeline-accion.png') })
})

// ui-11 — panel de Knowledge Graph (datos reales del backend).
test('knowledge graph (real)', async ({ page }) => {
  await page.goto(`${BASE}/`)
  await page.getByRole('heading', { name: 'DecisionLab' }).waitFor()
  await page.getByRole('button', { name: 'Knowledge graph' }).click()
  await page.getByText('Knowledge', { exact: true }).waitFor({ timeout: 10_000 })
  await page.waitForTimeout(2500) // deja cargar grafo / fetch
  // Reajusta el grafo al contenedor ya estabilizado (fitView inicial corre
  // antes de que el panel alcance su altura final y deja los nodos diminutos).
  const fit = page.locator('.react-flow__controls-fitview')
  if (await fit.count()) {
    await fit.click()
    await page.waitForTimeout(1200)
  }
  // Capturar la REGIÓN VISIBLE del panel (clip sobre su bounding box), no el
  // elemento completo: el grafo hace fitView al área visible, así que un
  // element.screenshot del scrollHeight lo dejaba diminuto y descolgado.
  const panel = page.getByRole('complementary').last()
  const box = await panel.boundingBox()
  if (!box) throw new Error('KG panel sin bounding box')
  await page.screenshot({
    path: path.join(FIG, 'ui-11-knowledge-graph.png'),
    clip: box,
  })
})
