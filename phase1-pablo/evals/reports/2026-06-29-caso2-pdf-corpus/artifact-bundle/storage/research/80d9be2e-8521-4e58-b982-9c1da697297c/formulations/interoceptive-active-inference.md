# Interoceptive Active Inference — Mathematical Formulations

## Formulation 1: Continuous Free-Energy Gradient Descent with Precision-Weighted Prediction Errors
**Approach**: Continuous-time ODE system where internal beliefs evolve via gradient descent on variational free energy, and actions are selected to minimize precision-weighted interoceptive prediction errors.
**Based on**: Friston (2010); Petzschner et al. (2021); derived from postulates P1, P3

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| **s(t)** | Interoceptive observation | Noisy sensory signal reflecting internal physiological state (e.g., energy level inferred from resource proximity/consumption) | Continuous ∈ ℝ |
| **μ(t)** | Belief state (posterior mean) | Agent's current best estimate of its hidden physiological state | Continuous ∈ ℝ |
| **μ_p** | Interoceptive prior (setpoint) | Prior belief about the ideal physiological state compatible with survival | Continuous ∈ ℝ |
| **ε_s(t)** | Sensory prediction error | Mismatch between observation and belief: s(t) − μ(t) | Continuous ∈ ℝ |
| **ε_p(t)** | Prior prediction error | Mismatch between belief and prior: μ(t) − μ_p | Continuous ∈ ℝ |
| **F(t)** | Variational free energy | Precision-weighted sum of squared prediction errors; proxy for surprise | Continuous ∈ [0, +∞) |
| **a(t)** | Action | Discrete action chosen by agent (up, down, left, right, stay, eat) | Discrete, 6 choices |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| **π_s** | Sensory precision | 1.0 | Friston (2010): inverse variance of sensory noise; normalized default |
| **π_p** | Prior precision | 2.0 | Petzschner et al. (2021): priors over survival-compatible states are typically strong |
| **κ** | Belief learning rate | 0.5 | Gradient descent step size on F; standard predictive coding convention (Friston, 2010) |
| **μ_p** | Interoceptive setpoint | 1.0 | Represents "fully sated" energy level; normalized |
| **σ_s** | Sensory noise std. dev. | 0.2 | Moderate interoceptive noise; Petzschner et al. (2021) note interoceptive signals are inherently noisy |
| **β** | Action inverse temperature | 5.0 | Controls stochasticity of action selection; moderate exploitation bias |

### Equations

**Eq. 1 — Variational free energy (prediction error energy):**
`F(t) = 0.5 * π_s * ε_s(t)^2 + 0.5 * π_p * ε_p(t)^2`
$$F(t) = \frac{1}{2}\,\pi_s\,\varepsilon_s(t)^2 + \frac{1}{2}\,\pi_p\,\varepsilon_p(t)^2 \tag{1}$$

where:
`ε_s(t) = s(t) − μ(t)`
$$\varepsilon_s(t) = s(t) - \mu(t) \tag{1a}$$

`ε_p(t) = μ(t) − μ_p`
$$\varepsilon_p(t) = \mu(t) - \mu_p \tag{1b}$$

**Eq. 2 — Belief update (gradient descent on F):**
`dμ/dt = κ · (π_s · ε_s(t) − π_p · ε_p(t))`
$$\frac{d\mu}{dt} = \kappa \left( \pi_s\,\varepsilon_s(t) - \pi_p\,\varepsilon_p(t) \right) \tag{2}$$

This implements perceptual inference: the belief μ moves toward both the sensory observation (pulled by sensory error) and the prior setpoint (pulled by prior error), weighted by their respective precisions.

**Eq. 3 — Predicted free energy under action a:**
`F_pred(a) = 0.5 · π_s · (s_pred(a) − μ(t))^2 + 0.5 · π_p · (μ(t) − μ_p)^2`
$$F_{\text{pred}}(a) = \frac{1}{2}\,\pi_s\,(s_{\text{pred}}(a) - \mu(t))^2 + \frac{1}{2}\,\pi_p\,(\mu(t) - \mu_p)^2 \tag{3}$$

where s_pred(a) is the predicted sensory signal after taking action a (estimated from perception: e.g., eating predicts energy increase, moving predicts unchanged or decreased energy).

