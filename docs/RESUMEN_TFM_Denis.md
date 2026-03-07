# Resumen del TFM de Denis Yamunaque

**Titulo**: Interaccion entre el sistema homeostatico y el sistema hedonico en el control del comportamiento alimentario

**Autor**: Denis Jorge Nunes Yamunaque
**Director**: Prof. Dr. Eduardo Manuel Sanchez Vila
**Universidad**: USC — Master en Neurociencias, Curso 2024/2025

---

## 1. Problema

La regulacion del comportamiento alimentario depende de dos sistemas biologicos:

- **Sistema homeostatico**: regula necesidades fisiologicas (hambre, balance energetico). Responde a senales internas como grelina (hambre) y leptina (saciedad).
- **Sistema hedonico**: modula motivacion y placer asociados al consumo. Relacionado con el sistema dopaminergico y el aprendizaje por refuerzo.

Tradicionalmente se estudiaron por separado, pero interactuan dinamicamente. Cuando el sistema hedonico sobrepasa las senales homeostaticas, puede provocar ingesta excesiva (obesidad, trastornos alimentarios).

## 2. Hipotesis

1. Existe interaccion bidireccional entre ambos sistemas.
2. Esa interaccion puede explicar comportamientos compulsivos en la ingesta.
3. La integracion permite al organismo ajustar su conducta segun necesidades biologicas Y propiedades motivacionales del alimento.

## 3. Modelo computacional

### 3.1 Modelo homeostatico (ecuaciones diferenciales)

Variables principales:
- `F(t)`: reservas de grasa corporal
- `Gly(t)`: glucogeno hepatico
- `G(t)`: concentracion de grelina (hormona del hambre)
- `L(t)`: concentracion de leptina (hormona de saciedad)
- `I(t)`: tasa de ingesta calorica

Ecuaciones diferenciales (EDOs) gobiernan la evolucion temporal:
- **Grasa**: `dF/dt = cF * I(t) - alphaF * F(t)` (almacenamiento vs utilizacion)
- **Glucogeno**: `dGly/dt = cGly * I(t) - alphaGly * Gly(t) - beta * A(t)` (almacenamiento vs utilizacion)
- **Grelina**: `dG/dt = kG * (1 - min(1, Gly/Glymax)) - G/tauG` (produccion vs degradacion)
- **Leptina**: `dL/dt = kL * min(1, F/Fmax) - L/tauL` (produccion vs degradacion)

La senal de **Hambre** se calcula como:
```
Leff(t) = gamma * L(t) * sigmoid(F(t)/Fmax - 0.5)
H(t) = max(0, G(t) - Leff(t))
```

### 3.2 Modelo hedonico (Q-Learning)

Aprendizaje por refuerzo donde el agente aprende a maximizar recompensa en un entorno de cuadricula.

- **Estado**: posicion del agente + palatabilidad del alimento + variables fisiologicas (opcional)
- **Acciones**: arriba, abajo, izquierda, derecha, comer
- **Tabla Q**: almacena recompensa esperada para cada par (estado, accion)
- **Regla de aprendizaje**: `Q(s,a) <- Q(s,a) + alpha * [R + gamma * max_a' Q(s',a') - Q(s,a)]`
- **Estrategia**: epsilon-greedy (exploracion -> explotacion)
- **Senal hedonica**: valor maximo de la tabla Q en la posicion actual

### 3.3 Integracion de los dos sistemas

Tres modos de integracion evaluados:

| Caso | Descripcion |
|------|-------------|
| **1** | Sistemas independientes. Senal de decision = media aritmetica de ambas senales |
| **2** | Hedoico -> Homeostatico. La senal hedonica modula la senal de hambre: `H(t) = 0.95*H(t) + 0.05*W(t)` |
| **3.1** | Homeostatico -> Hedonico (recompensa inmediata). `R(t) = R(t) * H(t)/Hm` |
| **3.2** | Homeostatico -> Hedonico (recompensa esperada). `Qmax(t) = Qmax(t) * H(t)/Hm` |

## 4. Diseno experimental

### Entornos simulados

Dos variables de entorno cruzadas:

