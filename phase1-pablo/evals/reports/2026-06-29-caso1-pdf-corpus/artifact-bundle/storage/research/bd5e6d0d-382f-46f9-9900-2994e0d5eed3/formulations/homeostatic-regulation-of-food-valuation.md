# Homeostatic Regulation of Food Valuation — Mathematical Formulations

## Formulation 1: Drive-Reduction ODE with Goal-Directed Valuation
**Approach**: Continuous-time homeostatic ODE system (discretized) coupling energy stores, hunger drive, and multi-attribute food valuation with deterministic threshold-based action selection.
**Based on**: Jacquier (2016) energy-balance ODEs; Rangel (2013) multi-attribute value computation (Postulates P1, P3, P6)

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $E_t$ | Energy store | Normalized internal energy reserve (proxy for fat mass) | Continuous, [0, 1] |
| $H_t$ | Hunger drive | Motivational drive state derived from energy deficit | Continuous, [0, 1] |
| $V_t(a)$ | Action value | Subjective value of action $a$ at time $t$ | Continuous, ℝ |
| $w_{c,t}$ | Caloric weight | Attribute weight for caloric/nutritional value | Continuous, [0, 1] |
| $w_{e,t}$ | Effort weight | Attribute weight penalizing movement cost | Continuous, [0, 1] |
| $d_t$ | Resource distance | Manhattan distance to nearest visible food resource | Discrete, ℕ₀ |
| $\text{ate}_t$ | Ate flag | Binary indicator: 1 if agent consumed food at time $t$ | Binary, {0, 1} |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\alpha_E$ | Basal metabolic cost | 0.01 per step | Jacquier (2016), adapted to grid timescale |
| $c_{\text{food}}$ | Energy gain from eating | 0.30 | Normalized; represents a substantial meal |
| $E_{\text{set}}$ | Energy set-point | 0.50 | Jacquier (2016) homeostatic set-point concept |
| $k_H$ | Hunger sensitivity | 4.0 | Tuned so that sigmoid spans [0,1] across deficit range |
| $\eta$ | Drive decay rate | 0.05 | Controls speed of hunger ODE relaxation |
| $r_{\text{food}}$ | Base food reward | 1.0 | Rangel (2013) normalized value scale |
| $c_{\text{step}}$ | Step cost | −0.05 | Small penalty for movement to encourage efficiency |
| $\theta$ | Eat threshold | 0.3 | Minimum hunger to initiate eating (Rangel, 2013: meal-initiation threshold) |

### Equations

**Eq. 1 — Energy dynamics:**
`E_{t+1} = clamp(E_t − α_E + c_food · ate_t, 0, 1)`
$$E_{t+1} = \text{clamp}\!\Big(E_t - \alpha_E + c_{\text{food}} \cdot \text{ate}_t,\; 0,\; 1\Big) \tag{1}$$

**Eq. 2 — Hunger drive (sigmoid of deficit):**
`H_t = σ(k_H · (E_set − E_t))`
$$H_t = \sigma\!\Big(k_H \cdot (E_{\text{set}} - E_t)\Big) = \frac{1}{1 + \exp\!\big(-k_H \,(E_{\text{set}} - E_t)\big)} \tag{2}$$

**Eq. 3 — State-dependent attribute weights:**
`w_c,t = H_t;  w_e,t = 1 − H_t`
$$w_{c,t} = H_t, \qquad w_{e,t} = 1 - H_t \tag{3}$$

**Eq. 4 — Food value (eat action):**
`V_eat(t) = w_c,t · r_food · H_t`
$$V_{\text{eat}}(t) = w_{c,t} \cdot r_{\text{food}} \cdot H_t \tag{4}$$

**Eq. 5 — Move-toward-food value:**
`V_move(a, t) = w_c,t · r_food · H_t / (1 + d_t(a)) + c_step · w_e,t`
$$V_{\text{move}}(a, t) = \frac{w_{c,t} \cdot r_{\text{food}} \cdot H_t}{1 + d_t(a)} + c_{\text{step}} \cdot w_{e,t} \tag{5}$$

**Eq. 6 — Stay value:**
`V_stay(t) = 0`
$$V_{\text{stay}}(t) = 0 \tag{6}$$

