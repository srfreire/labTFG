# Predictive Coding — Mathematical Formulations

## Formulation 1: Hierarchical Precision-Weighted Prediction Error Minimization (Gradient-Descent ODE)
**Approach**: Continuous-time ODE-based gradient descent on a precision-weighted free energy functional, with hierarchical belief states updated each tick and actions selected via softmax over predicted free energy reduction.
**Based on**: Rao & Ballard (1999); Friston (2010); Friston & Kiebel (2009); derived from postulates P1, P2, P3, P4.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $s(t)$ | Sensory observation | Vector encoding the agent's current perception: position $(x,y)$, nearby resource locations, hunger/satiation flag | Continuous, $\mathbb{R}^n$ |
| $\mu^{(1)}(t)$ | Level-1 belief state | Agent's best estimate of immediate environmental state (e.g., predicted resource presence in nearby cells) | Continuous, $\mathbb{R}^{n_1}$ |
| $\mu^{(2)}(t)$ | Level-2 belief state | Higher-order belief encoding abstract context (e.g., expected resource density, "world quality") | Continuous, $\mathbb{R}^{n_2}$ |
| $\varepsilon^{(1)}(t)$ | Level-1 prediction error | Mismatch between sensory observation and level-1 prediction: $s(t) - g^{(1)}(\mu^{(1)})$ | Continuous, $\mathbb{R}^{n}$ |
| $\varepsilon^{(2)}(t)$ | Level-2 prediction error | Mismatch between level-1 belief and level-2 prediction: $\mu^{(1)} - g^{(2)}(\mu^{(2)})$ | Continuous, $\mathbb{R}^{n_1}$ |
| $\Pi^{(1)}$ | Level-1 precision | Inverse variance weighting on sensory prediction errors (attention to sensory channel) | Continuous, $\mathbb{R}^+$ |
| $\Pi^{(2)}$ | Level-2 precision | Inverse variance weighting on higher-level prediction errors (confidence in abstract model) | Continuous, $\mathbb{R}^+$ |
| $F(t)$ | Variational free energy | Scalar objective: precision-weighted sum of squared prediction errors across hierarchy | Continuous, $\mathbb{R}^+$ |
| $a(t)$ | Action | Discrete choice from {move_up, move_down, move_left, move_right, stay, eat} | Discrete |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\kappa$ | Inference learning rate | 0.5 | Rao & Ballard (1999), typical gradient step size |
| $\Pi^{(1)}_0$ | Initial level-1 precision | 2.0 | Friston (2010), moderate sensory confidence |
| $\Pi^{(2)}_0$ | Initial level-2 precision | 1.0 | Friston (2010), lower prior confidence |
| $\eta_\Pi$ | Precision adaptation rate | 0.1 | Friston (2010), slow precision learning |
| $N_{\text{iter}}$ | Inference iterations per step | 5 | Prior pipeline run (knowledge backbone) |
| $\beta$ | Action softmax inverse temperature | 4.0 | Standard in active inference implementations |
| $\lambda$ | Prediction error decay (temporal smoothing) | 0.8 | Friston & Kiebel (2009), temporal dynamics |
| $\sigma^2_{\text{init}}$ | Initial error variance estimate | 1.0 | Normalization default |

### Equations

**Eq. 1 — Level-1 prediction error:**
`ε_1(t) = s(t) − g_1(μ_1(t))`
$$\varepsilon^{(1)}(t) = s(t) - g^{(1)}\!\bigl(\mu^{(1)}(t)\bigr) \tag{1}$$

where $g^{(1)}(\mu^{(1)})$ is the level-1 generative mapping: predicted sensory input given the current level-1 belief. In the grid world, $g^{(1)}$ maps the agent's belief about nearby resource locations to an expected sensory vector.

**Eq. 2 — Level-2 prediction error:**
`ε_2(t) = μ_1(t) − g_2(μ_2(t))`
$$\varepsilon^{(2)}(t) = \mu^{(1)}(t) - g^{(2)}\!\bigl(\mu^{(2)}(t)\bigr) \tag{2}$$

where $g^{(2)}(\mu^{(2)})$ is the level-2 generative mapping: predicted level-1 states given the higher-order context belief.

