# Decisiones Resueltas — Modelos de Denis

## Pregunta 1: Valores de parámetros ODE

**Decisión**: Usar los valores de la **Tabla 2.1 del TFM de Denis** (pág. 17), no los de Jacquier et al. (2014).

**Motivo**: Denis reestructuró las ecuaciones de Jacquier significativamente — no es una reparametrización sino una simplificación pedagógica. Las ecuaciones tienen formas distintas (ej: el hambre en Jacquier es una ODE, en Denis es algebraica `H = max(0, G - Leff)`). Los parámetros de Jacquier no mapean 1:1.

**Valores base** (Tabla 2.1):
- `K_H=0.0005, K_F=0.01, K_Gly=0.05, MEAL_INTAKE=10.0`
- Iniciales: `H=0.5, F=50.0, Gly=20.0, G=0.1, L=0.8`
- Q-Learning: `α=0.1, γ=0.9, ε=1.0, ε_decay=0.9995, ε_min=0.01`

**Parámetros faltantes** (`Fmax, Glymax, tauG, tauL, kG, kL, γ_leff`): derivar del código de Denis o usar valores razonables. Documentar procedencia.

---

## Pregunta 2: Estructura de recompensa (modelo hedónico)

**Decisión**: Recompensa simple `+1` por comer, `-0.01` por paso.

**Motivo**: Mantiene el modelo base limpio y testeable. La función de recompensa será un parámetro configurable para que los modos de integración (Cases 3.1/3.2) puedan sustituirla por recompensas basadas en palatabilidad (`palatability * MEAL_INTAKE`) cuando se necesite modular por hambre (`R = R·H/Hm`).

---

## Pregunta 3: Discretización del estado Q-Learning

**Decisión**: Estado = `(posición, comida_presente, palatabilidad)`. **Sin** incluir hambre en el estado.

**Motivo**: Denis describe la influencia del hambre sobre el modelo hedónico a través de modulación de recompensa/Q-valores (Cases 3.1/3.2), no expandiendo el espacio de estados. Mantiene la Q-table pequeña y manejable.

---

## Pregunta 4: Propiedad del protocolo DecisionModel

**Decisión**: El protocolo vive en `src/decisionlab/models/protocol.py`. Fase 2 lo importa directamente. Si necesita cambios, se coordinan entre fases.

**Motivo**: YAGNI — no crear un paquete compartido hasta que sea necesario.

---

## Pregunta 5: Fase de entrenamiento del modelo hedónico

**Decisión**: Incluir un método `train(episodes)` básico desde el principio.

**Motivo**: El modelo hedónico (Q-Learning) es inútil sin entrenamiento previo — no es algo que se pueda diferir. Implementación simple: sin checkpointing, sin callbacks.
