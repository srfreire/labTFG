import { test, expect, type Page } from '@playwright/test'

const INITIAL_PROMPT = 'Quiero estudiar la regulación homeostática del hambre'
const CHOOSE_MODELS = 'Compara los tres modelos'

const STEP_SUGGESTIONS = [
  'Lanza la simulación',
  'Registra las trayectorias con el Tracker',
  'Analiza los resultados',
  'Informe completo, calidad estándar',
]
const FINAL_SUGGESTION = 'Muéstrame la evolución del drive del modelo drive-dynamics'

// Architect designs the env, then the Orchestrator offers the available Phase 1
// models. Pick all three to compare, landing on the "Lanza la simulación" suggestion.
async function chooseModels(page: Page) {
  const btn = page.getByRole('button', { name: CHOOSE_MODELS })
  await expect(btn).toBeVisible({ timeout: 20_000 })
  await btn.click()
  await expect(
    page.getByRole('button', { name: 'Lanza la simulación' }),
  ).toBeVisible({ timeout: 20_000 })
}

async function runPipeline(page: Page) {
  for (const label of STEP_SUGGESTIONS) {
    const btn = page.getByRole('button', { name: label })
    await expect(btn).toBeVisible({ timeout: 20_000 })
    await btn.click()
  }
  await expect(
    page.getByRole('button', { name: FINAL_SUGGESTION }),
  ).toBeVisible({ timeout: 20_000 })
}

test.describe('DecisionLab Mock Mode', () => {

  test('loads mock UI with all agents', async ({ page }) => {
    await page.goto('/?mock')
    await expect(page.getByRole('heading', { name: 'DecisionLab' })).toBeVisible()
    for (const name of ['Orchestrator', 'Architect', 'Tracker', 'Analyst', 'Reporter']) {
      await expect(page.getByText(name).first()).toBeVisible()
    }
  })

  test('full mock pipeline — turn by turn with suggestions', async ({ page }) => {
    await page.goto('/?mock')
    await expect(page.getByRole('heading', { name: 'DecisionLab' })).toBeVisible()
    await page.getByText(INITIAL_PROMPT).click()
    await expect(page.getByText('Environment Spec')).toBeVisible({ timeout: 20_000 })
    await expect(page.getByRole('main').getByText('food ×8 (regenera)', { exact: true })).toBeVisible()
    await expect(page.getByText('Modelos de Fase 1 disponibles')).toBeVisible({ timeout: 20_000 })
    await chooseModels(page)
    await expect(page.getByText('regulación homeostática').first()).toBeVisible()
    await runPipeline(page)
    await expect(page.getByRole('main').getByText('Simulación', { exact: true })).toBeVisible()
    await expect(page.getByText('Eventos críticos').first()).toBeVisible()
    await expect(page.getByText('Step 1 / 60')).toBeVisible()
    await expect(page.getByText('Agentes', { exact: true })).toBeVisible()
    await expect(page.getByText('Trayectorias', { exact: true })).toBeVisible()
    await expect(page.getByText('continuous_drive_dynamics').first()).toBeVisible()
    await expect(page.getByText('Análisis')).toBeVisible()
    const charts = page.getByTestId('analysis-charts').first()
    await expect(charts.getByText('Evolución de energía (normalizada) por agente')).toBeVisible()
    await expect(charts.getByText('Distribución de acciones')).toBeVisible()
    await expect(charts.getByText('Acumulación de drive y reinicio al consumir (Drive-dynamics ODE)')).toBeVisible()
    await expect(page.getByText('experiments/caso2/informe_final.pdf')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Descargar PDF informe_final.pdf' })).toBeVisible()
    await expect(page.getByRole('complementary').getByText('active_inference_efe', { exact: true })).toBeVisible()
    const completedBadges = page.getByRole('complementary').getByText('Completado')
    expect(await completedBadges.count()).toBeGreaterThanOrEqual(5)
  })

  test('keeps only the latest replay player visible after restart', async ({ page }) => {
    await page.goto('/?mock')
    await page.getByRole('button', { name: INITIAL_PROMPT }).click()
    await chooseModels(page)
    await runPipeline(page)
    await page.getByRole('button', { name: 'Empezar un nuevo experimento' }).click()
    await chooseModels(page)
    await runPipeline(page)
    await expect(page.getByRole('main').getByText('Simulación', { exact: true })).toHaveCount(1)
    await expect(page.getByText('Step 1 / 60')).toHaveCount(1)
  })

  test('decision traces — cards in chat and popover in replay', async ({ page }) => {
    await page.goto('/?mock')
    await page.getByText(INITIAL_PROMPT).click()
    await chooseModels(page)
    await runPipeline(page)
    await expect(page.getByText('Decision Trace').first()).toBeVisible()
    await expect(page.getByText('Pre-decisión').first()).toBeVisible()
    await expect(page.getByText('Post-decisión').first()).toBeVisible()
    await expect(page.getByText('move_up: 8.7').first()).toBeVisible()
    const confidenceMarker = page.locator('[title*="perdió confianza"]')
    await expect(confidenceMarker).toBeVisible()
    await confidenceMarker.click()
    const closeBtn = page.getByRole('main').locator('button:has-text("×")').first()
    await expect(closeBtn).toBeVisible()
    await expect(page.getByText('Step 47 / 60')).toBeVisible()
    await closeBtn.click()
  })

})
