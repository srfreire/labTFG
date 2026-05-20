import { test, expect } from '@playwright/test'

test.describe('DecisionLab E2E', () => {

  test('loads UI with facehash avatars and agent panel', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'DecisionLab' })).toBeVisible()

    // Wait for WS to connect — agent panel only renders agents after ws.send_json
    const sidebar = page.locator('aside')
    await expect(sidebar.getByText('Orchestrator').first()).toBeVisible({ timeout: 15_000 })

    // Agent panel — 5 agents in sidebar (Orchestrator + 4 subagents)
    for (const name of ['Orchestrator', 'Architect', 'Tracker', 'Analyst', 'Reporter']) {
      await expect(sidebar.getByText(name, { exact: true }).first()).toBeVisible()
    }

    // Facehash SVGs rendered (5 agent avatars + send button svg)
    const svgs = page.locator('svg')
    await expect(svgs.first()).toBeVisible()
    expect(await svgs.count()).toBeGreaterThanOrEqual(6)
  })

  test('chat greeting and orchestrator response', async ({ page }) => {
    await page.goto('/')
    const sidebar = page.locator('aside')
    await expect(sidebar.getByText('Orchestrator').first()).toBeVisible({ timeout: 15_000 })

    const input = page.locator('input[type="text"]')
    await expect(input).toBeVisible({ timeout: 15_000 })
    await input.click()
    await page.keyboard.type('Hola', { delay: 50 })
    await page.keyboard.press('Enter')

    // User message text appears in chat
    await expect(page.locator('.msg-content').first()).toBeVisible({ timeout: 60_000 })

    // Orchestrator responds (wait for response after thinking)
    const chatArea = page.locator('.overflow-y-auto')
    await expect(chatArea.locator('.msg-content').nth(1)).toBeVisible({ timeout: 60_000 })
  })

  test('full pipeline with agent tool visibility', async ({ page }) => {
    test.setTimeout(600_000) // 10 minutes — full pipeline is slow
    await page.goto('/')
    const sidebar = page.locator('aside')
    await expect(sidebar.getByText('Orchestrator').first()).toBeVisible({ timeout: 15_000 })

    const input = page.locator('input[type="text"]')

    await input.fill('Hazlo todo: crea un entorno 6x6 con 4 food, ejecuta 20 pasos, observa, analiza y genera informe')
    await input.press('Enter')

    // Pipeline eventually produces results — wait for all 4 agents done
    // (AgentPanel renders the literal text "Completado" for isDone state)
    await expect(sidebar.getByText('Completado')).toHaveCount(4, { timeout: 600_000 })

    // Verify data cards appeared
    await expect(page.getByText('Trayectorias')).toBeVisible()
    await expect(page.getByText('Análisis')).toBeVisible()
  })

})