**Eq. 4 — Action selection (softmax over negative predicted free energy):**
`P(a) = exp(−β · F_pred(a)) / Σ_j exp(−β · F_pred(j))`
$$P(a) = \frac{\exp(-\beta \, F_{\text{pred}}(a))}{\sum_j \exp(-\beta \, F_{\text{pred}}(j))} \tag{4}$$

### Decision logic

1. **Perceive**: Receive observation vector: own grid position `(x, y)`, list of nearby resource positions, boolean `ate_last_step`, current energy level `e(t)`.
2. **Compute sensory signal**: Set `s(t) = e(t)` (energy level serves as interoceptive observation, normalized to [0, 1]).
3. **Compute prediction errors**: Using Eq. (1a) and (1b), compute `ε_s(t) = s(t) − μ(t)` and `ε_p(t) = μ(t) − μ_p`.
4. **Update belief** (perceptual inference): Apply Eq. (2) as a discrete step: `μ(t+1) = μ(t) + κ · (π_s · ε_s(t) − π_p · ε_p(t))`.
5. **Predict sensory outcome for each action**:
   - For `eat` (if resource at current position): `s_pred(eat) = min(1.0, s(t) + 0.3)` (energy gain).
   - For each `move` direction: `s_pred(move) = s(t) − 0.05` (small metabolic cost). If move goes toward the nearest resource, also add a small anticipatory component: `s_pred(move_toward) = s(t) − 0.03`.
   - For `stay`: `s_pred(stay) = s(t) − 0.02` (minimal metabolic cost).
6. **Compute predicted free energy** for each action using Eq. (3).
7. **Select action** by sampling from the softmax distribution in Eq. (4).
8. **After action + reward**: Update belief μ via Eq. (2) on the next `decide()` call.

---

## Formulation 2: Homeostatic Reinforcement Learning with Drive-Reduction Reward
**Approach**: Algebraic / value-based RL where a scalar drive (distance from physiological setpoint) defines reward as drive reduction, and action values are updated via temporal-difference learning.
**Based on**: Keramati & Gutkin (2014); derived from postulates P4, P5

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| **h(t)** | Physiological state (energy) | Current energy level of the agent, normalized | Continuous ∈ [0, 1] |
| **h*** | Homeostatic setpoint | Ideal energy level | Continuous ∈ (0, 1] |
| **D(t)** | Drive | Scalar homeostatic displacement; equivalent to surprise | Continuous ∈ [0, +∞) |
| **r(t)** | Primary reward | Drive reduction achieved by the last action | Continuous ∈ ℝ |
| **Q(s, a)** | Action value | Expected discounted sum of future drive reductions for action a in state s | Continuous ∈ ℝ |
| **a(t)** | Action | Discrete action (up, down, left, right, stay, eat) | Discrete, 6 choices |
| **s(t)** | State representation | Tuple of (position, nearby resources, energy level) discretized | Discrete |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| **h*** | Homeostatic setpoint | 0.8 | Keramati & Gutkin (2014): high but sub-maximal setpoint reflecting optimal physiology |
| **m** | Drive sensitivity | 4.0 | Keramati & Gutkin (2014): multiplicative constant in drive function |
| **n** | Drive exponent | 2.0 | Keramati & Gutkin (2014): quadratic drive ≈ Euclidean distance in homeostatic space |
| **γ** | Temporal discount factor | 0.9 | Keramati & Gutkin (2014): must be < 1 for physiological rationality |
| **α** | Learning rate (TD) | 0.1 | Standard RL convention |
| **β** | Action inverse temperature | 8.0 | Controls exploration-exploitation; moderate |
| **c_move** | Metabolic cost of movement | 0.05 | Normalized energy cost per step |
| **c_stay** | Metabolic cost of staying | 0.02 | Minimal resting cost |
| **k_eat** | Energy gain from eating | 0.3 | Normalized resource gain |

### Equations

**Eq. 1 — Drive function (homeostatic displacement ≡ surprise):**
`D(h(t)) = m · |h* − h(t)|^n`
$$D(h(t)) = m \cdot |h^* - h(t)|^n \tag{1}$$

This implements the formal equivalence D(H_t) = −ln p(H_t), where the prior p(H_t) is a Gaussian centered at h* (Keramati & Gutkin, 2014).