**Eq. 3 — Free energy (prediction error energy):**
`F(t) = 0.5 · Π_1 · ‖ε_1(t)‖² + 0.5 · Π_2 · ‖ε_2(t)‖² − 0.5 · (ln Π_1 + ln Π_2)`
$$F(t) = \frac{1}{2}\,\Pi^{(1)} \|\varepsilon^{(1)}(t)\|^2 + \frac{1}{2}\,\Pi^{(2)} \|\varepsilon^{(2)}(t)\|^2 - \frac{1}{2}\bigl(\ln \Pi^{(1)} + \ln \Pi^{(2)}\bigr) \tag{3}$$

This is the Gaussian free energy under a Laplace approximation (Friston, 2010). The log-precision terms prevent trivial minimization by setting precision to zero.

**Eq. 4 — Level-1 belief update (gradient descent on F):**
`dμ_1/dt = −κ · ∂F/∂μ_1 = κ · (Π_1 · ∂g_1/∂μ_1ᵀ · ε_1 − Π_2 · ε_2)`
$$\frac{d\mu^{(1)}}{dt} = \kappa \left( \Pi^{(1)} \frac{\partial g^{(1)}}{\partial \mu^{(1)}}^\top \varepsilon^{(1)} - \Pi^{(2)}\, \varepsilon^{(2)} \right) \tag{4}$$

The first term pulls beliefs toward sensory data (bottom-up); the second term enforces consistency with higher-level predictions (top-down).

**Eq. 5 — Level-2 belief update:**
`dμ_2/dt = −κ · ∂F/∂μ_2 = κ · Π_2 · ∂g_2/∂μ_2ᵀ · ε_2`
$$\frac{d\mu^{(2)}}{dt} = \kappa \, \Pi^{(2)} \frac{\partial g^{(2)}}{\partial \mu^{(2)}}^\top \varepsilon^{(2)} \tag{5}$$

**Eq. 6 — Precision adaptation:**
`Π_l ← Π_l + η_Π · (1/‖ε_l‖² − Π_l)`
$$\Pi^{(l)} \leftarrow \Pi^{(l)} + \eta_\Pi \left( \frac{1}{\|\varepsilon^{(l)}\|^2 + \sigma^2_{\text{init}}} - \Pi^{(l)} \right) \tag{6}$$

Precision is driven toward the empirical inverse variance of recent prediction errors (Friston, 2010). The $\sigma^2_{\text{init}}$ term prevents division by zero.

**Eq. 7 — Predicted free energy for action a:**
`F_pred(a) = 0.5 · Π_1 · ‖s_pred(a) − g_1(μ_1)‖² + 0.5 · Π_2 · ‖ε_2‖²`
$$F_{\text{pred}}(a) = \frac{1}{2}\,\Pi^{(1)}\, \|s_{\text{pred}}(a) - g^{(1)}(\mu^{(1)})\|^2 + \frac{1}{2}\,\Pi^{(2)}\, \|\varepsilon^{(2)}\|^2 \tag{7}$$

where $s_{\text{pred}}(a)$ is the agent's predicted sensory outcome of taking action $a$.

**Eq. 8 — Action selection (softmax over negative predicted free energy):**
`P(a) = exp(−β · F_pred(a)) / Σ_j exp(−β · F_pred(j))`
$$P(a) = \frac{\exp\bigl(-\beta \, F_{\text{pred}}(a)\bigr)}{\sum_{j} \exp\bigl(-\beta \, F_{\text{pred}}(j)\bigr)} \tag{8}$$

### Decision logic

1. **Perceive**: Receive sensory vector $s(t)$ encoding position $(x,y)$, list of nearby resource positions, and whether the agent just ate.
2. **Inference loop** (repeat $N_{\text{iter}}$ times):
   - Compute $\varepsilon^{(1)}$ via Eq. 1 and $\varepsilon^{(2)}$ via Eq. 2.
   - Update $\mu^{(1)}$ via Eq. 4 (discretized: $\mu^{(1)} \leftarrow \mu^{(1)} + \kappa \cdot \Delta\mu^{(1)}$).
   - Update $\mu^{(2)}$ via Eq. 5.
