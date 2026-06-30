# Lab eval — `caso1`

_seed_: 42 · _steps_: 60 · _total_: 267.97 s · _coste estimado_: $1.2839

## Entorno (Architect)
Rejilla 8x8 · acciones: move_up, move_down, move_left, move_right, eat, stay
- recurso `food` x6 (regenera: True)

## Modelos simulados
| Modelo | key | eventos | recompensa total |
|---|---|---:|---:|
| Valor por atributos (algebraico) | `attribute-based-value-computation/weighted-linear-summation-with-state-dependent-attribute-weights-algebraic` | 60 | 1.0 |
| Autocontrol dlPFC (reponderación) | `dlpfc-self-control-modulation/attribute-reweighting-algebraic-model` | 60 | 0.0 |
| DDM (Wiener) | `drift-diffusion-model/classical-wiener-process-with-per-action-accumulators` | 60 | 10.0 |
| Dirigido vs hábito (Q dual) | `goal-directed-vs-habitual-control/dual-q-table-with-fixed-exponential-decay-arbitration` | 60 | 1.0 |
| Homeostasis (drive-reduction ODE) | `homeostatic-regulation-of-food-valuation/drive-reduction-ode-with-goal-directed-valuation` | 60 | 3.0 |
| Pavloviano (Rescorla-Wagner softmax) | `pavlovian-control-of-food-approach/rescorlawagner-cached-value-agent-with-softmax-action-selection` | 60 | 0.0 |

## Fidelidad de observación (Tracker)
Tripleta joinable — escritas 12, PG 12, denso 12, sparse 12 → **consistent=True**

## Determinismo
Re-simulación de `attribute-based-value-computation/weighted-linear-summation-with-state-dependent-attribute-weights-algebraic` con la misma semilla → trayectoria idéntica: **True**

## Informe (Reporter)
PDF producido: True · PDF real de LaTeX (no fallback): **True**

## Coste y latencia
Tokens in/out: 335124/18566 · llamadas: 23 · coste estimado: $1.2839

| Etapa | s | in tok | out tok |
|---|---:|---:|---:|
| architect | 8.84 | 3982 | 703 |
| simulation | 0.09 | 0 | 0 |
| tracker | 64.23 | 92947 | 3637 |
| kg_write | 0.62 | 0 | 0 |
| analyst | 109.14 | 202231 | 6099 |
| reporter | 84.72 | 35964 | 8127 |
