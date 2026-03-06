# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**TFG** (Trabajo de Fin de Grado, Enxenaría Informatica, USC) de Juan Freire Alvarez, dirigido por Eduardo Manuel Sanchez Vila.

**Titulo**: Laboratorio virtual para la simulacion y analisis de paradigmas de toma de decisiones humanas mediante agentes inteligentes

El TFG es la **segunda parte** de un proyecto mas amplio. La primera parte (complementaria) aborda el modelado de agentes autonomos basados en paradigmas de toma de decisiones. Este TFG construye la infraestructura para simular, observar, analizar y documentar el comportamiento de esos agentes.

## Estructura del repositorio

- `CLAUDE.md` — Instrucciones para Claude Code
- `Acordo_TFG_JuanFreireAlvarez_firmado.pdf` — Acuerdo oficial del TFG con los objetivos
- `docs/` — Documentos de referencia
  - `TFM_v_FINAL.pdf` — Paper de referencia/inspiracion (TFM de Denis Yamunaque). NO es la tesis de Juan.
  - `survival_metabolicModel_behave_clean_Denis.py` — Script de ejemplo del paper de referencia
- `phase2-juan/` — Trabajo del TFG de Juan
  - `TODO.md` — Objetivos del TFG extraidos del acuerdo
  - `DISEÑO.md` — Diseño de la arquitectura del laboratorio virtual
  - `docs/plans/` — Planes de implementacion

## Objetivos del TFG (paradigma Agentic AI)

1. **Agente Plataforma de simulacion** — entorno configurable (objetivos, recursos, restricciones)
2. **Agente Observador** — monitoriza agentes, registra eventos, episodios y trayectorias de decision
3. **Agente Analitico** — procesa datos del Observador, identifica patrones comportamiento-objetivos
4. **Agente Redactor** — genera informes estructurados, conclusiones y propuestas de mejora

## Running the reference script

```bash
python docs/survival_metabolicModel_behave_clean_Denis.py
```

Requires: Python 3 with `tkinter` (built-in), `matplotlib`, `numpy`.

### Known bug in reference script

Line 341: uses global `threshold_hungry` instead of `organism.threshold_hungry`.
