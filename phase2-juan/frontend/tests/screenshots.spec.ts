import { test, type Page } from '@playwright/test'
import path from 'node:path'
const FIG =
  '/Users/juanfreire/Documents/academic/labtfg/phase2-juan/docs/tfg-memoria-latex/figuras'

test.use({
  viewport: { width: 1680, height: 1050 },
  deviceScaleFactor: 2,
})
async function shotElement(page: Page, testid: string, file: string) {
  const el = page.getByTestId(testid).first()
  await el.scrollIntoViewIfNeeded()
  await page.waitForTimeout(500)
  await el.screenshot({ path: path.join(FIG, file) })
}

test('galería de la interfaz para la memoria (modo mock)', async ({ page }) => {
  await page.goto('/?mock')
  await page.getByRole('heading', { name: 'DecisionLab' }).waitFor()
  await page.addStyleTag({
    content: '[data-testid="mock-badge"]{display:none !important}',
  })
  await page.getByText('Ejecuta una run corta con drive_reduction_rl').click()
  for (const label of [
    'Lanza la simulación',
    'Registra las trayectorias con el Tracker',
    'Analiza los resultados',
    'Genera el informe PDF',
  ]) {
    const btn = page.getByRole('button', { name: label })
    await btn.waitFor({ state: 'visible', timeout: 20_000 })
    await btn.click()
  }
  await page
    .getByRole('button', { name: 'Muéstrame la evolución de la Q-table' })
    .waitFor({ timeout: 20_000 })
  await page.waitForTimeout(1400) // deja asentar charts/animaciones
  await shotElement(page, 'env-card', 'ui-02-architect-spec.png')
  await shotElement(page, 'sim-replay', 'ui-03-simulacion-replay.png')
  await shotElement(page, 'analysis-charts', 'ui-04-analisis-charts.png')
  await shotElement(page, 'tracker-card', 'ui-05-tracker-trayectorias.png')
  await shotElement(page, 'analyst-card', 'ui-06-analyst-patrones.png')
  await shotElement(page, 'decision-traces', 'ui-07-decision-traces.png')
  await page
    .getByRole('complementary')
    .first()
    .screenshot({ path: path.join(FIG, 'ui-08-pipeline-panel.png') })
  await page.getByTestId('sim-replay').first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(600)
  await page.screenshot({ path: path.join(FIG, 'ui-01-dashboard-inicial.png') })
})
