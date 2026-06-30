# Lab eval — `caso2`

_seed_: 42 · _steps_: 60 · _total_: 208.27 s · _coste estimado_: $0.9984

## Entorno (Architect)
Rejilla 10x10 · acciones: move_up, move_down, move_left, move_right, eat, stay
- recurso `food` x8 (regenera: True)

## Modelos simulados
| Modelo | key | eventos | recompensa total |
|---|---|---:|---:|
| Drive-dynamics ODE (urgencia) | `homeostatic-regulation/continuous-drive-dynamics-with-urgency-threshold-policy` | 60 | 4.0 |
| HRL drive-reduction (TD-Q) | `homeostatic-reinforcement-learning/drive-reduction-td-q-learning-model-free` | 60 | 2.0 |
| Active inference (EFE + alostasis) | `interoceptive-active-inference/expected-free-energy-policy-selection-with-allostatic-prior-shifting` | 19 | 1.0 |
| Predictive coding jerárquico | `predictive-coding/hierarchical-precision-weighted-prediction-error-minimization-gradient-descent-ode` | 60 | 0.0 |

## Fidelidad de observación (Tracker)
Tripleta joinable — escritas 9, PG 9, denso 9, sparse 9 → **consistent=True**

## Determinismo
Re-simulación de `homeostatic-regulation/continuous-drive-dynamics-with-urgency-threshold-policy` con la misma semilla → trayectoria idéntica: **True**

## Informe (Reporter)
PDF producido: True · PDF real de LaTeX (no fallback): **True**

## Coste y latencia
Tokens in/out: 261389/14285 · llamadas: 20 · coste estimado: $0.9984

| Etapa | s | in tok | out tok |
|---|---:|---:|---:|
| architect | 15.03 | 4070 | 705 |
| simulation | 0.12 | 0 | 0 |
| tracker | 65.74 | 58431 | 3412 |
| kg_write | 1.26 | 0 | 0 |
| analyst | 88.43 | 171733 | 4875 |
| reporter | 37.38 | 27155 | 5293 |
