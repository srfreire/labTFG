import { test, expect, type Route } from '@playwright/test'

const EMPTY_GRAPH = { nodes: [], edges: [], current_run_node_ids: [] }

function mockGraph(page: import('@playwright/test').Page, body: object) {
  return page.route('**/api/knowledge/graph**', route => route.fulfill({ json: body }))
}

test.describe('Knowledge Panel — drawer + Graph tab (P7-004)', () => {

  test('drawer toggles open via sidebar button and closes via X', async ({ page }) => {
    await mockGraph(page, EMPTY_GRAPH)
    await page.goto('/?mock')
    await expect(page.getByRole('heading', { name: 'DecisionLab' })).toBeVisible()

    await expect(page.getByRole('button', { name: 'Close knowledge panel' })).not.toBeVisible()
    await page.getByTitle('Knowledge graph').click()

    await expect(page.getByRole('button', { name: 'Graph', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Memories' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Provenance' })).toBeVisible()

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

    await expect(page.getByText('homeostatic')).toBeVisible()
    await expect(page.getByText('P1')).toBeVisible()

    await page.getByPlaceholder(/run_id/i).fill('00000000-0000-0000-0000-000000000001')
    await page.getByRole('button', { name: /^apply$/i }).click()

    await expect.poll(() => fetchedRunId).toBe('00000000-0000-0000-0000-000000000001')
  })

  test('shows placeholder when backend returns 503', async ({ page }) => {
    await page.route('**/api/knowledge/graph**', route => route.fulfill({ status: 503, body: '' }))
    await page.goto('/?mock')
    await page.getByTitle('Knowledge graph').click()

    await expect(page.getByText(/Knowledge Graph unavailable/i)).toBeVisible()
  })

  test('shows empty state when backend returns no nodes', async ({ page }) => {
    await mockGraph(page, EMPTY_GRAPH)
    await page.goto('/?mock')
    await page.getByTitle('Knowledge graph').click()

    await expect(page.getByText(/No knowledge stored yet/i)).toBeVisible()
  })
})

test.describe('Knowledge Panel — Memories tab (P7-005)', () => {

  function mockMemoriesPage(
    page: import('@playwright/test').Page,
    handler: (route: Route, query: URLSearchParams) => void,
  ) {
    return page.route('**/api/knowledge/memories**', route => {
      const url = new URL(route.request().url())
      handler(route, url.searchParams)
    })
  }

  test('renders rows and expand-on-click shows full content', async ({ page }) => {
    await mockGraph(page, EMPTY_GRAPH)
    await mockMemoriesPage(page, (route) =>
      route.fulfill({
        json: {
          items: [
            {
              id: 'm1',
              content: 'this is the long memory content that should expand',
              namespace: 'paradigm',
              run_id: 'r1',
              memory_type: 'semantic',
              source_stage: 'researcher',
              created_at: '2026-01-01T12:34:56',
            },
          ],
          total: 1,
          page: 1,
          page_size: 50,
        },
      })
    )
    await page.goto('/?mock')
    await page.getByTitle('Knowledge graph').click()
    await page.getByRole('button', { name: 'Memories' }).click()

    // Match table cell, not the <option> in the select
    await expect(page.locator('td', { hasText: 'paradigm' })).toBeVisible()
    await expect(page.getByText('semantic')).toBeVisible()
    await expect(page.getByText(/1 memories/)).toBeVisible()

    // Click the row to expand the full content
    await page.getByText('this is the long memory content').click()
    // The full content is in a whitespace-pre-wrap div now
    await expect(page.getByText('this is the long memory content that should expand')).toBeVisible()
  })

  test('namespace + run_id filters hit the backend with expected query string', async ({ page }) => {
    await mockGraph(page, EMPTY_GRAPH)
    let lastQuery: URLSearchParams | null = null
    await mockMemoriesPage(page, (route, query) => {
      lastQuery = query
      route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 50 } })
    })
    await page.goto('/?mock')
    await page.getByTitle('Knowledge graph').click()
    await page.getByRole('button', { name: 'Memories' }).click()

    // Wait for the initial request
    await expect.poll(() => lastQuery?.has('page')).toBe(true)

    // Set filters and apply
    await page.locator('select').selectOption('paradigm')
    await page.getByPlaceholder(/run_id/i).fill('11111111-1111-1111-1111-111111111111')
    await page.getByRole('button', { name: /^apply$/i }).click()

    await expect.poll(() => lastQuery?.get('namespace')).toBe('paradigm')
    await expect.poll(() => lastQuery?.get('run_id')).toBe('11111111-1111-1111-1111-111111111111')
  })

  test('page size is capped to 200 client-side', async ({ page }) => {
    await mockGraph(page, EMPTY_GRAPH)
    let lastQuery: URLSearchParams | null = null
    await mockMemoriesPage(page, (route, query) => {
      lastQuery = query
      route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 200 } })
    })
    await page.goto('/?mock')
    await page.getByTitle('Knowledge graph').click()
    await page.getByRole('button', { name: 'Memories' }).click()

    await page.getByTitle('page size (max 200)').fill('9999')
    await page.getByRole('button', { name: /^apply$/i }).click()

    await expect.poll(() => lastQuery?.get('page_size')).toBe('200')
  })
})

test.describe('Knowledge Panel — Provenance tab (P7-005)', () => {

  test('empty state when no node selected', async ({ page }) => {
    await mockGraph(page, EMPTY_GRAPH)
    await page.goto('/?mock')
    await page.getByTitle('Knowledge graph').click()
    await page.getByRole('button', { name: 'Provenance' }).click()

    await expect(page.getByText(/No node selected/i)).toBeVisible()
  })

  test('clicking a node switches to Provenance and renders trail', async ({ page }) => {
    await page.route('**/api/knowledge/graph**', route =>
      route.fulfill({
        json: {
          nodes: [
            { id: 'n1', label: 'Postulate', props: { name: 'P1' } },
          ],
          edges: [],
          current_run_node_ids: [],
        },
      })
    )
    await page.route('**/api/knowledge/provenance/**', route =>
      route.fulfill({
        json: {
          node: { id: 'n1', label: 'Postulate', props: { name: 'P1' } },
          trail: [
            {
              edge: { id: 'e1', type: 'SUPPORTED_BY', props: {} },
              node: { id: 'p1', label: 'Paper', props: { title: 'Foundational paper' } },
            },
          ],
        },
      })
    )
    await page.goto('/?mock')
    await page.getByTitle('Knowledge graph').click()

    // Click the node renderer (P1 label visible inside the node card)
    await page.getByText('P1').click()

    // Switched to Provenance tab
    await expect(page.getByText('SUPPORTED_BY')).toBeVisible()
    await expect(page.getByText('Foundational paper')).toBeVisible()
  })

  test('empty trail shows empty-trail copy (not an error)', async ({ page }) => {
    await page.route('**/api/knowledge/graph**', route =>
      route.fulfill({
        json: {
          nodes: [{ id: 'n1', label: 'Postulate', props: { name: 'P1' } }],
          edges: [],
          current_run_node_ids: [],
        },
      })
    )
    await page.route('**/api/knowledge/provenance/**', route =>
      route.fulfill({
        json: {
          node: { id: 'n1', label: 'Postulate', props: { name: 'P1' } },
          trail: [],
        },
      })
    )
    await page.goto('/?mock')
    await page.getByTitle('Knowledge graph').click()
    await page.getByText('P1').click()

    await expect(page.getByText(/no tiene una cadena de procedencia/i)).toBeVisible()
  })
})