### Decision logic
1. Compute $E_t$ and $H_t$ from Eqs. (1)–(2).
2. Compute attribute weights from Eq. (3).
3. **If** food is at current cell **and** $H_t \geq \theta$: compute $V_{\text{eat}}$ via Eq. (4). Also compute $V_{\text{move}}(a)$ for all moves and $V_{\text{stay}}$ via Eqs. (5)–(6).
4. **Else if** food is at current cell **and** $H_t < \theta$: set $V_{\text{eat}} = 0$ (below meal-initiation threshold). Compute move/stay values.
5. **If** no food at current cell: $V_{\text{eat}}$ is unavailable. Compute $V_{\text{move}}(a)$ for all movement actions using Eq. (5) where $d_t(a)$ is the post-move distance to nearest food, and $V_{\text{stay}}$ via Eq. (6).
6. **Select** $a^* = \arg\max_a V(a, t)$ (greedy/goal-directed selection). Ties broken randomly.
7. After action execution, observe $\text{ate}_t$ and update $E_{t+1}$ via Eq. (1).

---

## Formulation 2: Hormonal Modulation with Softmax Reinforcement Learning
**Approach**: Model-free RL with Q-learning, where ghrelin and leptin proxies multiplicatively modulate Q-values before softmax action selection.
**Based on**: Rangel (2013) hormonal modulation of decision circuitry (Postulates P2, P4); Jacquier (2016) ghrelin/leptin dynamics; Berridge wanting/liking distinction referenced in Rangel (2013)

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $E_t$ | Energy store | Normalized internal energy reserve | Continuous, [0, 1] |
| $G_t$ | Ghrelin proxy | Short-term hunger/orexigenic signal (rises with fasting, falls after eating) | Continuous, [0, 1] |
| $L_t$ | Leptin proxy | Long-term anorexigenic signal (proportional to energy stores) | Continuous, [0, 1] |
| $M_t$ | Hormonal modulator | Composite gain factor applied to food-related Q-values | Continuous, ℝ⁺ |
| $Q(s, a)$ | Action-value function | Learned expected discounted reward for state-action pair | Continuous, ℝ |
| $\delta_t$ | Reward prediction error | TD-error signal driving Q-value updates | Continuous, ℝ |
| $R_t$ | Reward signal | Immediate reward received after action | Continuous, ℝ |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\alpha_E$ | Basal metabolic cost | 0.01 | Jacquier (2016) adapted |
| $c_{\text{food}}$ | Energy gain from eating | 0.30 | Normalized |
| $\lambda_G$ | Ghrelin rise rate | 0.03 per step | Jacquier (2016): ghrelin rises pre-prandially |
| $\kappa_G$ | Ghrelin suppression on eating | 0.50 | Jacquier (2016): rapid post-prandial ghrelin suppression |
| $k_L$ | Leptin coupling to energy | 1.0 | Jacquier (2016): leptin ∝ fat mass |
| $w_G$ | Ghrelin weight in modulator | 2.0 | Rangel (2013): ghrelin amplifies food value |
| $w_L$ | Leptin weight in modulator | 2.0 | Rangel (2013): leptin suppresses food value |
| $\alpha$ | Learning rate | 0.10 | Standard RL (Sutton & Barto convention) |
| $\gamma$ | Discount factor | 0.90 | Standard RL |
| $\beta$ | Inverse temperature (softmax) | 5.0 | Moderate exploration–exploitation balance |
| $r_{\text{food}}$ | Base reward for eating | 1.0 | Normalized |
| $c_{\text{step}}$ | Step cost | −0.02 | Small movement penalty |

### Equations

**Eq. 1 — Energy dynamics:**
`E_{t+1} = clamp(E_t − α_E + c_food · ate_t, 0, 1)`
$$E_{t+1} = \text{clamp}\!\Big(E_t - \alpha_E + c_{\text{food}} \cdot \text{ate}_t,\; 0,\; 1\Big) \tag{1}$$

**Eq. 2 — Ghrelin dynamics:**
`G_{t+1} = clamp(G_t + λ_G − κ_G · ate_t, 0, 1)`
$$G_{t+1} = \text{clamp}\!\Big(G_t + \lambda_G - \kappa_G \cdot \text{ate}_t,\; 0,\; 1\Big) \tag{2}$$

**Eq. 3 — Leptin proxy:**
`L_t = E_t^{k_L}`
$$L_t = E_t^{\,k_L} \tag{3}$$

