# Drift-Diffusion Model — Mathematical Formulations

## Formulation 1: Classical Wiener Process with Per-Action Accumulators
**Approach**: Stochastic differential equation (SDE) — discrete-time Wiener process with parallel accumulators, one per candidate action; first to threshold wins.
**Based on**: Ratcliff (1978); Bogacz et al. (2006); extended to multi-action grid setting following the per-action accumulator approach in knowledge backbone (Run 542c7e41).

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $X_i(t)$ | Evidence accumulator for action $i$ | Running total of accumulated evidence favoring action $i$ at internal time-step $t$ | Continuous, ∈ [0, a] |
| $v_i$ | Drift rate for action $i$ | Mean rate of evidence accumulation for action $i$, computed from perception | Continuous, ∈ (−∞, +∞) |
| $\xi_i(t)$ | Noise sample | Independent Gaussian noise at step $t$ for accumulator $i$ | Continuous, $\sim \mathcal{N}(0, 1)$ |
| $R$ | Chosen action | The action whose accumulator first crosses threshold $a$ | Categorical, ∈ {up, down, left, right, stay, eat} |
| $T_d$ | Decision time | Number of internal integration steps until a boundary crossing | Integer, ≥ 1 |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $a$ | Decision boundary (threshold) | 1.5 | Typical range [0.5, 2.0]; Ratcliff & McKoon (2008) |
| $\sigma$ | Diffusion coefficient (within-trial noise) | 0.1 | Standard scaling convention; Ratcliff (1978) |
| $z_0$ | Starting point (fraction of $a$) | 0.5 · $a$ = 0.75 | Unbiased default; Ratcliff & Rouder (1998) |
| $\Delta t$ | Integration time-step | 0.01 | Discretization of Wiener process; Bogacz et al. (2006) |
| $T_{max}$ | Maximum deliberation steps | 100 | Prevents indefinite accumulation |
| $k_{res}$ | Resource proximity scaling | 2.0 | Derived from postulate P2: stimulus quality → drift rate |
| $k_{eat}$ | Eat action base drift | 1.0 | Sets baseline desirability of eating when resource is present |
| $\gamma$ | Recency weighting for reward history | 0.9 | Standard exponential moving average decay |

### Equations

**Eq. 1 — Drift rate computation:**
`v_i = k_res * proximity_signal(i) + k_eat * is_eat_and_resource_here(i) + reward_bias(i)`
$$v_i = k_{\text{res}} \cdot \text{prox}_i + k_{\text{eat}} \cdot \mathbb{1}[\text{eat} \wedge \text{resource}] + \bar{r}_i \tag{1}$$

where $\text{prox}_i$ is the inverse-distance signal to the nearest resource in the direction of action $i$ (0 if no resource visible), $\mathbb{1}[\text{eat} \wedge \text{resource}]$ is 1 only for the eat action when a resource occupies the agent's cell, and $\bar{r}_i$ is an exponentially-weighted running mean of past rewards received after taking action $i$.

**Eq. 2 — Evidence accumulation (discrete Wiener process):**
`X_i(t+1) = X_i(t) + v_i * Δt + σ * sqrt(Δt) * ξ_i(t)`
$$X_i(t+1) = X_i(t) + v_i \, \Delta t + \sigma \sqrt{\Delta t} \; \xi_i(t), \quad \xi_i(t) \sim \mathcal{N}(0,1) \tag{2}$$

Each accumulator $X_i$ is initialized at $z_0$ and evolves independently. Values are clamped to $[0, a]$ (reflecting lower boundary at 0, absorbing upper boundary at $a$).

**Eq. 3 — Boundary-crossing decision rule:**
`R = argmin_i { t : X_i(t) >= a }`
$$R = \arg\min_i \bigl\{ t : X_i(t) \geq a \bigr\} \tag{3}$$

The first accumulator to reach the upper boundary $a$ determines the chosen action. Ties are broken randomly.

**Eq. 4 — Timeout fallback:**
`if no X_i(t) >= a for t <= T_max: R = argmax_i X_i(T_max)`
$$\text{if } \forall i,\; X_i(t) < a \;\;\forall t \leq T_{\max}: \quad R = \arg\max_i \, X_i(T_{\max}) \tag{4}$$

