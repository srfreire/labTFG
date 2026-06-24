# Golden-scenario benchmark — resultados

## Capa 1 — contrato observable (GS-0)

| Agente | Resultado | Detalle |
|---|---|---|
| MVT (forrajeo) | PASS | decide read-only, q_values exposed |
| Diet-breadth (forrajeo) | PASS | decide read-only, q_values exposed |
| Q-learning (RL) | PASS | decide read-only, q_values exposed |
| Actor-critic (RL) | PASS | decide read-only, q_values exposed |
| GreedyForagerOracle (techo) | PASS | decide read-only, q_values exposed |
| RandomModel (suelo) | PASS | decide read-only, q_values exposed |

## Capa 1 — determinismo del motor

| Agente | Resultado | Detalle |
|---|---|---|
| MVT (forrajeo) | PASS | 120 actions identical across runs |
| Diet-breadth (forrajeo) | PASS | 120 actions identical across runs |
| Q-learning (RL) | PASS | 120 actions identical across runs |
| Actor-critic (RL) | PASS | 120 actions identical across runs |
| GreedyForagerOracle (techo) | PASS | 120 actions identical across runs |
| RandomModel (suelo) | PASS | 120 actions identical across runs |

## Capa 2 — golden scenarios

| ID | Modelo | Predicción | Resultado | Métrica observada |
|---|---|---|---|---|
| GS-OFT-1 | MVT (forrajeo) | Abandona el parche al decaer la tasa marginal | PASS | max_residence=12, departures=8 (need >=3 and >=2) |
| GS-OFT-2 | MVT (forrajeo) | ↑ coste de viaje ⇒ ↑ tiempo de residencia | PASS | mean residence low_cost=2.14 -> high_cost=2.73 (increases) |
| GS-OFT-3 | Diet-breadth (forrajeo) | Regla 0-1: excluye la presa pobre si abunda la buena | PASS | singleton-diet fraction dense=0.65, scarce=0.00 (dense must exclude poor prey, scarce must not) |
| GS-RL-1 | Q-learning (RL) | aprende (curva ascendente) | PASS | reward-rate improvement=+0.460 (need >=+0.1); exploración ε 0.99→0.05 |
| GS-RL-1 | Actor-critic (RL) | aprende (curva ascendente) | FALLA | reward-rate improvement=+0.012 (need >=+0.1); temperatura β 3.0→15.0 |
| GS-RL-1 | MVT (forrajeo) | control no-aprende (plano) | PASS | reward-rate change=+0.003 (flat if |.|<=0.1) |
| GS-RL-1 | Diet-breadth (forrajeo) | control no-aprende (plano) | PASS | reward-rate change=-0.008 (flat if |.|<=0.1) |

## Anclas de forrajeo (tarea de aprendizaje)

- GreedyForagerOracle (techo): tasa de recompensa = 0.741
- RandomModel (suelo): tasa de recompensa = 0.078
