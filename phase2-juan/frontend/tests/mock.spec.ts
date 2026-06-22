import { test, expect, type Page } from '@playwright/test'

// Turn-based mock: the first message kicks off the Architect step, then each
// Orchestrator suggestion advances the pipeline one step.
const STEP_SUGGESTIONS = [
  'Lanza la simulación',
  'Registra las trayectorias con el Tracker',
  'Analiza los resultados',
  'Genera el informe PDF',
]

// Click through every suggestion until the Reporter finishes. Assumes the
// Architect step has already produced the first suggestion.
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

    // All 5 agents visible in sidebar (text is lowercase, CSS makes it uppercase)
    for (const name of ['Orchestrator', 'Architect', 'Tracker', 'Analyst', 'Reporter']) {
      await expect(page.getByText(name).first()).toBeVisible()
    }
  })

  test('full mock pipeline — turn by turn with suggestions', async ({ page }) => {
    await page.goto('/?mock')
    await expect(page.getByRole('heading', { name: 'DecisionLab' })).toBeVisible()

    // First message kicks off the Architect step
    await page.getByText('Ejecuta una run corta con drive_reduction_rl').click()

    // Architect step: environment spec card + predictions + first suggestion
    await expect(page.getByText('Environment Spec')).toBeVisible({ timeout: 20_000 })
    await expect(page.getByRole('main').getByText('food ×6', { exact: true })).toBeVisible()
    await expect(page.getByText('regulación homeostática')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Lanza la simulación' })).toBeVisible()

    // Drive the rest of the pipeline through the suggestions
    await runPipeline(page)

    // Simulation grid rendered with critical events
    await expect(page.getByRole('main').getByText('Simulación', { exact: true })).toBeVisible()
    await expect(page.getByText('Eventos críticos').first()).toBeVisible()
    await expect(page.getByText('Step 1 / 30')).toBeVisible()
    await expect(page.getByText('Agentes', { exact: true })).toBeVisible()

    // Tracker card appeared
    await expect(page.getByText('Trayectorias', { exact: true })).toBeVisible()
    await expect(page.getByText('drive_reduction_rl').first()).toBeVisible()

    // Analyst card appeared
    await expect(page.getByText('Análisis')).toBeVisible()

    // Charts rendered (recharts)
    await expect(page.getByText('Evolución de energía por agente')).toBeVisible()
    await expect(page.getByText('Distribución de acciones')).toBeVisible()
    await expect(page.getByText('Evolución Q-values por acción (drive_reduction_rl)')).toBeVisible()

    // Reporter message
    await expect(page.getByText('experiments/mock/analisis_homeostatic_regulation.pdf')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Descargar PDF analisis_homeostatic_regulation.pdf' })).toBeVisible()

    // Simulation agents in sidebar
    await expect(page.getByRole('complementary').getByText('pi_negative_feedback', { exact: true })).toBeVisible()

    // All pipeline agents completed
    const completedBadges = page.getByRole('complementary').getByText('Completado')
    expect(await completedBadges.count()).toBeGreaterThanOrEqual(5)
  })

  test('keeps only the latest replay player visible after restart', async ({ page }) => {
    await page.goto('/?mock')
    await page.getByRole('button', {
      name: 'Ejecuta una run corta con drive_reduction_rl',
    }).click()
    await runPipeline(page)

    // Restart from the Reporter suggestion → back to the Architect step
    await page.getByRole('button', { name: 'Empezar un nuevo experimento' }).click()
    await expect(page.getByRole('button', { name: 'Lanza la simulación' })).toBeVisible({ timeout: 20_000 })
    await runPipeline(page)

    // Only the most recent simulation keeps a live replay player
    await expect(page.getByRole('main').getByText('Simulación', { exact: true })).toHaveCount(1)
    await expect(page.getByText('Step 1 / 30')).toHaveCount(1)
  })

  test('decision traces — cards in chat and popover in replay', async ({ page }) => {
    await page.goto('/?mock')
    await page.getByText('Ejecuta una run corta con drive_reduction_rl').click()
    await runPipeline(page)

    // Decision Trace cards appear in chat (from Analyst message)
    await expect(page.getByText('Decision Trace').first()).toBeVisible()

    // Shows Pre/Post columns
    await expect(page.getByText('Pre-decisión').first()).toBeVisible()
    await expect(page.getByText('Post-decisión').first()).toBeVisible()

    // Shows Q-value pills for drive_reduction_rl
    await expect(page.getByText('eat: 12.3').first()).toBeVisible()

    // Shows comparison — pi_negative_feedback trace also rendered
    await expect(page.getByText('Sin Q-values').first()).toBeVisible()

    // Replay: click confidence drop critical event marker → popover appears
    const confidenceMarker = page.locator('[title*="perdió confianza"]')
    await expect(confidenceMarker).toBeVisible()
    await confidenceMarker.click()

    // Bar-first popover shows with close button
    const closeBtn = page.getByRole('main').locator('button:has-text("×")').first()
    await expect(closeBtn).toBeVisible()

    // Popover shows the agent name
    await expect(page.getByText('Step 17 / 30')).toBeVisible()

    // Close the popover
    await closeBtn.click()
  })

})