**Eq. 5 — Reward history update (after action & reward):**
`r_bar_i = γ * r_bar_i + (1 - γ) * reward`
$$\bar{r}_i \leftarrow \gamma \, \bar{r}_i + (1 - \gamma) \, r_{\text{obs}} \tag{5}$$

Only the accumulator for the chosen action $i = R$ is updated; others decay toward zero at rate $(1 - \gamma)$.

### Decision logic

1. **Perceive**: Read grid position $(x, y)$, list of nearby resource positions, and whether a resource is on the current cell.
2. **Compute drift rates**: For each of the 6 candidate actions {up, down, left, right, stay, eat}, compute $v_i$ via **Eq. 1**.
   - For movement actions, $\text{prox}_i$ = $1 / (1 + d_i)$ where $d_i$ is the Manhattan distance to the nearest resource in that direction (0 if none visible).
   - For `eat`, $\text{prox}_{\text{eat}} = 0$; instead the $k_{\text{eat}}$ term activates if a resource is present on the cell.
   - For `stay`, $v_{\text{stay}} = \bar{r}_{\text{stay}}$ (only reward history contributes).
3. **Initialize accumulators**: Set $X_i(0) = z_0$ for all $i$.
4. **Accumulate evidence**: Iterate **Eq. 2** for $t = 0, 1, \ldots, T_{\max}$:
   - At each step, check **Eq. 3**: if any $X_i(t) \geq a$, select that action $R = i$ and stop.
   - Clamp $X_i(t)$ to $[0, a]$ after each step (reflecting lower boundary).
5. **Timeout**: If no accumulator reaches $a$ by $T_{\max}$, select via **Eq. 4**.
6. **Execute action** $R$.
7. **Update**: After receiving reward $r_{\text{obs}}$, update $\bar{r}_R$ via **Eq. 5**.

---

## Formulation 2: Algebraic Closed-Form DDM with Softmax Action Selection
**Approach**: Algebraic — uses the closed-form first-passage time solution (inverse Gaussian) to compute expected accuracy and mean decision time per action, then selects actions via softmax over a composite value function.
**Based on**: Ratcliff & McKoon (2008) closed-form accuracy equations; Bogacz et al. (2006) Eq. 2.8 for choice probability; softmax pattern from knowledge backbone (Run f22fa692).

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $P_i$ | Choice probability for action $i$ | Probability that the DDM accumulator for action $i$ would hit the upper boundary | Continuous, ∈ (0, 1) |
| $\bar{T}_i$ | Expected decision time for action $i$ | Mean first-passage time for the accumulator | Continuous, > 0 |
| $V_i$ | Composite action value | Accuracy-weighted, time-discounted value of action $i$ | Continuous, ∈ ℝ |
| $\pi_i$ | Action selection probability | Softmax probability of choosing action $i$ | Continuous, ∈ (0, 1) |
| $Q_i$ | Learned action utility | Running estimate of future reward from taking action $i$ | Continuous, ∈ ℝ |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $a$ | Boundary separation | 1.5 | Ratcliff & McKoon (2008); typical value for moderate caution |
| $z$ | Starting point (relative, fraction of $a$) | 0.5 | Unbiased; Ratcliff & Rouder (1998) |
| $\sigma$ | Diffusion coefficient | 0.1 | Scaling convention; Ratcliff (1978) |
| $\beta$ | Softmax inverse temperature | 5.0 | Controls exploration-exploitation; knowledge backbone default |
| $\alpha$ | Learning rate for $Q$ update | 0.1 | Standard RL learning rate |
| $k_v$ | Drift rate scaling constant | 1.0 | Maps perceptual signal to drift rate units |
| $\lambda$ | Time cost penalty | 0.1 | Penalizes slow decisions; derived from P3 (speed-accuracy trade-off) |
| $w_P$ | Weight on accuracy component | 1.0 | Relative importance of expected accuracy |
| $w_Q$ | Weight on learned utility | 0.5 | Relative importance of learned reward signal |

### Equations