**Eq. 4 — Hormonal modulator:**
`M_t = (1 + w_G · G_t) / (1 + w_L · L_t)`
$$M_t = \frac{1 + w_G \cdot G_t}{1 + w_L \cdot L_t} \tag{4}$$

**Eq. 5 — State-dependent reward:**
`R_t = H_t · r_food  if ate_t = 1,  else c_step`
$$R_t = \begin{cases} M_t \cdot r_{\text{food}} & \text{if } \text{ate}_t = 1 \\ c_{\text{step}} & \text{otherwise} \end{cases} \tag{5}$$

**Eq. 6 — TD update (Q-learning):**
`Q(s_t, a_t) ← Q(s_t, a_t) + α · δ_t`
`δ_t = R_t + γ · max_a' Q(s_{t+1}, a') − Q(s_t, a_t)`
$$\delta_t = R_t + \gamma \max_{a'} Q(s_{t+1}, a') - Q(s_t, a_t) \tag{6a}$$
$$Q(s_t, a_t) \leftarrow Q(s_t, a_t) + \alpha \, \delta_t \tag{6b}$$

**Eq. 7 — Modulated action selection (softmax):**
`P(a|s_t) = exp(β · M_t · Q(s_t, a)) / Σ_j exp(β · M_t · Q(s_t, j))  for food-related a`
$$P(a \mid s_t) = \frac{\exp\!\Big(\beta \cdot \tilde{Q}(s_t, a)\Big)}{\sum_{j} \exp\!\Big(\beta \cdot \tilde{Q}(s_t, j)\Big)} \tag{7}$$

where $\tilde{Q}(s_t, a) = M_t \cdot Q(s_t, a)$ if $a$ is a food-related action (eat or move-toward-food), and $\tilde{Q}(s_t, a) = Q(s_t, a)$ for non-food actions (stay).

### Decision logic
1. Update energy $E_{t+1}$, ghrelin $G_{t+1}$, and leptin $L_t$ via Eqs. (1)–(3).
2. Compute hormonal modulator $M_t$ via Eq. (4).
3. For each available action $a$ in the current state $s_t$, compute modulated Q-value $\tilde{Q}(s_t, a)$ per Eq. (7).
4. Sample action $a_t \sim P(a \mid s_t)$ using softmax (Eq. 7). This implements stochastic exploration modulated by internal hormonal state.
5. Execute $a_t$, observe reward $R_t$ (Eq. 5) and next state $s_{t+1}$.
6. Compute TD-error $\delta_t$ and update $Q(s_t, a_t)$ via Eq. (6).
7. **Key behavioral property**: When ghrelin is high and leptin is low ($M_t \gg 1$), food-seeking Q-values are amplified → agent strongly prefers eating. When satiated ($M_t \approx 1$ or $M_t < 1$), food Q-values are suppressed → agent explores or rests.

---

## Formulation 3: Dual-Controller Competition with Pavlovian Override
**Approach**: Two competing controllers (goal-directed and habitual) with arbitration, plus a Pavlovian cue-driven override for proximal food, producing a mixture policy. No gradient-based learning in the goal-directed system; habitual system learns via cached Q-values.
**Based on**: Rangel (2013) three-controller architecture (Postulate P5); devaluation insensitivity of habitual system; Pavlovian override (Postulate P5, P6); Rangel (2008) framework for value-based decision making

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $E_t$ | Energy store | Normalized internal energy reserve | Continuous, [0, 1] |
| $H_t$ | Hunger drive | Motivational state, $\in [0, 1]$ | Continuous, [0, 1] |
| $V^{GD}_t(a)$ | Goal-directed value | Model-based value computed from current hunger and expected outcomes | Continuous, ℝ |
| $Q^{H}(s, a)$ | Habitual Q-value | Cached stimulus–response value, updated slowly via RPE | Continuous, ℝ |
| $\pi^{P}_t(a)$ | Pavlovian response | Fixed innate tendency to approach/consume proximal food | Probability, [0, 1] |
| $\omega_t$ | Arbitration weight | Relative weight of goal-directed vs. habitual controller | Continuous, [0, 1] |
| $n_{\text{eat}}$ | Eating experience count | Cumulative number of eat actions taken (proxy for training) | Discrete, ℕ₀ |
| $\delta_t$ | Prediction error | RPE for habitual system update | Continuous, ℝ |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\alpha_E$ | Basal metabolic cost | 0.01 | Jacquier (2016) adapted |
| $c_{\text{food}}$ | Energy gain from eating | 0.30 | Normalized |
| $\eta_H$ | Hunger rise rate | 0.02 per step | Adapted from Jacquier (2016) |
| $\kappa_H$ | Hunger reduction on eating | 0.40 | Post-prandial satiation |
| $\alpha_Q$ | Habitual learning rate | 0.05 | Slower than goal-directed; reflects stimulus–response caching |
| $\gamma$ | Discount factor | 0.90 | Standard RL |
| $\beta$ | Inverse temperature | 5.0 | Softmax sharpness |
| $\lambda_{\omega}$ | Habitization rate | 0.002 | Rate at which habitual controller gains weight with experience |
| $\omega_0$ | Initial goal-directed weight | 0.80 | Rangel (2013): novel actions are goal-directed dominant |
| $p_{\text{Pav}}$ | Pavlovian override strength | 0.20 | Rangel (2013): Pavlovian contribution, moderate |
| $r_{\text{food}}$ | Base food reward | 1.0 | Normalized |
| $c_{\text{step}}$ | Step cost | −0.02 | Movement penalty |
| $E_{\text{set}}$ | Energy set-point | 0.50 | Homeostatic reference |
| $k_H$ | Hunger sensitivity | 4.0 | Sigmoid steepness |