3. **Precision update**: Update $\Pi^{(1)}$ and $\Pi^{(2)}$ via Eq. 6.
4. **Action evaluation**: For each candidate action $a \in \{\text{up, down, left, right, stay, eat}\}$:
   - Predict sensory outcome $s_{\text{pred}}(a)$ using the generative model and current beliefs.
   - If action is `eat` and no food at current position, set $F_{\text{pred}}(\text{eat}) = +\infty$ (impossible action).
   - Compute $F_{\text{pred}}(a)$ via Eq. 7.
5. **Select action**: Sample action from softmax distribution (Eq. 8). Alternatively, use argmin for deterministic behavior.
6. **Return** selected action.

**Update step** (after receiving reward and new perception):
- Incorporate reward as a prediction-error signal: if reward was received (ate food), reduce interoceptive prediction error in $\varepsilon^{(1)}$; if expected food was absent, increase prediction error.
- Run inference loop again with new $s(t+1)$ to update beliefs for next decision.

---

## Formulation 2: Algebraic Precision-Weighted Bayesian Filtering (Single-Step Conjugate Update)
**Approach**: Closed-form algebraic Bayesian update at each time step using precision-weighted averaging (conjugate Gaussian inference) — no iterative gradient descent, no ODEs. Beliefs are updated in a single analytic step per tick.
**Based on**: Rao & Ballard (1999); Friston (2010) — Gaussian/Laplace approximation; derived from postulates P1, P2, P4.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $s(t)$ | Sensory observation | Encoded perception: position, nearby resources, hunger state | Continuous, $\mathbb{R}^n$ |
| $\hat{\mu}(t)$ | Posterior belief (state estimate) | Agent's point estimate of local environmental state after Bayesian update | Continuous, $\mathbb{R}^n$ |
| $\hat{\pi}_s$ | Sensory precision | Confidence in sensory observations (inverse observation noise) | Continuous, $\mathbb{R}^+$ |
| $\hat{\pi}_0$ | Prior precision | Confidence in prior predictions (inverse prior variance) | Continuous, $\mathbb{R}^+$ |
| $\mu_0(t)$ | Prior prediction | Expected state based on previous posterior and transition model | Continuous, $\mathbb{R}^n$ |
| $\varepsilon(t)$ | Prediction error | $s(t) - \mu_0(t)$: mismatch between observation and prior prediction | Continuous, $\mathbb{R}^n$ |
| $w(t)$ | Precision-weighted surprise | Scalar summary of how surprising the current observation is | Continuous, $\mathbb{R}^+$ |
| $V(c)$ | Cell value | Expected precision-weighted reward proximity for each neighboring cell $c$ | Continuous, $\mathbb{R}$ |
| $a(t)$ | Action | Discrete choice from {move_up, move_down, move_left, move_right, stay, eat} | Discrete |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\hat{\pi}_{s,0}$ | Initial sensory precision | 4.0 | Friston (2010), high sensory confidence |
| $\hat{\pi}_{0,0}$ | Initial prior precision | 1.0 | Friston (2010), moderate prior confidence |
| $\alpha_\pi$ | Precision learning rate | 0.15 | Empirical; Friston (2010) |
| $\gamma$ | Temporal discount on prior | 0.9 | Friston & Kiebel (2009), temporal dynamics |
| $\beta$ | Action softmax inverse temperature | 5.0 | Standard value |
| $r_{\text{food}}$ | Reward signal for eating | 1.0 | Normalization constant |
| $r_{\text{empty}}$ | Penalty for failed eat | −0.5 | Encourages accurate predictions |
| $d_{\max}$ | Maximum perception distance (cells) | 5 | Grid-world design parameter |

### Equations

**Eq. 1 — Prior prediction (temporal transition model):**
`μ_0(t) = γ · μ̂(t−1) + (1−γ) · s_default`
$$\mu_0(t) = \gamma \, \hat{\mu}(t-1) + (1-\gamma)\, s_{\text{default}} \tag{1}$$

where $s_{\text{default}}$ is the agent's baseline expectation (e.g., "no food nearby"). The prior drifts toward the default in the absence of confirming evidence.

