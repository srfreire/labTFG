# Incentive Salience Theory — Mathematical formulations

## Formulation 1: Dual-Signal Temporal-Difference Model with Dopaminergic Incentive Bias
**Approach**: Algebraic value-learning framework where a TD-learned value function is modulated by a separate, state-dependent dopaminergic incentive salience signal that biases action selection
**Based on**: Montague, Daw & colleagues (2003); Redish (2004); derived from postulates P1, P2, P4

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $V(s)$ | Value function | Learned expected discounted reward for state $s$ | State → ℝ (internal) |
| $\delta_t$ | TD prediction error | Reward-prediction error used for learning updates | ℝ (internal, per step) |
| $L(s)$ | Liking | Hedonic impact experienced upon consuming resource at state $s$ | ℝ≥0 (internal) |
| $W(s)$ | Wanting (incentive salience) | Motivational attractiveness attributed to stimulus at state $s$ | ℝ≥0 (internal) |
| $d_t$ | Dopaminergic state | Current tonic dopamine level, modulating wanting | ℝ>0 (internal) |
| $r_t$ | Reward | Hedonic reward received at time $t$ (maps to liking) | ℝ (perception-derived) |
| $Q(s,a)$ | Action-value | Expected value of taking action $a$ in state $s$ | State×Action → ℝ (internal) |
| $\pi(a \mid s)$ | Policy | Probability of choosing action $a$ in state $s$ | Probability (output) |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $\alpha$ | Learning rate | 0.1 | Standard RL (Sutton & Barto, 1998) |
| $\gamma$ | Discount factor | 0.9 | Standard RL |
| $\beta$ | Softmax inverse temperature | 5.0 | Daw et al. (2003) |
| $\kappa$ | Incentive salience weight | 0.5 | Derived from dual-role dopamine model (Montague et al., 2003) |
| $\eta$ | Sensitization rate | 0.02 | Robinson & Berridge (1993): gradual sensitization over repeated exposures |
| $d_0$ | Baseline dopaminergic state | 1.0 | Normative baseline |
| $d_{\max}$ | Maximum dopaminergic state | 3.0 | Upper bound on sensitization (Robinson & Berridge, 2016) |
| $\lambda$ | Dopamine decay rate | 0.005 | Slow tonic decay toward baseline |

### Equations

**Eq. 1 — TD prediction error (learning signal):**
$$\delta_t = r_t + \gamma \max_{a'} Q(s_{t+1}, a') - Q(s_t, a_t) \tag{1}$$

**Eq. 2 — Q-value update (learning, liking-driven):**
$$Q(s_t, a_t) \leftarrow Q(s_t, a_t) + \alpha \cdot \delta_t \tag{2}$$

**Eq. 3 — Liking (hedonic impact at consumption):**
$$L(s_t) = r_t \tag{3}$$

Liking is the raw hedonic signal, independent of dopamine state (postulate P3).

**Eq. 4 — Incentive salience (wanting):**
$$W(s) = d_t \cdot \max_a Q(s, a) \tag{4}$$

Wanting is the learned value scaled by dopaminergic state. This captures P2: dopamine modulates wanting but not liking.

**Eq. 5 — Effective action value (combined signal):**
$$U(s, a) = Q(s, a) + \kappa \cdot d_t \cdot Q(s, a) = (1 + \kappa \cdot d_t) \cdot Q(s, a) \tag{5}$$

The effective utility merges the learned value with the incentive salience bias. The $\kappa \cdot d_t$ term captures the motivational amplification.

**Eq. 6 — Policy (softmax action selection):**
$$\pi(a \mid s_t) = \frac{\exp(\beta \cdot U(s_t, a))}{\sum_{a'} \exp(\beta \cdot U(s_t, a'))} \tag{6}$$

**Eq. 7 — Dopaminergic sensitization dynamics:**
$$d_{t+1} = d_t + \eta \cdot \mathbb{1}[r_t > 0] - \lambda \cdot (d_t - d_0) \tag{7}$$

Dopamine state increases with each reward encounter (sensitization, P5) and slowly decays toward baseline. Clamped: $d_t \in [d_0, d_{\max}]$.

### Decision logic

1. **Perceive** current state $s_t$: agent position, locations of nearby resources, and whether the agent is on a resource.
2. **If on a resource**: compute $U(s_t, \text{eat})$ via Eq. 5. Compare against moving/staying.
3. **For each possible action** $a \in \{\text{up, down, left, right, stay, eat}\}$:
   - Determine the resulting next state $s'$.
   - Compute $U(s_t, a)$ using Eq. 5. For movement actions, $Q(s_t, a)$ is the learned Q-value for that state–action pair. For `eat`, $Q$ reflects learned consumption value.