**Eq. 1 — Drift rate from perception:**
`v_i = k_v * signal_i`
$$v_i = k_v \cdot s_i \tag{1}$$

where $s_i$ is the perceptual signal for action $i$: inverse-distance to nearest resource in the movement direction, or a binary resource-present indicator for `eat`, or 0 for `stay`.

**Eq. 2 — Closed-form choice probability (Bogacz et al., 2006 Eq. 2.8):**
`P_i = 1 / (1 + exp(-2 * v_i * a / σ²))`
$$P_i = \frac{1}{1 + \exp\!\bigl(-2\,v_i\,a \,/\, \sigma^2\bigr)} \tag{2}$$

This is the exact probability that a Wiener process with drift $v_i$, boundaries at 0 and $a$, starting at $z = a/2$, hits the upper boundary $a$ first. When $v_i = 0$, $P_i = 0.5$ (chance).

**Eq. 3 — Expected decision time (Bogacz et al., 2006 Eq. 2.10):**
`T_bar_i = (a / (2 * v_i)) * tanh(v_i * a / σ²)`
$$\bar{T}_i = \frac{a}{2\,v_i} \tanh\!\left(\frac{v_i \, a}{\sigma^2}\right) \tag{3}$$

For $v_i \to 0$, L'Hôpital gives $\bar{T}_i \to a^2 / (2\sigma^2)$. A numerical guard is used: if $|v_i| < \epsilon$, use the limit form.

**Eq. 4 — Composite action value:**
`V_i = w_P * P_i - λ * T_bar_i + w_Q * Q_i`
$$V_i = w_P \, P_i - \lambda \, \bar{T}_i + w_Q \, Q_i \tag{4}$$

This combines DDM-predicted accuracy (higher is better), a time cost (longer deliberation is penalized, implementing the speed-accuracy trade-off per P3), and a learned utility term.

**Eq. 5 — Softmax action selection:**
`π_i = exp(β * V_i) / Σ_j exp(β * V_j)`
$$\pi_i = \frac{\exp(\beta \, V_i)}{\sum_{j} \exp(\beta \, V_j)} \tag{5}$$

**Eq. 6 — Q-value update (temporal difference):**
`Q_i ← Q_i + α * (reward - Q_i)`
$$Q_i \leftarrow Q_i + \alpha \bigl(r_{\text{obs}} - Q_i\bigr) \tag{6}$$

Only the chosen action's $Q$ is updated.

### Decision logic

1. **Perceive**: Read grid position, nearby resources, resource-on-cell flag.
2. **Compute perceptual signals** $s_i$ for each action $i \in \{\text{up, down, left, right, stay, eat}\}$:
   - Movement: $s_i = 1 / (1 + d_i)$ where $d_i$ = Manhattan distance to closest resource in direction $i$ (0 if none).
   - Eat: $s_{\text{eat}} = 1$ if resource on cell, else $s_{\text{eat}} = -0.5$ (evidence against eating).
   - Stay: $s_{\text{stay}} = 0$ (neutral signal).
3. **Compute drift rates** via **Eq. 1**.
4. **Compute accuracy** $P_i$ via **Eq. 2** and **expected time** $\bar{T}_i$ via **Eq. 3** for each action.
5. **Compute composite value** $V_i$ via **Eq. 4**.
6. **Select action** by sampling from the softmax distribution **Eq. 5**.
7. **Execute** the sampled action.
8. **Update**: After observing reward, update $Q_R$ via **Eq. 6**.

---

