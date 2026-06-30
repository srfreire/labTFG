# Homeostatic Regulation — Mathematical Formulations

## Formulation 1: Homeostatic Reinforcement Learning (HRL) with Drive-Reduction Reward
**Approach**: Algebraic drive-reduction framework integrated with tabular Q-learning; reward is defined as the decrease in a convex drive function, and actions are selected via softmax over learned Q-values.
**Based on**: Keramati & Gutkin (2014); derived from postulates P1, P2, P5

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| h(t) | Energy level | Scalar physiological variable representing the agent's current energy/nutrient store | Continuous, [0, 1] |
| h* | Setpoint | Ideal target value for the energy level | Continuous, (0, 1] |
| D(t) | Drive | Scalar motivational signal measuring deviation from setpoint | Continuous, [0, +∞) |
| r(t) | Reward | Drive reduction produced by the outcome at time t | Continuous, (−∞, +∞) |
| Q(s,a) | Action-value | Expected discounted sum of future drive-reductions for state s and action a | Continuous, (−∞, +∞) |
| δ(t) | TD error | Temporal-difference reward prediction error | Continuous, (−∞, +∞) |
| s(t) | External state | Agent's grid position and local resource map (discretised) | Discrete |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| h* | Setpoint | 0.8 | Keramati & Gutkin (2014), normalised energy target |
| n | Drive exponent | 2 | Keramati & Gutkin (2014), quadratic drive convexity |
| c_dec | Energy decay rate | 0.02 per step | Calibrated; represents metabolic cost per time step |
| c_eat | Energy gain from eating | 0.3 | Calibrated; energy restored per food item |
| c_move | Movement energy cost | 0.005 | Calibrated; extra metabolic cost per move action |
| γ | Discount factor | 0.95 | Keramati & Gutkin (2014), required < 1 for homeostatic optimality |
| α | Learning rate | 0.1 | Standard Q-learning default |
| β | Inverse temperature | 5.0 | Moderate exploration–exploitation trade-off |

### Equations

**Eq. 1 — Energy dynamics (metabolic decay):**
`h(t+1) = clip(h(t) - c_dec - c_move * moved + c_eat * ate, 0, 1)`
$$h(t{+}1) = \text{clip}\!\Big(h(t) - c_{\text{dec}} - c_{\text{move}} \cdot \mathbb{1}_{\text{moved}} + c_{\text{eat}} \cdot \mathbb{1}_{\text{ate}},\; 0,\; 1\Big) \tag{1}$$

**Eq. 2 — Drive function (convex deviation):**
`D(t) = |h(t) - h*|^n`
$$D(t) = \left| h(t) - h^* \right|^n \tag{2}$$

**Eq. 3 — Primary reward as drive reduction:**
`r(t) = D(t) - D(t+1)`
$$r(t) = D(t) - D(t{+}1) \tag{3}$$

**Eq. 4 — TD error:**
`δ(t) = r(t) + γ · max_a' Q(s(t+1), a') - Q(s(t), a(t))`
$$\delta(t) = r(t) + \gamma \max_{a'} Q\!\big(s(t{+}1), a'\big) - Q\!\big(s(t), a(t)\big) \tag{4}$$

**Eq. 5 — Q-value update:**
`Q(s(t), a(t)) ← Q(s(t), a(t)) + α · δ(t)`
$$Q\!\big(s(t), a(t)\big) \leftarrow Q\!\big(s(t), a(t)\big) + \alpha \, \delta(t) \tag{5}$$

**Eq. 6 — Softmax action selection:**
`P(a | s) = exp(β · Q(s, a)) / Σ_j exp(β · Q(s, j))`
$$P(a \mid s) = \frac{\exp\!\big(\beta \, Q(s, a)\big)}{\sum_{j} \exp\!\big(\beta \, Q(s, j)\big)} \tag{6}$$

### Decision logic

1. **Perceive**: Observe external state s(t) = (grid position, nearby resource positions, food_at_current_cell). Observe internal state h(t).
2. **Compute drive**: Calculate D(t) via **Eq. 2**.
3. **Enumerate actions**: Available actions = {up, down, left, right, stay, eat}. Action "eat" is only available if food_at_current_cell is true.
4. **Action selection**: For each available action a, look up Q(s(t), a). Compute selection probabilities via **Eq. 6**. Sample action a(t) from this distribution.
5. **Execute action**: Perform a(t). If a(t) ∈ {up, down, left, right}, set moved=1; if a(t) = eat and food present, set ate=1.
6. **Update internal state**: Compute h(t+1) via **Eq. 1**.
7. **Compute reward**: Compute D(t+1) via **Eq. 2** on h(t+1). Compute r(t) via **Eq. 3**.
8. **Learn**: Compute δ(t) via **Eq. 4**. Update Q-table via **Eq. 5**.