**Eq. 2 — Prediction error:**
`ε(t) = s(t) − μ_0(t)`
$$\varepsilon(t) = s(t) - \mu_0(t) \tag{2}$$

**Eq. 3 — Posterior belief (precision-weighted average):**
`μ̂(t) = (π_s · s(t) + π_0 · μ_0(t)) / (π_s + π_0)`
$$\hat{\mu}(t) = \frac{\hat{\pi}_s \, s(t) + \hat{\pi}_0 \, \mu_0(t)}{\hat{\pi}_s + \hat{\pi}_0} \tag{3}$$

This is the exact conjugate Gaussian posterior mean (Friston, 2010; Rao & Ballard, 1999). When sensory precision $\hat{\pi}_s$ is high, the posterior tracks the observation; when prior precision $\hat{\pi}_0$ is high, the posterior is dominated by the prediction.

**Eq. 4 — Posterior precision:**
`π_post = π_s + π_0`
$$\hat{\pi}_{\text{post}} = \hat{\pi}_s + \hat{\pi}_0 \tag{4}$$

**Eq. 5 — Precision-weighted surprise (scalar summary):**
`w(t) = π_s · ‖ε(t)‖² / (π_s + π_0)`
$$w(t) = \frac{\hat{\pi}_s \, \|\varepsilon(t)\|^2}{\hat{\pi}_s + \hat{\pi}_0} \tag{5}$$

High $w(t)$ indicates a genuinely surprising observation that has shifted the posterior substantially.

**Eq. 6 — Sensory precision adaptation:**
`π_s ← π_s + α_π · (1/(‖ε‖² + 0.01) − π_s)`
$$\hat{\pi}_s \leftarrow \hat{\pi}_s + \alpha_\pi \left(\frac{1}{\|\varepsilon(t)\|^2 + 0.01} - \hat{\pi}_s\right) \tag{6}$$

Persistently small errors increase sensory precision (the world is predictable → trust sensors more). Large errors decrease it.

**Eq. 7 — Cell value for movement actions:**
`V(c) = π_s · R̂(c) − (1−π_s/(π_s+π_0)) · d(c)`
$$V(c) = \hat{\pi}_s \, \hat{R}(c) - \left(1 - \frac{\hat{\pi}_s}{\hat{\pi}_s + \hat{\pi}_0}\right) d(c) \tag{7}$$

where $\hat{R}(c)$ is the believed resource value at cell $c$ (from the posterior belief $\hat{\mu}$), and $d(c)$ is Manhattan distance to cell $c$. The second term penalizes distance, weighted by the agent's relative reliance on prior (uncertainty discourages long moves).

**Eq. 8 — Action probability:**
`P(a) = exp(β · V(a)) / Σ_j exp(β · V(j))`
$$P(a) = \frac{\exp\bigl(\beta \, V(a)\bigr)}{\sum_{j} \exp\bigl(\beta \, V(j)\bigr)} \tag{8}$$

### Decision logic

1. **Perceive**: Receive $s(t)$: position, nearby resource map, ate-last-step flag.
2. **Predict**: Compute prior $\mu_0(t)$ from last posterior via Eq. 1.
3. **Compute error**: $\varepsilon(t) = s(t) - \mu_0(t)$ (Eq. 2).
4. **Update belief**: Compute $\hat{\mu}(t)$ in one algebraic step via Eq. 3.
5. **Evaluate actions**:
   - For `eat`: If food present at current cell (according to $\hat{\mu}$), $V(\text{eat}) = \hat{\pi}_s \cdot r_{\text{food}}$. If no food believed present, $V(\text{eat}) = r_{\text{empty}}$.
   - For each movement action (up/down/left/right): Compute $V(c)$ for the destination cell via Eq. 7.
   - For `stay`: $V(\text{stay}) = 0$ (baseline, no cost, no gain unless food is here — in which case eat is preferred).
6. **Select action**: Sample from softmax (Eq. 8) over all action values.
7. **Return** selected action.

**Update step** (after receiving reward and new perception):
- If ate and received reward: reinforce sensory precision ($\hat{\pi}_s$ increased by $\alpha_\pi$, confirming prediction accuracy).
- If ate and no reward (prediction was wrong): decrease $\hat{\pi}_s$ by $\alpha_\pi$.
- Adapt precision via Eq. 6 using the new prediction error.
- Store $\hat{\mu}(t)$ as the prior basis for the next step.