## Formulation 3: Collapsing-Boundary ODE Accumulators with Lateral Inhibition
**Approach**: System of coupled ordinary differential equations (ODEs) with leak, mutual inhibition between accumulators, and a time-dependent urgency signal that collapses the effective threshold — inspired by neural race models.
**Based on**: Bogacz et al. (2006) unified model framework; Gold & Shadlen (2007) neural ramp-to-threshold; urgency/collapsing boundary extension per postulate P3 and knowledge backbone (Run 542c7e41); lateral inhibition from Usher & McClelland (2001) leaky competing accumulator model.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $x_i(t)$ | Activation of accumulator $i$ at time $t$ | Neural-like firing rate representing evidence for action $i$ | Continuous, ≥ 0 |
| $v_i$ | Input drive (drift) for action $i$ | Perceptual evidence signal | Continuous, ∈ ℝ |
| $\theta(t)$ | Effective decision threshold at time $t$ | Decreases over deliberation steps (urgency) | Continuous, ∈ $(0, a]$ |
| $u(t)$ | Urgency signal | Linearly increasing pressure to decide | Continuous, ≥ 0 |
| $R$ | Chosen action | Action whose accumulator first crosses $\theta(t)$ | Categorical |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $a$ | Initial decision boundary | 1.5 | Ratcliff & McKoon (2008) |
| $\kappa$ | Leak rate (self-decay) | 0.15 | Usher & McClelland (2001); prevents runaway activation |
| $w$ | Lateral inhibition weight | 0.05 | Usher & McClelland (2001); competition between accumulators |
| $\sigma$ | Noise intensity | 0.1 | Standard scaling; Ratcliff (1978) |
| $\Delta t$ | Integration time-step | 0.01 | Discretization step |
| $T_{\max}$ | Maximum deliberation steps | 100 | Prevents indefinite deliberation |
| $\mu$ | Urgency rate (boundary collapse speed) | 0.01 | Controls how fast threshold drops; Bogacz et al. (2006) extension |
| $\theta_{\min}$ | Minimum threshold (floor) | 0.3 | Prevents collapse to zero; knowledge backbone: $0.2 \cdot a$ |
| $k_v$ | Drift scaling constant | 1.5 | Maps perceptual proximity to input drive |
| $\alpha$ | Learning rate for reward traces | 0.1 | Standard RL parameter |

### Equations

**Eq. 1 — Input drive computation:**
`v_i = k_v * signal_i + reward_trace_i`
$$v_i = k_v \cdot s_i + \bar{r}_i \tag{1}$$

where $s_i$ is the perceptual signal (same convention as Formulation 2) and $\bar{r}_i$ is a learned reward trace.

**Eq. 2 — Leaky competing accumulator dynamics (ODE, Euler discretization):**
`x_i(t+1) = x_i(t) + Δt * (v_i - κ * x_i(t) - w * Σ_{j≠i} x_j(t)) + σ * sqrt(Δt) * ξ_i(t)`
$$x_i(t\!+\!1) = x_i(t) + \Delta t \Bigl[\, v_i - \kappa \, x_i(t) - w \!\sum_{j \neq i} x_j(t) \,\Bigr] + \sigma \sqrt{\Delta t}\;\xi_i(t) \tag{2}$$

where $\xi_i(t) \sim \mathcal{N}(0,1)$. Activations are rectified: $x_i(t) = \max(0, x_i(t))$ after each step.

**Eq. 3 — Urgency signal (linear ramp):**
`u(t) = μ * t`
$$u(t) = \mu \, t \tag{3}$$

**Eq. 4 — Collapsing effective boundary:**
`θ(t) = max(a - u(t), θ_min)`
$$\theta(t) = \max\!\bigl(a - u(t),\; \theta_{\min}\bigr) \tag{4}$$

The effective threshold decreases linearly from $a$ toward $\theta_{\min}$, implementing the urgency-gating mechanism described by Gold & Shadlen (2007) and the collapsing-boundary extension noted in the deep report assumptions.

**Eq. 5 — Boundary-crossing decision rule:**
`R = first i such that x_i(t) >= θ(t)`
$$R = \arg\min_i \bigl\{ t : x_i(t) \geq \theta(t) \bigr\} \tag{5}$$

**Eq. 6 — Timeout fallback:**
`if no crossing by T_max: R = argmax_i x_i(T_max)`
$$\text{if } \forall i,\; x_i(t) < \theta(t)\;\;\forall t \leq T_{\max}: \quad R = \arg\max_i \, x_i(T_{\max}) \tag{6}$$

**Eq. 7 — Reward trace update:**
`r_bar_i ← r_bar_i + α * (reward - r_bar_i)`
$$\bar{r}_i \leftarrow \bar{r}_i + \alpha\bigl(r_{\text{obs}} - \bar{r}_i\bigr) \tag{7}$$