4. **Select action** by sampling from the softmax distribution $\pi(a \mid s_t)$ (Eq. 6).
5. **After acting**, observe reward $r_t$ and next state $s_{t+1}$.
6. **Update Q-values** using Eqs. 1–2.
7. **Update dopaminergic state** $d_t$ using Eq. 7: if the agent consumed a resource ($r_t > 0$), $d_t$ increases by $\eta$; otherwise it decays toward $d_0$.
8. **Note**: Liking ($L$, Eq. 3) is recorded but does **not** feed back into action selection — only wanting ($W$, through $U$) drives behavior. This implements the wanting–liking dissociation (P1, P3).

---

## Formulation 2: Probabilistic Cue-Triggered Wanting with Bayesian State Estimation
**Approach**: Probabilistic/Bayesian framework where the agent maintains beliefs over resource locations, and incentive salience acts as a multiplicative prior bias on approach probability toward cue-associated states
**Based on**: Berridge (2007); Robinson & Berridge (1993); postulates P4, P5, P6

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $b_t(s)$ | Belief | Probability that state $s$ contains a resource, given observations up to $t$ | [0,1] per cell (internal) |
| $\sigma_t(s)$ | Incentive salience map | Motivational attractiveness of each state $s$, combining belief and wanting | ℝ≥0 per cell (internal) |
| $D_t$ | Dopaminergic drive | Scalar motivational amplifier (sensitizable) | ℝ>0 (internal) |
| $H_t$ | Hedonic register | Cumulative liking experienced (tracks pleasure, not used for decisions) | ℝ (internal) |
| $\rho_t$ | Cue signal | Binary/graded perceptual signal: is a resource-predictive cue nearby? | {0,1} or [0,1] (perception) |
| $\phi(s)$ | Cue strength | Learned associative strength between a state/cue and reward | [0,1] (internal) |
| $p_{\text{eat}}$ | Probability of choosing eat | Probability of eating when on a resource | [0,1] (derived) |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $D_0$ | Baseline dopaminergic drive | 1.0 | Normative |
| $\eta_s$ | Sensitization increment | 0.03 | Robinson & Berridge (1993): gradual mesolimbic sensitization |
| $\lambda_D$ | Drive decay rate | 0.01 | Slow return to baseline |
| $D_{\max}$ | Max dopaminergic drive | 4.0 | Robinson & Berridge (2016) |
| $\alpha_b$ | Belief learning rate | 0.15 | Bayesian-approximate update rate |
| $\alpha_\phi$ | Cue-association learning rate | 0.1 | Pavlovian conditioning rate (Berridge, 2007) |
| $\omega$ | Wanting exponent | 1.5 | Supra-linear wanting scaling (Redish, 2004) |
| $\tau$ | Distance discount | 0.8 | Spatial discounting per Manhattan distance step |

### Equations

**Eq. 1 — Belief update (approximate Bayesian):**
$$b_{t+1}(s) = b_t(s) + \alpha_b \cdot (\mathbb{1}[\text{resource observed at } s] - b_t(s)) \tag{1}$$

For unobserved states, beliefs decay: $b_{t+1}(s) \leftarrow (1 - 0.01) \cdot b_t(s)$.

**Eq. 2 — Cue-association learning (Pavlovian):**
$$\phi_{t+1}(s) = \phi_t(s) + \alpha_\phi \cdot (r_t \cdot \mathbb{1}[s_t = s] - \phi_t(s)) \tag{2}$$

$\phi(s)$ tracks the associative strength between visiting state $s$ and receiving reward (P4).

**Eq. 3 — Incentive salience map (wanting):**
$$\sigma_t(s) = D_t^{\,\omega} \cdot \left[ b_t(s) \cdot \phi_t(s) \right] \tag{3}$$

Incentive salience is the belief-weighted cue strength, amplified supra-linearly by dopaminergic drive ($\omega > 1$ per Redish, 2004). This captures how wanting can grow disproportionately to actual reward probability.

**Eq. 4 — Spatially-discounted attraction toward state $s$:**
$$A_t(s) = \sigma_t(s) \cdot \tau^{\,\text{dist}(s_t, s)} \tag{4}$$

where $\text{dist}(s_t, s)$ is the Manhattan distance from the agent's current position to state $s$.

**Eq. 5 — Action score (directional pull):**
$$\text{Score}(a) = \sum_{s \in \mathcal{S}} A_t(s) \cdot \mathbb{1}[\text{action } a \text{ moves toward } s] \tag{5}$$

