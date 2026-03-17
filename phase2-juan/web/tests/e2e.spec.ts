import { test, expect } from '@playwright/test'

test.describe('DecisionLab E2E', () => {

  test('loads UI with facehash avatars and agent panel', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('DecisionLab')).toBeVisible()
    // Wait for WS to connect (may need auto-reconnect)
    await expect(page.getByText('conectado')).toBeVisible({ timeout: 15_000 })

    // Agent panel — 4 agents in sidebar
    const sidebar = page.locator('.hidden.md\\:block')
    for (const name of ['Architect', 'Tracker', 'Analyst', 'Reporter']) {
      await expect(sidebar.getByText(name, { exact: true }).first()).toBeVisible()
    }

    // Facehash SVGs rendered (agent rows + workers + orchestrator)
    const svgs = page.locator('svg')
    await expect(svgs.first()).toBeVisible()
    expect(await svgs.count()).toBeGreaterThanOrEqual(9)

    // All agents start idle
    expect(await sidebar.getByText('idle').count()).toBe(4)
  })

  test('chat greeting and orchestrator response', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('conectado')).toBeVisible({ timeout: 15_000 })

    const input = page.locator('input[type="text"]')
    await input.fill('Hola')
    await input.press('Enter')

    // User message text appears
    await expect(page.getByText('Hola').first()).toBeVisible({ timeout: 10_000 })

    // Orchestrator responds (wait for response after thinking)
    const chatArea = page.locator('.overflow-y-auto')
    await expect(chatArea.locator('.msg-content').nth(1)).toBeVisible({ timeout: 60_000 })
  })

  test('full pipeline with agent tool visibility', async ({ page }) => {
    test.setTimeout(600_000) // 10 minutes — full pipeline is slow
    await page.goto('/')
    await expect(page.getByText('conectado')).toBeVisible({ timeout: 15_000 })

    const input = page.locator('input[type="text"]')
    const sidebar = page.locator('.hidden.md\\:block')

    await input.fill('Hazlo todo: crea un entorno 6x6 con 4 food, ejecuta 20 pasos, observa, analiza y genera informe')
    await input.press('Enter')

    // Pipeline eventually produces results — wait for all 4 agents done
    await expect(sidebar.getByText('done')).toHaveCount(4, { timeout: 600_000 })

    // Verify data cards appeared
    await expect(page.getByText('Trayectorias')).toBeVisible()
    await expect(page.getByText('Análisis')).toBeVisible()
  })

})
