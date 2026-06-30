import { test, type Page } from '@playwright/test'
import path from 'node:path'

// Carpeta de figuras de la memoria LaTeX
const FIG =
  '/Users/juanfreire/Documents/academic/labtfg/phase2-juan/docs/tfg-memoria-latex/figuras'

test.use({
  viewport: { width: 1680, height: 1050 },
  deviceScaleFactor: 2,
})

// Captura el elemento identificado por su testid (recorte ajustado, sin el
// "cromo" del chat) para que cada figura de detalle sea visualmente limpia.
async function shotElement(page: Page, testid: string, file: string) {
  const el = page.getByTestId(testid).first()
  await el.scrollIntoViewIfNeeded()
  await page.waitForTimeout(500)
  await el.screenshot({ path: path.join(FIG, file) })
}

test('galería de la interfaz para la memoria (modo mock)', async ({ page }) => {
  await page.goto('/?mock')
  await page.getByRole('heading', { name: 'DecisionLab' }).waitFor()
  // Oculta el badge MOCK de forma persistente: la UI es idéntica a la real,
  // así que las figuras de la memoria no deben mostrar el indicador de demo.
  await page.addStyleTag({
    content: '[data-testid="mock-badge"]{display:none !important}',
  })

  // Ejecuta el pipeline mock completo, avanzando turno a turno por las
  // sugerencias del Orchestrator hasta tener todas las salidas en pantalla.
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
  await page.waitForTimeout(1400) // deja asentar charts/animaciones

  // --- Detalle por agente / feature -------------------------------------
  // Cada figura captura su PROPIO elemento para que sean visualmente
  // distintas y autocontenidas.

  // Architect — tarjeta de especificación del entorno
  await shotElement(page, 'env-card', 'ui-02-architect-spec.png')

  // Simulación + replay (grid animado, eventos críticos, controles de step)
  await shotElement(page, 'sim-replay', 'ui-03-simulacion-replay.png')

  // Analyst — gráficas comparativas (energía, acciones y Q-values)
  await shotElement(page, 'analysis-charts', 'ui-04-analisis-charts.png')

  // Tracker — trayectorias por agente (pasos, recursos, acciones)
  await shotElement(page, 'tracker-card', 'ui-05-tracker-trayectorias.png')

  // Analyst — patrones detectados y comparaciones entre modelos
  await shotElement(page, 'analyst-card', 'ui-06-analyst-patrones.png')

  // Trazas de decisión (tarjetas pre/post por agente)
  await shotElement(page, 'decision-traces', 'ui-07-decision-traces.png')

  // Panel lateral del pipeline (estados de agentes + lab floor + entorno)
  await page
    .getByRole('complementary')
    .first()
    .screenshot({ path: path.join(FIG, 'ui-08-pipeline-panel.png') })

  // --- Vista completa del laboratorio -----------------------------------
  // Viewport con el panel lateral (pipeline completado) + el chat mostrando
  // la simulación: la captura "completa" representativa del laboratorio.
  await page.getByTestId('sim-replay').first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(600)
  await page.screenshot({ path: path.join(FIG, 'ui-01-dashboard-inicial.png') })

  // NOTA: la figura del Reporter (ui-09-reporter-pdf.png) NO se genera aquí.
  // Es una página real del informe PDF que produce el Reporter (rasterizada
  // con pdftoppm), no una captura de la web.
})