For `eat`: $\text{Score}(\text{eat}) = D_t^{\,\omega} \cdot \phi_t(s_t) \cdot \mathbb{1}[\text{resource at } s_t]$.
For `stay`: $\text{Score}(\text{stay}) = \epsilon$ (small baseline, e.g., 0.01).

**Eq. 6 — Action selection (proportional to score):**
$$\pi(a) = \frac{\text{Score}(a)}{\sum_{a'} \text{Score}(a')} \tag{6}$$

**Eq. 7 — Hedonic register (liking, recorded only):**
$$H_{t+1} = H_t + r_t \tag{7}$$

Liking accumulates from consumption but does NOT influence action selection (P1, P3).

**Eq. 8 — Dopaminergic sensitization:**
$$D_{t+1} = \min\!\Big(D_{\max},\; D_t + \eta_s \cdot \mathbb{1}[r_t > 0]\Big) - \lambda_D \cdot (D_t - D_0) \tag{8}$$

### Decision logic

1. **Perceive** the grid: agent position $s_t$, visible resource locations, and whether the agent is on a resource.
2. **Update beliefs** $b_t(s)$ for all observed cells using Eq. 1; decay beliefs for unobserved cells.
3. **Compute incentive salience map** $\sigma_t(s)$ for all cells using Eq. 3.
4. **Compute spatially-discounted attraction** $A_t(s)$ for all cells using Eq. 4.
5. **For each action** $a$:
   - If $a$ is a movement action: compute $\text{Score}(a)$ as the sum of attractions toward all cells that $a$ moves the agent closer to (Eq. 5).
   - If $a = \text{eat}$: score is $D_t^{\omega} \cdot \phi_t(s_t)$ if a resource is present, else 0.
   - If $a = \text{stay}$: score is $\epsilon = 0.01$.
6. **Normalize** scores into a probability distribution (Eq. 6) and **sample** an action.
7. **After acting**, observe reward $r_t$ and update:
   - Cue associations $\phi(s)$ via Eq. 2.
   - Hedonic register $H_t$ via Eq. 7 (bookkeeping only).
   - Dopaminergic drive $D_t$ via Eq. 8.
8. **Key behavioral signature**: As $D_t$ grows through sensitization, the agent becomes increasingly attracted to cue-associated locations ($\sigma$ grows supra-linearly), even if the actual hedonic return $H$ per episode is flat or declining — implementing the wanting–liking dissociation (P1, P5).

---

## Formulation 3: Dual-ODE Dynamical System with Wanting–Liking Dissociation
**Approach**: Continuous-time ordinary differential equation (ODE) system where wanting and liking evolve as coupled but dissociable dynamical variables, discretized per simulation tick for agent decisions
**Based on**: Robinson & Berridge (1993); Berridge & Robinson (1998, 2016); postulates P1, P2, P3, P5

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| $w_t$ | Wanting level | Current motivational drive / incentive salience intensity | ℝ≥0 (internal, dynamic) |
| $l_t$ | Liking level | Current hedonic capacity / pleasure sensitivity | ℝ>0 (internal, dynamic) |
| $S_t$ | Sensitization state | Accumulated neural sensitization of the wanting system | ℝ≥0 (internal, dynamic) |
| $c_t$ | Cue proximity | Intensity of nearest reward-predictive cue (inverse distance to closest resource) | ℝ≥0 (perception-derived) |
| $r_t$ | Reward | Hedonic reward received upon eating | ℝ≥0 (perception-derived) |
| $E_t$ | Energy/satiation | Internal energy level reflecting recent consumption | ℝ≥0 (internal, dynamic) |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| $a_w$ | Wanting cue reactivity | 2.0 | Berridge (2007): cues strongly elicit wanting |
| $b_w$ | Wanting decay rate | 0.3 | Natural decay of motivational urge without cues |
| $a_S$ | Sensitization gain on wanting | 1.0 | Robinson & Berridge (1993): sensitization amplifies cue-triggered wanting |
| $\eta_S$ | Sensitization growth rate | 0.05 | Robinson & Berridge (2016): gradual and persistent |
| $\lambda_S$ | Sensitization decay rate | 0.002 | Very slow decay — sensitization is long-lasting (Robinson & Berridge, 2024) |
| $S_{\max}$ | Max sensitization | 5.0 | Bounded upper limit |
| $l_0$ | Baseline liking capacity | 1.0 | Normative hedonic set-point |
| $\mu_l$ | Liking restoration rate | 0.1 | Hedonic adaptation back to baseline (Berridge & Robinson, 1998) |
| $\delta_l$ | Liking tolerance decrement | 0.05 | Hedonic tolerance with repeated consumption (Berridge & Robinson, 2016) |
| $\theta_w$ | Wanting threshold for approach | 0.5 | Below this, agent defaults to exploration |
| $\theta_e$ | Eat threshold (wanting) | 1.5 | High wanting needed to trigger consumption action |
| $E_{\text{decay}}$ | Energy decay per step | 0.05 | Basal metabolic cost |

