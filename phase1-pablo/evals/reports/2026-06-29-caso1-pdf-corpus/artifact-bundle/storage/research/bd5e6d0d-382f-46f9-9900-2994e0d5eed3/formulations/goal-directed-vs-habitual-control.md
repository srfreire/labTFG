# Goal-Directed vs. Habitual Control — Mathematical Formulations

## Formulation 1: Dual Q-Table with Fixed Exponential-Decay Arbitration
**Approach**: Algebraic dual-system reinforcement learning with separate model-free and model-based Q-tables, mixed by a deterministic training-count-based arbitration weight.
**Based on**: Rangel, Camerer & Montague (2008); Rangel (2013); postulates P1–P5.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $s$ | State | Agent's current grid cell $(x, y)$ | Discrete |
| $a$ | Action | One of {up, down, left, right, stay, eat} | Discrete |
| $o$ | Outcome | Result of action: food obtained, empty move, etc. | Discrete |
| $Q_{MF}(s, a)$ | Model-free Q-value | Cached habitual action value, updated by TD(0) | Continuous |
| $Q_{MB}(s, a)$ | Model-based Q-value | Goal-directed action value, computed prospectively each step | Continuous |
| $Q_{net}(s, a)$ | Net action value | Arbitrated blend of $Q_{MF}$ and $Q_{MB}$ | Continuous |
| $h$ | Hunger drive | Internal physiological state representing current need | Continuous $[0, 1]$ |
| $r^D(o)$ | Decision-time desirability | Current subjective value of outcome $o$, modulated by $h$ | Continuous |
| $\hat{p}(o \mid a, s)$ | Learned transition model | Agent's estimate of action–outcome contingency | Continuous $[0, 1]$ |
| $\delta$ | TD prediction error | Reward prediction error used to update $Q_{MF}$ | Continuous |
| $\omega$ | Arbitration weight | Proportion of goal-directed control in the mixture | Continuous $[0, 1]$ |
| $N(s)$ | Visit count | Number of times the agent has visited state $s$ | Discrete $\geq 0$ |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\alpha_{MF}$ | Model-free learning rate | 0.10 | Standard TD-learning range (Rangel et al., 2008) |
| $\alpha_T$ | Transition model learning rate | 0.20 | Higher than $\alpha_{MF}$ — model-based systems update faster (Rangel, 2013; postulate P2) |
| $\gamma$ | Temporal discount factor | 0.95 | Standard RL discounting |
| $\beta$ | Inverse temperature (softmax) | 5.0 | Moderate exploitation (Rangel et al., 2008) |
| $\lambda$ | Habit formation rate | 0.05 | Controls speed of exponential decay of $\omega$; tuned to match overtraining timeline (postulate P4) |
| $\eta$ | Hunger rise rate | 0.02 | Per-step increase when not eating |
| $\phi$ | Satiation amount | 0.30 | Hunger reduction upon eating |
| $r_{food}$ | Base food reward | 1.0 | Normalized reward unit |
| $c_{step}$ | Step cost | −0.01 | Small penalty to encourage efficiency |

### Equations

**Eq. 1 — Hunger dynamics:**
`h(t+1) = clip(h(t) + η − φ · ate(t), 0, 1)`
$$h_{t+1} = \text{clip}\!\Big(h_t + \eta - \phi \cdot \mathbb{1}[\text{ate}_t],\; 0,\; 1\Big) \tag{1}$$

**Eq. 2 — Decision-time desirability (goal-directed reward):**
`r_D(food) = h · r_food;  r_D(no_food) = c_step`
$$r^D(o) = \begin{cases} h_t \cdot r_{food} & \text{if } o = \text{food} \\ c_{step} & \text{otherwise} \end{cases} \tag{2}$$

**Eq. 3 — Model-based Q-value (prospective computation):**
`Q_MB(s, a) = Σ_o p_hat(o|a,s) · r_D(o)`
$$Q_{MB}(s, a) = \sum_{o \in O} \hat{p}(o \mid a, s) \cdot r^D(o) \tag{3}$$

