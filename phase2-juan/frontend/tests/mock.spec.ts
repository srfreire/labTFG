import { test, expect, type Page } from '@playwright/test'
const STEP_SUGGESTIONS = [
  'Lanza la simulación',
  'Registra las trayectorias con el Tracker',
  'Analiza los resultados',
  'Genera el informe PDF',
]
async function runPipeline(page: Page) {
  for (const label of STEP_SUGGESTIONS) {
    const btn = page.getByRole('button', { name: label })
    await expect(btn).toBeVisible({ timeout: 20_000 })
    await btn.click()
  }
  await expect(
    page.getByRole('button', { name: 'Muéstrame la evolución de la Q-table' }),
  ).toBeVisible({ timeout: 20_000 })
}

test.describe('DecisionLab Mock Mode', () => {

  test('loads mock UI with all agents', async ({ page }) => {
    await page.goto('/?mock')
    await expect(page.getByRole('heading', { name: 'DecisionLab' })).toBeVisible()
    await expect(page.getByText('MOCK')).toBeVisible()
    for (const name of ['Orchestrator', 'Architect', 'Tracker', 'Analyst', 'Reporter']) {
      await expect(page.getByText(name).first()).toBeVisible()
    }
  })

  test('full mock pipeline — turn by turn with suggestions', async ({ page }) => {
    await page.goto('/?mock')
    await expect(page.getByRole('heading', { name: 'DecisionLab' })).toBeVisible()
    await page.getByText('Ejecuta una run corta con drive_reduction_rl').click()
    await expect(page.getByText('Environment Spec')).toBeVisible({ timeout: 20_000 })
    await expect(page.getByRole('main').getByText('food ×6', { exact: true })).toBeVisible()
    await expect(page.getByText('regulación homeostática')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Lanza la simulación' })).toBeVisible()
    await runPipeline(page)
    await expect(page.getByRole('main').getByText('Simulación', { exact: true })).toBeVisible()
    await expect(page.getByText('Eventos críticos').first()).toBeVisible()
    await expect(page.getByText('Step 1 / 30')).toBeVisible()
    await expect(page.getByText('Agentes', { exact: true })).toBeVisible()
    await expect(page.getByText('Trayectorias', { exact: true })).toBeVisible()
    await expect(page.getByText('drive_reduction_rl').first()).toBeVisible()
    await expect(page.getByText('Análisis')).toBeVisible()
    await expect(page.getByText('Evolución de energía por agente')).toBeVisible()
    await expect(page.getByText('Distribución de acciones')).toBeVisible()
    await expect(page.getByText('Evolución Q-values por acción (drive_reduction_rl)')).toBeVisible()
    await expect(page.getByText('experiments/mock/analisis_homeostatic_regulation.pdf')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Descargar PDF analisis_homeostatic_regulation.pdf' })).toBeVisible()
    await expect(page.getByRole('complementary').getByText('pi_negative_feedback', { exact: true })).toBeVisible()
    const completedBadges = page.getByRole('complementary').getByText('Completado')
    expect(await completedBadges.count()).toBeGreaterThanOrEqual(5)
  })

  test('keeps only the latest replay player visible after restart', async ({ page }) => {
    await page.goto('/?mock')
    await page.getByRole('button', {
      name: 'Ejecuta una run corta con drive_reduction_rl',
    }).click()
    await runPipeline(page)
    await page.getByRole('button', { name: 'Empezar un nuevo experimento' }).click()
    await expect(page.getByRole('button', { name: 'Lanza la simulación' })).toBeVisible({ timeout: 20_000 })
    await runPipeline(page)
    await expect(page.getByRole('main').getByText('Simulación', { exact: true })).toHaveCount(1)
    await expect(page.getByText('Step 1 / 30')).toHaveCount(1)
  })

  test('decision traces — cards in chat and popover in replay', async ({ page }) => {
    await page.goto('/?mock')
    await page.getByText('Ejecuta una run corta con drive_reduction_rl').click()
    await runPipeline(page)
    await expect(page.getByText('Decision Trace').first()).toBeVisible()
    await expect(page.getByText('Pre-decisión').first()).toBeVisible()
    await expect(page.getByText('Post-decisión').first()).toBeVisible()
    await expect(page.getByText('eat: 12.3').first()).toBeVisible()
    await expect(page.getByText('Sin Q-values').first()).toBeVisible()
    const confidenceMarker = page.locator('[title*="perdió confianza"]')
    await expect(confidenceMarker).toBeVisible()
    await confidenceMarker.click()
    const closeBtn = page.getByRole('main').locator('button:has-text("×")').first()
    await expect(closeBtn).toBeVisible()
    await expect(page.getByText('Step 17 / 30')).toBeVisible()
    await closeBtn.click()
  })

})
