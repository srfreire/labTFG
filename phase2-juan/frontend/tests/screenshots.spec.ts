import { test } from '@playwright/test'
import path from 'node:path'

// Carpeta de figuras de la memoria LaTeX
const FIG =
  '/Users/juanfreire/Documents/academic/labtfg/phase2-juan/docs/tfg-memoria-latex/figuras'

test.use({
  viewport: { width: 1680, height: 1050 },
  deviceScaleFactor: 2,
})

test('capturas para la memoria (modo mock)', async ({ page }) => {
  // 1) Dashboard inicial — sidebar de agentes + chat de bienvenida
  await page.goto('/?mock')
  await page.getByRole('heading', { name: 'DecisionLab' }).waitFor()
  await page.waitForTimeout(800)
  await page.screenshot({ path: path.join(FIG, 'ui-01-dashboard-inicial.png') })

  // Dispara el pipeline mock completo, avanzando turno a turno por las sugerencias
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
  await page.waitForTimeout(1200) // deja asentar charts/animaciones

  // 2) Panel lateral de agentes (lab floor + estados completados)
  await page.getByRole('complementary').screenshot({
    path: path.join(FIG, 'ui-02-panel-agentes.png'),
  })

  // Cada figura captura su PROPIO elemento (no el viewport), para que sean
  // visualmente distintas. El mensaje del Analyst lleva charts y traces en la
  // misma burbuja, así que un screenshot de viewport las solapaba.

  // 3) Simulación + replay (grid animado, eventos críticos, controles de step)
  const sim = page.getByTestId('sim-replay')
  await sim.scrollIntoViewIfNeeded()
  await page.waitForTimeout(600)
  await sim.screenshot({ path: path.join(FIG, 'ui-03-simulacion-replay.png') })

  // 4) Gráficas del Analyst (energía, acciones y Q-values) — solo el bloque de charts
  const charts = page.getByTestId('analysis-charts')
  await charts.scrollIntoViewIfNeeded()
  await page.waitForTimeout(600)
  await charts.screenshot({ path: path.join(FIG, 'ui-04-analisis-charts.png') })

  // 5) Trazas de decisión (tarjetas pre/post por agente) — solo el bloque de traces
  const traces = page.getByTestId('decision-traces')
  await traces.scrollIntoViewIfNeeded()
  await page.waitForTimeout(400)
  await traces.screenshot({ path: path.join(FIG, 'ui-05-decision-traces.png') })

  // NOTA: ui-06-reporter-pdf.png NO se genera aquí. Es una página real del
  // informe PDF que produce el Reporter (rasterizada con pdftoppm), no una
  // captura de la web — capturar el viewport del chat aquí salía casi idéntico
  // a ui-05. No reintroducir una screenshot con ese nombre o se sobreescribiría
  // la figura del PDF usada en la memoria (fig:reporter-pdf, cap. de diseño).
})