---

## Formulation 2: Continuous Drive-Dynamics with Urgency-Threshold Policy
**Approach**: ODE-based continuous-time drive dynamics with a deterministic threshold-and-gradient policy; no learning — the agent uses a reactive, cybernetic negative-feedback controller with urgency-gated action switching.
**Based on**: Cannon (1929), Hull (1943) drive-reduction theory; derived from postulates P1, P2

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| h(t) | Energy level | Scalar physiological variable (normalised energy) | Continuous, [0, 1] |
| h* | Setpoint | Ideal energy level | Continuous, (0, 1] |
| D(t) | Drive | Motivational urgency signal | Continuous, [0, +∞) |
| dD/dt | Drive velocity | Rate of change of drive; indicates whether the organism is improving or deteriorating | Continuous, (−∞, +∞) |
| v_a | Action value | Estimated immediate drive reduction for action a | Continuous, (−∞, +∞) |
| d_res(i) | Resource distance | Manhattan distance to the i-th visible resource | Discrete, [0, +∞) |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| h* | Setpoint | 0.8 | Matched to Formulation 1 |
| n | Drive exponent | 2 | Hull (1943) / Keramati & Gutkin (2014), quadratic urgency |
| λ | Natural decay rate | 0.02 per step | Metabolic drain per tick |
| c_eat | Eating restoration | 0.3 | Calibrated; food value |
| c_move | Movement cost | 0.005 | Calibrated; action metabolic cost |
| D_crit | Critical drive threshold | 0.15 | Calibrated; triggers foraging urgency |
| D_low | Low drive threshold | 0.02 | Calibrated; below this, agent rests |

### Equations

**Eq. 1 — Energy dynamics (discrete-time ODE approximation):**
`h(t+1) = h(t) + Δt · (−λ + c_eat · ate − c_move · moved)`
$$h(t{+}1) = h(t) + \Delta t \left( -\lambda + c_{\text{eat}} \cdot \mathbb{1}_{\text{ate}} - c_{\text{move}} \cdot \mathbb{1}_{\text{moved}} \right) \tag{1}$$

where Δt = 1 (one simulation step).

**Eq. 2 — Drive (deviation-based urgency):**
`D(t) = (max(h* - h(t), 0))^n`
$$D(t) = \left(\max\!\big(h^* - h(t),\, 0\big)\right)^n \tag{2}$$

Note: Drive is asymmetric — only deficit (h < h*) generates drive. This follows Hull (1943) where deprivation, not excess, is motivating.

**Eq. 3 — Drive velocity (finite difference):**
`dD/dt ≈ D(t) - D(t-1)`
$$\frac{dD}{dt} \approx D(t) - D(t{-}1) \tag{3}$$

**Eq. 4 — Prospective action value (one-step lookahead):**
`v_a = D(t) - D_predicted(t+1 | a)`
$$v_a = D(t) - \hat{D}(t{+}1 \mid a) \tag{4}$$

where $\hat{D}(t{+}1 \mid a)$ is the drive predicted after executing action $a$, computed by simulating **Eq. 1** and **Eq. 2** forward one step.

**Eq. 5 — Nearest-resource gradient (for movement):**
`g(a) = d_nearest(current) - d_nearest(cell_after_a)`
$$g(a) = d_{\text{nearest}}(\text{current}) - d_{\text{nearest}}(\text{cell}(a)) \tag{5}$$

This measures whether action $a$ brings the agent closer to the nearest food resource.

### Decision logic

1. **Perceive**: Observe h(t), food_at_current_cell, positions of visible resources.
2. **Compute drive**: Calculate D(t) via **Eq. 2**. Calculate dD/dt via **Eq. 3**.
3. **Mode selection (urgency gating)**:
   - **IF** D(t) < D_low → mode = REST (drive is negligible; agent is near setpoint).
   - **ELSE IF** food_at_current_cell is true AND D(t) > 0 → mode = EAT (immediate opportunity to reduce drive).
   - **ELSE IF** D(t) ≥ D_crit OR dD/dt > 0 → mode = FORAGE (drive is high or worsening; seek food).
   - **ELSE** → mode = REST (drive is moderate and improving; conserve energy).
4. **Action execution by mode**:
   - **REST**: Select action = stay.
   - **EAT**: Select action = eat.
   - **FORAGE**: For each movement action a ∈ {up, down, left, right}, compute gradient g(a) via **Eq. 5**. Select the action with maximum g(a). If no resource is visible, select a random movement direction. Ties broken randomly.
5. **Update**: After action execution, update h(t+1) via **Eq. 1**. Store D(t) for next step's drive velocity computation (**Eq. 3**).

---