### Equations

**Eq. 1 — Wanting dynamics (ODE, Euler-discretized):**
$$w_{t+1} = w_t + \Delta t \Big[ a_w \cdot (1 + a_S \cdot S_t) \cdot c_t - b_w \cdot w_t \Big] \tag{1}$$

Wanting is driven up by cue proximity $c_t$, amplified by sensitization $S_t$, and naturally decays. This formalizes P2 and P4: wanting is cue-triggered and dopamine-amplified.

**Eq. 2 — Liking dynamics (ODE, Euler-discretized):**
$$l_{t+1} = l_t + \Delta t \Big[ \mu_l \cdot (l_0 - l_t) - \delta_l \cdot \mathbb{1}[r_t > 0] \Big] \tag{2}$$

Liking drifts back toward the hedonic set-point $l_0$ but decreases slightly with each consumption event (tolerance). Crucially, liking has **no dependence on $S_t$ or the dopamine-like wanting variables** (P3).

**Eq. 3 — Sensitization dynamics:**
$$S_{t+1} = S_t + \Delta t \Big[ \eta_S \cdot \mathbb{1}[r_t > 0] - \lambda_S \cdot S_t \Big] \tag{3}$$

Sensitization grows with each reward encounter and decays very slowly (P5). Clamped at $[0, S_{\max}]$.

**Eq. 4 — Cue proximity signal:**
$$c_t = \frac{1}{1 + d_{\min}(s_t)} \tag{4}$$

where $d_{\min}(s_t)$ is the Manhattan distance from the agent's position to the nearest visible resource. If no resource is visible, $c_t = 0$.

**Eq. 5 — Experienced pleasure from eating:**
$$\text{pleasure}_t = l_t \cdot r_t \tag{5}$$

Actual hedonic experience scales with liking capacity — can diminish even as wanting grows (P5 dissociation).

**Eq. 6 — Energy dynamics:**
$$E_{t+1} = E_t - E_{\text{decay}} + \mathbb{1}[\text{ate}] \cdot r_t \tag{6}$$

### Decision logic

1. **Perceive** the grid: agent position $s_t$, locations of visible resources.
2. **Compute cue proximity** $c_t$ using Eq. 4.
3. **Update wanting** $w_t$ using Eq. 1.
4. **Decision rules (threshold-based, deterministic with tie-breaking):**

   **Rule A — Eat:** If the agent is on a resource cell **AND** $w_t \geq \theta_e$:
   → Choose action `eat`.

   **Rule B — Approach (cue-triggered wanting):** If $w_t \geq \theta_w$ **AND** a resource is visible:
   → Move in the direction that **minimizes Manhattan distance** to the nearest visible resource (the resource with the highest $c_t$). If tied, pick randomly among tied directions.

   **Rule C — Explore (low wanting):** If $w_t < \theta_w$:
   → Choose a random movement action (uniform over up/down/left/right), favoring directions not recently visited (simple recency avoidance: avoid reversing the last move if possible).

   **Rule D — Stay:** If the agent is on a resource cell **AND** $\theta_w \leq w_t < \theta_e$:
   → Choose `stay` (waiting for wanting to build further via cue proximity before eating — models "hovering" near rewards).

5. **After acting**, observe reward $r_t$ and update:
   - Liking $l_t$ via Eq. 2.
   - Sensitization $S_t$ via Eq. 3.
   - Energy $E_t$ via Eq. 6.
6. **Emergent wanting–liking dissociation**: Over many reward encounters, $S_t$ accumulates (Eq. 3), causing $w_t$ to spike more strongly to cues (Eq. 1) — the agent approaches resources more vigorously. Meanwhile, $l_t$ drifts downward due to tolerance (Eq. 2), so $\text{pleasure}_t$ (Eq. 5) stagnates or declines. The agent increasingly "wants" what it no longer "likes" as much — the core signature of incentive sensitization (P5).
7. **Adaptive behavior**: In early episodes (low $S_t$), the agent explores broadly (Rule C dominates). As cue associations develop and sensitization grows, the agent becomes increasingly cue-reactive and approach-dominant (Rule B/A dominate), even if hedonic returns diminish — modeling the transition toward compulsive reward-seeking described by Robinson & Berridge (1993).
