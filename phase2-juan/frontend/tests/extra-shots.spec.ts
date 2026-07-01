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
  const analyze = page.getByRole('button', { name: 'Analiza los resultados' })
  await analyze.waitFor({ state: 'visible', timeout: 20_000 })
  await analyze.click()
  await page.waitForTimeout(1700)
  await hideBadge(page)
  await page.screenshot({ path: path.join(FIG, 'ui-10-pipeline-accion.png') })
})
test('knowledge graph (real)', async ({ page }) => {
  await page.goto(`${BASE}/`)
  await page.getByRole('heading', { name: 'DecisionLab' }).waitFor()
  await page.getByRole('button', { name: 'Knowledge graph' }).click()
  await page.getByText('Knowledge', { exact: true }).waitFor({ timeout: 10_000 })
  await page.waitForTimeout(2500) // deja cargar grafo / fetch
  const fit = page.locator('.react-flow__controls-fitview')
  if (await fit.count()) {
    await fit.click()
    await page.waitForTimeout(1200)
  }
  const panel = page.getByRole('complementary').last()
  const box = await panel.boundingBox()
  if (!box) throw new Error('KG panel sin bounding box')
  await page.screenshot({
    path: path.join(FIG, 'ui-11-knowledge-graph.png'),
    clip: box,
  })
})