## Formulation 3: Interoceptive Active Inference (IAI) with Free-Energy Minimisation
**Approach**: Probabilistic Bayesian framework where the agent maintains a generative model of its internal state, infers its energy level under uncertainty, and selects actions by minimising expected free energy — unifying perception and action as dual means of homeostatic maintenance.
**Based on**: Friston (2010); Petzschner et al. (2021); derived from postulates P3, P4, P5

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| h(t) | True energy level | Actual (hidden) physiological state | Continuous, [0, 1] |
| μ(t) | Believed energy level | Agent's posterior mean estimate of h(t) | Continuous, [0, 1] |
| σ²_q(t) | Posterior variance | Uncertainty about the internal state estimate | Continuous, (0, +∞) |
| ε_int(t) | Interoceptive prediction error | Difference between sensory observation and prediction | Continuous, (−∞, +∞) |
| o(t) | Interoceptive observation | Noisy sensory signal of energy level | Continuous, [0, 1] |
| G(a) | Expected free energy | Scalar objective for action evaluation; combines pragmatic (goal) and epistemic (information-gain) value | Continuous, (−∞, +∞) |
| s(t) | External state | Grid position and local resource map | Discrete |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| h* | Setpoint (preferred state) | 0.8 | Friston (2010), homeostatic prior |
| σ²_p | Prior precision (setpoint variance) | 0.04 | Controls tightness of homeostatic prior; Petzschner et al. (2021) |
| σ²_s | Sensory noise variance | 0.01 | Interoceptive channel noise; Petzschner et al. (2021) |
| λ | Natural energy decay | 0.02 | Metabolic drain per step |
| c_eat | Eating restoration | 0.3 | Calibrated |
| c_move | Movement cost | 0.005 | Calibrated |
| β_G | Inverse temperature for policy | 4.0 | Moderate action selection sharpness |
| κ | Epistemic weight | 0.5 | Balances exploration (information gain) vs. exploitation (pragmatic value) |

### Equations

**Eq. 1 — Generative model (energy dynamics):**
`h(t+1) = h(t) - λ + c_eat · ate - c_move · moved + w(t), w ~ N(0, σ²_w)`
$$h(t{+}1) = h(t) - \lambda + c_{\text{eat}} \cdot \mathbb{1}_{\text{ate}} - c_{\text{move}} \cdot \mathbb{1}_{\text{moved}} + w(t), \quad w(t) \sim \mathcal{N}(0, \sigma^2_w) \tag{1}$$

**Eq. 2 — Interoceptive observation (likelihood):**
`o(t) = h(t) + v(t), v ~ N(0, σ²_s)`
$$o(t) = h(t) + v(t), \quad v(t) \sim \mathcal{N}(0, \sigma^2_s) \tag{2}$$

**Eq. 3 — Bayesian state inference (Kalman-like update):**
`μ(t) = μ_prior(t) + K(t) · (o(t) - μ_prior(t))`
$$\mu(t) = \mu_{\text{prior}}(t) + K(t) \big( o(t) - \mu_{\text{prior}}(t) \big) \tag{3}$$

where the prior prediction is:
`μ_prior(t) = μ(t-1) - λ + c_eat · ate_prev - c_move · moved_prev`
$$\mu_{\text{prior}}(t) = \mu(t{-}1) - \lambda + c_{\text{eat}} \cdot \mathbb{1}_{\text{ate\_prev}} - c_{\text{move}} \cdot \mathbb{1}_{\text{moved\_prev}} \tag{3a}$$

and the Kalman gain is:
`K(t) = σ²_q_prior(t) / (σ²_q_prior(t) + σ²_s)`
$$K(t) = \frac{\sigma^2_{q,\text{prior}}(t)}{\sigma^2_{q,\text{prior}}(t) + \sigma^2_s} \tag{3b}$$

**Eq. 4 — Posterior variance update:**
`σ²_q(t) = (1 - K(t)) · σ²_q_prior(t)`
$$\sigma^2_q(t) = \big(1 - K(t)\big) \, \sigma^2_{q,\text{prior}}(t) \tag{4}$$

where σ²_q_prior(t) = σ²_q(t−1) + σ²_w.

**Eq. 5 — Interoceptive prediction error:**
`ε_int(t) = o(t) - μ_prior(t)`
$$\varepsilon_{\text{int}}(t) = o(t) - \mu_{\text{prior}}(t) \tag{5}$$

**Eq. 6 — Pragmatic value (negative expected deviation from setpoint):**
`V_prag(a) = −(μ_predicted(a) - h*)²`
$$V_{\text{prag}}(a) = -\big(\hat{\mu}(a) - h^*\big)^2 \tag{6}$$

where $\hat{\mu}(a)$ is the predicted posterior mean after taking action $a$ (one-step forward simulation using **Eq. 1** and **Eq. 3**).