### Equations

**Eq. 1 — Energy dynamics:**
`E_{t+1} = clamp(E_t − α_E + c_food · ate_t, 0, 1)`
$$E_{t+1} = \text{clamp}\!\Big(E_t - \alpha_E + c_{\text{food}} \cdot \text{ate}_t,\; 0,\; 1\Big) \tag{1}$$

**Eq. 2 — Hunger dynamics:**
`H_{t+1} = clamp(H_t + η_H − κ_H · ate_t, 0, 1)`
$$H_{t+1} = \text{clamp}\!\Big(H_t + \eta_H - \kappa_H \cdot \text{ate}_t,\; 0,\; 1\Big) \tag{2}$$

**Eq. 3 — Goal-directed value (model-based, state-sensitive):**
`V_GD(eat, t) = H_t · r_food`
`V_GD(move_a, t) = H_t · r_food / (1 + d_t(a)) + c_step`
`V_GD(stay, t) = 0`
$$V^{GD}_t(\text{eat}) = H_t \cdot r_{\text{food}} \tag{3a}$$
$$V^{GD}_t(\text{move}_a) = \frac{H_t \cdot r_{\text{food}}}{1 + d_t(a)} + c_{\text{step}} \tag{3b}$$
$$V^{GD}_t(\text{stay}) = 0 \tag{3c}$$

**Eq. 4 — Habitual Q-value update (TD-learning, devaluation-insensitive):**
`R_t^H = r_food if ate_t else c_step`    *(Note: reward is NOT modulated by hunger)*
`δ_t = R_t^H + γ · max_a' Q^H(s_{t+1}, a') − Q^H(s_t, a_t)`
`Q^H(s_t, a_t) ← Q^H(s_t, a_t) + α_Q · δ_t`
$$R^H_t = \begin{cases} r_{\text{food}} & \text{if } \text{ate}_t = 1 \\ c_{\text{step}} & \text{otherwise} \end{cases} \tag{4a}$$
$$\delta_t = R^H_t + \gamma \max_{a'} Q^H(s_{t+1}, a') - Q^H(s_t, a_t) \tag{4b}$$
$$Q^H(s_t, a_t) \leftarrow Q^H(s_t, a_t) + \alpha_Q \, \delta_t \tag{4c}$$

**Eq. 5 — Controller arbitration:**
`ω_t = max(1 − ω_0 − λ_ω · n_eat, 0)  (goal-directed weight decays with experience)`
$$\omega_t = \max\!\Big(\omega_0 - \lambda_\omega \cdot n_{\text{eat}},\; 0\Big) \tag{5}$$

**Eq. 6 — Integrated value (before Pavlovian override):**
`V_int(a, t) = ω_t · V_GD(a, t) + (1 − ω_t) · Q^H(s_t, a)`
$$V^{\text{int}}_t(a) = \omega_t \cdot V^{GD}_t(a) + (1 - \omega_t) \cdot Q^H(s_t, a) \tag{6}$$