| | Alta palatabilidad (0.7-1.0) | Baja palatabilidad (0.1-0.3) |
|---|---|---|
| **Frecuencia regular** (70% renovacion) | Escenario 1 | Escenario 2 |
| **Frecuencia baja** (10% renovacion) | Escenario 3 | Escenario 4 |

Cada escenario se evalua con los 4 casos de integracion (1, 2, 3.1, 3.2).

### Parametros principales

| Parametro | Valor |
|-----------|-------|
| Hambre inicial | 0.5 |
| Grasa inicial | 50.0 |
| Glucogeno inicial | 20.0 |
| Learning rate (alpha) | 0.1 |
| Discount factor (gamma) | 0.9 |
| Epsilon inicial | 1.0 |
| Epsilon decay | 0.9995 |
| Simulacion | 1440 pasos (= 1 dia simulado, 1 paso = 1 min) |

### Implementacion

- Python con numpy, pandas, scikit-learn
- ~33 min por simulacion completa

## 5. Resultados clave

### Caso 1 (independientes)
Comportamiento predecible y estable. Progresion lineal en ganancia de peso. Referencia base.

### Caso 2 (hedonico -> homeostatico)
Aumento en la senal de hambre incluso con alta disponibilidad. Mayor frecuencia de ingesta (~26-33% vs ~10% del tiempo buscando comida). Biologicamente menos realista pero demuestra como la recompensa modula senales fisiologicas.

### Caso 3.1/3.2 (homeostatico -> hedonico)
Senal hedonica mas intensa. Consistente con la hipotesis de que las necesidades fisiologicas regulan al alza las necesidades hedonicas (Berridge, 2018). Genera senal anticipatoria que permite buscar alimento sin necesidad fisiologica urgente.

### Efecto de la palatabilidad
- **Alta palatabilidad**: sensibilizacion del sistema hedonico, patrones de ingesta compulsivos
- **Baja palatabilidad**: desensibilizacion del sistema hedonico, comportamiento mas moderado

### Efecto de la frecuencia
- Con menor disponibilidad de alimento, el agente con senal anticipatoria (casos 3.1/3.2) busca alimento con mayor frecuencia que el independiente (caso 1), ventaja evolutiva.

## 6. Conclusiones

1. La interaccion bidireccional entre sistemas homeostatico y hedonico es fundamental para explicar dinamicas complejas de la ingesta.
2. La senal hedonica actua como mecanismo de anticipacion: ventaja evolutiva en escasez, factor de riesgo en abundancia (obesidad).
3. Alta palatabilidad sensibiliza el sistema hedonico -> ingesta compulsiva.
4. Baja palatabilidad desensibiliza el sistema hedonico -> ingesta regulada.
5. El modelo ofrece un framework computacional para explorar como variaciones fisiologicas y contextuales afectan la toma de decisiones alimentarias.

## 7. Relevancia para el TFG

Este TFM es un ejemplo concreto de:
- **Modelado de toma de decisiones** con dos sistemas en conflicto/cooperacion
- **Agente autonomo** cuyo comportamiento esta guiado por un modelo matematico (homeostatico) y un modelo computacional (Q-Learning)
- **Simulacion en entorno de cuadricula** con recursos (alimento)
- **Analisis de comportamiento emergente** bajo distintas condiciones

El script `survival_metabolicModel_behave_clean_Denis.py` es una version simplificada previa que usa un modelo metabolico basico (energia + nutrientes) con un ciclo percibir-motivar-decidir-actuar, sin el componente de Q-Learning del TFM final.

## 8. Referencias

- Lutter & Nestler (2009). Homeostatic and hedonic signals interact in the regulation of food intake. *J Nutrition*
- Woods & Ramsay (2011). Food intake, metabolism and homeostasis. *Physiology & Behavior*
- Jacquier et al. (2014). A predictive model of body weight and food intake dynamics in rats. *PLOS ONE*
- Munzberg et al. (2016). Hedonics Act in Unison with the Homeostatic System. *Frontiers in Nutrition*
- Berridge (2018). Evolving Concepts of Emotion and Motivation. *Frontiers in Psychology*