**Eq. 7 — Epistemic value (expected information gain):**
`V_epist(a) = 0.5 · ln(σ²_q_prior(a) / σ²_q_post(a))`
$$V_{\text{epist}}(a) = \frac{1}{2} \ln \frac{\sigma^2_{q,\text{prior}}(a)}{\sigma^2_{q,\text{post}}(a)} \tag{7}$$

This is the expected Bayesian surprise (KL divergence between posterior and prior), representing how much the agent expects to learn about its internal state by taking action $a$.

**Eq. 8 — Expected free energy (combined objective):**
`G(a) = −V_prag(a) − κ · V_epist(a)`
$$G(a) = -V_{\text{prag}}(a) - \kappa \, V_{\text{epist}}(a) \tag{8}$$

Lower G is better (agent minimises free energy).

**Eq. 9 — Action selection (softmax over negative G):**
`P(a) = exp(−β_G · G(a)) / Σ_j exp(−β_G · G(j))`
$$P(a) = \frac{\exp\!\big(-\beta_G \, G(a)\big)}{\sum_j \exp\!\big(-\beta_G \, G(j)\big)} \tag{9}$$

### Decision logic

1. **Perceive**: Receive noisy interoceptive observation o(t) (simulated as h(t) + noise). Observe external state s(t) = (grid position, nearby resources, food_at_current_cell).
2. **Infer internal state**: Compute prior prediction μ_prior(t) via **Eq. 3a**. Compute Kalman gain K(t) via **Eq. 3b**. Update believed energy μ(t) via **Eq. 3**. Update uncertainty σ²_q(t) via **Eq. 4**. Compute prediction error ε_int(t) via **Eq. 5**.
3. **Enumerate actions**: Available actions = {up, down, left, right, stay, eat}. "eat" only if food_at_current_cell is true.
4. **Evaluate each action**:
   - For each action a, simulate one step forward:
     - Predict μ_predicted(a) using the generative model (**Eq. 1** applied to μ(t)).
     - Compute pragmatic value V_prag(a) via **Eq. 6**.
     - Compute epistemic value V_epist(a) via **Eq. 7** (for movement actions, epistemic value is approximately zero since internal state observation does not depend on position; for eat, it may differ if eating changes sensory precision).
     - Compute expected free energy G(a) via **Eq. 8**.
5. **Select action**: Compute probabilities via **Eq. 9**. Sample action a(t) from this distribution.
6. **Execute and update**: Perform a(t). Receive new o(t+1). Update μ(t+1) and σ²_q(t+1) via **Eqs. 3–4** on next step.

---

## Cross-formulation comparison

| Aspect | Formulation 1: HRL Drive-Reduction Q-Learning | Formulation 2: ODE Drive-Dynamics Threshold Policy | Formulation 3: Interoceptive Active Inference |
|--------|-----------------------------------------------|---------------------------------------------------|----------------------------------------------|
| Framework | Algebraic (tabular RL with drive-defined reward) | ODE-based continuous dynamics with deterministic threshold control | Probabilistic Bayesian inference + expected free energy minimisation |
| Key variables | Q(s,a), D(t), r(t) | D(t), dD/dt, g(a) | μ(t), σ²_q(t), G(a) |
| Core equation | r(t) = D(t) − D(t+1) (reward as drive reduction) | D(t) = (max(h*−h(t), 0))² (asymmetric urgency) | G(a) = −V_prag(a) − κ·V_epist(a) (expected free energy) |
| Decision mechanism | Softmax over learned Q-values (stochastic, experience-dependent) | Deterministic threshold-gated mode switching + greedy gradient following | Softmax over negative expected free energy (stochastic, model-based) |
| Learning | Yes — Q-values updated via TD error every step | No — purely reactive cybernetic controller | No explicit value learning; state estimation updated via Bayesian filtering |
| Internal state representation | Directly observed h(t); no uncertainty | Directly observed h(t); no uncertainty | Inferred μ(t) under noise; maintains posterior uncertainty σ²_q(t) |
| Strengths | Captures experience-dependent adaptation; mathematically proven equivalence of reward-maximisation and homeostatic stability (Keramati & Gutkin, 2014); flexible policy learning | Minimal computational cost; interpretable mode-switching; grounded in classical cybernetics (Cannon, 1929) and drive theory (Hull, 1943); no learning warm-up needed | Handles interoceptive uncertainty naturally; unifies perception and action (Friston, 2010); epistemic exploration emerges from formalism; supports predictive/allostatic behaviour (P4) |
| Limitations | Requires exploration to learn Q-values (cold-start); ignores state estimation uncertainty; large state space may slow convergence | No adaptation to novel environments; hard-coded thresholds reduce flexibility; no uncertainty representation | Computationally heavier (forward simulation per action); κ and σ² parameters require careful tuning; no long-horizon planning beyond one step |