**Eq. 7 — Softmax base policy:**
`P_base(a|s_t) = exp(β · V_int(a, t)) / Σ_j exp(β · V_int(j, t))`
$$P_{\text{base}}(a \mid s_t) = \frac{\exp\!\big(\beta \cdot V^{\text{int}}_t(a)\big)}{\sum_j \exp\!\big(\beta \cdot V^{\text{int}}_t(j)\big)} \tag{7}$$

**Eq. 8 — Pavlovian override (mixture policy):**
`π_Pav(eat) = p_Pav if food_at_cell else 0`
`P_final(a|s_t) = (1 − π_Pav(eat)) · P_base(a|s_t) + π_Pav(eat) · 𝟙[a = eat]`
$$P_{\text{final}}(a \mid s_t) = \big(1 - \pi^P_t(\text{eat})\big) \cdot P_{\text{base}}(a \mid s_t) + \pi^P_t(\text{eat}) \cdot \mathbb{1}[a = \text{eat}] \tag{8}$$

where $\pi^P_t(\text{eat}) = p_{\text{Pav}}$ if food is present at the agent's cell, and $0$ otherwise.

### Decision logic
1. Update $E_{t+1}$ via Eq. (1) and $H_{t+1}$ via Eq. (2).
2. Compute goal-directed values $V^{GD}_t(a)$ for all actions via Eq. (3). These are **sensitive to current hunger** — a satiated agent ($H_t \approx 0$) assigns near-zero value to eating.
3. Retrieve habitual Q-values $Q^H(s_t, a)$ for all actions (these are **not** hunger-modulated — Eq. 4a uses unmodulated reward).
4. Compute arbitration weight $\omega_t$ via Eq. (5). Early in training, $\omega_t$ is high (goal-directed dominates). After many eating experiences, $\omega_t$ decreases (habitual dominates).
5. Compute integrated values $V^{\text{int}}_t(a)$ via Eq. (6) and base policy via Eq. (7).
6. **If** food is at the agent's current cell, apply Pavlovian override via Eq. (8): with probability $p_{\text{Pav}}$, the agent eats regardless of computed values, capturing cue-driven consummatory behavior.
7. Sample action $a_t \sim P_{\text{final}}(a \mid s_t)$.
8. Execute action, observe outcome, update $Q^H$ via Eq. (4), and increment $n_{\text{eat}}$ if ate.
9. **Key emergent behaviors**:
   - **Early** (high $\omega_t$): agent eats when hungry, ignores food when satiated (devaluation-sensitive).
   - **Late** (low $\omega_t$): agent eats whenever near food regardless of hunger (habitual overeating).
   - **Always**: Pavlovian override causes occasional eating even when satiated and in goal-directed mode.

---

## Cross-formulation comparison

| Aspect | Formulation 1: Drive-Reduction ODE | Formulation 2: Hormonal Modulation RL | Formulation 3: Dual-Controller Competition |
|--------|-----------------------------------|--------------------------------------|-------------------------------------------|
| Framework | Algebraic / ODE (no learning) | Model-free Q-learning with hormonal gain modulation | Hybrid: model-based goal-directed + model-free habitual + Pavlovian |
| Key variables | $E_t$, $H_t$, $w_{c,t}$ | $G_t$ (ghrelin), $L_t$ (leptin), $M_t$ (modulator) | $\omega_t$ (arbitration), $Q^H$, $V^{GD}_t$ |
| Core equation | $H_t = \sigma(k_H(E_{\text{set}} - E_t))$ — sigmoid hunger drive | $M_t = \frac{1 + w_G G_t}{1 + w_L L_t}$ — hormonal modulator | $V^{\text{int}}_t = \omega_t V^{GD}_t + (1-\omega_t) Q^H$ — controller mixture |
| Decision mechanism | Deterministic argmax over analytically computed values | Stochastic softmax over hormonally modulated Q-values | Stochastic softmax over arbitrated controller outputs + Pavlovian override |
| Strengths | Simple, interpretable, no learning needed; clean hunger-driven attribute reweighting captures P6 | Explicit ghrelin/leptin dynamics capture P2, P4; learns from experience; bidirectional hormonal modulation | Captures controller competition (P5), devaluation insensitivity, Pavlovian override; richest behavioral repertoire |
| Limitations | No learning or adaptation; deterministic policy limits exploration; no habitual/Pavlovian effects | Single controller — no habitual vs. goal-directed distinction; hormones are proxies not mechanistic | Most complex; many parameters; arbitration schedule is heuristic (linear decay) rather than uncertainty-based |