**Eq. 2 — Primary reward (drive reduction):**
`r(t) = D(h(t)) − D(h(t+1))`
$$r(t) = D(h(t)) - D(h(t+1)) \tag{2}$$

Positive reward occurs when the action moves the agent closer to the setpoint; negative reward when it moves farther away.

**Eq. 3 — TD(0) value update:**
`Q(s, a) ← Q(s, a) + α · [r(t) + γ · max_a' Q(s', a') − Q(s, a)]`
$$Q(s, a) \leftarrow Q(s, a) + \alpha \left[ r(t) + \gamma \max_{a'} Q(s', a') - Q(s, a) \right] \tag{3}$$

**Eq. 4 — Action selection (softmax over Q-values):**
`P(a|s) = exp(β · Q(s, a)) / Σ_j exp(β · Q(s, j))`
$$P(a \mid s) = \frac{\exp(\beta \, Q(s, a))}{\sum_j \exp(\beta \, Q(s, j))} \tag{4}$$

**Eq. 5 — Physiological state dynamics:**
`h(t+1) = clip(h(t) + K(a), 0, 1)`
$$h(t+1) = \text{clip}\!\left(h(t) + K(a),\; 0,\; 1\right) \tag{5}$$

where K(a) is the outcome impact: K(eat) = +k_eat, K(move) = −c_move, K(stay) = −c_stay.

### Decision logic

1. **Perceive**: Receive position `(x, y)`, nearby resource positions, `ate_last_step`, energy `e(t)`.
2. **Set physiological state**: `h(t) = e(t)` (normalized energy).
3. **Encode state**: Discretize state as tuple `s = (distance_to_nearest_resource_bin, energy_bin)` using 5 distance bins × 5 energy bins = 25 states. Resource at current cell is distance bin 0.
4. **Compute Q-values**: Look up `Q(s, a)` for all 6 actions.
5. **Select action**: Sample from softmax Eq. (4).
6. **Execute action**, observe new energy `h(t+1)`.
7. **Compute reward**: Using Eq. (1), compute `D(h(t))` and `D(h(t+1))`. Then `r(t) = D(h(t)) − D(h(t+1))` via Eq. (2).
8. **Update Q-values**: Apply TD update Eq. (3) with new state `s'`.
9. **Special rules**:
   - If `h(t) < 0.2` (critically low energy), increase β temporarily to 15.0 (urgency — reduced exploration, consistent with P5: temporal discounting forces rapid correction).
   - `eat` action is only valid if a resource is at current position; otherwise Q(s, eat) = −∞.

---

## Formulation 3: Expected Free-Energy Policy Selection with Allostatic Prior Shifting
**Approach**: Discrete Bayesian policy selection where the agent evaluates candidate action sequences (policies) by their expected free energy, which decomposes into pragmatic value (homeostatic goal achievement) and epistemic value (information gain about resource locations); the interoceptive prior shifts allostatically with context.
**Based on**: Friston (2010); Petzschner et al. (2021); derived from postulates P1, P2, P3

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|
| **o(t)** | Observation | Full perception vector: (position, nearby_resources, ate_flag, energy) | Discrete (categorized) |
| **s(t)** | Hidden state | Agent's belief about the world state: (own_position_category, resource_map_belief, energy_level_category) | Discrete, finite |
| **π** | Policy | A planned sequence of T actions | Discrete; one of K candidate policies |
| **G(π)** | Expected free energy of policy π | Combines pragmatic and epistemic value over the policy horizon | Continuous ∈ ℝ |
| **μ_p(t)** | Allostatic prior (dynamic setpoint) | Context-dependent desired energy level; shifts based on environmental richness | Continuous ∈ (0, 1] |
| **C** | Prior preference distribution | Log-probability distribution over observations encoding survival-compatible states | Vector ∈ ℝ^|O| |
| **A** | Likelihood matrix | P(observation | hidden state); encodes sensory mapping | Matrix ∈ [0,1]^{|O|×|S|} |
| **B(a)** | Transition matrix for action a | P(s_{t+1} | s_t, a); encodes consequences of actions | Matrix ∈ [0,1]^{|S|×|S|} |
| **q(s_t)** | Approximate posterior over states | Current belief distribution over hidden states | Probability vector ∈ Δ^|S| |

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|
| **μ_p^{base}** | Baseline setpoint | 0.8 | Petzschner et al. (2021): survival-compatible energy prior |
| **λ_allo** | Allostatic adaptation rate | 0.1 | Controls speed of setpoint shifting; moderate adaptation (Petzschner et al., 2021, allostasis prediction) |
| **w_prag** | Pragmatic weight | 1.0 | Weight on goal-achievement (pragmatic) term in G |
| **w_epist** | Epistemic weight | 0.5 | Weight on information-gain (epistemic) term in G; encourages exploration |
| **T** | Planning horizon | 3 | Number of steps to plan ahead; short horizon for computational tractability |
| **β_G** | Policy inverse temperature | 4.0 | Softmax temperature for policy selection; Friston (2010) |
| **α_learn** | Transition model learning rate | 0.05 | Rate at which B matrices are updated from experience |
| **n_energy** | Energy discretization bins | 5 | Bins: [0-0.2), [0.2-0.4), [0.4-0.6), [0.6-0.8), [0.8-1.0] |
| **n_dist** | Distance discretization bins | 4 | Bins: [at_resource, near(1-2), medium(3-5), far(6+)] |

### Equations

**Eq. 1 — Allostatic prior update (dynamic setpoint):**
`μ_p(t+1) = μ_p(t) + λ_allo · (ρ(t) · μ_p^{base} + (1 − ρ(t)) · μ_p^{low} − μ_p(t))`
$$\mu_p(t+1) = \mu_p(t) + \lambda_{\text{allo}} \left( \rho(t) \cdot \mu_p^{\text{base}} + (1 - \rho(t)) \cdot \mu_p^{\text{low}} - \mu_p(t) \right) \tag{1}$$

where ρ(t) ∈ [0,1] is a resource-richness signal (proportion of nearby cells containing resources), and μ_p^{low} = 0.5 is a reduced setpoint for scarce environments. In resource-rich contexts, the agent raises its energy target (allostasis up); in scarce contexts, it lowers the target to conserve.

**Eq. 2 — Prior preference vector (log-preferences over observations):**
`C_o = −η · (o_energy − μ_p(t))^2`
$$C_o = -\eta \, (o_{\text{energy}} - \mu_p(t))^2 \tag{2}$$

where o_energy is the energy component of observation o (bin center), and η = 4.0 is the preference sharpness. Observations near the allostatic setpoint have highest (least negative) log-preference.

**Eq. 3 — Expected free energy of policy π:**
`G(π) = Σ_{τ=t+1}^{t+T} [ w_prag · E_q[ln q(s_τ|π) − ln C(o_τ)] + w_epist · (−E_q[H[P(o_τ|s_τ)]]) ]`
$$G(\pi) = \sum_{\tau=t+1}^{t+T} \left[ w_{\text{prag}} \underbrace{\mathbb{E}_{q}\!\left[\ln q(s_\tau|\pi) - C_{o_\tau}\right]}_{\text{pragmatic: risk}} + w_{\text{epist}} \underbrace{\left(-\mathbb{E}_{q}\!\left[\mathbf{H}[P(o_\tau|s_\tau)]\right]\right)}_{\text{epistemic: ambiguity}} \right] \tag{3}$$

Pragmatic value drives the agent toward observations matching the interoceptive prior (energy near setpoint). Epistemic value drives the agent to reduce uncertainty about the environment (explore to find resources).

**Eq. 4 — Policy posterior (softmax selection):**
`P(π) = σ(−β_G · G(π)) = exp(−β_G · G(π)) / Σ_j exp(−β_G · G(j))`
$$P(\pi) = \frac{\exp(-\beta_G \, G(\pi))}{\sum_j \exp(-\beta_G \, G(j))} \tag{4}$$

**Eq. 5 — Bayesian state inference (approximate posterior update):**
`q(s_t) ∝ P(o_t | s_t) · Σ_{s_{t-1}} B(a_{t-1})_{s_t, s_{t-1}} · q(s_{t-1})`
$$q(s_t) \propto P(o_t \mid s_t) \, \sum_{s_{t-1}} B(a_{t-1})_{s_t, s_{t-1}} \, q(s_{t-1}) \tag{5}$$

**Eq. 6 — Transition model learning (Dirichlet update):**
`b(a)_{s',s} ← b(a)_{s',s} + α_learn · 𝟙[s_t = s, s_{t+1} = s', a_t = a]`
$$b(a)_{s',s} \leftarrow b(a)_{s',s} + \alpha_{\text{learn}} \cdot \mathbb{1}[s_t = s,\, s_{t+1} = s',\, a_t = a] \tag{6}$$

B(a) is then obtained by normalizing the columns of b(a).

### Decision logic

1. **Perceive**: Receive position `(x, y)`, nearby resource list, `ate_flag`, energy `e(t)`.
2. **Encode observation**: Discretize into `o(t)` = (distance_to_nearest_resource_bin, energy_bin).
3. **Update allostatic prior**: Compute resource richness `ρ(t)` = (number of visible resources) / (max visible cells). Apply Eq. (1) to update `μ_p(t)`.
4. **Update preferences**: Recompute preference vector C using Eq. (2) with the new `μ_p(t)`.
5. **Bayesian state update**: Apply Eq. (5) to obtain posterior `q(s_t)` given `o(t)` and previous belief.
6. **Enumerate candidate policies**: Generate K candidate policies of length T. For tractability, use K = 18 policies: for each first action (6 choices), consider 3 heuristic continuations:
   - (a) repeat same action T times,
   - (b) move toward nearest resource then eat,
   - (c) move toward nearest resource then stay.
7. **Evaluate each policy**: For each π, simulate forward T steps using B(a) matrices to predict future state distributions. Compute G(π) via Eq. (3).
8. **Select policy**: Sample π from softmax Eq. (4). Execute the first action of the selected policy.
9. **After action + reward**:
   - Observe new state, update posterior via Eq. (5).
   - Update transition model via Eq. (6).
   - If `ate_flag`: the transition model learns that `eat` at a resource cell yields energy gain.

---

## Cross-formulation comparison

| Aspect | Formulation 1: Precision-Weighted Prediction Error | Formulation 2: Homeostatic RL with Drive Reduction | Formulation 3: Expected Free Energy with Allostatic Priors |
|--------|----------------------|----------------------|----------------------|
| Framework | Continuous ODE (discretized); gradient descent on free energy | Algebraic / value-based temporal-difference RL | Discrete Bayesian policy selection with planning |
| Key variables | Belief μ(t), prediction errors ε_s and ε_p, precisions π_s and π_p | Drive D(h(t)), Q-values Q(s,a), reward r(t) | Expected free energy G(π), allostatic prior μ_p(t), posterior q(s_t) |
| Core equation | dμ/dt = κ(π_s·ε_s − π_p·ε_p) — belief update via gradient descent on F | r(t) = D(h(t)) − D(h(t+1)) — reward as drive reduction | G(π) = Σ[pragmatic risk + epistemic ambiguity] — expected free energy decomposition |
| Decision mechanism | Softmax over predicted free energy of each single action | Softmax over learned Q-values (TD-updated) | Softmax over negative expected free energy of multi-step policies |
| Planning horizon | Myopic (1-step predicted F) | Implicit via discounted Q-values (infinite effective horizon, learned) | Explicit T-step lookahead (T=3) with enumerated policies |
| Exploration | Stochastic via softmax temperature β; no explicit epistemic drive | Stochastic via softmax; urgency modulation at low energy; no explicit exploration bonus | Explicit epistemic value term in G(π) drives exploration toward uncertain states |
| Setpoint / Prior | Fixed interoceptive prior μ_p | Fixed homeostatic setpoint h* | Dynamic allostatic prior μ_p(t) shifts with resource context |
| Learning | Online belief update only (no persistent memory across episodes) | Q-table updated via TD(0); persistent value learning | Transition model B(a) updated via Dirichlet counts; posterior updated online |
| Strengths | Directly implements predictive coding; minimal state; transparent precision-weighting explains attention effects | Proven physiological rationality (Keramati & Gutkin, 2014); simple to implement; learns from experience | Most complete: planning, exploration, allostasis, model learning; closest to full active inference |
| Limitations | No learning of value; myopic; no exploration incentive | No explicit model of environment; no allostasis; no epistemic drive | Computationally expensive (policy enumeration); many parameters; discretization may lose resolution |
| Primary literature | Friston (2010); Petzschner et al. (2021) | Keramati & Gutkin (2014) | Friston (2010); Petzschner et al. (2021) — allostasis prediction |