---

## Formulation 3: Active Inference with Expected Free Energy (Probabilistic Policy Selection)
**Approach**: Full active inference formulation where the agent evaluates candidate action policies by computing expected free energy — decomposed into pragmatic (goal-seeking) and epistemic (uncertainty-reducing) components — and selects policies via softmax. Beliefs are maintained as categorical distributions over discrete world states.
**Based on**: Friston (2010); Friston & Kiebel (2009); Petzschner et al. (2021); derived from postulates P3, P5, P6.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $o(t)$ | Observation | Discrete observation encoding: position, resources visible, ate-flag | Discrete, $\mathcal{O}$ |
| $\mathbf{s}(t)$ | Belief state (categorical) | Probability distribution over discrete hidden states $\{s_1, \ldots, s_K\}$ (grid cells × resource configurations) | Categorical, $\Delta^{K-1}$ |
| $\mathbf{s}_0(t)$ | Prior belief | Predicted state distribution before incorporating current observation | Categorical, $\Delta^{K-1}$ |
| $\varepsilon(t)$ | Prediction error | Discrepancy between observed and predicted observation likelihoods | Continuous, $\mathbb{R}^{|\mathcal{O}|}$ |
| $G(\pi)$ | Expected free energy for policy $\pi$ | Scalar evaluating how good a candidate action sequence is | Continuous, $\mathbb{R}$ |
| $G_{\text{prag}}(\pi)$ | Pragmatic value | Component of $G$ measuring divergence from preferred outcomes | Continuous, $\mathbb{R}^+$ |
| $G_{\text{epist}}(\pi)$ | Epistemic value | Component of $G$ measuring expected information gain | Continuous, $\mathbb{R}^-$ (negative = good) |
| $H(t)$ | Homeostatic need (hunger) | Internal state tracking energy depletion; deviation from setpoint drives pragmatic preferences | Continuous, $[0, 1]$ |
| $\mathbf{C}$ | Preferred outcome distribution | Encodes goals: what observations the agent "wants" (low free energy for food when hungry) | Categorical, $\Delta^{|\mathcal{O}|-1}$ |
| $a(t)$ | Action | First action of the selected policy | Discrete |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\beta_G$ | Policy softmax inverse temperature | 4.0 | Friston (2010), exploration–exploitation tradeoff |
| $\omega$ | Epistemic–pragmatic weighting | 0.5 | Balanced; Friston & Kiebel (2009) |
| $\alpha_H$ | Hunger accumulation rate | 0.05 | Petzschner et al. (2021), interoceptive dynamics |
| $\delta_H$ | Hunger reduction on eating | 0.4 | Petzschner et al. (2021), homeostatic set-point recovery |
| $H^*$ | Homeostatic set-point (hunger target) | 0.0 | Zero hunger is ideal |
| $K$ | Number of discrete hidden states | 25 | 5×5 local belief grid |
| $\tau$ | Policy horizon (time steps) | 1 | Single-step policy for tractability |
| $\alpha_B$ | Belief learning rate (likelihood matrix) | 0.05 | Slow learning; Friston (2010) |

### Equations

**Eq. 1 — Observation likelihood (generative model):**
`P(o | s_k) = A[o, k]`
$$P(o \,|\, s_k) = \mathbf{A}_{o,k} \tag{1}$$

The likelihood matrix $\mathbf{A}$ maps hidden states to expected observations. Initially set from the grid topology: if state $s_k$ has food, the observation "food_here" has high probability.

