import { test, expect } from '@playwright/test'

test.describe('DecisionLab E2E', () => {

  test('loads UI with facehash avatars and agent panel', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'DecisionLab' })).toBeVisible()
    const sidebar = page.locator('aside')
    await expect(sidebar.getByText('Orchestrator').first()).toBeVisible({ timeout: 15_000 })
    for (const name of ['Orchestrator', 'Architect', 'Tracker', 'Analyst', 'Reporter']) {
      await expect(sidebar.getByText(name, { exact: true }).first()).toBeVisible()
    }
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
    await expect(page.locator('.msg-content').first()).toBeVisible({ timeout: 60_000 })
    const chatArea = page.locator('.overflow-y-auto')
    await expect(chatArea.locator('.msg-content').nth(1)).toBeVisible({ timeout: 60_000 })
  })

  test('full pipeline produces tracker and analyst cards', async ({ page }) => {
    test.setTimeout(600_000) // 10 minutes — full pipeline is slow
    await page.goto('/')
    const sidebar = page.locator('aside')
    await expect(sidebar.getByText('Orchestrator').first()).toBeVisible({ timeout: 15_000 })

    const input = page.locator('input[type="text"]')

    await input.fill('Hazlo todo: crea un entorno 6x6 con 4 food, ejecuta 20 pasos, observa, analiza y genera informe')
    await input.press('Enter')
    await expect(sidebar.getByText('Completado')).toHaveCount(4, { timeout: 600_000 })
    await expect(page.getByText('Trayectorias', { exact: true })).toBeVisible()
    await expect(page.getByText('Análisis')).toBeVisible()
  })

})
