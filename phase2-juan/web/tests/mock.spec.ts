import { test, expect } from '@playwright/test'

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

  test('full mock pipeline — cards, charts, critical events, replay', async ({ page }) => {
    await page.goto('/?mock')
    await expect(page.getByRole('heading', { name: 'DecisionLab' })).toBeVisible()

    // Trigger mock pipeline
    await page.getByText('Ejecuta una run corta con drive_reduction_rl').click()

    // Wait for pipeline to complete (final continuation prompt)
    await expect(page.getByText('¿Quieres explorar algo más?')).toBeVisible({ timeout: 30_000 })

    // Environment spec card appeared
    await expect(page.getByText('Environment Spec')).toBeVisible()
    await expect(page.getByRole('main').getByText('food ×6', { exact: true })).toBeVisible()

    // Predictions appeared
    await expect(page.getByText('regulación homeostática')).toBeVisible()

    // Simulation grid rendered with critical events
    await expect(page.getByRole('main').getByText('Simulación', { exact: true })).toBeVisible()
    await expect(page.getByText('Eventos críticos').first()).toBeVisible()

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

  test('replay step indicator visible', async ({ page }) => {
    await page.goto('/?mock')
    await page.getByText('Ejecuta una run corta con drive_reduction_rl').click()
    await expect(page.getByText('¿Quieres explorar algo más?')).toBeVisible({ timeout: 30_000 })

    // Step indicator and Agentes legend visible
    await expect(page.getByText('Step 1 / 30')).toBeVisible()
    await expect(page.getByText('Agentes', { exact: true })).toBeVisible()
  })

  test('decision traces — cards in chat and popover in replay', async ({ page }) => {
    await page.goto('/?mock')
    await page.getByText('Ejecuta una run corta con drive_reduction_rl').click()
    await expect(page.getByText('¿Quieres explorar algo más?')).toBeVisible({ timeout: 30_000 })

    // Decision Trace cards appear in chat (from Analyst message)
    await expect(page.getByText('Decision Trace').first()).toBeVisible()

    // Shows Pre/Post columns
    await expect(page.getByText('Pre-decisión').first()).toBeVisible()
    await expect(page.getByText('Post-decisión').first()).toBeVisible()

    // Shows Q-value pills for drive_reduction_rl
    await expect(page.getByText('eat: 12.3').first()).toBeVisible()

    // Shows comparison — pi_negative_feedback trace also rendered
    await expect(page.getByText('Sin Q-values').first()).toBeVisible()

    // Q-values evolution chart
    await expect(page.getByText('Evolución Q-values por acción (drive_reduction_rl)')).toBeVisible()

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