**Eq. 2 — State transition model:**
`P(s_k' | s_k, a) = B_a[k', k]`
$$P(s_{k'} \,|\, s_k, a) = \mathbf{B}^{(a)}_{k',k} \tag{2}$$

Transition matrices $\mathbf{B}^{(a)}$ are deterministic for movement actions (moving to adjacent cell) and identity for stay/eat.

**Eq. 3 — Bayesian state estimation (belief update):**
`s(t) ∝ A[:, o(t)] ⊙ s_0(t)` (element-wise)
$$\mathbf{s}(t) = \frac{\mathbf{A}_{o(t),:}^\top \odot \mathbf{s}_0(t)}{\sum_k \mathbf{A}_{o(t),k} \, s_{0,k}(t)} \tag{3}$$

Standard Bayesian filtering: posterior is proportional to likelihood times prior.

**Eq. 4 — Prior prediction under policy (one-step):**
`s_0(t+1 | a) = B_a · s(t)`
$$\mathbf{s}_0(t+1 \,|\, a) = \mathbf{B}^{(a)} \, \mathbf{s}(t) \tag{4}$$

**Eq. 5 — Preferred outcome distribution (hunger-modulated):**
`C[o_food] = σ(H(t) / 0.1), C[o_other] = (1 − C[o_food]) / (|O|−1)`
$$C_{o_{\text{food}}} = \sigma\!\left(\frac{H(t)}{0.1}\right), \quad C_{o_{\text{other}}} = \frac{1 - C_{o_{\text{food}}}}{|\mathcal{O}| - 1} \tag{5}$$

where $\sigma$ is the sigmoid function. When hunger $H(t)$ is high, the agent strongly prefers food-related observations (Petzschner et al., 2021).

**Eq. 6 — Expected free energy (pragmatic component):**
`G_prag(a) = D_KL[ Q(o | a) ‖ C ]`
$$G_{\text{prag}}(a) = D_{\text{KL}}\!\bigl[\, Q(o \,|\, a) \;\|\; \mathbf{C} \,\bigr] \tag{6}$$

where $Q(o \,|\, a) = \sum_k \mathbf{A}_{o,k} \, s_{0,k}(t+1 \,|\, a)$ is the predicted observation distribution under action $a$. Low pragmatic $G$ means the predicted outcomes match the agent's preferences (Friston, 2010).

**Eq. 7 — Expected free energy (epistemic component):**
`G_epist(a) = −Σ_k s_0(k|a) · Σ_o A[o,k] · ln(A[o,k] / Q(o|a))`
$$G_{\text{epist}}(a) = -\sum_k s_{0,k}(t+1|a) \sum_o \mathbf{A}_{o,k} \ln \frac{\mathbf{A}_{o,k}}{Q(o|a)} \tag{7}$$

This is the negative expected information gain (mutual information between states and observations). Negative $G_{\text{epist}}$ means the action yields high information gain — the agent prefers to visit informative states (epistemic foraging from Friston, 2010).

**Eq. 8 — Total expected free energy:**
`G(a) = (1−ω) · G_prag(a) + ω · G_epist(a)`
$$G(a) = (1-\omega)\, G_{\text{prag}}(a) + \omega\, G_{\text{epist}}(a) \tag{8}$$

**Eq. 9 — Policy (action) selection:**
`P(a) = exp(−β_G · G(a)) / Σ_j exp(−β_G · G(j))`
$$P(a) = \frac{\exp\bigl(-\beta_G \, G(a)\bigr)}{\sum_j \exp\bigl(-\beta_G \, G(j)\bigr)} \tag{9}$$

Actions with lower expected free energy are more probable.

**Eq. 10 — Hunger dynamics (interoceptive state):**
`H(t+1) = clip(H(t) + α_H − δ_H · ate(t), 0, 1)`
$$H(t+1) = \text{clip}\!\bigl(H(t) + \alpha_H - \delta_H \cdot \mathbb{1}_{\text{ate}}(t),\; 0,\; 1\bigr) \tag{10}$$

Hunger increases each step and is reduced when the agent eats, modelling interoceptive prediction errors (Petzschner et al., 2021).

### Decision logic

1. **Perceive**: Receive observation $o(t)$ encoding position, visible resources, ate-flag.
2. **Update hunger**: Compute $H(t)$ via Eq. 10 based on whether the agent ate last step.
3. **Bayesian belief update**: Compute posterior $\mathbf{s}(t)$ from observation using Eq. 3 with prior $\mathbf{s}_0(t)$.
4. **Set preferences**: Compute preferred outcome distribution $\mathbf{C}$ via Eq. 5, modulated by current hunger $H(t)$.
5. **Evaluate each candidate action** $a \in \{\text{up, down, left, right, stay, eat}\}$:
   - Predict next state distribution: $\mathbf{s}_0(t+1|a)$ via Eq. 4.
   - Predict observation distribution: $Q(o|a) = \mathbf{A} \, \mathbf{s}_0(t+1|a)$.
   - Compute $G_{\text{prag}}(a)$ via Eq. 6.
   - Compute $G_{\text{epist}}(a)$ via Eq. 7.
   - Compute $G(a)$ via Eq. 8.
   - Special case: if action is `eat` and belief assigns < 0.1 probability to food at current position, set $G(\text{eat}) = +100$ (strongly disfavored).
6. **Select action**: Sample from softmax over $-G(a)$ (Eq. 9).
7. **Return** first action of selected policy.

**Update step** (after receiving reward and new perception):
- Update hunger state via Eq. 10.
- Update likelihood matrix $\mathbf{A}$ via Hebbian-like learning: $\mathbf{A}_{o(t), k} \leftarrow \mathbf{A}_{o(t), k} + \alpha_B \, s_k(t) \cdot (1 - \mathbf{A}_{o(t), k})$ for the observed outcome, then renormalize columns. This slowly improves the generative model (Friston, 2010 — learning on slower timescale).
- Propagate $\mathbf{s}(t)$ forward as prior $\mathbf{s}_0(t+1)$ for next step.

---

## Cross-formulation comparison

| Aspect | Formulation 1: Hierarchical PE Minimization (ODE) | Formulation 2: Algebraic Bayesian Filtering | Formulation 3: Active Inference (EFE) |
|--------|--------------------------------------------------|---------------------------------------------|---------------------------------------|
| Framework | Continuous-time ODE (discretized gradient descent) | Closed-form algebraic (conjugate Gaussian) | Probabilistic (categorical Bayesian + expected free energy) |
| Key variables | $\mu^{(1)}, \mu^{(2)}, \Pi^{(l)}, \varepsilon^{(l)}$ | $\hat{\mu}, \hat{\pi}_s, \hat{\pi}_0, \varepsilon$ | $\mathbf{s}(t), G(a), H(t), \mathbf{C}$ |
| Core equation | $d\mu^{(1)}/dt = \kappa(\Pi^{(1)} \partial g^{(1)\top} \varepsilon^{(1)} - \Pi^{(2)} \varepsilon^{(2)})$ | $\hat{\mu} = (\pi_s s + \pi_0 \mu_0)/(\pi_s + \pi_0)$ | $G(a) = (1{-}\omega) D_{\text{KL}}[Q(o|a) \| \mathbf{C}] + \omega \, G_{\text{epist}}(a)$ |
| Decision mechanism | Softmax over negative predicted free energy for each action | Softmax over cell-value function (precision-weighted reward proximity) | Softmax over negative expected free energy (epistemic + pragmatic) |
| Belief representation | Continuous point estimates at 2 hierarchical levels | Single-level continuous point estimate with precision | Categorical distribution over discrete states |
| Hierarchy | Explicit 2-level hierarchy with top-down and bottom-up error flow | Implicit single-level (prior vs. sensory) | Single-level state space but with explicit epistemic/pragmatic decomposition |
| Handles uncertainty | Via precision weighting of error signals | Via precision-weighted averaging (relative weight of prior vs. sensor) | Via entropy of predicted observation distribution and information gain |
| Strengths | Faithful to Rao & Ballard's neural architecture; iterative refinement captures convergence dynamics; explicit hierarchical structure | Computationally cheapest (single analytic step per tick); transparent closed-form solution; easy to interpret precision ratio | Most complete active inference implementation; naturally balances exploration (epistemic) and exploitation (pragmatic); hunger-driven preferences capture interoceptive coding |
| Limitations | Computationally heavier ($N_{\text{iter}}$ iterations per step); generative model Jacobians must be specified; continuous variables need careful discretization | No hierarchy — cannot represent multi-scale abstractions; limited expressiveness for complex generative models | Requires discrete state space (scales poorly without approximation); likelihood matrix $\mathbf{A}$ must be initialized; more parameters to tune |