### Decision logic

1. **Perceive**: Read grid position $(x,y)$, nearby resources, resource-on-cell flag.
2. **Compute perceptual signals** $s_i$ for each action (same mapping as Formulation 2 Step 2).
3. **Compute input drives** $v_i$ via **Eq. 1**, incorporating learned reward traces.
4. **Initialize accumulators**: $x_i(0) = 0$ for all $i$ (neural resting state; differs from Formulation 1's nonzero starting point).
5. **Iterate ODE** for $t = 0, 1, \ldots, T_{\max}$:
   a. Compute urgency $u(t)$ via **Eq. 3** and effective threshold $\theta(t)$ via **Eq. 4**.
   b. Update each accumulator $x_i$ via **Eq. 2** (leak + lateral inhibition + noise).
   c. Rectify: $x_i(t) \leftarrow \max(0, x_i(t))$.
   d. Check **Eq. 5**: if any $x_i(t) \geq \theta(t)$, select $R = i$ and stop. Break ties randomly.
6. **Timeout**: If no crossing by $T_{\max}$, select via **Eq. 6**.
7. **Execute action** $R$.
8. **Update**: After observing reward $r_{\text{obs}}$, update $\bar{r}_R$ via **Eq. 7**.

---

## Cross-formulation comparison

| Aspect | Formulation 1: Classical Wiener Per-Action | Formulation 2: Algebraic Closed-Form Softmax | Formulation 3: Collapsing-Boundary ODE |
|--------|-------------------------------------------|-----------------------------------------------|----------------------------------------|
| Framework | Stochastic (discrete-time Wiener SDE) | Algebraic (closed-form accuracy + mean RT) | Coupled ODEs with noise (Euler-integrated) |
| Key variables | $X_i(t)$ accumulators, drift $v_i$, boundary $a$ | Choice probability $P_i$, expected time $\bar{T}_i$, composite value $V_i$ | Activations $x_i(t)$, collapsing threshold $\theta(t)$, urgency $u(t)$ |
| Core equation | $X_i(t\!+\!1) = X_i(t) + v_i\Delta t + \sigma\sqrt{\Delta t}\,\xi_i$ (Eq. 2) | $P_i = 1/(1 + \exp(-2v_i a/\sigma^2))$ (Eq. 2) | $x_i(t\!+\!1) = x_i(t) + \Delta t[v_i - \kappa x_i - w\sum_{j\neq i}x_j] + \sigma\sqrt{\Delta t}\,\xi_i$ (Eq. 2) |
| Decision mechanism | First accumulator to hit fixed threshold $a$ wins (race) | Softmax sampling over closed-form DDM values | First accumulator to hit time-decreasing threshold $\theta(t)$ wins |
| Inter-action competition | None — accumulators are independent | Implicit via softmax normalization | Explicit lateral inhibition ($-w \sum_{j \neq i} x_j$) |
| Time pressure modeling | None (fixed boundary); relies on $T_{\max}$ timeout | Time cost $\lambda \bar{T}_i$ penalizes slow actions algebraically | Urgency signal collapses boundary dynamically (Eq. 4) |
| Stochasticity source | Within-trial Gaussian noise in accumulation | Softmax sampling (no within-trial noise simulation) | Within-trial Gaussian noise + rectification |
| Computational cost | Medium — runs up to $T_{\max}$ simulation steps per decision | Low — evaluates 6 closed-form expressions per decision | High — runs coupled ODEs with $N_{\text{actions}}$ interactions per step |
| Strengths | Directly implements the canonical DDM SDE (Ratcliff, 1978); transparent correspondence between model and neural ramp dynamics | Fast computation; combines DDM theory with RL in a tractable way; smooth gradient for learning | Biologically realistic (leak, inhibition, urgency); naturally handles time pressure; winner-take-all competition |
| Limitations | No inter-action competition; fixed boundary may cause slow decisions in ambiguous states | Loses within-trial dynamics (no trial-by-trial noise trajectory); accuracy formula assumes unbiased start | Most complex; many parameters; Euler discretization may require small $\Delta t$ for stability |
