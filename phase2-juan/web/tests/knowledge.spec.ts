import { test, expect } from '@playwright/test'

test.describe('Knowledge Panel — drawer + Graph tab (P7-004)', () => {

  test('drawer toggles open via sidebar button and closes via X', async ({ page }) => {
    await page.route('**/api/knowledge/graph**', route =>
      route.fulfill({ json: { nodes: [], edges: [], current_run_node_ids: [] } })
    )
    await page.goto('/?mock')
    await expect(page.getByRole('heading', { name: 'DecisionLab' })).toBeVisible()

    // Drawer not visible initially
    await expect(page.getByRole('button', { name: 'Close knowledge panel' })).not.toBeVisible()

    // Click the network toggle button (single icon button in sidebar header)
    await page.getByTitle('Knowledge graph').click()

    // Drawer appears with 3 tabs
    await expect(page.getByRole('button', { name: 'Graph', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Memories' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Provenance' })).toBeVisible()

    // Close via X
    await page.getByRole('button', { name: 'Close knowledge panel' }).click()
    await expect(page.getByRole('button', { name: 'Graph', exact: true })).not.toBeVisible()
  })

  test('renders nodes from backend and highlights run_id matches', async ({ page }) => {
    let fetchedRunId = ''
    await page.route('**/api/knowledge/graph**', route => {
      const url = new URL(route.request().url())
      fetchedRunId = url.searchParams.get('run_id') ?? ''
      route.fulfill({
        json: {
          nodes: [
            { id: 'n1', label: 'Paradigm', props: { name: 'homeostatic' } },
            { id: 'n2', label: 'Postulate', props: { id: 'P1' } },
          ],
          edges: [
            { id: 'e1', source: 'n1', target: 'n2', type: 'HAS_POSTULATE', props: {} },
          ],
          current_run_node_ids: fetchedRunId ? ['n1'] : [],
        },
      })
    })
    await page.goto('/?mock')
    await page.getByTitle('Knowledge graph').click()

    // Node labels appear
    await expect(page.getByText('homeostatic')).toBeVisible()
    await expect(page.getByText('P1')).toBeVisible()

    // Trigger run_id filter
    await page.getByPlaceholder(/run_id/i).fill('00000000-0000-0000-0000-000000000001')
    await page.getByRole('button', { name: /apply/i }).click()

    // The fetch was issued with the run_id param (the route handler captures it)
    await expect.poll(() => fetchedRunId).toBe('00000000-0000-0000-0000-000000000001')
  })

  test('shows placeholder when backend returns 503', async ({ page }) => {
    await page.route('**/api/knowledge/graph**', route => route.fulfill({ status: 503, body: '' }))
    await page.goto('/?mock')
    await page.getByTitle('Knowledge graph').click()

    await expect(page.getByText(/Knowledge Graph unavailable/i)).toBeVisible()
  })

  test('shows empty state when backend returns no nodes', async ({ page }) => {
    await page.route('**/api/knowledge/graph**', route =>
      route.fulfill({ json: { nodes: [], edges: [], current_run_node_ids: [] } })
    )
    await page.goto('/?mock')
    await page.getByTitle('Knowledge graph').click()

    await expect(page.getByText(/No knowledge stored yet/i)).toBeVisible()
  })

  test('Memories and Provenance tabs show placeholder copy', async ({ page }) => {
    await page.route('**/api/knowledge/graph**', route =>
      route.fulfill({ json: { nodes: [], edges: [], current_run_node_ids: [] } })
    )
    await page.goto('/?mock')
    await page.getByTitle('Knowledge graph').click()

    await page.getByRole('button', { name: 'Memories' }).click()
    await expect(page.getByText(/Memories tab — próximamente/i)).toBeVisible()

    await page.getByRole('button', { name: 'Provenance' }).click()
    await expect(page.getByText(/Provenance tab — próximamente/i)).toBeVisible()
  })
})