**Eq. 4 — Transition model update (after observing outcome):**
`p_hat(o|a,s) ← p_hat(o|a,s) + α_T · (I[o_observed] − p_hat(o|a,s))`
$$\hat{p}(o \mid a, s) \leftarrow \hat{p}(o \mid a, s) + \alpha_T \Big(\mathbb{1}[o = o_{obs}] - \hat{p}(o \mid a, s)\Big) \tag{4}$$

**Eq. 5 — TD prediction error:**
`δ = r_received + γ · max_a' Q_MF(s', a') − Q_MF(s, a)`
$$\delta = r_{received} + \gamma \cdot \max_{a'} Q_{MF}(s', a') - Q_{MF}(s, a) \tag{5}$$

**Eq. 6 — Model-free Q-value update:**
`Q_MF(s, a) ← Q_MF(s, a) + α_MF · δ`
$$Q_{MF}(s, a) \leftarrow Q_{MF}(s, a) + \alpha_{MF} \cdot \delta \tag{6}$$

**Eq. 7 — Arbitration weight (training-dependent exponential decay):**
`ω(s) = exp(−λ · N(s))`
$$\omega(s) = \exp\!\big(-\lambda \cdot N(s)\big) \tag{7}$$

**Eq. 8 — Net action value:**
`Q_net(s, a) = ω(s) · Q_MB(s, a) + (1 − ω(s)) · Q_MF(s, a)`
$$Q_{net}(s, a) = \omega(s) \cdot Q_{MB}(s, a) + \big(1 - \omega(s)\big) \cdot Q_{MF}(s, a) \tag{8}$$

**Eq. 9 — Softmax action selection:**
`P(a|s) = exp(β · Q_net(s, a)) / Σ_j exp(β · Q_net(s, j))`
$$P(a \mid s) = \frac{\exp\!\big(\beta \, Q_{net}(s, a)\big)}{\sum_{j \in A} \exp\!\big(\beta \, Q_{net}(s, j)\big)} \tag{9}$$

### Decision logic
1. **Perceive** current state $s = (x, y)$, list of nearby resource positions, and current hunger $h_t$.
2. **Compute** decision-time desirability $r^D(o)$ for each possible outcome using Eq. 2 (hunger-modulated).
3. **Compute** model-based values $Q_{MB}(s, a)$ for all actions $a \in A$ using Eq. 3 and the current transition model $\hat{p}$.
   - For movement actions, $\hat{p}(\text{food} \mid a_{move}, s) = 0$; reward is $c_{step}$ plus discounted future value approximated as $\gamma \cdot \max_{a'} Q_{MF}(s', a')$ for the destination $s'$.
   - For `eat` action: $\hat{p}(\text{food} \mid \text{eat}, s) = 1$ if resource present at $s$, else 0.
4. **Look up** cached model-free values $Q_{MF}(s, a)$ for all actions.
5. **Compute** arbitration weight $\omega(s)$ from visit count $N(s)$ via Eq. 7.
6. **Blend** values: $Q_{net}(s, a)$ via Eq. 8.
7. **Select action** stochastically from softmax distribution $P(a \mid s)$ via Eq. 9.
8. **Execute** the selected action; receive reward $r_{received}$ and observe new state $s'$ and outcome $o_{obs}$.
9. **Update** hunger via Eq. 1.
10. **Update** transition model $\hat{p}$ via Eq. 4.
11. **Update** model-free Q-value via Eqs. 5–6.
12. **Increment** visit count: $N(s) \leftarrow N(s) + 1$.

---

## Formulation 2: Uncertainty-Based Bayesian Arbitration
**Approach**: Probabilistic dual-system RL where each controller maintains Gaussian posterior beliefs over action values; arbitration is driven by relative uncertainty (inverse variance) rather than training count.
**Based on**: Rangel, Camerer & Montague (2008); Rangel (2013); postulates P1–P5; knowledge backbone pattern of sigmoid uncertainty-based arbitration.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $s$ | State | Agent's current grid cell $(x, y)$ | Discrete |
| $a$ | Action | One of {up, down, left, right, stay, eat} | Discrete |
| $\mu_{MF}(s,a)$ | Model-free value mean | Posterior mean of habitual action value | Continuous |
| $\sigma^2_{MF}(s,a)$ | Model-free value variance | Posterior uncertainty of habitual action value | Continuous $> 0$ |
| $\mu_{MB}(s,a)$ | Model-based value mean | Posterior mean of goal-directed action value | Continuous |
| $\sigma^2_{MB}(s,a)$ | Model-based value variance | Posterior uncertainty of goal-directed action value | Continuous $> 0$ |
| $\omega(s,a)$ | Arbitration weight | Reliability-weighted proportion of goal-directed control for action $a$ in state $s$ | Continuous $[0, 1]$ |
| $\hat{\mu}(s,a)$ | Fused value estimate | Precision-weighted mean of the two systems | Continuous |
| $h$ | Hunger drive | Internal physiological state | Continuous $[0, 1]$ |
| $r^D(o)$ | Decision-time desirability | Current value of outcome $o$, modulated by hunger | Continuous |
| $\hat{p}(o \mid a,s)$ | Learned transition model | Agent's action–outcome contingency estimate | Continuous $[0,1]$ |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\sigma^2_0$ | Prior variance (both systems) | 1.0 | Uninformative prior; standard Bayesian initialization |
| $\mu_0$ | Prior mean (both systems) | 0.0 | Neutral prior |
| $\sigma^2_{obs,MF}$ | MF observation noise variance | 0.50 | Reflects noisy experienced-reward signals (Rangel et al., 2008) |
| $\sigma^2_{obs,MB}$ | MB observation noise variance | 0.25 | Lower noise — model-based uses structured knowledge (Rangel, 2013) |
| $\alpha_T$ | Transition model learning rate | 0.20 | Consistent with Formulation 1 |
| $\kappa$ | Arbitration sigmoid sensitivity | 3.0 | Controls steepness of sigmoid; tuned to produce gradual transitions |
| $\beta$ | Inverse temperature (softmax) | 5.0 | Moderate exploitation |
| $\gamma$ | Temporal discount factor | 0.95 | Standard RL discounting |
| $\eta$ | Hunger rise rate | 0.02 | Per-step increase when not eating |
| $\phi$ | Satiation amount | 0.30 | Hunger reduction upon eating |
| $r_{food}$ | Base food reward | 1.0 | Normalized reward unit |
| $c_{step}$ | Step cost | −0.01 | Small penalty to encourage efficiency |

### Equations

**Eq. 1 — Hunger dynamics:**
`h(t+1) = clip(h(t) + η − φ · ate(t), 0, 1)`
$$h_{t+1} = \text{clip}\!\Big(h_t + \eta - \phi \cdot \mathbb{1}[\text{ate}_t],\; 0,\; 1\Big) \tag{1}$$

**Eq. 2 — Decision-time desirability:**
`r_D(food) = h · r_food;  r_D(no_food) = c_step`
$$r^D(o) = \begin{cases} h_t \cdot r_{food} & \text{if } o = \text{food} \\ c_{step} & \text{otherwise} \end{cases} \tag{2}$$

**Eq. 3 — Model-based value computation (prospective):**
`μ_MB(s, a) = Σ_o p_hat(o|a,s) · r_D(o)`
$$\mu_{MB}(s, a) = \sum_{o \in O} \hat{p}(o \mid a, s) \cdot r^D(o) \tag{3}$$

**Eq. 4 — Model-based variance (propagated uncertainty):**
`σ²_MB(s,a) = Σ_o p_hat(o|a,s) · (r_D(o) − μ_MB(s,a))² + σ²_obs,MB / (1 + N_MB(s,a))`
$$\sigma^2_{MB}(s,a) = \sum_{o} \hat{p}(o|a,s)\big(r^D(o) - \mu_{MB}(s,a)\big)^2 + \frac{\sigma^2_{obs,MB}}{1 + N_{MB}(s,a)} \tag{4}$$

**Eq. 5 — Model-free Bayesian update (Kalman-style):**
`K = σ²_MF(s,a) / (σ²_MF(s,a) + σ²_obs,MF)`
`μ_MF(s,a) ← μ_MF(s,a) + K · (r_received + γ · max_a' μ_MF(s',a') − μ_MF(s,a))`
`σ²_MF(s,a) ← (1 − K) · σ²_MF(s,a)`
$$K = \frac{\sigma^2_{MF}(s,a)}{\sigma^2_{MF}(s,a) + \sigma^2_{obs,MF}} \tag{5a}$$
$$\mu_{MF}(s,a) \leftarrow \mu_{MF}(s,a) + K \cdot \Big(r_{recv} + \gamma \max_{a'} \mu_{MF}(s',a') - \mu_{MF}(s,a)\Big) \tag{5b}$$
$$\sigma^2_{MF}(s,a) \leftarrow (1 - K) \cdot \sigma^2_{MF}(s,a) \tag{5c}$$

**Eq. 6 — Transition model update:**
`p_hat(o|a,s) ← p_hat(o|a,s) + α_T · (I[o_observed] − p_hat(o|a,s))`
$$\hat{p}(o \mid a,s) \leftarrow \hat{p}(o \mid a,s) + \alpha_T\Big(\mathbb{1}[o = o_{obs}] - \hat{p}(o \mid a,s)\Big) \tag{6}$$

**Eq. 7 — Uncertainty-based arbitration weight (sigmoid):**
`ω(s,a) = σ(κ · (σ²_MF(s,a) − σ²_MB(s,a)))`
$$\omega(s,a) = \sigma\!\Big(\kappa \cdot \big(\sigma^2_{MF}(s,a) - \sigma^2_{MB}(s,a)\big)\Big) = \frac{1}{1 + \exp\!\big(-\kappa(\sigma^2_{MF}(s,a) - \sigma^2_{MB}(s,a))\big)} \tag{7}$$

**Eq. 8 — Fused action value (precision-weighted combination):**
`μ_hat(s,a) = ω(s,a) · μ_MB(s,a) + (1 − ω(s,a)) · μ_MF(s,a)`
$$\hat{\mu}(s,a) = \omega(s,a) \cdot \mu_{MB}(s,a) + \big(1 - \omega(s,a)\big) \cdot \mu_{MF}(s,a) \tag{8}$$

**Eq. 9 — Softmax action selection:**
`P(a|s) = exp(β · μ_hat(s,a)) / Σ_j exp(β · μ_hat(s,j))`
$$P(a \mid s) = \frac{\exp\!\big(\beta \, \hat{\mu}(s,a)\big)}{\sum_{j \in A} \exp\!\big(\beta \, \hat{\mu}(s,j)\big)} \tag{9}$$

### Decision logic
1. **Perceive** current state $s = (x, y)$, nearby resources, and hunger $h_t$.
2. **Compute** decision-time desirability $r^D(o)$ for each outcome via Eq. 2.
3. **Compute** model-based value mean $\mu_{MB}(s, a)$ and variance $\sigma^2_{MB}(s, a)$ for all actions via Eqs. 3–4.
   - For movement actions: $\mu_{MB}(s, a_{move}) = c_{step} + \gamma \cdot \max_{a'} \mu_{MF}(s', a')$ (bootstrap from MF at next state); variance set to $\sigma^2_{obs,MB} / (1 + N_{MB}(s,a))$.
   - For `eat` at resource: $\mu_{MB}(s, \text{eat}) = \hat{p}(\text{food}|\text{eat},s) \cdot r^D(\text{food})$.
4. **Retrieve** model-free posterior means $\mu_{MF}(s,a)$ and variances $\sigma^2_{MF}(s,a)$.
5. **Compute** per-action arbitration weights $\omega(s, a)$ via Eq. 7.
   - When MF uncertainty $\gg$ MB uncertainty → $\omega \to 1$ (goal-directed dominates; early training, novel states).
   - When MF uncertainty $\ll$ MB uncertainty → $\omega \to 0$ (habit dominates; well-practiced states).
6. **Fuse** values: $\hat{\mu}(s,a)$ via Eq. 8.
7. **Select action** stochastically from softmax $P(a \mid s)$ via Eq. 9.
8. **Execute** action; observe reward $r_{recv}$, new state $s'$, outcome $o_{obs}$.
9. **Update** hunger via Eq. 1.
10. **Update** transition model via Eq. 6; increment $N_{MB}(s,a)$.
11. **Update** model-free posterior via Eqs. 5a–5c.

---

## Formulation 3: ODE-Based Habit Strength with Continuous Arbitration Dynamics
**Approach**: Continuous-time ODE system where habit strength, goal-directed value, and an arbitration resource ("cognitive control capacity") co-evolve; actions are selected by a winner-take-all comparison at each time step.
**Based on**: Rangel, Camerer & Montague (2008); Rangel (2013); postulates P1–P5; knowledge backbone pattern of ODE-based dual-process self-control with executive depletion-recovery dynamics.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $s$ | State | Agent's current grid cell $(x, y)$ | Discrete |
| $a$ | Action | One of {up, down, left, right, stay, eat} | Discrete |
| $H(s, a)$ | Habit strength | Continuously evolving S–R association strength for action $a$ in state $s$ | Continuous $\geq 0$ |
| $V_{GD}(s, a)$ | Goal-directed value | Prospectively computed action value | Continuous |
| $C_t$ | Cognitive control capacity | Depletable resource for maintaining goal-directed override; analogous to prefrontal executive function | Continuous $[0, 1]$ |
| $h$ | Hunger drive | Internal physiological state | Continuous $[0, 1]$ |
| $r^D(o)$ | Decision-time desirability | Current value of outcome $o$, modulated by $h$ | Continuous |
| $\hat{p}(o \mid a,s)$ | Learned transition model | Action–outcome contingency estimate | Continuous $[0, 1]$ |
| $U(s, a)$ | Composite action urgency | Combined signal determining action selection | Continuous |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\tau_H$ | Habit accumulation rate | 0.03 | Slow growth of S–R strength; reflects overtraining timescale (Rangel et al., 2008; postulate P4) |
| $\tau_D$ | Habit decay rate | 0.005 | Slow decay of unused habits |
| $\alpha_T$ | Transition model learning rate | 0.20 | Rapid model update (Rangel, 2013) |
| $C_{max}$ | Max cognitive control capacity | 1.0 | Normalized upper bound |
| $\rho$ | Control recovery rate | 0.05 | Per-step recovery toward $C_{max}$ when habitual action is taken |
| $\xi$ | Control depletion per GD override | 0.10 | Cost of using goal-directed deliberation (Rangel et al., 2008 — computational cost of MB planning) |
| $\theta$ | Override threshold | 0.15 | Minimum $C_t$ required to engage goal-directed system |
| $\gamma$ | Temporal discount factor | 0.95 | Standard RL discounting |
| $\eta$ | Hunger rise rate | 0.02 | Per-step increase when not eating |
| $\phi$ | Satiation amount | 0.30 | Hunger reduction upon eating |
| $r_{food}$ | Base food reward | 1.0 | Normalized reward unit |
| $c_{step}$ | Step cost | −0.01 | Small penalty |
| $\beta$ | Inverse temperature | 5.0 | For softmax within each system's action set |

### Equations

**Eq. 1 — Hunger dynamics:**
`h(t+1) = clip(h(t) + η − φ · ate(t), 0, 1)`
$$h_{t+1} = \text{clip}\!\Big(h_t + \eta - \phi \cdot \mathbb{1}[\text{ate}_t],\; 0,\; 1\Big) \tag{1}$$

**Eq. 2 — Decision-time desirability:**
`r_D(food) = h · r_food;  r_D(no_food) = c_step`
$$r^D(o) = \begin{cases} h_t \cdot r_{food} & \text{if } o = \text{food} \\ c_{step} & \text{otherwise} \end{cases} \tag{2}$$

**Eq. 3 — Goal-directed value (prospective, same as Formulation 1):**
`V_GD(s, a) = Σ_o p_hat(o|a,s) · r_D(o)`
$$V_{GD}(s, a) = \sum_{o \in O} \hat{p}(o \mid a, s) \cdot r^D(o) \tag{3}$$

**Eq. 4 — Habit strength ODE (discrete-time Euler step):**
`H(s,a) ← H(s,a) + τ_H · r_received_positive · I[a was executed in s] − τ_D · H(s,a)`
$$H(s, a) \leftarrow H(s, a) + \tau_H \cdot [r_{recv}]^{+} \cdot \mathbb{1}[a_t = a, s_t = s] - \tau_D \cdot H(s, a) \tag{4}$$

where $[x]^+ = \max(0, x)$ ensures habits only accumulate from positive reinforcement.

**Eq. 5 — Cognitive control capacity dynamics:**
`C(t+1) = clip(C(t) + ρ · (C_max − C(t)) − ξ · I[GD_used], 0, C_max)`
$$C_{t+1} = \text{clip}\!\Big(C_t + \rho\,(C_{max} - C_t) - \xi \cdot \mathbb{1}[\text{GD used}],\; 0,\; C_{max}\Big) \tag{5}$$

**Eq. 6 — System selection criterion:**
`If C(t) ≥ θ: use goal-directed system with probability p_GD`
`p_GD = C(t)  (linear scaling)`
`Else: forced habitual control (p_GD = 0)`
$$p_{GD} = \begin{cases} C_t & \text{if } C_t \geq \theta \\ 0 & \text{if } C_t < \theta \end{cases} \tag{6}$$

**Eq. 7 — Composite action urgency (stochastic system selection):**
`With prob p_GD: U(s,a) = V_GD(s,a)`
`With prob 1−p_GD: U(s,a) = H(s,a)`
$$U(s,a) = \begin{cases} V_{GD}(s,a) & \text{w.p. } p_{GD} \\ H(s,a) & \text{w.p. } 1 - p_{GD} \end{cases} \tag{7}$$

**Eq. 8 — Softmax action selection over urgency:**
`P(a|s) = exp(β · U(s,a)) / Σ_j exp(β · U(s,j))`
$$P(a \mid s) = \frac{\exp\!\big(\beta \, U(s,a)\big)}{\sum_{j \in A} \exp\!\big(\beta \, U(s,j)\big)} \tag{8}$$

**Eq. 9 — Transition model update:**
`p_hat(o|a,s) ← p_hat(o|a,s) + α_T · (I[o_observed] − p_hat(o|a,s))`
$$\hat{p}(o \mid a, s) \leftarrow \hat{p}(o \mid a, s) + \alpha_T\Big(\mathbb{1}[o = o_{obs}] - \hat{p}(o \mid a, s)\Big) \tag{9}$$

### Decision logic
1. **Perceive** current state $s = (x, y)$, nearby resources, hunger $h_t$, and current cognitive control capacity $C_t$.
2. **Compute** desirability $r^D(o)$ via Eq. 2.
3. **Evaluate cognitive control**: check whether $C_t \geq \theta$ (Eq. 6).
4. **System selection** (stochastic):
   - Draw a uniform random number $u \sim \text{Uniform}(0, 1)$.
   - If $C_t \geq \theta$ **and** $u < p_{GD} = C_t$: **goal-directed mode** is active.
     - Compute $V_{GD}(s, a)$ for all actions via Eq. 3. Set $U(s, a) = V_{GD}(s, a)$.
   - Else: **habitual mode** is active.
     - Retrieve habit strengths $H(s, a)$ for all actions. Set $U(s, a) = H(s, a)$.
5. **Select action** stochastically via softmax over $U(s, a)$ (Eq. 8).
6. **Execute** action; observe reward $r_{recv}$, new state $s'$, outcome $o_{obs}$.
7. **Update** hunger via Eq. 1.
8. **Update** habit strengths $H(s, a)$ for the executed action via Eq. 4. All habits decay slightly via the $-\tau_D \cdot H$ term.
9. **Update** transition model via Eq. 9.
10. **Update** cognitive control capacity via Eq. 5:
    - If goal-directed mode was used: $C_t$ is depleted by $\xi$.
    - Otherwise: $C_t$ recovers toward $C_{max}$ at rate $\rho$.
11. **Key behavioral property**: After many steps, habit strengths $H(s, a)$ for frequently rewarded actions become large and stable. Simultaneously, repeated goal-directed deliberation depletes $C_t$, causing the agent to fall back on habits. This produces the overtraining → habit shift (postulate P4). If an outcome is devalued (hunger drops), $V_{GD}$ immediately reflects this (postulate P2), but $H$ does not change until the action is re-experienced with a negative or zero reward (postulate P3).

---

## Cross-formulation comparison

| Aspect | Formulation 1: Dual Q-Table with Fixed Exponential-Decay Arbitration | Formulation 2: Uncertainty-Based Bayesian Arbitration | Formulation 3: ODE-Based Habit Strength with Cognitive Control Depletion |
|--------|----------------------------------------------------------------------|-------------------------------------------------------|--------------------------------------------------------------------------|
| **Framework** | Algebraic (dual Q-tables + deterministic mixing) | Probabilistic (Gaussian posteriors + precision-weighted fusion) | ODE / dynamical systems (continuous habit growth + resource depletion) |
| **Key variables** | $Q_{MF}$, $Q_{MB}$, $\omega$ (visit-count-based) | $\mu_{MF}$, $\sigma^2_{MF}$, $\sigma^2_{MB}$, $\omega$ (uncertainty-based) | $H$ (habit strength), $V_{GD}$, $C_t$ (cognitive control capacity) |
| **Core equation** | Eq. 7: $\omega(s) = \exp(-\lambda N(s))$ — exponential decay arbitration | Eq. 7: $\omega = \sigma(\kappa(\sigma^2_{MF} - \sigma^2_{MB}))$ — sigmoid uncertainty arbitration | Eq. 5: $C_{t+1} = C_t + \rho(C_{max}-C_t) - \xi \cdot\mathbb{1}[\text{GD}]$ — control capacity dynamics |
| **Decision mechanism** | Softmax over linear blend $\omega Q_{MB} + (1-\omega)Q_{MF}$ | Softmax over precision-weighted fused mean $\hat{\mu}$ | Stochastic system selection (GD vs habit) gated by cognitive control $C_t$, then softmax within selected system |
| **Arbitration driver** | Visit count $N(s)$ — purely experience-based, deterministic shift | Relative posterior variance — adaptive, can reverse if environment changes | Depletable cognitive resource $C_t$ — reflects fatigue / effort cost of deliberation |
| **Devaluation sensitivity** | Graded: $Q_{MB}$ updates immediately via $r^D$; blended output shifts proportionally to $\omega$ | Graded and adaptive: MB values update immediately; arbitration can shift toward MB if MF uncertainty increases after devaluation | Binary-stochastic: when GD is selected (probabilistic), devaluation is respected; when habit is selected, it is ignored |
| **Strengths** | Simple to implement; transparent training-count-dependent habit shift; directly implements postulate P4 | Principled Bayesian arbitration; naturally handles non-stationary environments; arbitration is reversible | Captures cognitive fatigue / ego-depletion effects; habit and deliberation are qualitatively different (not just blended); biologically motivated by PFC resource constraints |
| **Limitations** | Arbitration is rigid — cannot re-engage GD in familiar but changed environments; no uncertainty representation | More complex; requires tuning of noise parameters; variance may collapse too quickly in simple grids | Stochastic system switching introduces high variance in behavior; harder to tune threshold $\theta$ and depletion rate $\xi$; less smooth value integration |
