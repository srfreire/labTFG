# Attribute-Based Value Computation — Mathematical Formulations

## Formulation 1: Weighted Linear Summation with State-Dependent Attribute Weights (Algebraic)
**Approach**: Static algebraic multi-attribute utility model where overall option value is a weighted linear sum of attribute values, with weights modulated by internal physiological state and attentional allocation.
**Based on**: Rangel (2013); Rangel, Camerer & Montague (2008); derived from postulates P1, P3, P5.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $V(o)$ | Overall value of option $o$ | Scalar subjective value used for action selection | Continuous, real |
| $a_i(o)$ | Attribute value | Subjective evaluation of option $o$ on attribute dimension $i$ | Continuous, $[-1, 1]$ |
| $w_i$ | Effective attribute weight | Relative importance of attribute $i$ in value integration | Continuous, $[0, 1]$ |
| $H_t$ | Hunger state | Internal physiological drive (0 = sated, 1 = maximally hungry) | Continuous, $[0, 1]$ |
| $\alpha_i$ | Attentional allocation | Fraction of cognitive resources directed at attribute $i$ | Continuous, $[0, 1]$; $\sum_i \alpha_i = 1$ |
| $V(a)$ | Action value | Value of taking action $a$ given perceived options | Continuous, real |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\beta$ | Softmax inverse temperature | 5.0 | Prior pipeline calibrations; typical range 1–10 |
| $\gamma_H$ | Hunger influence on immediate-attribute weight | 0.6 | Derived from Rangel (2013): hunger amplifies taste/hedonic weight |
| $\delta$ | Temporal discount for delayed attributes | 0.7 | Rangel (2013): abstract attributes are down-weighted under low control |
| $\eta$ | Hunger decay rate per timestep | 0.01 | Simulation convention (slow metabolic timescale) |
| $R_{\text{food}}$ | Hunger restoration from eating | 0.3 | Simulation convention |
| $N$ | Number of attributes | 2 | Rangel (2013): taste and health as canonical pair |

### Equations

**Eq. 1 — Attribute weights from state and attention:**
`w_imm = α_imm · (1 + γ_H · H_t) / Z`
`w_abs = α_abs · δ / Z`
`Z = α_imm · (1 + γ_H · H_t) + α_abs · δ`
$$w_{\text{imm}} = \frac{\alpha_{\text{imm}} \cdot (1 + \gamma_H \cdot H_t)}{Z}, \quad w_{\text{abs}} = \frac{\alpha_{\text{abs}} \cdot \delta}{Z} \tag{1}$$
$$Z = \alpha_{\text{imm}} \cdot (1 + \gamma_H \cdot H_t) + \alpha_{\text{abs}} \cdot \delta$$

Here, $\text{imm}$ = immediate attribute (e.g., taste/proximity), $\text{abs}$ = abstract attribute (e.g., health/future benefit). Weights are normalized so $w_{\text{imm}} + w_{\text{abs}} = 1$.

**Eq. 2 — Overall option value (weighted linear sum):**
`V(o) = w_imm · a_imm(o) + w_abs · a_abs(o)`
$$V(o) = w_{\text{imm}} \cdot a_{\text{imm}}(o) + w_{\text{abs}} \cdot a_{\text{abs}}(o) \tag{2}$$

**Eq. 3 — Action value mapping:**
`V(a) = V(o_a)  if action a leads to an option; else V(a) = 0`
$$V(a) = \begin{cases} V(o_a) & \text{if action } a \text{ reaches option } o_a \\ 0 & \text{otherwise} \end{cases} \tag{3}$$

For movement actions: $o_a$ is the nearest resource in the direction of action $a$. The immediate attribute $a_{\text{imm}}(o)$ is computed as $1.0 - d(o)/d_{\max}$ (proximity-scaled desirability, where $d$ is Manhattan distance). The abstract attribute $a_{\text{abs}}(o)$ is a fixed nutritional quality rating of the resource $\in [-1, 1]$. For the `eat` action: $a_{\text{imm}}(\text{eat}) = 1.0$ (immediate reward), $a_{\text{abs}}(\text{eat}) = q_{\text{resource}}$ (nutritional quality of the resource at the agent's cell). For `stay`: $V(\text{stay}) = 0$.

**Eq. 4 — Softmax action selection:**
`P(a) = exp(β · V(a)) / Σ_j exp(β · V(j))`
$$P(a) = \frac{\exp(\beta \cdot V(a))}{\sum_{j \in \mathcal{A}} \exp(\beta \cdot V(j))} \tag{4}$$

**Eq. 5 — Hunger state update:**
`H_{t+1} = min(1, H_t + η − R_food · ate_t)`
$$H_{t+1} = \min\!\Big(1,\; H_t + \eta - R_{\text{food}} \cdot \mathbb{1}[\text{ate}_t]\Big) \tag{5}$$

**Eq. 6 — Attention update via reward prediction error:**
`α_imm ← α_imm + λ · (r_t − V_t) · a_imm(o_t)`
`α_abs ← α_abs + λ · (r_t − V_t) · a_abs(o_t)`
`α_i ← max(ε, α_i) then normalize so Σ α_i = 1`
$$\alpha_i \leftarrow \alpha_i + \lambda \cdot (r_t - V_t) \cdot a_i(o_t), \quad \text{then } \alpha_i \leftarrow \frac{\max(\epsilon,\, \alpha_i)}{\sum_j \max(\epsilon,\, \alpha_j)} \tag{6}$$

where $\lambda = 0.05$ is the attention learning rate and $\epsilon = 0.05$ prevents any attribute from being fully ignored.

### Decision logic
1. **Perceive**: Read agent position, nearby resource locations and types, hunger $H_t$.
2. **Compute attribute values**: For each candidate action $a \in \{\text{up, down, left, right, stay, eat}\}$, compute $a_{\text{imm}}(o_a)$ and $a_{\text{abs}}(o_a)$ using the perception (Eq. 3 notes).
3. **Compute weights**: Using current $H_t$, $\alpha_{\text{imm}}$, $\alpha_{\text{abs}}$, compute $w_{\text{imm}}$ and $w_{\text{abs}}$ via **Eq. 1**.
4. **Compute option values**: For each action, compute $V(a)$ via **Eq. 2** and **Eq. 3**.
5. **Select action**: Sample action from softmax distribution over $V(a)$ values via **Eq. 4**.
6. **Update** (after action execution):
   - Update hunger via **Eq. 5**.
   - Compute reward prediction error $r_t - V_t$ where $r_t$ is the received reward.
   - Update attention allocations $\alpha_i$ via **Eq. 6**.

---

## Formulation 2: Attribute-Based Evidence Accumulation (Drift-Diffusion)
**Approach**: Dynamic stochastic process where value evidence for each action accumulates over deliberation time, with drift rates determined by attribute-weighted values and noise capturing attribute conflict. Actions are selected when an accumulator hits a decision threshold.
**Based on**: Rangel (2013) prediction of conflict → slower RT; Rangel, Camerer & Montague (2008) on value comparison; drift-diffusion framework from prior pipeline knowledge.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $E_a(t)$ | Evidence accumulator for action $a$ | Running total of value evidence favoring action $a$ at deliberation step $t$ | Continuous, starts at 0 |
| $\mu_a$ | Drift rate for action $a$ | Mean rate of evidence accumulation, derived from attribute-weighted value | Continuous, real |
| $a_i(o)$ | Attribute value | Subjective evaluation of option $o$ on attribute $i$ | Continuous, $[-1, 1]$ |
| $w_i$ | Attribute weight | Importance of attribute $i$ | Continuous, $(0, 1]$ |
| $H_t$ | Hunger state | Internal drive level | Continuous, $[0, 1]$ |
| $\sigma_a$ | Noise magnitude | Scaled by attribute conflict for action $a$ | Continuous, $> 0$ |
| $\text{conflict}(o)$ | Attribute conflict | Degree of disagreement between attributes for option $o$ | Continuous, $\geq 0$ |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\theta$ | Decision threshold | 1.0 | Standard DDM calibration; agent commits when $E_a \geq \theta$ |
| $\sigma_0$ | Base noise | 0.3 | Typical DDM noise level for moderate stochasticity |
| $\kappa$ | Conflict-noise scaling | 0.5 | Derived from Rangel (2013): conflict increases RT and noise |
| $T_{\max}$ | Maximum deliberation steps | 10 | Simulation constraint (bounded rationality) |
| $\beta_w$ | Weight learning rate | 0.05 | Standard reinforcement learning rate |
| $\eta$ | Hunger decay rate | 0.01 | Same as Formulation 1 |
| $R_{\text{food}}$ | Hunger restoration | 0.3 | Same as Formulation 1 |

### Equations

**Eq. 1 — Attribute weights (hunger-modulated):**
`w_imm = (1 + H_t) / (2 + H_t)`
`w_abs = 1 / (2 + H_t)`
$$w_{\text{imm}} = \frac{1 + H_t}{2 + H_t}, \qquad w_{\text{abs}} = \frac{1}{2 + H_t} \tag{1}$$

This ensures $w_{\text{imm}} + w_{\text{abs}} = 1$ and hunger monotonically increases the immediate-attribute weight.

**Eq. 2 — Drift rate from weighted attribute sum:**
`μ_a = w_imm · a_imm(o_a) + w_abs · a_abs(o_a)`
$$\mu_a = w_{\text{imm}} \cdot a_{\text{imm}}(o_a) + w_{\text{abs}} \cdot a_{\text{abs}}(o_a) \tag{2}$$

**Eq. 3 — Attribute conflict:**
`conflict(o) = |a_imm(o) − a_abs(o)|`
$$\text{conflict}(o_a) = |a_{\text{imm}}(o_a) - a_{\text{abs}}(o_a)| \tag{3}$$

**Eq. 4 — Noise magnitude (conflict-scaled):**
`σ_a = σ_0 · (1 + κ · conflict(o_a))`
$$\sigma_a = \sigma_0 \cdot \big(1 + \kappa \cdot \text{conflict}(o_a)\big) \tag{4}$$

**Eq. 5 — Evidence accumulation (discrete-time DDM):**
`E_a(t+1) = E_a(t) + μ_a + σ_a · ξ_t,  where ξ_t ~ N(0,1)`
$$E_a(t+1) = E_a(t) + \mu_a + \sigma_a \cdot \xi_t, \quad \xi_t \sim \mathcal{N}(0, 1) \tag{5}$$

**Eq. 6 — Threshold-based action selection:**
`a* = first action a where E_a(t) ≥ θ; if no accumulator hits θ by T_max, a* = argmax_a E_a(T_max)`
$$a^* = \begin{cases} a & \text{if } \exists\, t \leq T_{\max}: E_a(t) \geq \theta \text{ (first hit)} \\ \arg\max_a E_a(T_{\max}) & \text{otherwise} \end{cases} \tag{6}$$

**Eq. 7 — Attribute weight update (post-decision):**
`w_i ← w_i + β_w · RPE · a_i(o*), then normalize`
`RPE = r_t − μ_{a*}`
$$w_i \leftarrow w_i + \beta_w \cdot \text{RPE} \cdot a_i(o^*), \quad \text{RPE} = r_t - \mu_{a^*} \tag{7}$$

**Eq. 8 — Hunger update:**
`H_{t+1} = min(1, H_t + η − R_food · ate_t)`
$$H_{t+1} = \min\!\Big(1,\; H_t + \eta - R_{\text{food}} \cdot \mathbb{1}[\text{ate}_t]\Big) \tag{8}$$

### Decision logic
1. **Perceive**: Read agent position, nearby resources, hunger $H_t$.
2. **Compute attribute values**: For each action $a$, determine $a_{\text{imm}}(o_a)$ (proximity-scaled desirability) and $a_{\text{abs}}(o_a)$ (nutritional quality).
3. **Compute attribute weights** via **Eq. 1** using current hunger.
4. **Compute drift rates** $\mu_a$ for each action via **Eq. 2**.
5. **Compute conflict-scaled noise** $\sigma_a$ for each action via **Eq. 3** and **Eq. 4**.
6. **Run evidence accumulation**: Initialize all $E_a(0) = 0$. For $t = 1, \ldots, T_{\max}$:
   - Update each $E_a(t)$ via **Eq. 5**.
   - If any $E_a(t) \geq \theta$, stop and select that action.
7. **Fallback**: If no threshold is reached by $T_{\max}$, select $a^* = \arg\max_a E_a(T_{\max})$ via **Eq. 6**.
8. **Update** (after action execution):
   - Update hunger via **Eq. 8**.
   - Compute RPE and update attribute weights via **Eq. 7**, then renormalize weights to sum to 1.

---

## Formulation 3: ODE-Based Dynamic Attribute Valuation with Cognitive Control
**Approach**: Continuous-time ODE system where attribute weights, hunger state, and a cognitive control (self-regulation) variable co-evolve. The control variable represents dlPFC engagement that dynamically up-weights abstract attributes, creating a self-regulation mechanism.
**Based on**: Rangel (2013) on dlPFC top-down modulation of attribute weights; Rangel, Camerer & Montague (2008) on goal-directed valuation; postulates P3, P5.

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $H(t)$ | Hunger state | Internal drive; rises over time, drops on eating | Continuous, $[0, 1]$ |
| $K(t)$ | Cognitive control (self-regulation) level | Represents dlPFC engagement; depletes with use, recovers passively | Continuous, $[0, 1]$ |
| $w_{\text{imm}}(t)$ | Immediate attribute weight | Dynamic weight for hedonic/proximity attributes | Continuous, $[0, 1]$ |
| $w_{\text{abs}}(t)$ | Abstract attribute weight | Dynamic weight for health/quality attributes | Continuous, $[0, 1]$ |
| $V(o)$ | Option value | Weighted attribute sum for option $o$ | Continuous, real |
| $Q(a)$ | Action-value | Learned expected return from taking action $a$ | Continuous, real |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\eta_H$ | Hunger rise rate | 0.01 | Simulation metabolic timescale |
| $R_{\text{food}}$ | Hunger restoration from eating | 0.3 | Simulation convention |
| $\tau_K$ | Cognitive control recovery time constant | 50.0 | Rangel (2013): dlPFC engagement is effortful and recovers slowly |
| $K_0$ | Resting cognitive control level | 0.5 | Moderate baseline self-regulation |
| $c_K$ | Control depletion per decision step | 0.02 | Models ego-depletion / cognitive cost of abstract attribute processing |
| $\phi$ | Control boost to abstract weight | 1.5 | Rangel (2013): dlPFC amplifies health/abstract attribute weighting |
| $\tau_w$ | Weight dynamics time constant | 5.0 | Determines how quickly weights track state changes |
| $\beta$ | Softmax inverse temperature | 5.0 | Standard action selection parameter |
| $\alpha_Q$ | Q-value learning rate | 0.1 | Standard RL learning rate |
| $\gamma$ | Discount factor for Q-learning | 0.9 | Standard temporal discounting |

### Equations

**Eq. 1 — Hunger dynamics (ODE, Euler-discretized):**
`dH/dt = η_H − R_food · ate_t`
`H_{t+1} = clip(H_t + η_H − R_food · ate_t, 0, 1)`
$$\frac{dH}{dt} = \eta_H - R_{\text{food}} \cdot \mathbb{1}[\text{ate}] \tag{1}$$

**Eq. 2 — Cognitive control dynamics (ODE, Euler-discretized):**
`dK/dt = (K_0 − K) / τ_K − c_K · decided_t`
`K_{t+1} = clip(K_t + (K_0 − K_t) / τ_K − c_K, 0, 1)`
$$\frac{dK}{dt} = \frac{K_0 - K}{\tau_K} - c_K \cdot \mathbb{1}[\text{decided}] \tag{2}$$

The first term passively restores $K$ toward the resting level $K_0$; the second term depletes control every timestep an action is selected (every step).

**Eq. 3 — Target attribute weights (equilibrium targets driven by state):**
`w_imm^* = (1 + H_t) / (2 + H_t + φ · K_t)`
`w_abs^* = (1 + φ · K_t) / (2 + H_t + φ · K_t)`
$$w_{\text{imm}}^* = \frac{1 + H_t}{2 + H_t + \phi \cdot K_t}, \qquad w_{\text{abs}}^* = \frac{1 + \phi \cdot K_t}{2 + H_t + \phi \cdot K_t} \tag{3}$$

These targets ensure weights sum to 1 and reflect the competition between hunger (favoring immediate) and cognitive control (favoring abstract).

**Eq. 4 — Weight dynamics (exponential tracking, Euler-discretized):**
`dw_i/dt = (w_i* − w_i) / τ_w`
`w_i(t+1) = w_i(t) + (w_i* − w_i(t)) / τ_w`
$$\frac{dw_i}{dt} = \frac{w_i^* - w_i}{\tau_w} \tag{4}$$

Weights smoothly track their target values, introducing inertia: sudden state changes do not instantly reconfigure attribute weighting.

**Eq. 5 — Option value (weighted linear sum):**
`V(o) = w_imm(t) · a_imm(o) + w_abs(t) · a_abs(o)`
$$V(o) = w_{\text{imm}}(t) \cdot a_{\text{imm}}(o) + w_{\text{abs}}(t) \cdot a_{\text{abs}}(o) \tag{5}$$

**Eq. 6 — Q-value update (TD learning blended with attribute value):**
`Q(a) ← Q(a) + α_Q · (r_t + γ · max_a' Q(a') − Q(a))`
$$Q(a) \leftarrow Q(a) + \alpha_Q \cdot \Big(r_t + \gamma \cdot \max_{a'} Q(a') - Q(a)\Big) \tag{6}$$

**Eq. 7 — Blended action value:**
`U(a) = 0.5 · V(o_a) + 0.5 · Q(a)`
$$U(a) = \frac{1}{2}\,V(o_a) + \frac{1}{2}\,Q(a) \tag{7}$$

This blends the attribute-based value (goal-directed) with the learned Q-value (which captures environmental structure), consistent with Rangel, Camerer & Montague (2008)'s dual-system framework.

**Eq. 8 — Softmax action selection:**
`P(a) = exp(β · U(a)) / Σ_j exp(β · U(j))`
$$P(a) = \frac{\exp(\beta \cdot U(a))}{\sum_{j \in \mathcal{A}} \exp(\beta \cdot U(j))} \tag{8}$$

### Decision logic
1. **Perceive**: Read agent position, nearby resource locations/types, whether agent ate last step, hunger $H_t$, control $K_t$, current weights $w_{\text{imm}}(t)$, $w_{\text{abs}}(t)$.
2. **Integrate ODEs** (Euler step):
   - Update hunger $H_t$ via **Eq. 1**.
   - Update cognitive control $K_t$ via **Eq. 2**.
   - Compute target weights $w_i^*$ via **Eq. 3**.
   - Update weights $w_i$ via **Eq. 4**.
3. **Compute attribute values**: For each action $a$:
   - $a_{\text{imm}}(o_a)$: proximity-scaled desirability (1.0 if at resource for `eat`; distance-decayed for movement).
   - $a_{\text{abs}}(o_a)$: nutritional quality of the nearest resource in that direction.
4. **Compute option values** $V(o_a)$ for each action via **Eq. 5**.
5. **Retrieve Q-values** $Q(a)$ from learned table.
6. **Compute blended values** $U(a)$ for each action via **Eq. 7**.
7. **Select action**: Sample from softmax distribution over $U(a)$ via **Eq. 8**.
8. **Post-action update**:
   - After receiving reward $r_t$ and observing new state, update $Q(a)$ via **Eq. 6**.

---

## Cross-formulation comparison

| Aspect | Formulation 1: Weighted Linear Summation | Formulation 2: Evidence Accumulation (DDM) | Formulation 3: ODE Dynamic Control |
|--------|------------------------------------------|---------------------------------------------|-------------------------------------|
| Framework | Algebraic (static per-step computation) | Stochastic process (sequential sampling) | Continuous-time ODE system (Euler-discretized) |
| Key variables | $V(o)$, $w_i$, $\alpha_i$ | $E_a(t)$, $\mu_a$, $\text{conflict}(o)$ | $H(t)$, $K(t)$, $w_i(t)$, $U(a)$ |
| Core equation | $V(o) = \sum_i w_i \cdot a_i(o)$ (Eq. 2) | $E_a(t\!+\!1) = E_a(t) + \mu_a + \sigma_a \xi_t$ (Eq. 5) | $dw_i/dt = (w_i^* - w_i)/\tau_w$ with $w^*$ from hunger–control competition (Eq. 3–4) |
| Decision mechanism | Softmax over computed values | First-to-threshold race among accumulators | Softmax over blended attribute + Q-values |
| Attribute weight origin | Attention allocation $\alpha_i$ modulated by hunger, learned via RPE | Fixed functional form of hunger; conflict modulates noise, not weights directly | ODE-governed weights tracking equilibrium set by hunger vs. cognitive control |
| Learning mechanism | Attention allocation updates via RPE (Eq. 6) | Attribute weight updates via RPE (Eq. 7) | Q-value TD learning (Eq. 6); weights adapt implicitly via state dynamics |
| Handles attribute conflict | Indirectly (high-conflict options may have moderate $V$) | Explicitly: conflict → higher noise → more stochastic and slower decisions (Eq. 3–4) | Indirectly via cognitive control depletion (high conflict depletes $K$) |
| Strengths | Simple, transparent, direct mapping to Rangel (2013) linear model; attention is an explicit learnable variable | Captures RT effects (deliberation time varies with conflict); naturalistic stochastic choice; aligns with DDM literature | Rich dynamics: weight inertia, self-regulation depletion, blends goal-directed and experiential learning |
| Limitations | No temporal dynamics in deliberation; no explicit conflict mechanism | More complex; DDM inner loop adds computational cost per step; weight learning is simple | Most complex; many parameters; ODE discretization may introduce artifacts; harder to calibrate |
